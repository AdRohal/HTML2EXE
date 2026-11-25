import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from h2e import jobs, python_builder as pb  # noqa: E402


def write(base, rel, text='x'):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


class NameTests(unittest.TestCase):
    def test_safe_exe_name(self):
        self.assertEqual(pb.safe_exe_name('..\\..\\evil'), 'evil')
        self.assertEqual(pb.safe_exe_name('a/b:c*?'), 'a_b_c')
        self.assertEqual(pb.safe_exe_name(''), 'MyApp')
        self.assertEqual(pb.safe_exe_name(None), 'MyApp')
        self.assertEqual(pb.safe_exe_name('My App 2'), 'My App 2')


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='h2e-py-')

    def test_entry_point_priority(self):
        write(self.dir, 'zeta.py')
        write(self.dir, 'app.py')
        entry, files = pb.find_entry_point(self.dir)
        self.assertEqual(entry, 'app.py')
        self.assertEqual(files, ['app.py', 'zeta.py'])

    def test_first_py_file_when_no_standard_name(self):
        write(self.dir, 'zeta.py')
        write(self.dir, 'alpha.py')
        self.assertEqual(pb.find_entry_point(self.dir)[0], 'alpha.py')

    def test_no_python_files(self):
        write(self.dir, 'readme.txt')
        self.assertIsNone(pb.find_entry_point(self.dir)[0])

    def test_imports_use_ast_not_substring_matching(self):
        write(self.dir, 'main.py',
              '# flask is great\nimport requests\nfrom PIL import Image\n'
              'text = "numpy is not imported"\nimport os.path\nfrom . import sibling\n')
        found = pb.detect_imports(self.dir, ['main.py'])
        self.assertIn('requests', found)
        self.assertIn('PIL', found)
        self.assertIn('os', found)
        self.assertNotIn('flask', found)
        self.assertNotIn('numpy', found)

    def test_broken_script_does_not_crash_detection(self):
        write(self.dir, 'main.py', 'def broken(:\n')
        self.assertEqual(pb.detect_imports(self.dir, ['main.py']), set())

    def test_data_entries_include_root_files_and_asset_folders_only(self):
        write(self.dir, 'main.py')
        write(self.dir, 'config.json', '{}')
        write(self.dir, 'assets/logo.png')
        write(self.dir, 'pkg/module.py')            # python-only package: not data
        write(self.dir, 'venv/lib/x.txt')           # skipped
        write(self.dir, '.git/config')              # skipped
        entries = dict((os.path.basename(s), d) for s, d in pb.find_data_entries(self.dir))
        self.assertEqual(entries.get('config.json'), '.')
        self.assertEqual(entries.get('assets'), 'assets')
        self.assertNotIn('pkg', entries)
        self.assertNotIn('venv', entries)
        self.assertNotIn('.git', entries)
        self.assertNotIn('main.py', entries)


class SpecTests(unittest.TestCase):
    def _spec(self, **kw):
        args = dict(entry_path=r"C:\it's here\main.py", project_dir=r"C:\it's here",
                    exe_name='My App', datas=[(r"C:\it's here\assets", 'assets')],
                    hidden_imports=['flask'], console=False, icon=r"C:\icons\a'b.ico",
                    single_file=True, optimize=False)
        args.update(kw)
        return pb.build_spec(**args)

    def test_spec_is_valid_python_with_awkward_paths(self):
        for single in (True, False):
            for opt in (True, False):
                text = self._spec(single_file=single, optimize=opt)
                compile(text, 'x.spec', 'exec')         # must parse
                self.assertIn("console=False", text)
                self.assertIn("hiddenimports=['flask']", text)
                self.assertEqual('COLLECT(' in text, not single)
                self.assertIn('optimize=2' if opt else 'optimize=-1', text)

    def test_console_true_when_not_hidden(self):
        self.assertIn('console=True', self._spec(console=True))


class ConvertErrorTests(unittest.TestCase):
    def test_missing_path_is_404(self):
        res, status = pb.convert({'pythonPath': r'C:\definitely\not\here', 'exeName': 'x'})
        self.assertEqual(status, 404)

    def test_folder_without_python_is_400(self):
        d = tempfile.mkdtemp(prefix='h2e-py-')
        write(d, 'notes.txt')
        res, status = pb.convert({'pythonPath': d, 'exeName': 'x'})
        self.assertEqual(status, 400)
        self.assertIn('No Python', res['error'])

    def test_non_python_file_is_400(self):
        d = tempfile.mkdtemp(prefix='h2e-py-')
        path = write(d, 'notes.txt')
        res, status = pb.convert({'pythonPath': path, 'exeName': 'x'})
        self.assertEqual(status, 400)


class JobRunTests(unittest.TestCase):
    def test_run_outside_job_captures_output(self):
        res = jobs.run([sys.executable, '-c', 'print("hello"); import sys; sys.exit(3)'])
        self.assertEqual(res.returncode, 3)
        self.assertIn('hello', res.stdout)

    def test_run_inside_job_streams_into_log(self):
        def work(job):
            res = jobs.run([sys.executable, '-c', 'print("streamed-line")'])
            return {'success': res.returncode == 0, 'out': res.stdout}
        job = jobs.start_job('t', work)
        for _ in range(100):
            if job.status != 'running':
                break
            time.sleep(0.1)
        self.assertEqual(job.status, 'done')
        self.assertIn('streamed-line', job.snapshot()['lines'])
        self.assertIn('streamed-line', job.result['out'])

    def test_cancel_kills_a_running_subprocess(self):
        def work(job):
            jobs.run([sys.executable, '-c', 'import time; print("up", flush=True); time.sleep(60)'])
            return {'success': True}
        job = jobs.start_job('t', work)
        for _ in range(100):
            if 'up' in job.snapshot()['lines']:
                break
            time.sleep(0.1)
        started = time.time()
        job.cancel()
        for _ in range(100):
            if job.status != 'running':
                break
            time.sleep(0.1)
        self.assertEqual(job.status, 'cancelled')
        self.assertLess(time.time() - started, 10)


if __name__ == '__main__':
    unittest.main()


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='h2e-an-')

    def test_gui_and_requirements(self):
        write(self.dir, 'main.py', "import tkinter\nimport requests\nif __name__ == '__main__':\n    pass\n")
        write(self.dir, 'requirements.txt', 'requests>=2\n# c\nPillow==10.0 # pin\n')
        info = pb.analyze(self.dir)
        self.assertTrue(info['gui'])
        self.assertEqual(info['entry'], 'main.py')
        self.assertEqual(info['requirements']['packages'], ['requests', 'Pillow'])

    def test_skips_virtualenv_and_finds_nested_entry(self):
        write(self.dir, 'venv/pyvenv.cfg', '')
        write(self.dir, 'venv/lib/x.py', 'import evil\n')
        write(self.dir, 'src/cli.py', "if __name__ == '__main__':\n    pass\n")
        info = pb.analyze(self.dir)
        self.assertEqual(info['entry'], 'src/cli.py')
        self.assertNotIn('evil', info['thirdParty'])

    def test_errors(self):
        with self.assertRaises(FileNotFoundError):
            pb.analyze(os.path.join(self.dir, 'nope'))
        with self.assertRaises(ValueError):
            pb.analyze(self.dir)

    def test_env_file_never_bundled(self):
        write(self.dir, 'main.py')
        write(self.dir, '.env', 'KEY=1')
        self.assertFalse(any('.env' in s for s, _ in pb.find_data_entries(self.dir)))

    def test_version_info_and_spec(self):
        text = pb.version_info_text('My App', '1.2', 'Acme', 'MyApp')
        self.assertIn('(1, 2, 0, 0)', text)
        self.assertIn("'Acme'", text)
        spec = pb.build_spec('m.py', '.', 'A', [], [], False, None, True, False, True, 'v.txt', ['h.py'])
        self.assertIn('uac_admin=True', spec)
        self.assertIn("version='v.txt'", spec)
        self.assertIn("runtime_hooks=['h.py']", spec)
