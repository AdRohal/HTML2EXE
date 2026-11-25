"""Background jobs with live log streaming.

Builds can take minutes, so the HTTP request that starts one returns a job id
immediately and the UI polls ``/api/job-status``. Output from legacy code that
simply ``print()``s is captured per-thread, so it shows up in the live log too.
"""
import subprocess
import sys
import threading
import time
import uuid

_LOCK = threading.Lock()
JOBS = {}
MAX_LOG_LINES = 5000


class JobCancelled(Exception):
    """Raised inside a job when the user pressed Cancel."""


class Job:
    def __init__(self, kind):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.status = 'running'          # running | done | error | cancelled
        self.lines = []
        self.result = None
        self.started = time.time()
        self.finished = None
        self.cancel_requested = False
        self._procs = []
        self._lock = threading.Lock()
        self.build_env = {}           # variables from .env files, given to build tools (never logged)
        self._secrets = []            # values to hide from the log

    # -- logging ---------------------------------------------------------
    def add_secrets(self, values):
        """Register values that must never appear in the log (replaced by ***)."""
        with self._lock:
            self._secrets = sorted({v for v in list(self._secrets) + list(values) if v}, key=len, reverse=True)

    def redact(self, text):
        for value in self._secrets:
            if value in text:
                text = text.replace(value, '***')
        return text

    def log(self, message):
        text = self.redact(str(message))
        with self._lock:
            for line in text.splitlines() or ['']:
                self.lines.append(line)
            if len(self.lines) > MAX_LOG_LINES:
                del self.lines[:len(self.lines) - MAX_LOG_LINES]

    def snapshot(self, since=0):
        with self._lock:
            # `since` counts lines ever written; keep it simple: absolute index
            return {
                'id': self.id,
                'kind': self.kind,
                'status': self.status,
                'lines': self.lines[since:],
                'next': len(self.lines),
                'result': self.result if self.status != 'running' else None,
                'elapsed': round((self.finished or time.time()) - self.started, 1),
            }

    # -- cancel ----------------------------------------------------------
    def check_cancelled(self):
        if self.cancel_requested:
            raise JobCancelled()

    def cancel(self):
        self.cancel_requested = True
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            _kill_tree(proc)

    # -- subprocess with streaming output ----------------------------------
    def run_cmd(self, cmd, cwd=None, env=None, shell=False, collect=None):
        """Run a command, streaming each output line into the job log.

        Returns the exit code. Raises JobCancelled if the job was cancelled.
        """
        self.check_cancelled()
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        printable = cmd if isinstance(cmd, str) else ' '.join(cmd)
        self.log(f'$ {printable}')
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, shell=shell,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            creationflags=flags,
        )
        with self._lock:
            self._procs.append(proc)
        try:
            for line in proc.stdout:
                line = self.redact(line.rstrip('\r\n'))
                if collect is not None:
                    collect.append(line)
                self.log(line)
            proc.wait()
        finally:
            with self._lock:
                if proc in self._procs:
                    self._procs.remove(proc)
            try:
                proc.stdout.close()
            except Exception:
                pass
        self.check_cancelled()
        return proc.returncode


def run(cmd, cwd=None, env=None, shell=False, **_ignored):
    """Drop-in for ``subprocess.run(..., capture_output=True, text=True)``.

    Inside a job the output streams into the live log and Cancel kills the
    process tree; outside a job it is a plain captured run. Output (stdout and
    stderr merged) is returned in ``.stdout``; ``.stderr`` mirrors it so
    callers that print the error text keep working.
    """
    job = current_job()
    if job is None:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        res = subprocess.run(cmd, cwd=cwd, env=env, shell=shell, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                             errors='replace', creationflags=flags)
        return subprocess.CompletedProcess(res.args, res.returncode, res.stdout or '', res.stdout or '')
    lines = []
    code = job.run_cmd(cmd, cwd=cwd, env=env, shell=shell, collect=lines)
    text = chr(10).join(lines)
    return subprocess.CompletedProcess(cmd, code, text, text)


def _kill_tree(proc):
    try:
        if sys.platform == 'win32':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            proc.kill()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Thread-aware stdout so legacy print() output lands in the right job log
# ---------------------------------------------------------------------------
_THREAD = threading.local()


class _RoutedStream:
    def __init__(self, original):
        self._original = original
        self._partial = ''

    def write(self, text):
        job = getattr(_THREAD, 'job', None)
        if job is None:
            return self._original.write(text) if self._original else len(text)
        buf = getattr(_THREAD, 'buf', '') + text
        *complete, rest = buf.split('\n')
        _THREAD.buf = rest
        for line in complete:
            job.log(line)
        return len(text)

    def flush(self):
        if self._original:
            try:
                self._original.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._original, name)


_installed = False


def _install_stream_router():
    global _installed
    if _installed:
        return
    sys.stdout = _RoutedStream(sys.stdout)
    sys.stderr = _RoutedStream(sys.stderr)
    _installed = True


def start_job(kind, func):
    """Run ``func(job)`` in a thread. ``func`` returns the final result dict."""
    _install_stream_router()
    job = Job(kind)
    with _LOCK:
        JOBS[job.id] = job
        # forget old finished jobs
        for jid in [j for j, v in JOBS.items() if v.finished and time.time() - v.finished > 3600]:
            del JOBS[jid]

    def runner():
        _THREAD.job = job
        _THREAD.buf = ''
        try:
            job.result = func(job)
            ok = bool(job.result) and not job.result.get('error') and job.result.get('success', True)
            job.status = 'done' if ok else 'error'
        except JobCancelled:
            job.result = {'success': False, 'error': 'Cancelled'}
            job.status = 'cancelled'
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            import traceback
            job.log(traceback.format_exc())
            job.result = {'success': False, 'error': str(exc)}
            job.status = 'error'
        finally:
            if getattr(_THREAD, 'buf', ''):
                job.log(_THREAD.buf)
            job.finished = time.time()
            _THREAD.job = None

    threading.Thread(target=runner, daemon=True, name=f'job-{job.id}').start()
    return job


def current_job():
    """The job running on this thread, if any."""
    return getattr(_THREAD, 'job', None)


def get_job(job_id):
    with _LOCK:
        return JOBS.get(job_id)
