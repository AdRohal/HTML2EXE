"""create-project API: starter templates, imported folders, name safety (isolated HOME)."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import builder  # noqa: E402
from h2e import jobs, recipes  # noqa: E402


class CreateProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        builder.BuilderHTTPHandler.builder_root = os.path.dirname(os.path.abspath(builder.__file__))
        cls.server = HTTPServer(('127.0.0.1', 0), builder.BuilderHTTPHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix='h2e-home-')
        patcher = mock.patch.dict(os.environ, {'USERPROFILE': self.home, 'HOME': self.home})
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, method, path, body=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={'X-Builder-Token': builder.API_TOKEN,
                                              'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as err:
            return err.code, json.load(err)

    def test_each_template_creates_a_buildable_project(self):
        for template in ('blank', 'modern', 'dashboard', 'calculator'):
            status, res = self.call('POST', '/api/create-project', {'name': f'T-{template}', 'template': template})
            self.assertEqual(status, 200, res)
            folder = res['downloadFolder']
            self.assertTrue(os.path.isfile(os.path.join(folder, 'index.html')), template)
            plan = recipes.prepare(folder, jobs.Job('t'))          # exactly what a build does first
            self.assertEqual(plan['kind'], 'static')
            self.assertTrue(os.path.isfile(os.path.join(plan['source_dir'], 'index.html')))

    def test_templates_are_distinct_and_link_existing_assets(self):
        from h2e import templates
        pages = {}
        for name in templates.TEMPLATES:
            folder = tempfile.mkdtemp(prefix='h2e-tpl-')
            templates.write_template(folder, name)
            with open(os.path.join(folder, 'index.html'), encoding='utf-8') as fh:
                pages[name] = fh.read()
            for asset in ('style.css', 'script.js'):
                self.assertIn(asset, pages[name], name)
                self.assertTrue(os.path.isfile(os.path.join(folder, asset)), (name, asset))
        self.assertEqual(len(set(pages.values())), len(pages), 'every template needs its own index.html')

    def test_created_project_is_listed(self):
        self.call('POST', '/api/create-project', {'name': 'Listed', 'template': 'blank', 'author': 'me'})
        status, res = self.call('GET', '/api/projects')
        self.assertEqual([p['id'] for p in res['projects']], ['Listed'])
        self.assertEqual(res['projects'][0]['author'], 'me')

    def test_recreating_does_not_overwrite_user_edits(self):
        _, res = self.call('POST', '/api/create-project', {'name': 'Keep', 'template': 'blank'})
        index = os.path.join(res['downloadFolder'], 'index.html')
        with open(index, 'w', encoding='utf-8') as fh:
            fh.write('<h1>my edit</h1>')
        self.call('POST', '/api/create-project', {'name': 'Keep', 'template': 'modern'})
        with open(index, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '<h1>my edit</h1>')

    def test_importing_the_projects_own_folder_never_deletes_it(self):
        _, res = self.call('POST', '/api/create-project', {'name': 'Self', 'template': 'blank'})
        folder = res['downloadFolder']
        status, again = self.call('POST', '/api/create-project', {'name': 'Self', 'folderPath': folder})
        self.assertEqual(status, 200, again)
        self.assertTrue(os.path.isfile(os.path.join(folder, 'index.html')))

    def test_working_copy_skips_caches_but_keeps_build_output(self):
        src = tempfile.mkdtemp(prefix='h2e-src-')
        for rel in ('package.json', 'src/app.js', 'dist/index.html', 'node_modules/x/i.js',
                    '.next/cache/c.js', '.nuxt/n.js', 'coverage/c.json'):
            path = os.path.join(src, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('{}')
        status, res = self.call('POST', '/api/create-project', {'name': 'Copy', 'folderPath': src})
        self.assertEqual(status, 200, res)
        copied = {os.path.relpath(os.path.join(r, f), res['downloadFolder']).replace(os.sep, '/')
                  for r, _d, fs in os.walk(res['downloadFolder']) for f in fs}
        self.assertEqual(copied, {'package.json', 'src/app.js', 'dist/index.html', '.h2e-workspace'})

    def test_env_files_are_not_copied_into_the_working_copy(self):
        src = tempfile.mkdtemp(prefix='h2e-src-')
        for rel, text in (('package.json', '{}'), ('.env', 'A=1'), ('.env.local', 'SECRET_KEY=abcdefgh12345'),
                          ('.env.production', 'B=2'), ('.env.example', 'SECRET_KEY='), ('app.js', 'x')):
            with open(os.path.join(src, rel), 'w', encoding='utf-8') as fh:
                fh.write(text)
        status, res = self.call('POST', '/api/create-project', {'name': 'NoEnv', 'folderPath': src})
        self.assertEqual(status, 200, res)
        self.assertEqual(sorted(os.listdir(res['downloadFolder'])), ['.env.example', '.h2e-workspace', 'app.js', 'package.json'])
        self.assertTrue(os.path.isfile(os.path.join(src, '.env.local')))       # the owner's file is untouched

    def test_env_scan_returns_names_kinds_and_lengths_but_never_values(self):
        src = tempfile.mkdtemp(prefix='h2e-src-')
        with open(os.path.join(src, '.env.local'), 'w', encoding='utf-8') as fh:
            fh.write('TMDB_API_KEY=FAKE-SECRET-KEY-1234567890abcd\nNEXT_PUBLIC_SITE=https://example.test\n'
                     'DATABASE_URL="postgres://user:p@ss word@db.example.test:5432/app"\n')
        status, res = self.call('POST', '/api/env-scan', {'folderPath': src})
        self.assertEqual(status, 200)
        text = json.dumps(res)
        for value in ('FAKE-SECRET-KEY', 'p@ss word', 'db.example.test', 'example.test'):
            self.assertNotIn(value, text)
        self.assertEqual({v['name'] for v in res['vars']}, {'TMDB_API_KEY', 'NEXT_PUBLIC_SITE', 'DATABASE_URL'})
        self.assertEqual(res['files'], ['.env.local'])
        status, _ = self.call('POST', '/api/env-scan', {'folderPath': r'C:\definitely\not\here'})
        self.assertEqual(status, 400)

    def test_unknown_template_falls_back_to_blank(self):
        status, res = self.call('POST', '/api/create-project', {'name': 'Odd', 'template': '../../etc'})
        self.assertEqual(status, 200)
        self.assertTrue(os.path.isfile(os.path.join(res['downloadFolder'], 'index.html')))

    def test_unsafe_names_are_rejected(self):
        for bad in ('..', 'a/b', 'a\b', 'x:y', ''):
            status, _ = self.call('POST', '/api/create-project', {'name': bad, 'template': 'blank'})
            self.assertEqual(status, 400, repr(bad))


if __name__ == '__main__':
    unittest.main()
