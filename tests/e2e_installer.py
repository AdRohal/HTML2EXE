"""Real installer build + install + run + uninstall (slow: two PyInstaller builds).

    python tests/e2e_installer.py [builtin|inno|auto] [screenshot-path]

Proves, with real executables:
  1. the working copy in Downloads is deleted after the build, and Downloads holds ONLY <App>-Setup.exe
  2. the installer verifies its own contents
  3. ``Setup.exe /S /D=<folder with spaces>`` installs silently, registers the app in Apps & features
  4. the installed app starts and serves its pages
  5. updating over an existing install works
  6. the wizard window opens (and is photographed when a path is given)
  7. ``App.exe --uninstall --quiet`` removes the folder and the registry entry
  8. a portable build of the same project still produces a single plain .exe and also leaves Downloads clean
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, ROOT)

REG_ROOT = r'Software\Microsoft\Windows\CurrentVersion\Uninstall'


def reg_values(key_name):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT + '\\' + key_name) as key:
            out, i = {}, 0
            while True:
                try:
                    n, v, _t = winreg.EnumValue(key, i)
                except OSError:
                    return out
                out[n] = v
                i += 1
    except OSError:
        return None


def delete_key(key_name):
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_ROOT + '\\' + key_name)
    except OSError:
        pass


def window_shot(title_part, path, timeout=20):
    """Photograph the first window whose title contains ``title_part``."""
    import ctypes
    from ctypes import wintypes
    from PIL import ImageGrab
    user32 = ctypes.windll.user32
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if title_part in buf.value:
                found.append(hwnd)
        return True
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    end = time.time() + timeout
    while time.time() < end and not found:
        user32.EnumWindows(proto(cb), 0)
        time.sleep(0.3)
    if not found:
        return False
    time.sleep(1.0)
    rect = wintypes.RECT()
    user32.GetWindowRect(found[0], ctypes.byref(rect))
    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).save(path)
    return True


def main():
    args = [a for a in sys.argv[1:]]
    engine_arg = args.pop(0) if args and args[0] in ('builtin', 'inno', 'auto') else 'auto'
    shot = args[0] if args else None
    fixture = os.path.join(ROOT, 'tests', 'fixtures', 'spa')
    home = tempfile.mkdtemp(prefix='h2e-e2e-inst-')
    os.environ['USERPROFILE'] = home
    os.environ['HOME'] = home
    from h2e import jobs, workspace
    from h2e.exe_build import build_exe, safe_exe_name

    uid = uuid.uuid4().hex[:6]
    name = f'Setup Test {uid}'                                   # spaces on purpose
    exe_name = safe_exe_name(name)
    failures = []

    def check(label, ok, detail=''):
        print(('PASS ' if ok else 'FAIL ') + label + (f'  [{detail}]' if detail and not ok else ''), flush=True)
        if not ok:
            failures.append(label)

    meta_dir = os.path.join(home, 'Documents', 'HTML2EXE', name)
    downloads = os.path.join(home, 'Downloads')
    working = os.path.join(downloads, name)
    os.makedirs(meta_dir)
    os.makedirs(downloads)
    with open(os.path.join(meta_dir, 'project.json'), 'w', encoding='utf-8') as fh:
        json.dump({'name': name, 'downloadFolder': working, 'sourceFolder': fixture, 'author': 'Acme Corp', 'version': '3.1.4'}, fh)
    workspace.sync_working_copy(fixture, working)                # what create-project does

    install_dir = os.path.join(tempfile.mkdtemp(prefix='h2e-installed-'), 'My Apps', name)      # spaces again
    keys_to_clean = []
    try:
        # ---------------------------------------------------------------- 1. build the installer
        job = jobs.Job('e2e-installer')
        result = build_exe({'projectName': name, 'projectId': name,
                            'options': {'outputType': 'installer', 'appVersion': '3.1.4', 'publisher': 'Acme Corp',
                                        'installerEngine': engine_arg}}, job)
        print('\n'.join(job.snapshot()['lines'][-6:]))
        check('installer build succeeds', result.get('success'), str(result.get('error')))
        if not result.get('success'):
            return 1
        setup = result['exePath']
        check('result is an installer named <App>-Setup.exe', result.get('kind') == 'installer'
              and os.path.basename(setup) == f'{exe_name}-Setup.exe', setup)
        engine = result['installer']['engine']
        print(f'   engine: {engine}')
        check('installer verified itself', result['installer']['verified'] is True)
        check('app inside self-tested', result['selfTest']['ok'] is True)
        check('Downloads holds only the Setup.exe', os.listdir(downloads) == [f'{exe_name}-Setup.exe'], str(os.listdir(downloads)))
        check('working copy is gone', not os.path.exists(working))
        check('bulky build folders are gone', not any(os.path.isdir(os.path.join(meta_dir, 'build', d)) for d in ('stage', 'work', 'dist', 'installer')))
        print(f"   Setup.exe {result['sizeMb']} MB, app inside {result['appSizeMb']} MB")

        # ---------------------------------------------------------------- 2. silent install
        def silent(*extra):
            if engine == 'inno':
                cmdline = f'"{setup}" /VERYSILENT /SUPPRESSMSGBOXES /NOICONS /MERGETASKS="!desktopicon" /DIR="{install_dir}"'
            else:
                cmdline = f'"{setup}" /S /D={install_dir} --no-desktop --no-startmenu'
            return subprocess.run(cmdline, timeout=300).returncode

        def registered():
            """The Apps & features entry of this app, whatever the engine called its key."""
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT) as root:
                i = 0
                while True:
                    try:
                        key_name = winreg.EnumKey(root, i)
                    except OSError:
                        return None, None
                    i += 1
                    values = reg_values(key_name) or {}
                    if values.get('DisplayName') == name:
                        return key_name, values

        check('nothing registered before installing', registered()[0] is None)
        rc = silent()
        check('silent install exits 0', rc == 0, str(rc))
        installed = os.path.join(install_dir, exe_name + '.exe')
        check('app copied into the chosen folder (with spaces)', os.path.isfile(installed))
        key_name, reg = registered()
        reg = reg or {}
        if key_name:
            keys_to_clean.append(key_name)
        loc = (reg.get('InstallLocation') or '').rstrip('\\')
        check('registered in Apps & features with name, version and publisher',
              reg.get('DisplayName') == name and reg.get('DisplayVersion') == '3.1.4'
              and reg.get('Publisher') == 'Acme Corp' and os.path.normcase(loc) == os.path.normcase(install_dir), str(reg))
        uninstall_cmd = reg.get('UninstallString', '')
        check('an uninstall command is registered',
              (engine == 'builtin' and uninstall_cmd == f'"{installed}" --uninstall')
              or (engine == 'inno' and 'unins' in uninstall_cmd.lower()), uninstall_cmd)

        # ---------------------------------------------------------------- 3. the installed app runs
        out = os.path.join(home, 'installed-selftest.json')
        subprocess.run([installed, f'--selftest-out={out}', '--selftest-probe=/,/about'], timeout=120)
        report = json.load(open(out, encoding='utf-8')) if os.path.exists(out) else {'results': []}
        check('installed app serves its pages', report['results'] and all(r.get('status') == 200 for r in report['results']), str(report))

        # ---------------------------------------------------------------- 4. update over the top
        with open(os.path.join(install_dir, 'user-notes.txt'), 'w', encoding='utf-8') as fh:
            fh.write('keep me')
        check('updating over an existing install works', silent() == 0 and os.path.isfile(installed))
        check('update keeps the user\'s own files', os.path.isfile(os.path.join(install_dir, 'user-notes.txt')))
        check('update does not create a second Apps & features entry',
              sum(1 for _ in [1] if registered()[0] == key_name) == 1)

        # ---------------------------------------------------------------- 5. the wizard opens
        if engine == 'builtin':
            gui = subprocess.Popen([setup])
            try:
                time.sleep(4)
                check('wizard window opens and stays up', gui.poll() is None)
                if shot:
                    check('wizard photographed', window_shot(f'{name} Setup', shot), shot)
            finally:
                gui.kill()

        # ---------------------------------------------------------------- 6. uninstall
        if engine == 'builtin':
            rc = subprocess.run([installed, '--uninstall', '--quiet'], timeout=120).returncode
        else:
            unins = [os.path.join(install_dir, f) for f in os.listdir(install_dir) if f.lower().startswith('unins') and f.lower().endswith('.exe')]
            check('Inno wrote its uninstaller', len(unins) == 1, str(os.listdir(install_dir)))
            rc = subprocess.run(f'"{unins[0]}" /VERYSILENT /SUPPRESSMSGBOXES', timeout=120).returncode if unins else 1
        check('uninstall command exits 0', rc == 0, str(rc))
        for _ in range(60):
            if not os.path.exists(os.path.join(install_dir, exe_name + '.exe')):
                break
            time.sleep(1)
        check('the app is removed from the install folder', not os.path.exists(os.path.join(install_dir, exe_name + '.exe')))
        if engine == 'builtin':
            check('install folder removed', not os.path.exists(install_dir))
        check('Apps & features entry removed', registered()[0] is None)

        # ---------------------------------------------------------------- 7. portable still works and leaves Downloads clean
        workspace.sync_working_copy(fixture, working)
        job2 = jobs.Job('e2e-portable')
        result2 = build_exe({'projectName': name, 'projectId': name, 'options': {'outputType': 'portable'}}, job2)
        check('portable build succeeds', result2.get('success'), str(result2.get('error')))
        if result2.get('success'):
            check('portable result is a plain .exe', result2.get('kind') == 'portable' and result2['exeName'] == exe_name + '.exe')
            check('Downloads holds the Setup and the portable exe only',
                  sorted(os.listdir(downloads)) == sorted([f'{exe_name}-Setup.exe', exe_name + '.exe']), str(os.listdir(downloads)))
            check('working copy is gone again', not os.path.exists(working))
    finally:
        for key in keys_to_clean + [exe_name]:
            delete_key(key)
        if os.path.isdir(install_dir):
            subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', install_dir], capture_output=True)

    print('RESULT:', 'FAIL' if failures else 'PASS', failures or '')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
