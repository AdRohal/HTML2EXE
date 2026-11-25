"""Real Next.js (API routes + secrets) -> EXE test (slow: npm install, next build, PyInstaller).

    python tests/e2e_nextserver.py [existing-fixture-folder]

Builds a Next.js 16 app with next.config.ts, two API routes that only answer 200 when they received the
right secret, and a .env.local holding fake secrets. Then it proves:
  1. server mode: the EXE starts its bundled Node server and the API routes see the decrypted secrets;
  2. no plaintext secret exists in the EXE, the working copy, the stage folder, project.json or the log;
  3. envMode "none": the secrets are left out (the API answers 500) ...
  4. ... and a .env the user puts in the app's data folder supplies them again (200).
"""
import hashlib
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, ROOT)

KEY = 'FAKE-SECRET-KEY-1234567890abcd'
DB = 'postgres://user:p@ss word@db.example.test:5432/app'
PUBLIC = 'https://example.test'


def w(base, rel, text):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


def make_fixture(base):
    w(base, 'package.json', json.dumps({
        'name': 'srv', 'version': '1.0.0', 'private': True,
        'scripts': {'dev': 'next dev', 'build': 'next build', 'start': 'next start'},
        'dependencies': {'next': '16.4.6', 'react': '19.3.0', 'react-dom': '19.3.0'},
        'devDependencies': {'typescript': '^5', '@types/node': '^20', '@types/react': '^19', '@types/react-dom': '^19'}}))
    w(base, 'tsconfig.json', json.dumps({'compilerOptions': {
        'target': 'ES2017', 'lib': ['dom', 'dom.iterable', 'esnext'], 'allowJs': True, 'skipLibCheck': True, 'strict': True,
        'noEmit': True, 'esModuleInterop': True, 'module': 'esnext', 'moduleResolution': 'bundler', 'resolveJsonModule': True,
        'isolatedModules': True, 'jsx': 'react-jsx', 'incremental': True, 'plugins': [{'name': 'next'}],
        'paths': {'@/*': ['./src/*']}}, 'include': ['next-env.d.ts', '**/*.ts', '**/*.tsx', '.next/types/**/*.ts'],
        'exclude': ['node_modules']}))
    w(base, 'next.config.ts', 'import type { NextConfig } from "next";\n\nconst nextConfig: NextConfig = {\n  reactStrictMode: true,\n};\n\nexport default nextConfig;\n')
    w(base, 'src/app/layout.tsx', 'export default function Root({ children }: { children: React.ReactNode }) {\n  return <html lang="en"><body>{children}</body></html>;\n}\n')
    w(base, 'src/app/page.tsx', 'export const dynamic = "force-dynamic";\nexport default function Home() {\n  return <h1 id="t">srv-home-ok</h1>;\n}\n')
    # The routes compare SHA-256 hashes: a literal secret in source code would end up in the compiled output.
    route = ('import { createHash } from "crypto";\nexport const dynamic = "force-dynamic";\nexport async function GET() {\n'
             '  const sha = createHash("sha256").update(process.env.%s || "").digest("hex");\n'
             '  const ok = sha === "%s";\n  return Response.json({ ok }, { status: ok ? 200 : 500 });\n}\n')
    w(base, 'src/app/api/key/route.ts', route % ('TMDB_API_KEY', hashlib.sha256(KEY.encode()).hexdigest()))
    w(base, 'src/app/api/db/route.ts', route % ('DATABASE_URL', hashlib.sha256(DB.encode()).hexdigest()))
    w(base, 'public/hello.txt', 'public-file-ok')
    w(base, '.env.local', 'TMDB_API_KEY=%s\nNEXT_PUBLIC_SITE=%s\n# a comment\nDATABASE_URL="%s"\n' % (KEY, PUBLIC, DB))


def contains(path, needles):
    """Which needles appear in a file (read in chunks) or anywhere under a folder."""
    found = set()
    targets = []
    if os.path.isdir(path):
        for root, _d, files in os.walk(path):
            targets += [os.path.join(root, f) for f in files]
    elif os.path.isfile(path):
        targets = [path]
    for target in targets:
        try:
            with open(target, 'rb') as fh:
                tail = b''
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    data = tail + chunk
                    for n in needles:
                        if n in data:
                            found.add((n.decode(), os.path.relpath(target, path) if os.path.isdir(path) else os.path.basename(target)))
                    tail = chunk[-64:]
        except OSError:
            pass
    return found


def main():
    fixture = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    if fixture is None:
        fixture = tempfile.mkdtemp(prefix='h2e-nextsrv-')
        make_fixture(fixture)
    else:
        make_fixture(fixture)                          # refresh sources, keep node_modules for speed
    home = tempfile.mkdtemp(prefix='h2e-e2e-')
    os.environ['USERPROFILE'] = home
    os.environ['HOME'] = home
    os.environ['LOCALAPPDATA'] = os.path.join(home, 'AppData', 'Local')       # the EXE's data folder
    os.makedirs(os.environ['LOCALAPPDATA'])
    from h2e import jobs, workspace
    from h2e.exe_build import build_exe, self_test

    name = 'Srv App'
    meta_dir = os.path.join(home, 'Documents', 'HTML2EXE', name)
    work = os.path.join(home, 'Downloads', name)
    os.makedirs(meta_dir)
    # what create-project does: a working copy WITHOUT dependencies, caches or env files
    workspace.sync_working_copy(fixture, work)
    with open(os.path.join(meta_dir, 'project.json'), 'w', encoding='utf-8') as fh:
        json.dump({'name': name, 'downloadFolder': work, 'sourceFolder': fixture}, fh)

    failures = []

    def check(label, ok, detail=''):
        print(('PASS ' if ok else 'FAIL ') + label + (f'  [{detail}]' if detail and not ok else ''), flush=True)
        if not ok:
            failures.append(label)

    # ---------------------------------------------------------------- 1. bundled, encrypted secrets
    job = jobs.Job('e2e')
    result = build_exe({'projectName': name, 'projectId': name, 'options': {'envMode': 'bundle', 'keepWorkFiles': True}}, job)
    log = '\n'.join(job.snapshot()['lines'])
    print('\n'.join(job.snapshot()['lines'][-14:]))
    check('server build succeeds', result.get('success'), str(result.get('error')))
    if not result.get('success'):
        return 1
    check('result says server mode', result.get('server') is True)
    check('leak scan finds nothing in the built files', result.get('leaks') == [], str(result.get('leaks')))
    check('3 variables bundled + encrypted', result['secrets'] == {'bundled': 3, 'excluded': 0, 'encrypted': True, 'mode': 'bundle'}, str(result['secrets']))
    exe = result['exePath']
    build_dir = os.path.join(meta_dir, 'build')
    probe = self_test(exe, build_dir, job, probes=('/', '/api/key', '/api/db', '/hello.txt'), timeout=300)
    check('EXE serves page, both API routes (secrets decrypted) and public files',
          probe['ok'], json.dumps(probe.get('results'))[:400])

    needles = [KEY.encode(), b'p@ss word', b'db.example.test', b'postgres://']
    for label, path in (('the .exe', exe), ('working copy', work), ('stage folder', os.path.join(build_dir, 'stage')),
                        ('launcher source (main.py)', os.path.join(build_dir, 'main.py')),
                        ('project.json', os.path.join(meta_dir, 'project.json')), ('selftest.json', os.path.join(build_dir, 'selftest.json')),
                        ('build log', None)):
        hits = contains(path, needles) if path else {(n.decode(), 'log') for n in needles if n.decode() in log}
        check(f'no plaintext secret in {label}', not hits, str(sorted(hits))[:300])
    check('the secrets file in the build folder is binary ciphertext',
          not contains(os.path.join(build_dir, 'secrets.bin'), needles) and os.path.getsize(os.path.join(build_dir, 'secrets.bin')) > 60)
    check('the working copy in Downloads was deleted after the build', not os.path.exists(work))
    check('node_modules and .next were parked for fast rebuilds',
          os.path.isdir(os.path.join(meta_dir, 'cache', 'node_modules')) and os.path.isdir(os.path.join(meta_dir, 'cache', '.next')))
    check('original folder still has the owner\'s .env.local untouched', os.path.isfile(os.path.join(fixture, '.env.local')))

    # ---------------------------------------------------------------- 2. envMode none + user supplied .env
    workspace.sync_working_copy(fixture, work)
    job2 = jobs.Job('e2e2')
    result2 = build_exe({'projectName': name, 'projectId': name, 'options': {'envMode': 'none'}}, job2)
    check('second build (secrets not bundled) succeeds', result2.get('success'), str(result2.get('error')))
    check('second build reused the parked dependencies (no reinstall)', 'skipping install' in '\n'.join(job2.snapshot()['lines']), '\n'.join(job2.snapshot()['lines'])[:300])
    if result2.get('success'):
        check('nothing encrypted this time', result2['secrets']['encrypted'] is False and not os.path.exists(os.path.join(build_dir, 'secrets.bin')))
        data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'H2E-Srv_App')
        env_file = os.path.join(data_dir, '.env')
        if os.path.exists(env_file):
            os.remove(env_file)
        probe_none = self_test(result2['exePath'], build_dir, job2, probes=('/api/key',), timeout=300)
        check('without secrets the API answers 500 (they are really absent)', not probe_none['ok']
              and probe_none['results'][0]['status'] == 500, json.dumps(probe_none.get('results')))
        os.makedirs(data_dir, exist_ok=True)
        with open(env_file, 'w', encoding='utf-8') as fh:
            fh.write('TMDB_API_KEY=%s\nDATABASE_URL="%s"\n' % (KEY, DB))
        probe_user = self_test(result2['exePath'], build_dir, job2, probes=('/api/key', '/api/db'), timeout=300)
        check('a .env in the app data folder supplies the secrets', probe_user['ok'], json.dumps(probe_user.get('results')))

    print('RESULT:', 'FAIL' if failures else 'PASS', failures or '', f'(fixture={fixture})')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
