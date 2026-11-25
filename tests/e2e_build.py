"""End-to-end build test (slow: runs PyInstaller).  Not part of the quick suite.

    python tests/e2e_build.py [fixture-folder ...]

It builds each fixture into a throw-away HOME, then runs the produced EXE in
self-test mode and checks that client-side routes (/about) return 200.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ROOT)


def main():
    fixtures = sys.argv[1:] or [os.path.join(ROOT, 'tests', 'fixtures', 'spa')]
    home = tempfile.mkdtemp(prefix='h2e-e2e-')
    os.environ['USERPROFILE'] = home
    os.environ['HOME'] = home
    from h2e import jobs
    from h2e.exe_build import build_exe, self_test
    failures = 0
    for fixture in fixtures:
        name = os.path.basename(os.path.normpath(fixture)).replace('-', ' ')
        meta_dir = os.path.join(home, 'Documents', 'HTML2EXE', name)
        os.makedirs(meta_dir)
        work = os.path.join(home, 'Downloads', name)
        shutil.copytree(fixture, work, ignore=shutil.ignore_patterns('node_modules', '.git'))
        with open(os.path.join(meta_dir, 'project.json'), 'w', encoding='utf-8') as fh:
            json.dump({'name': name, 'downloadFolder': work, 'sourceFolder': fixture}, fh)
        job = jobs.Job('e2e')
        result = build_exe({'projectName': name, 'projectId': name}, job)
        print('\n'.join(job.snapshot()['lines'][-25:]))
        print(f'== {name}: success={result.get("success")} error={result.get("error")}')
        if not result.get('success'):
            failures += 1
            continue
        probe = self_test(result['exePath'], os.path.join(meta_dir, 'build'), job, probes=('/', '/about', '/deep/route'))
        print('   probes:', probe)
        if not probe['ok']:
            failures += 1
    print('RESULT:', 'FAIL' if failures else 'PASS', f'(home={home})')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
