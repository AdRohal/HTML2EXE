"""Full flow through the real HTTP API: create-project -> async build -> poll -> EXE (slow).

    python tests/e2e_api.py [project-folder]
"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def main():
    folder = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, 'tests', 'fixtures', 'spa')
    home = tempfile.mkdtemp(prefix='h2e-api-')
    os.environ['USERPROFILE'] = home
    os.environ['HOME'] = home
    sys.path.insert(0, ROOT)
    import builder

    builder.BuilderHTTPHandler.builder_root = ROOT
    server = HTTPServer(('127.0.0.1', 0), builder.BuilderHTTPHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def call(method, path, body=None):
        req = urllib.request.Request(
            f'http://127.0.0.1:{port}{path}', method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'X-Builder-Token': builder.API_TOKEN, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            return json.load(err)

    created = call('POST', '/api/create-project', {'name': 'API Test App', 'folderPath': folder})
    print('create-project:', created.get('success'), created.get('error'))
    started = call('POST', '/api/build-project', {'projectName': 'API Test App', 'projectId': 'API Test App',
                                                  'async': True})
    job_id = started['jobId']
    since, shown = 0, 0
    while True:
        time.sleep(1)
        snap = call('GET', f'/api/job-status?id={job_id}&since={since}')
        since = snap['next']
        for line in snap['lines']:
            if shown < 12 or not line.startswith(('INFO', '[')) and 'INFO:' not in line:
                print('  |', line)
                shown += 1
        if snap['status'] != 'running':
            break
    result = snap['result']
    print('STATUS:', snap['status'], '| selfTest:', (result or {}).get('selfTest', {}).get('ok'),
          '| exe:', (result or {}).get('exePath'))
    server.shutdown()
    ok = snap['status'] == 'done' and result.get('selfTest', {}).get('ok')
    print('RESULT:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
