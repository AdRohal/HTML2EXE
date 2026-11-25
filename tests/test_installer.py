import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from h2e import installer, winshell  # noqa: E402
from h2e.launcher import render_launcher  # noqa: E402

REG_ROOT = r'Software\Microsoft\Windows\CurrentVersion\Uninstall'


def write(base, rel, data):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(data if isinstance(data, bytes) else data.encode())
    return path


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reg_read(key_name):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT + '\\' + key_name) as key:
            values = {}
            i = 0
            while True:
                try:
                    n, v, _t = winreg.EnumValue(key, i)
                except OSError:
                    return values
                values[n] = v
                i += 1
    except OSError:
        return None


def reg_delete(key_name):
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_ROOT + '\\' + key_name)
    except OSError:
        pass


class InstallerCase(unittest.TestCase):
    """Loads a generated installer around a fake payload, with registry key and shortcut folders redirected."""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix='h2e-inst-')
        self.key = 'H2E-test-' + uuid.uuid4().hex[:10]
        self.addCleanup(reg_delete, self.key)
        self.payload_bytes = b'FAKE-PAYLOAD-' + os.urandom(3 * 1024 * 1024)
        self.config = {'name': 'Test App', 'exe_name': 'Test_App.exe', 'app_key': self.key, 'version': '2.5.1',
                       'publisher': 'Acme', 'payload_size': len(self.payload_bytes),
                       'payload_sha256': __import__('hashlib').sha256(self.payload_bytes).hexdigest()}
        source = write(self.work, 'setup_main.py', installer.render_installer(self.config))
        self.mod = load(source, 'setup_under_test_' + self.key.replace('-', '_'))
        payload = write(self.work, 'payload/Test_App.exe', self.payload_bytes)
        self.mod.PAYLOAD = payload
        self.mod.LOG_PATH = os.path.join(self.work, 'setup.log')
        self.desktop = os.path.join(self.work, 'Desktop')
        self.menu = os.path.join(self.work, 'Programs')
        self.mod.desktop_dir = lambda: self.desktop
        self.mod.start_menu_dir = lambda: self.menu
        self.target = os.path.join(self.work, 'Program Files Like', 'Test App')


class InstallTests(InstallerCase):
    def test_payload_check(self):
        self.assertTrue(self.mod.payload_ok())
        with open(self.mod.PAYLOAD, 'r+b') as fh:
            fh.seek(100)
            fh.write(b'X')
        self.assertFalse(self.mod.payload_ok())
        os.remove(self.mod.PAYLOAD)
        self.assertFalse(self.mod.payload_ok())

    def test_install_copies_registers_and_creates_shortcuts(self):
        progress = []
        dst = self.mod.install({'dir': self.target}, lambda f, t: progress.append(f))
        self.assertEqual(dst, os.path.join(self.target, 'Test_App.exe'))
        with open(dst, 'rb') as fh:
            self.assertEqual(fh.read(), self.payload_bytes)
        self.assertEqual(os.listdir(self.target), ['Test_App.exe'])                 # no .part leftovers
        self.assertEqual(progress[-1], 1.0)
        self.assertEqual(progress, sorted(progress))
        reg = reg_read(self.key)
        self.assertEqual(reg['DisplayName'], 'Test App')
        self.assertEqual(reg['DisplayVersion'], '2.5.1')
        self.assertEqual(reg['Publisher'], 'Acme')
        self.assertEqual(reg['InstallLocation'], self.target)
        self.assertEqual(reg['DisplayIcon'], dst)
        self.assertEqual(reg['UninstallString'], f'"{dst}" --uninstall')
        self.assertEqual(reg['QuietUninstallString'], f'"{dst}" --uninstall --quiet')
        self.assertGreater(reg['EstimatedSize'], 1000)
        self.assertEqual(self.mod.installed_dir(), self.target)
        for folder in (self.desktop, self.menu):
            lnk = os.path.join(folder, 'Test App.lnk')
            self.assertTrue(os.path.isfile(lnk), lnk)
        target = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK).TargetPath"],
            env=dict(os.environ, LNK=os.path.join(self.desktop, 'Test App.lnk')), capture_output=True, text=True).stdout.strip()
        self.assertTrue(os.path.samefile(target, dst), target)       # Windows stores the long form of 8.3 paths

    def test_shortcut_choices_are_respected(self):
        self.mod.install({'dir': self.target, 'desktop': False, 'startmenu': True})
        self.assertFalse(os.path.exists(os.path.join(self.desktop, 'Test App.lnk')))
        self.assertTrue(os.path.exists(os.path.join(self.menu, 'Test App.lnk')))

    def test_damaged_payload_installs_nothing(self):
        with open(self.mod.PAYLOAD, 'r+b') as fh:
            fh.seek(1000)
            fh.write(b'TAMPERED')
        with self.assertRaises(self.mod.InstallError) as ctx:
            self.mod.install({'dir': self.target})
        self.assertIn('damaged', str(ctx.exception))
        self.assertEqual(os.listdir(self.target), [])                                  # not even a .part file
        self.assertIsNone(reg_read(self.key))
        self.assertFalse(os.path.exists(os.path.join(self.menu, 'Test App.lnk')))

    def test_cancelling_leaves_nothing_behind(self):
        calls = {'n': 0}

        def cancelled():
            calls['n'] += 1
            return calls['n'] > 1
        with self.assertRaises(self.mod.InstallError):
            self.mod.install({'dir': self.target}, cancelled=cancelled)
        self.assertEqual(os.listdir(self.target), [])
        self.assertIsNone(reg_read(self.key))

    def test_updating_keeps_other_files_and_replaces_the_exe(self):
        os.makedirs(self.target)
        write(self.target, 'Test_App.exe', b'old version')
        write(self.target, 'user-notes.txt', b'keep me')
        self.mod.install({'dir': self.target})
        with open(os.path.join(self.target, 'Test_App.exe'), 'rb') as fh:
            self.assertEqual(fh.read(), self.payload_bytes)
        with open(os.path.join(self.target, 'user-notes.txt'), 'rb') as fh:
            self.assertEqual(fh.read(), b'keep me')

    def test_a_running_app_is_reported_clearly(self):
        os.makedirs(self.target)
        exe = write(self.target, 'Test_App.exe', b'old version')
        with open(exe, 'rb'):                                                         # like a running program: file is open
            with self.assertRaises(self.mod.InstallError) as ctx:
                self.mod.install({'dir': self.target})
        self.assertIn('Close it', str(ctx.exception))
        self.assertEqual(os.listdir(self.target), ['Test_App.exe'])

    def test_a_whole_drive_is_not_a_valid_folder(self):
        with self.assertRaises(self.mod.InstallError):
            self.mod.install({'dir': os.path.splitdrive(self.work)[0] + '\\'})

    def test_default_folder_is_per_user(self):
        self.assertEqual(self.mod.default_dir(), os.path.join(os.environ['LOCALAPPDATA'], 'Programs', 'Test App'))


class CommandLineTests(InstallerCase):
    def test_argument_parsing(self):
        p = self.mod.parse_args
        self.assertEqual(p([])['silent'], False)
        for flag in ('/S', '/s', '/SILENT', '--silent', '/VERYSILENT'):
            self.assertTrue(p([flag])['silent'], flag)
        self.assertEqual(p(['/D=C:\\Apps\\Test App'])['dir'], 'C:\\Apps\\Test App')
        self.assertEqual(p(['--dir="C:\\Apps x"'])['dir'], 'C:\\Apps x')
        self.assertEqual(p(['/S', '/D=C:\\My Apps\\Test App', '--no-desktop'])['dir'], 'C:\\My Apps\\Test App')   # unquoted, spaces
        self.assertEqual(p(['/D=C:\\My', 'Apps\\Test'])['dir'], 'C:\\My Apps\\Test')
        self.assertEqual(p(['/D=C:\\NoSpaces', '/S'])['dir'], 'C:\\NoSpaces')                  # stops at the next switch
        o = p(['/S', '--no-desktop', '--no-startmenu', '--launch', '--selftest-out=C:\\t.json'])
        self.assertEqual((o['desktop'], o['startmenu'], o['launch'], o['selftest']), (False, False, True, 'C:\\t.json'))

    def test_silent_install_exit_codes(self):
        old = sys.argv
        try:
            sys.argv = ['setup.exe', '/S', f'/D={self.target}', '--no-desktop']
            self.assertEqual(self.mod.main(), 0)
            self.assertTrue(os.path.isfile(os.path.join(self.target, 'Test_App.exe')))
            os.remove(self.mod.PAYLOAD)
            with open(self.mod.PAYLOAD, 'wb') as fh:
                fh.write(b'short')
            sys.argv = ['setup.exe', '/S', f'/D={self.target}2']
            self.assertEqual(self.mod.main(), 1)
        finally:
            sys.argv = old

    def test_selftest_reports_payload_health(self):
        out = os.path.join(self.work, 'st.json')
        old = sys.argv
        try:
            sys.argv = ['setup.exe', f'--selftest-out={out}']
            self.assertEqual(self.mod.main(), 0)
            with open(out, encoding='utf-8') as fh:
                report = json.load(fh)
            self.assertTrue(report['ok'])
            self.assertEqual(report['version'], '2.5.1')
            with open(self.mod.PAYLOAD, 'r+b') as fh:
                fh.write(b'Z')
            self.assertEqual(self.mod.main(), 1)
        finally:
            sys.argv = old


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix='h2e-uninst-')
        self.key = 'H2E-test-' + uuid.uuid4().hex[:10]
        self.addCleanup(reg_delete, self.key)
        config = {'title': 'Test App', 'mode': 'static', 'app_id': 'H2E-' + self.key, 'build_id': 'b',
                  'installer': True, 'app_key': self.key}
        source = write(self.work, 'launcher.py', render_launcher(config))
        self.mod = load(source, 'launcher_uninstall_' + self.key.replace('-', '_'))
        self.install_dir = os.path.join(self.work, 'Programs', 'Test App')
        write(self.install_dir, 'Test_App.exe', b'exe')
        write(self.install_dir, 'extra.dat', b'x')
        self.desktop = os.path.join(self.work, 'Desktop')
        self.menu = os.path.join(self.work, 'Menu')
        for folder in (self.desktop, self.menu):
            write(folder, 'Test App.lnk', b'lnk')
        self.mod.desktop_dir = lambda: self.desktop
        self.mod.start_menu_dir = lambda: self.menu
        os.environ['TEMP_BACKUP_FOR_TEST'] = os.environ.get('TEMP', '')
        self.spawned = []
        self.spawn = lambda cmd, **kw: self.spawned.append((cmd, kw))
        self.register(self.install_dir)

    def register(self, location):
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_ROOT + '\\' + self.key, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, 'InstallLocation', 0, winreg.REG_SZ, location)
            winreg.SetValueEx(key, 'DisplayName', 0, winreg.REG_SZ, 'Test App')

    def test_quiet_uninstall_removes_shortcuts_and_registry_and_schedules_the_folder(self):
        code = self.mod.uninstall(quiet=True, install_dir=self.install_dir, spawn=self.spawn)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.desktop, 'Test App.lnk')))
        self.assertFalse(os.path.exists(os.path.join(self.menu, 'Test App.lnk')))
        self.assertIsNone(reg_read(self.key))
        self.assertTrue(os.path.isdir(self.install_dir))                      # deleted later, after this process exits
        (cmd, kw), = self.spawned
        self.assertEqual(cmd[:2], ['cmd', '/c'])
        with open(cmd[2], encoding='utf-8') as fh:
            script = fh.read()
        self.assertIn(self.install_dir, script)
        self.assertEqual(script.count('rmdir'), 1)                            # quiet keeps the user's data
        os.remove(cmd[2])

    def test_generated_script_really_deletes_the_folder_and_itself(self):
        script = os.path.join(self.work, 'del.cmd')
        locked = os.path.join(self.install_dir, 'sub', 'deep')
        write(locked, 'file.txt', b'x')
        self.mod._delete_script([self.install_dir], script)
        subprocess.run(['cmd', '/c', script], capture_output=True, timeout=60)
        self.assertFalse(os.path.exists(self.install_dir))
        self.assertFalse(os.path.exists(script))

    def test_refuses_when_this_is_not_the_registered_install(self):
        other = os.path.join(self.work, 'Downloads', 'Test App')               # e.g. a copy somebody ran from elsewhere
        write(other, 'Test_App.exe', b'exe')
        self.assertEqual(self.mod.uninstall(quiet=True, install_dir=other, spawn=self.spawn), 1)
        self.assertEqual(self.spawned, [])
        self.assertTrue(os.path.isdir(other))
        self.assertTrue(os.path.isfile(os.path.join(self.desktop, 'Test App.lnk')))     # nothing was touched
        self.assertIsNotNone(reg_read(self.key))

    def test_refuses_when_nothing_is_registered(self):
        reg_delete(self.key)
        self.assertEqual(self.mod.uninstall(quiet=True, install_dir=self.install_dir, spawn=self.spawn), 1)
        self.assertEqual(self.spawned, [])

    def test_refuses_a_drive_root_even_if_registered(self):
        root = os.path.splitdrive(self.work)[0] + '\\'
        reg_delete(self.key)
        self.register(root)
        self.assertEqual(self.mod.uninstall(quiet=True, install_dir=root, spawn=self.spawn), 1)
        self.assertEqual(self.spawned, [])

    def test_answering_no_changes_nothing(self):
        asked = []
        code = self.mod.uninstall(install_dir=self.install_dir, ask=lambda t, d=False: asked.append(t) or False, spawn=self.spawn)
        self.assertEqual(code, 0)
        self.assertEqual(len(asked), 1)
        self.assertEqual(self.spawned, [])
        self.assertIsNotNone(reg_read(self.key))
        self.assertTrue(os.path.isfile(os.path.join(self.desktop, 'Test App.lnk')))

    def test_interactive_uninstall_can_also_delete_user_data(self):
        data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'H2E-' + self.key)
        os.makedirs(data_dir, exist_ok=True)
        self.addCleanup(lambda: __import__('shutil').rmtree(data_dir, ignore_errors=True))
        self.assertEqual(self.mod.uninstall(install_dir=self.install_dir, ask=lambda t, d=False: True, spawn=self.spawn), 0)
        (cmd, _kw), = self.spawned
        with open(cmd[2], encoding='utf-8') as fh:
            script = fh.read()
        os.remove(cmd[2])
        self.assertIn(data_dir, script)
        self.assertEqual(script.count('rmdir'), 2)


class BuilderSideTests(unittest.TestCase):
    def test_versions_and_publishers_are_sanitised(self):
        self.assertEqual(installer.normalize_version('1.2.3'), '1.2.3')
        self.assertEqual(installer.normalize_version('10'), '10')
        for bad in ('', None, 'v1.0', '1.0-beta', '1..2', '1.2.3.4.5', '<script>'):
            self.assertEqual(installer.normalize_version(bad), '1.0.0', bad)
        self.assertEqual(installer.clean_publisher('Unknown'), '')
        self.assertEqual(installer.clean_publisher('  Acme\r\nInc  '), 'Acme Inc')
        self.assertEqual(len(installer.clean_publisher('x' * 500)), 80)

    def test_config_travels_as_base64_json_and_the_source_parses(self):
        import ast
        source = installer.render_installer({'name': 'A "quoted" \\ name', 'exe_name': 'A.exe', 'app_key': 'A',
                                             'payload_size': 1, 'payload_sha256': 'x'})
        ast.parse(source)
        self.assertNotIn('__CONFIG_B64__', source)
        self.assertNotIn('__WINSHELL__', source)
        encoded = [l for l in source.splitlines() if l.startswith('CONFIG = ')][0].split('"')[1]
        self.assertEqual(json.loads(base64.b64decode(encoded))['name'], 'A "quoted" \\ name')

    def test_known_folders_resolve(self):
        self.assertTrue(os.path.isabs(winshell.desktop_dir()))
        self.assertTrue(os.path.isabs(winshell.start_menu_dir()))
        self.assertTrue(winshell.start_menu_dir().lower().endswith('programs'))


if __name__ == '__main__':
    unittest.main()


class ScopeArgsTests(unittest.TestCase):
    def test_allusers_switch(self):
        import importlib.util
        from h2e import installer
        ns = {'__file__': 'setup.py'}
        src = installer.render_installer({'name': 'T', 'exe_name': 'T.exe', 'app_key': 'T', 'payload_size': 1, 'payload_sha256': 'x'})
        exec(compile(src.split("\ndef main():")[0], 'setup', 'exec'), ns)
        self.assertEqual(ns['parse_args'](['/S', '--allusers'])['scope'], 'machine')
        self.assertEqual(ns['parse_args'](['/S'])['scope'], 'user')
        self.assertTrue(ns['default_dir']('machine').lower().endswith(chr(92) + 't'))
        self.assertIn('Programs', ns['default_dir']('user'))
