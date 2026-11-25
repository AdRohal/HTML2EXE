"""Build the public release of HTML2EXE: ``release/HTML2EXE-Installer-V<version>.exe``.

    python tools/build_release.py

What it does
------------
1. Packs HTML2EXE itself with PyInstaller (one-folder: starts fast), leaving out ``tests/``, ``docs/``, the Claude and
   design tooling folders and the project notes. Only the app, its UI and the LICENSE go in.
2. Wraps that folder in the branded installer (dark navy/violet wizard, license page, per-user or all-users install,
   Ko-fi button) and names it ``HTML2EXE-Installer-V<version>.exe``.
3. Writes ``release/HTML2EXE-Installer-V<version>.exe.sha256`` so downloads can be verified.

The build runs against a throw-away home folder, so nothing is added to your own HTML2EXE project list or Downloads.
"""
import base64
import hashlib
import io
import os
import re
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PUBLISHER = 'AdRohal'
EMAIL = 'Rohal.dev@hotmail.com'
KOFI = 'https://ko-fi.com/adrohal'
TAGLINE = 'Turn websites and Python programs into Windows apps and installers.'
POINTS = (
    'Portable .exe or Setup installer, with your own icon',
    'React, Vue, Astro, Next.js, PHP, Laravel and plain HTML',
    'Encrypted .env secrets, tested builds, everything stays on your PC',
)
# nothing here is shipped: tests, docs, project notes and tooling folders (dot-folders are skipped automatically)
EXCLUDE = ('tests', 'docs', 'projects', 'tools', 'release', 'PRODUCT.md', 'DESIGN.md', 'README.md', 'requirements.txt')


def logo_png_b64(size=96):
    from PIL import Image
    with Image.open(os.path.join(ROOT, 'builder_ui', 'assets', 'logo.png')) as img:
        img = img.convert('RGBA')
        img.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='PNG', optimize=True)
    return base64.b64encode(buf.getvalue()).decode('ascii')


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    home = tempfile.mkdtemp(prefix='h2e-release-')
    os.environ['USERPROFILE'] = os.environ['HOME'] = home          # keep the builder's own folders out of your profile
    from h2e import dashboard, jobs, python_builder
    version = dashboard.APP_VERSION
    with open(os.path.join(ROOT, 'LICENSE'), encoding='utf-8') as fh:
        license_text = fh.read().strip()
    license_text = (chr(10) * 2).join(' '.join(block.split()) for block in re.split(r'\n\s*\n', license_text))   # reflow paragraphs
    brand = {'logo_b64': logo_png_b64(), 'email': EMAIL, 'kofi': KOFI, 'tagline': TAGLINE, 'points': list(POINTS),
             'license': license_text}
    out_dir = os.path.join(ROOT, 'release')
    os.makedirs(out_dir, exist_ok=True)
    setup_name = f'HTML2EXE-Installer-V{version}'
    for stale in (setup_name + '.exe', setup_name + '.exe.sha256'):
        try:
            os.remove(os.path.join(out_dir, stale))
        except OSError:
            pass
    payload = {
        'pythonPath': ROOT, 'entry': 'builder.py', 'exeName': 'HTML2EXE', 'hideConsole': True, 'singleFile': False,
        'isolated': False, 'outputType': 'installer', 'installerEngine': 'builtin', 'appVersion': version,
        'publisher': PUBLISHER, 'outputDir': out_dir, 'excludeData': list(EXCLUDE), 'extraData': ['LICENSE'],
        'brand': brand, 'setupName': setup_name,
    }
    started = time.time()
    job = jobs.start_job('release', lambda j: python_builder.convert(payload)[0])
    shown = 0
    while job.status == 'running':
        time.sleep(1)
        while shown < len(job.lines):
            print(job.lines[shown], flush=True)
            shown += 1
    while shown < len(job.lines):
        print(job.lines[shown], flush=True)
        shown += 1
    result = job.result or {}
    if job.status != 'done':
        print('RELEASE FAILED:', result.get('error'))
        return 1
    setup = result['exePath']
    digest = sha256(setup)
    with open(setup + '.sha256', 'w', encoding='utf-8') as fh:
        fh.write(f'{digest} *{os.path.basename(setup)}\n')
    shutil.rmtree(home, ignore_errors=True)
    print(f'\nRELEASE READY ({time.time() - started:.0f}s): {setup}\n  size  {os.path.getsize(setup) / (1024 * 1024):.1f} MB\n  sha256 {digest}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
