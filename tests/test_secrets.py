import base64
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from h2e import exe_build, jobs, recipes, secrets  # noqa: E402
from h2e.launcher import render_launcher  # noqa: E402

SECRET = 'FAKE-SECRET-KEY-1234567890abcd'
DB_URL = 'postgres://user:p@ss word@db.example.test:5432/app'


def write(base, rel, text='x', binary=False):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb' if binary else 'w', **({} if binary else {'encoding': 'utf-8'})) as fh:
        fh.write(text)
    return path


class ParseTests(unittest.TestCase):
    def test_basic_quotes_comments_export_and_multiline(self):
        text = ('# comment\n'
                'A=plain\n'
                'export B="double \\"quoted\\" \\n line"\n'
                "C='single # not a comment'\n"
                'D=value # inline comment\n'
                'E="multi\nline"\n'
                'EMPTY=\n'
                'not a variable\n')
        values = secrets.parse_env_text(text)
        self.assertEqual(values['A'], 'plain')
        self.assertEqual(values['B'], 'double "quoted" \n line')
        self.assertEqual(values['C'], 'single # not a comment')
        self.assertEqual(values['D'], 'value')
        self.assertEqual(values['E'], 'multi\nline')
        self.assertEqual(values['EMPTY'], '')
        self.assertNotIn('not a variable', values)

    def test_crlf_and_bom_files(self):
        d = tempfile.mkdtemp(prefix='h2e-env-')
        write(d, '.env.local', b'\xef\xbb\xbfA=1\r\nB="two"\r\n', binary=True)
        values, _ = secrets.load_project_env(d)
        self.assertEqual(values, {'A': '1', 'B': 'two'})

    def test_precedence_matches_next_production_order(self):
        d = tempfile.mkdtemp(prefix='h2e-env-')
        write(d, '.env', 'A=env\nB=env\nC=env\nD=env\n')
        write(d, '.env.production', 'B=prod\nC=prod\nD=prod\n')
        write(d, '.env.local', 'C=local\nD=local\n')
        write(d, '.env.production.local', 'D=prodlocal\n')
        values, sources = secrets.load_project_env(d)
        self.assertEqual(values, {'A': 'env', 'B': 'prod', 'C': 'local', 'D': 'prodlocal'})
        self.assertEqual(sources['C'], '.env.local')
        self.assertEqual(sources['D'], '.env.production.local')

    def test_variable_expansion(self):
        d = tempfile.mkdtemp(prefix='h2e-env-')
        write(d, '.env.local', 'HOST=db.local\nURL=postgres://${HOST}:5432/x\nMISSING=a${NOPE_NOT_SET}b\n')
        values, _ = secrets.load_project_env(d)
        self.assertEqual(values['URL'], 'postgres://db.local:5432/x')
        self.assertEqual(values['MISSING'], 'ab')

    def test_env_file_names(self):
        for name in ('.env', '.env.local', '.env.production', '.env.production.local', '.env.development.local'):
            self.assertTrue(secrets.is_env_file_name(name), name)
        for name in ('.env.example', '.env.sample', '.env.template', 'env.js', '.envrc', 'x.env', '.environment'):
            self.assertFalse(secrets.is_env_file_name(name), name)

    def test_missing_folder_is_empty(self):
        self.assertEqual(secrets.load_project_env(r'C:\definitely\not\here'), ({}, {}))


class ClassifyTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(secrets.classify('NEXT_PUBLIC_SITE'), ('public', 'normal'))
        self.assertEqual(secrets.classify('VITE_API'), ('public', 'normal'))
        self.assertEqual(secrets.classify('TMDB_API_KEY'), ('secret', 'normal'))
        self.assertEqual(secrets.classify('DATABASE_URL')[1], 'high')
        self.assertEqual(secrets.classify('JWT_SECRET')[1], 'high')
        self.assertEqual(secrets.classify('ANYTHING', 'mysql://root:hunter2@host/db')[1], 'high')

    def test_describe_never_contains_values(self):
        d = tempfile.mkdtemp(prefix='h2e-env-')
        write(d, '.env.local', f'TMDB_API_KEY={SECRET}\nNEXT_PUBLIC_SITE=https://example.test\nDATABASE_URL="{DB_URL}"\n')
        result = secrets.describe(d)
        dumped = json.dumps(result)
        self.assertNotIn(SECRET, dumped)
        self.assertNotIn('p@ss word', dumped)
        self.assertNotIn('example.test', dumped)              # not even the public value
        names = {v['name']: v for v in result['vars']}
        self.assertEqual(set(names), {'TMDB_API_KEY', 'NEXT_PUBLIC_SITE', 'DATABASE_URL'})
        self.assertEqual(names['TMDB_API_KEY']['length'], len(SECRET))
        self.assertEqual(names['DATABASE_URL']['risk'], 'high')
        self.assertEqual(result['files'], ['.env.local'])

    def test_secret_values_for_redaction_skip_public_and_short(self):
        values = {'NEXT_PUBLIC_A': 'https://public.example', 'TOKEN': 'abcdefgh12345', 'FLAG': 'true', 'PORT': '3000'}
        self.assertEqual(secrets.secret_values(values), {'abcdefgh12345'})


class EncryptionTests(unittest.TestCase):
    def test_round_trip_and_nothing_readable_in_blob(self):
        values = {'TMDB_API_KEY': SECRET, 'DATABASE_URL': DB_URL, 'UNICODE': 'h\u00e9llo \u2713'}
        blob, share = secrets.encrypt_env(values, 'H2E-app:build1')
        self.assertEqual(secrets.decrypt_env(blob, share, 'H2E-app:build1'), values)
        for needle in (SECRET.encode(), b'postgres', b'TMDB_API_KEY'):
            self.assertNotIn(needle, blob)

    def test_each_encryption_is_different(self):
        a = secrets.encrypt_env({'K': 'v' * 12}, 'x')
        b = secrets.encrypt_env({'K': 'v' * 12}, 'x')
        self.assertNotEqual(a[0], b[0])
        self.assertNotEqual(a[1], b[1])

    def test_tampering_wrong_share_and_wrong_build_all_fail(self):
        blob, share = secrets.encrypt_env({'K': 'secretvalue'}, 'app:build')
        flipped = bytearray(blob)
        flipped[-1] ^= 1
        with self.assertRaises(ValueError):
            secrets.decrypt_env(bytes(flipped), share, 'app:build')
        with self.assertRaises(ValueError):
            secrets.decrypt_env(blob, bytes(32), 'app:build')
        with self.assertRaises(ValueError):
            secrets.decrypt_env(blob, share, 'app:other-build')
        with self.assertRaises(ValueError):
            secrets.decrypt_env(b'XXXX' + blob[4:], share, 'app:build')

    def test_launcher_decrypts_what_the_builder_encrypts(self):
        values = {'TMDB_API_KEY': SECRET}
        blob, share = secrets.encrypt_env(values, 'H2E-demo:b123')
        root = tempfile.mkdtemp(prefix='h2e-launch-')
        write(root, '_secrets/secrets.bin', blob, binary=True)
        config = {'title': 't', 'mode': 'node', 'app_id': 'H2E-demo', 'build_id': 'b123', 'has_secrets': True,
                  'secret_share': base64.b64encode(share).decode()}
        path = write(root, 'launcher_under_test.py', render_launcher(config))
        spec = importlib.util.spec_from_file_location('launcher_under_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.BASE_DIR = root
        self.assertEqual(module._bundled_env(), values)
        module.CONFIG['build_id'] = 'different'
        with self.assertRaises(ValueError):
            module._bundled_env()

    def test_launcher_env_file_parser(self):
        config = {'title': 't', 'mode': 'node', 'app_id': 'a', 'build_id': 'b'}
        root = tempfile.mkdtemp(prefix='h2e-launch-')
        path = write(root, 'launcher_under_test2.py', render_launcher(config))
        spec = importlib.util.spec_from_file_location('launcher_under_test2', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parsed = module._parse_env('# c\nA=1\nexport B="two words"\nC=\'x\'\n\nbroken line\n')
        self.assertEqual(parsed, {'A': '1', 'B': 'two words', 'C': 'x'})


class RedactionTests(unittest.TestCase):
    def test_log_and_captured_output_never_show_registered_secrets(self):
        job = jobs.Job('t')
        job.add_secrets([SECRET, DB_URL])
        job.log(f'connecting with {SECRET} and {DB_URL}')
        self.assertNotIn(SECRET, '\n'.join(job.snapshot()['lines']))
        self.assertIn('***', job.snapshot()['lines'][0])
        lines = []
        code = job.run_cmd([sys.executable, '-c', f'print("key={SECRET}")'], collect=lines)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ['key=***'])
        self.assertNotIn(SECRET, '\n'.join(job.snapshot()['lines']))


class LeakScanTests(unittest.TestCase):
    def test_reports_names_and_files_but_never_values(self):
        d = tempfile.mkdtemp(prefix='h2e-leak-')
        write(d, '.next/server/page.html', f'<script>var k="{SECRET}"</script>')
        write(d, 'static/app.js', f'fetch("/x", {{headers: {{k: "{SECRET}"}}}})')
        write(d, 'clean.js', 'nothing here')
        found = secrets.find_leaks(d, {'TMDB_API_KEY': SECRET, 'OTHER_TOKEN': 'abcdefgh-not-present'})
        self.assertEqual(set(found), {'TMDB_API_KEY'})
        self.assertEqual(len(found['TMDB_API_KEY']), 2)
        self.assertNotIn(SECRET, json.dumps(found))

    def test_short_values_are_ignored_and_clean_folders_are_clean(self):
        d = tempfile.mkdtemp(prefix='h2e-leak-')
        write(d, 'a.js', 'var port = 3000; var flag = true;')
        self.assertEqual(secrets.find_leaks(d, {'PORT': '3000', 'FLAG': 'true'}), {})
        self.assertEqual(secrets.find_leaks(d, {'TOKEN': 'abcdefgh12345'}), {})
        self.assertEqual(secrets.find_leaks(r'C:\definitely\not\here', {'TOKEN': 'abcdefgh12345'}), {})

    def test_huge_files_are_skipped(self):
        d = tempfile.mkdtemp(prefix='h2e-leak-')
        write(d, 'big.bin', b'xx' + SECRET.encode() + b'yy', binary=True)
        self.assertEqual(secrets.find_leaks(d, {'K': SECRET}, max_size=10), {})
        self.assertEqual(set(secrets.find_leaks(d, {'K': SECRET})), {'K'})


class StagingTests(unittest.TestCase):
    def test_stage_ignores_real_env_files_but_keeps_templates(self):
        src = tempfile.mkdtemp(prefix='h2e-stage-')
        for name in ('.env', '.env.local', '.env.production.local', '.env.example', 'server.js'):
            write(src, name)
        write(src, 'node_modules/x/index.js')
        write(src, 'sub/.env.local')
        dst = os.path.join(tempfile.mkdtemp(prefix='h2e-stage-'), 'out')
        exe_build.stage_copy(src, dst, exe_build.NODE_STAGE_IGNORE)       # node bundles keep node_modules
        found = {os.path.relpath(os.path.join(r, f), dst).replace(os.sep, '/') for r, _d, fs in os.walk(dst) for f in fs}
        self.assertEqual(found, {'.env.example', 'server.js', 'node_modules/x/index.js'})
        dst2 = os.path.join(tempfile.mkdtemp(prefix='h2e-stage-'), 'out')
        exe_build.stage_copy(src, dst2, exe_build.STAGE_IGNORE)           # static bundles drop node_modules
        found2 = {os.path.relpath(os.path.join(r, f), dst2).replace(os.sep, '/') for r, _d, fs in os.walk(dst2) for f in fs}
        self.assertEqual(found2, {'.env.example', 'server.js'})


class NextConfigTests(unittest.TestCase):
    def project(self, config_name=None, config_text=''):
        d = tempfile.mkdtemp(prefix='h2e-next-')
        write(d, 'package.json', json.dumps({'dependencies': {'next': '16.0.0'}}))
        if config_name:
            write(d, config_name, config_text)
        return d

    def test_every_config_flavour_is_wrapped_and_restored_byte_for_byte(self):
        cases = {'next.config.ts': 'import type { NextConfig } from "next";\nexport default {} as NextConfig;\n',
                 'next.config.mts': 'export default {};\n',
                 'next.config.js': 'module.exports = { reactStrictMode: true };\n',
                 'next.config.mjs': 'export default { reactStrictMode: true };\n',
                 'next.config.cjs': 'module.exports = {};\n'}
        for name, text in cases.items():
            for output in ('standalone', 'export'):
                d = self.project(name, text)
                with recipes._next_config_output(d, jobs.Job('t'), output):
                    files = set(os.listdir(d))
                    self.assertIn('next.config.h2e-original.' + name.rsplit('.', 1)[1], files, name)
                    wrapper_name = name if name.endswith(('ts', 'mts')) else 'next.config.mjs'
                    with open(os.path.join(d, wrapper_name), encoding='utf-8') as fh:
                        wrapper = fh.read()
                    self.assertIn('Generated by HTML2EXE', wrapper)
                    self.assertIn(f"output: '{output}'", wrapper)
                self.assertEqual(sorted(os.listdir(d)), sorted(['package.json', name]), (name, output))
                with open(os.path.join(d, name), encoding='utf-8') as fh:
                    self.assertEqual(fh.read(), text, (name, output))

    def test_no_config_gets_a_temporary_one(self):
        d = self.project()
        with recipes._next_config_output(d, jobs.Job('t'), 'standalone'):
            self.assertTrue(os.path.isfile(os.path.join(d, 'next.config.mjs')))
        self.assertEqual(os.listdir(d), ['package.json'])

    def test_config_is_restored_even_when_the_build_fails(self):
        d = self.project('next.config.ts', 'export default {};\n')
        with self.assertRaises(RuntimeError):
            with recipes._next_config_output(d, jobs.Job('t'), 'standalone'):
                raise RuntimeError('build exploded')
        with open(os.path.join(d, 'next.config.ts'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'export default {};\n')

    def test_recovers_a_config_left_behind_by_a_killed_build(self):
        d = self.project()
        write(d, 'next.config.ts', '// Generated by HTML2EXE - restored after the build\nexport default {};\n')
        write(d, 'next.config.h2e-original.ts', 'export default { real: true };\n')
        with recipes._next_config_output(d, jobs.Job('t'), 'standalone'):
            pass
        with open(os.path.join(d, 'next.config.ts'), encoding='utf-8') as fh:
            self.assertIn('real: true', fh.read())


class ServerDetectionTests(unittest.TestCase):
    def make(self, *files):
        d = tempfile.mkdtemp(prefix='h2e-next-')
        write(d, 'package.json', json.dumps({'dependencies': {'next': '16.0.0'}, 'scripts': {'build': 'next build'}}))
        for f in files:
            write(d, f)
        return d

    def test_api_route_handlers_and_middleware_are_detected(self):
        self.assertEqual(recipes.next_server_features(self.make('src/app/api/x/route.ts')), ['API routes', 'route handlers'])
        self.assertEqual(recipes.next_server_features(self.make('app/hello/route.js')), ['route handlers'])
        self.assertEqual(recipes.next_server_features(self.make('pages/api/x.js')), ['API routes'])
        self.assertEqual(recipes.next_server_features(self.make('middleware.ts', 'app/page.tsx')), ['middleware'])
        self.assertEqual(recipes.next_server_features(self.make('app/page.tsx')), [])

    def test_detect_reports_server_mode_and_a_friendly_note(self):
        info = recipes.detect(self.make('src/app/api/anime/episodes/route.ts'))
        self.assertTrue(info['server'])
        self.assertEqual(info['framework'], 'nextjs')
        self.assertTrue(any('bundled Node.js server' in n for n in info['notes']))
        self.assertFalse(recipes.detect(self.make('app/page.tsx'))['server'])


class InstallFingerprintTests(unittest.TestCase):
    def test_dependencies_are_reinstalled_only_when_the_lock_files_change(self):
        d = tempfile.mkdtemp(prefix='h2e-npm-')
        write(d, 'package.json', '{"dependencies": {"a": "1"}}')
        job = jobs.Job('t')
        calls = []

        def fake_run(cmd, cwd=None, env=None, shell=False, collect=None):
            calls.append(cmd)
            os.makedirs(os.path.join(cwd, 'node_modules'), exist_ok=True)
            return 0
        job.run_cmd = fake_run
        with mock.patch.object(recipes, '_require_node'):
            recipes._npm_install(d, job)                   # first time: installs
            recipes._npm_install(d, job)                   # unchanged: skipped
            self.assertEqual(len(calls), 1)
            write(d, 'package.json', '{"dependencies": {"a": "2"}}')
            recipes._npm_install(d, job)                   # changed: installs again
            self.assertEqual(len(calls), 2)
            recipes._npm_install(d, job)
            self.assertEqual(len(calls), 2)

    def test_node_modules_without_a_stamp_are_trusted(self):
        d = tempfile.mkdtemp(prefix='h2e-npm-')
        write(d, 'package.json', '{}')
        os.makedirs(os.path.join(d, 'node_modules'))
        job = jobs.Job('t')
        job.run_cmd = mock.Mock()
        recipes._npm_install(d, job)
        job.run_cmd.assert_not_called()


class BuildEnvTests(unittest.TestCase):
    def test_env_file_values_never_override_the_real_environment(self):
        job = jobs.Job('t')
        job.build_env = {'H2E_TEST_ONLY_VAR': 'from-file', 'PATH': 'ignored'}
        env = recipes._node_env(job=job)
        self.assertEqual(env['H2E_TEST_ONLY_VAR'], 'from-file')
        self.assertNotEqual(env['PATH'], 'ignored')
        self.assertEqual(recipes._node_env({'H2E_TEST_ONLY_VAR': 'explicit'}, job)['H2E_TEST_ONLY_VAR'], 'explicit')

    def test_fingerprint_changes_with_public_values_but_stores_no_secret(self):
        job = jobs.Job('t')
        job.build_env = {'NEXT_PUBLIC_A': '1', 'TOKEN': 'abc'}
        before = recipes._env_fingerprint(job)
        job.build_env['NEXT_PUBLIC_A'] = '2'
        self.assertNotEqual(before, recipes._env_fingerprint(job))
        job.build_env['NEXT_PUBLIC_A'] = '1'
        job.build_env['TOKEN'] = 'changed-secret-value'          # a secret VALUE change does not force a rebuild
        self.assertEqual(before, recipes._env_fingerprint(job))
        job.build_env['NEW_SECRET'] = 'x'                         # but a new variable does
        self.assertNotEqual(before, recipes._env_fingerprint(job))

    def test_shutil_is_not_needed_for_stamps(self):
        d = tempfile.mkdtemp(prefix='h2e-stamp-')
        write(d, 'src/a.js')
        recipes._stamp_write(d, 'standalone', 'abc')
        self.assertTrue(recipes._stamp_fresh(d, 'standalone', 'abc'))
        self.assertFalse(recipes._stamp_fresh(d, 'standalone', 'other'))
        future = os.path.getmtime(recipes._stamp_path(d)) + 100
        os.utime(os.path.join(d, 'src', 'a.js'), (future, future))        # a source file newer than the stamp
        self.assertFalse(recipes._stamp_fresh(d, 'standalone', 'abc'))
        shutil.rmtree(d)


if __name__ == '__main__':
    unittest.main()
