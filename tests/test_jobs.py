"""Background-job API tests (fast, no PyInstaller)."""
import json
import os
import sys
import threading
import time
import unittest
import urllib.request
from unittest import mock
from http.server import HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import builder  # noqa: E402
from h2e import jobs  # noqa: E402


class JobApiTests(unittest.TestCase):
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

    def wait(self, job_id, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            status, snap = self.call('GET', f'/api/job-status?id={job_id}')
            if snap['status'] != 'running':
                return snap
            time.sleep(0.1)
        self.fail('job did not finish')

    def test_async_build_with_bad_id_returns_job_and_error(self):
        status, started = self.call('POST', '/api/build-project',
                                    {'projectName': 'x', 'projectId': '../evil', 'async': True})
        self.assertEqual(status, 200)
        snap = self.wait(started['jobId'])
        self.assertEqual(snap['status'], 'error')
        self.assertIn('Invalid project ID', snap['result']['error'])

    def test_cancel_reports_cancelled_not_http_500(self):
        """Cancel must reach the job runner as 'cancelled' through the API handler."""
        def slow_convert(_data):
            jobs.run([sys.executable, '-c', 'import time; print("tick", flush=True); time.sleep(60)'])
            return {'success': True}, 200

        with mock.patch.object(builder.python_builder, 'convert', slow_convert):
            status, started = self.call('POST', '/api/convert-python-to-exe',
                                        {'pythonPath': 'x', 'async': True})
            job_id = started['jobId']
            for _ in range(100):
                _, snap = self.call('GET', f'/api/job-status?id={job_id}')
                if 'tick' in snap['lines']:
                    break
                time.sleep(0.1)
            t0 = time.time()
            self.call('POST', '/api/job-cancel', {'id': job_id})
            final = self.wait(job_id, timeout=15)
        self.assertEqual(final['status'], 'cancelled')
        self.assertEqual(final['result']['error'], 'Cancelled')
        self.assertLess(time.time() - t0, 10)

    def test_unknown_job_is_404(self):
        status, _ = self.call('GET', '/api/job-status?id=nope')
        self.assertEqual(status, 404)

    def test_system_check_lists_tools_and_frameworks(self):
        status, data = self.call('GET', '/api/system-check')
        self.assertEqual(status, 200)
        ids = {c['id'] for c in data['checks']}
        self.assertTrue({'python', 'pyinstaller', 'node', 'webview2'} <= ids)
        fw = {f['id']: f['support'] for f in data['frameworks']}
        self.assertEqual(fw['astro'], 'supported')
        self.assertEqual(fw['laravel'], 'experimental')

    def test_job_streams_log_lines_and_print_output(self):
        def work(job):
            job.log('hello')
            print('from print')
            return {'success': True}
        job = jobs.start_job('t', work)
        deadline = time.time() + 5
        while job.status == 'running' and time.time() < deadline:
            time.sleep(0.05)
        snap = job.snapshot(0)
        self.assertEqual(snap['status'], 'done')
        self.assertIn('hello', snap['lines'])
        self.assertIn('from print', snap['lines'])

    def test_run_cmd_streams_and_cancel_stops_it(self):
        def work(job):
            job.run_cmd([sys.executable, '-c', 'import time;print("started",flush=True);time.sleep(30)'])
            return {'success': True}
        job = jobs.start_job('t', work)
        deadline = time.time() + 10
        while 'started' not in job.snapshot(0)['lines'] and time.time() < deadline:
            time.sleep(0.05)
        job.cancel()
        deadline = time.time() + 10
        while job.status == 'running' and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(job.status, 'cancelled')

    def test_ui_assets_are_served(self):
        for path, needle in (('/app.js', b'runJob'), ('/style.css', b'--primary-dark')):
            req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}')
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.assertIn(needle, resp.read(), path)
        for gone in ('/script.js', '/jobs.js', '/api.js'):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f'http://127.0.0.1:{self.port}{gone}', timeout=10)
            self.assertEqual(ctx.exception.code, 404, gone)

if __name__ == '__main__':
    unittest.main()
