import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from h2e import jobs  # noqa: E402
from h2e.exe_build import self_test  # noqa: E402


def pid_alive(pid):
    out = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, text=True).stdout
    return str(pid) in out


@unittest.skipUnless(sys.platform == 'win32', 'uses a .bat launcher stand-in')
class SelfTestTimeoutTests(unittest.TestCase):
    def test_timeout_kills_the_launcher_and_its_children(self):
        folder = tempfile.mkdtemp(prefix='h2e-st-')
        pid_file = os.path.join(folder, 'child.pid')
        child = os.path.join(folder, 'child.py')
        with open(child, 'w', encoding='utf-8') as fh:
            fh.write(f'import os, time\nopen({pid_file!r}, "w").write(str(os.getpid()))\ntime.sleep(120)\n')
        bat = os.path.join(folder, 'fake.bat')
        with open(bat, 'w', encoding='utf-8') as fh:
            fh.write(f'@echo off\r\n"{sys.executable}" "{child}"\r\n')   # never writes the report

        started = time.time()
        result = self_test(bat, folder, jobs.Job('t'), timeout=4)
        self.assertFalse(result['ok'])
        self.assertLess(time.time() - started, 20)
        for _ in range(20):                       # the child wrote its pid before we gave up
            if os.path.isfile(pid_file) and open(pid_file).read().strip():
                break
            time.sleep(0.25)
        pid = int(open(pid_file).read())
        time.sleep(1)
        self.assertFalse(pid_alive(pid), 'child process survived the self-test timeout')


if __name__ == '__main__':
    unittest.main()
