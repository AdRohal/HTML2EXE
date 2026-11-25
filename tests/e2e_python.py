"""Real Python -> EXE conversion through the HTTP API, then run the EXE (slow).

    python tests/e2e_python.py

Builds a tiny console project twice (single file and one-folder), checks that the
bundled data file and sub-folder asset are readable from the produced EXE.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MAIN = '''import json, os, sys
base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(base, "config.json"), encoding="utf-8") as fh:
    cfg = json.load(fh)
with open(os.path.join(base, "assets", "note.txt"), encoding="utf-8") as fh:
    note = fh.read().strip()
print("PYEXE-OK", cfg["value"], note)
'''


def main():
    home = tempfile.mkdtemp(prefix='h2e-pyapi-')
    os.environ['USERPROFILE'] = home
    os.environ['HOME'] = home
    sys.path.insert(0, ROOT)
    import builder

    project = os.path.join(home, 'my project')           # a space in the path on purpose
    os.makedirs(os.path.join(project, 'assets'))
    for rel, text in (('main.py', MAIN), ('config.json', json.dumps({'value': 42})),
                      (os.path.join('assets', 'note.txt'), 'asset-ok')):
        with open(os.path.join(project, rel), 'w', encoding='utf-8') as fh:
            fh.write(text)

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

    failures = 0
    for single in (True, False):
        out_dir = os.path.join(home, f'out-{"one" if single else "dir"}')
        started = call('POST', '/api/convert-python-to-exe', {
            'pythonPath': project, 'exeName': '..\\Py Test ' + ('one' if single else 'dir'),
            'hideConsole': False, 'singleFile': single, 'optimize': not single,
            'outputDir': out_dir, 'async': True})
        job_id = started['jobId']
        since, lines = 0, []
        while True:
            time.sleep(1)
            snap = call('GET', f'/api/job-status?id={job_id}&since={since}')
            since = snap['next']
            lines += snap['lines']
            if snap['status'] != 'running':
                break
        result = snap['result'] or {}
        status = 'PASS'
        detail = ''
        if snap['status'] != 'done':
            status, detail = 'FAIL', f"job {snap['status']}: {result.get('error')}"
        else:
            exe = result['exePath']
            if '..' in os.path.relpath(exe, out_dir):
                status, detail = 'FAIL', f'exe escaped output dir: {exe}'
            else:
                proc = subprocess.run([exe], capture_output=True, text=True, timeout=120)
                if 'PYEXE-OK 42 asset-ok' not in proc.stdout:
                    status, detail = 'FAIL', f'exe output: {proc.stdout!r} {proc.stderr[-300:]!r}'
        live = [l for l in lines if 'PyInstaller' in l or 'Analysis' in l or 'EXE' in l]
        if status == 'PASS' and not live:
            status, detail = 'FAIL', 'no live PyInstaller output reached the job log'
        if status != 'PASS':
            failures += 1
            print('\n'.join(lines[-25:]))
        print(f'== python->exe single_file={single}: {status} {detail} [{result.get("exePath")}]', flush=True)
    server.shutdown()
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
