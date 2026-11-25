import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from h2e import dashboard  # noqa: E402


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix='h2e-dash-')
        self._old = os.environ.get('USERPROFILE'), os.environ.get('HOME')
        os.environ['USERPROFILE'] = os.environ['HOME'] = self.home
        self.root = os.path.join(self.home, 'Documents', 'HTML2EXE')

    def tearDown(self):
        for key, val in zip(('USERPROFILE', 'HOME'), self._old):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def project(self, name, framework='static'):
        folder = os.path.join(self.root, name)
        os.makedirs(folder)
        with open(os.path.join(folder, 'project.json'), 'w', encoding='utf-8') as fh:
            json.dump({'name': name, 'analysis': {'framework': framework}}, fh)
        return folder

    def test_empty(self):
        s = dashboard.stats()
        self.assertEqual((s['projects'], s['builtApps'], s['avgSizeMb']), (0, 0, None))

    def test_counts_only_existing_builds(self):
        a, b = self.project('A'), self.project('B', 'python')
        self.project('C')
        exe = os.path.join(self.home, 'a.exe')
        with open(exe, 'wb') as fh:
            fh.write(b'x' * 2 * 1024 * 1024)
        dashboard.record_build(a, {'exePath': exe, 'sizeMb': 2.0, 'kind': 'installer', 'success': True})
        dashboard.record_build(b, {'exePath': os.path.join(self.home, 'gone.exe'), 'kind': 'portable'})
        s = dashboard.stats()
        self.assertEqual((s['projects'], s['pythonProjects'], s['builtApps']), (3, 1, 1))
        self.assertEqual(s['avgSizeMb'], 2.0)
        self.assertEqual(s['recent'][0]['kind'], 'installer')

    def test_history_is_bounded(self):
        a = self.project('A')
        for _ in range(30):
            dashboard.record_build(a, {'exePath': 'x', 'kind': 'portable'})
        with open(os.path.join(a, 'project.json'), encoding='utf-8') as fh:
            self.assertLessEqual(len(json.load(fh)['builds']), 20)


if __name__ == '__main__':
    unittest.main()
