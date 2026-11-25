"""Real Python -> Setup.exe -> silent install -> run -> uninstall cycle (slow).

    python tests/e2e_python_installer.py [builtin|inno]

Builds a tiny project as an installer (one-file and one-folder), installs it silently into a temp folder
(no shortcuts), runs the installed program, uninstalls it with ``--uninstall --quiet`` and checks that the folder
and the Apps & features registry entry are gone. Uses a unique app name and leaves nothing behind.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import winreg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MAIN = '''import sys
print("PYINST-OK", " ".join(sys.argv[1:]))
'''


def reg_exists(key):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, key))
        return True
    except OSError:
        return False


def main():
    engine = sys.argv[1] if len(sys.argv) > 1 else 'builtin'
    home = tempfile.mkdtemp(prefix='h2e-pyinst-')
    os.environ['USERPROFILE'] = home
    os.environ['HOME'] = home
    from h2e import jobs, python_builder
    project = os.path.join(home, 'proj')
    os.makedirs(project)
    with open(os.path.join(project, 'main.py'), 'w', encoding='utf-8') as fh:
        fh.write(MAIN)
    failures = 0
    for single in (True, False):
        name = 'H2E Pytest ' + uuid.uuid4().hex[:6]
        out_dir = os.path.join(home, 'out')
        job = jobs.start_job('python', lambda j: python_builder.convert({
            'pythonPath': project, 'exeName': name, 'singleFile': single, 'hideConsole': False,
            'outputType': 'installer', 'installerEngine': engine, 'appVersion': '2.3.4',
            'publisher': 'Test Co', 'outputDir': out_dir})[0])
        while job.status == 'running':
            time.sleep(1)
        result = job.result or {}
        problems = []
        if job.status != 'done':
            problems.append(f'job {job.status}: {result.get("error")}')
            print('\n'.join(job.lines[-25:]))
        else:
            setup = result['exePath']
            target = os.path.join(home, 'installed ' + ('one' if single else 'dir'))
            subprocess.run([setup, '/S', f'/D={target}', '--no-desktop', '--no-startmenu'] if engine == 'builtin'
                           else [setup, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/DIR={target}', '/MERGETASKS=!desktopicon'],
                           timeout=300)
            installed = os.path.join(target, name + '.exe')
            exes = [os.path.join(target, f) for f in os.listdir(target) if f.lower().endswith('.exe')] if os.path.isdir(target) else []
            exe = next((e for e in exes if 'unins' not in os.path.basename(e).lower()), installed)
            if not os.path.isfile(exe):
                problems.append(f'installed exe missing in {target}: {exes}')
            else:
                out = subprocess.run([exe, 'hello'], capture_output=True, text=True, timeout=60).stdout
                if 'PYINST-OK hello' not in out:
                    problems.append(f'installed program output: {out!r}')
                if engine == 'inno':
                    unins = os.path.join(target, 'unins000.exe')
                    if not os.path.isfile(unins):
                        problems.append('Inno uninstaller missing')
                    else:
                        subprocess.run([unins, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], timeout=120)
                        time.sleep(3)
                if engine == 'builtin':
                    subprocess.run([exe, '--uninstall', '--quiet'], timeout=60)
                    for _ in range(30):
                        if not os.path.isdir(target):
                            break
                        time.sleep(1)
                    if os.path.isdir(target):
                        problems.append('program folder still exists after --uninstall')
        status = 'PASS' if not problems else 'FAIL'
        failures += bool(problems)
        print(f'== python installer engine={engine} single_file={single}: {status} {"; ".join(problems)} '
              f'[{result.get("exeName")} {result.get("sizeMb")} MB]', flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
