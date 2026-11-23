"""Security tests for the builder's local HTTP API.

Run:  python -m unittest discover -s tests -v
"""
import http.client
import json
import os
import sys
import threading
import unittest
from http.server import HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import builder  # noqa: E402


class SecurityTests(unittest.TestCase):
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

    def request(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        hdrs = {'Host': host or f'127.0.0.1:{self.port}'}
        hdrs.update(headers or {})
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in hdrs.items():
            conn.putheader(k, v)
        data = json.dumps(body).encode() if body is not None else None
        if data is not None:
            conn.putheader('Content-Length', str(len(data)))
            conn.putheader('Content-Type', 'application/json')
        conn.endheaders(data)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp.status, dict(resp.getheaders()), payload

    def auth(self, **extra):
        h = {'X-Builder-Token': builder.API_TOKEN}
        h.update(extra)
        return h

    def test_api_without_token_is_forbidden(self):
        self.assertEqual(self.request('GET', '/api/settings')[0], 403)
        self.assertEqual(self.request('POST', '/api/delete-project', {'projectId': 'x'})[0], 403)

    def test_api_with_wrong_token_is_forbidden(self):
        status, *_ = self.request('GET', '/api/settings', headers={'X-Builder-Token': 'nope'})
        self.assertEqual(status, 403)

    def test_api_with_token_works_and_has_no_cors_wildcard(self):
        status, headers, _ = self.request('GET', '/api/settings', headers=self.auth())
        self.assertEqual(status, 200)
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_foreign_origin_is_forbidden_even_with_token(self):
        status, *_ = self.request('GET', '/api/settings', headers=self.auth(Origin='https://evil.example'))
        self.assertEqual(status, 403)

    def test_own_origin_is_allowed(self):
        status, *_ = self.request('GET', '/api/settings', headers=self.auth(Origin=f'http://127.0.0.1:{self.port}'))
        self.assertEqual(status, 200)

    def test_dns_rebinding_host_is_forbidden(self):
        status, *_ = self.request('GET', '/api/settings', headers=self.auth(), host='evil.example')
        self.assertEqual(status, 403)

    def test_index_page_gets_token(self):
        status, _, payload = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(builder.API_TOKEN.encode(), payload)

    def test_static_path_traversal_blocked(self):
        for path in ('/assets/../../builder.py', '/assets/..%2f..%2fbuilder.py', '/assets/../../.git/config'):
            status, _, payload = self.request('GET', path)
            self.assertNotEqual(status, 200, path)
            self.assertNotIn(b'class BuilderHTTPHandler', payload)

    def test_delete_project_rejects_traversal_ids(self):
        bs = chr(92)
        for bad in ('..', '../x', '..' + bs + 'x', 'a/b', 'C:' + bs + 'Windows', '', '.'):
            status, _, _ = self.request('POST', '/api/delete-project', {'projectId': bad}, headers=self.auth())
            self.assertEqual(status, 400, repr(bad))

    def test_safe_id_helper(self):
        self.assertTrue(builder.is_safe_project_id('My App 2'))
        for bad in ('..', '.', ' x', 'x ', 'a/b', 'a' + chr(92) + 'b', 'a:b', ''):
            self.assertFalse(builder.is_safe_project_id(bad), repr(bad))
        self.assertIsNone(builder.project_dir_for('../evil'))


if __name__ == '__main__':
    unittest.main()
