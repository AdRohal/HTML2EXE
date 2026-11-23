"""System check: what is installed and what each feature needs."""
import importlib.util
import os
import shutil
import subprocess
import sys

from .recipes import FRAMEWORKS

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def _version(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                             creationflags=NO_WINDOW, shell=isinstance(cmd, str))
        text = (out.stdout or out.stderr).strip().splitlines()
        return text[0] if text else ''
    except Exception:
        return ''


def _has_module(name):
    return importlib.util.find_spec(name) is not None


def webview2_installed():
    if sys.platform != 'win32':
        return True
    import winreg
    guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for hive, sub in (
        (winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\' + guid),
        (winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\' + guid),
        (winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\EdgeUpdate\\Clients\\' + guid),
    ):
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, _ = winreg.QueryValueEx(key, 'pv')
                if value and value != '0.0.0.0':
                    return value
        except OSError:
            continue
    return False


def run_checks(android_check=None):
    """Return a list of check dicts: id, label, ok, detail, needed_for, fix."""
    checks = []

    def add(cid, label, ok, detail, needed_for, fix=''):
        checks.append({'id': cid, 'label': label, 'ok': bool(ok), 'detail': detail,
                       'neededFor': needed_for, 'fix': fix})

    frozen = getattr(sys, 'frozen', False)
    add('python', 'Python', not frozen and sys.version_info >= (3, 8),
        f'{sys.version.split()[0]}' if not frozen else 'Running as a packaged app - needs a Python install on PATH to build',
        'Building EXEs', 'https://www.python.org/downloads/')
    add('pyinstaller', 'PyInstaller', _has_module('PyInstaller'),
        'installed' if _has_module('PyInstaller') else 'missing', 'Building EXEs', 'pip install pyinstaller')
    add('pywebview', 'pywebview', _has_module('webview'),
        'installed' if _has_module('webview') else 'missing', 'Builder window + generated apps', 'pip install pywebview')
    add('pillow', 'Pillow', _has_module('PIL'),
        'installed' if _has_module('PIL') else 'missing (PNG icons will not be converted)', 'PNG app icons',
        'pip install Pillow')

    node = shutil.which('node')
    add('node', 'Node.js', node, _version([node, '--version']) if node else 'not found',
        'React / Vue / Astro / Next.js / Nuxt / Angular projects, Android APK', 'https://nodejs.org')
    npm = shutil.which('npm') or shutil.which('npm.cmd')
    add('npm', 'npm', npm, _version([npm, '--version']) if npm else 'not found',
        'Installing and building framework projects', 'https://nodejs.org')
    composer = shutil.which('composer') or shutil.which('composer.bat')
    add('composer', 'Composer (optional)', composer, 'found' if composer else 'not found',
        'Laravel projects without a vendor/ folder', 'https://getcomposer.org')

    wv2 = webview2_installed()
    add('webview2', 'WebView2 Runtime', wv2, str(wv2) if wv2 else 'not found',
        'Running the apps you build (end users need it too)',
        'https://developer.microsoft.com/microsoft-edge/webview2/')

    if android_check:
        try:
            android = android_check()
            add('java', 'Java JDK 17+', android['java']['ok'], android['java']['message'], 'Android APK',
                'https://adoptium.net')
            add('androidsdk', 'Android SDK', android['sdk']['ok'], android['sdk']['message'], 'Android APK',
                'https://developer.android.com/studio')
        except Exception as exc:  # pragma: no cover - defensive
            add('java', 'Java / Android SDK', False, f'check failed: {exc}', 'Android APK')

    core = ('pyinstaller', 'pywebview')
    return {
        'checks': checks,
        'canBuildExe': all(c['ok'] for c in checks if c['id'] in core) and not frozen,
        'frameworks': [{'id': k, 'label': v[0], 'support': v[1]} for k, v in FRAMEWORKS.items()],
        'canBuildFrameworks': all(c['ok'] for c in checks if c['id'] in ('node', 'npm')),
    }
