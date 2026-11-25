"""Real Laravel -> EXE test (slow, needs internet; downloads PHP, Composer, Laravel).

    python tests/e2e_laravel.py [cache-dir]

Everything lives under ``cache-dir`` (default: <temp>/h2e-laravel-cache) so a second
run reuses the downloads. Steps:
  1. portable PHP via h2e.php_runtime            (the same download the app does)
  2. composer.phar, then ``composer create-project laravel/laravel``
  3. recipes + build_exe() on the Laravel folder -> EXE
  4. run the EXE in self-test mode and probe the real Laravel routes
  5. check the writable per-user copy: .env got an APP_KEY and SQLite was migrated
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

COMPOSER_URL = 'https://getcomposer.org/download/latest-stable/composer.phar'


def main():
    cache = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), 'h2e-laravel-cache')
    home = os.path.join(cache, 'home')
    os.makedirs(home, exist_ok=True)
    os.environ['USERPROFILE'] = home
    os.environ['HOME'] = home
    os.environ['LOCALAPPDATA'] = os.path.join(home, 'AppData', 'Local')   # the EXE's app-data root
    os.makedirs(os.environ['LOCALAPPDATA'], exist_ok=True)
    sys.path.insert(0, ROOT)
    from h2e import jobs
    from h2e.exe_build import build_exe, self_test
    from h2e.php_runtime import ensure_php

    job = jobs.Job('laravel-e2e')

    def flush():
        for line in job.snapshot()['lines']:
            print('  |', line)
        job.lines.clear()

    php_dir = ensure_php(job)
    php = os.path.join(php_dir, 'php.exe')
    ini = os.path.join(cache, 'composer-php.ini')
    ext = os.path.join(php_dir, 'ext')
    with open(ini, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(['extension_dir="%s"' % ext, 'memory_limit=-1', 'date.timezone=UTC'] +
                           ['extension=%s' % n for n in ('openssl', 'mbstring', 'curl', 'zip', 'fileinfo',
                                                         'pdo_sqlite', 'sqlite3')]) + '\n')
    phar = os.path.join(cache, 'composer.phar')
    if not os.path.isfile(phar):
        print('Downloading composer.phar ...')
        req = urllib.request.Request(COMPOSER_URL, headers={'User-Agent': 'HTML2EXE-e2e'})
        with urllib.request.urlopen(req, timeout=120) as resp, open(phar, 'wb') as out:
            shutil.copyfileobj(resp, out)

    app = os.path.join(cache, 'laravel-app')
    if not os.path.isfile(os.path.join(app, 'vendor', 'autoload.php')):
        shutil.rmtree(app, ignore_errors=True)
        print('composer create-project laravel/laravel (a few minutes, ~50 MB) ...')
        code = subprocess.call([php, '-c', ini, phar, 'create-project', 'laravel/laravel', app,
                                '--prefer-dist', '--no-interaction', '--no-progress'], cwd=cache)
        if code != 0:
            print('RESULT: FAIL (composer create-project failed)')
            return 1

    # Registered like the UI does: a project with downloadFolder pointing at the Laravel folder.
    name = 'Laravel E2E'
    meta_dir = os.path.join(home, 'Documents', 'HTML2EXE', name)
    shutil.rmtree(meta_dir, ignore_errors=True)
    os.makedirs(meta_dir)
    with open(os.path.join(meta_dir, 'project.json'), 'w', encoding='utf-8') as fh:
        json.dump({'name': name, 'downloadFolder': app, 'sourceFolder': app}, fh)

    result = build_exe({'projectName': name, 'projectId': name}, job)
    flush()
    print(f'== build: success={result.get("success")} error={result.get("error")}')
    if not result.get('success'):
        print('RESULT: FAIL')
        return 1

    build_dir = os.path.join(meta_dir, 'build')
    probe = self_test(result['exePath'], build_dir, job, probes=('/', '/up'), timeout=180)
    flush()
    print('   probes:', probe)
    failures = 0 if probe['ok'] else 1

    data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'H2E-' + result['exeName'][:-4])
    env_file = os.path.join(data_dir, 'app', '.env')
    sqlite_file = os.path.join(data_dir, 'app', 'database', 'database.sqlite')
    key_ok = os.path.isfile(env_file) and 'APP_KEY=base64:' in open(env_file, encoding='utf-8').read()
    db_ok = os.path.isfile(sqlite_file) and os.path.getsize(sqlite_file) > 0
    print(f'   writable copy: {data_dir}')
    print(f'   APP_KEY generated: {key_ok}   SQLite migrated (size>0): {db_ok}')
    failures += (0 if key_ok else 1) + (0 if db_ok else 1)
    print('RESULT:', 'FAIL' if failures else 'PASS')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
