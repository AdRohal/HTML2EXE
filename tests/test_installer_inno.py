import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from h2e import installer, winshell  # noqa: E402


def write(base, rel, data):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(data)
    return path


class InnoScriptTests(unittest.TestCase):
    def script(self, **kw):
        args = dict(display_name='My App', exe_name='My_App', app_exe=r'C:\build\My_App.exe', version='1.2.3',
                    publisher='Acme', icon_path=None, output_dir=r'C:\out', setup_name='My_App-Setup',
                    app_key='My_App', data_folder='H2E-My_App')
        args.update(kw)
        return installer.render_iss(**args)

    def test_per_user_install_with_the_expected_pieces(self):
        text = self.script()
        for needle in ('AppName=My App', 'AppVersion=1.2.3', 'AppPublisher=Acme', 'PrivilegesRequired=lowest',
                       'DefaultDirName={autopf}\\My App', 'OutputBaseFilename=My_App-Setup', 'OutputDir=C:\\out',
                       'Source: "C:\\build\\My_App.exe"; DestDir: "{app}"', '{autoprograms}\\My App',
                       'Tasks: desktopicon', 'postinstall skipifsilent shellexec', 'UninstallDisplayIcon={app}\\My_App.exe',
                       "ExpandConstant('{localappdata}\\H2E-My_App')"):
            self.assertIn(needle, text, needle)
        self.assertNotIn('PrivilegesRequiredOverridesAllowed', text)           # never asks for administrator rights

    def test_publisher_and_icon_are_optional_and_icon_must_be_an_existing_ico(self):
        self.assertNotIn('AppPublisher', self.script(publisher=''))
        self.assertNotIn('SetupIconFile', self.script(icon_path=r'C:\definitely\not\here.ico'))
        d = tempfile.mkdtemp(prefix='h2e-iss-')
        ico = write(d, 'a.ico', b'ico')
        png = write(d, 'a.png', b'png')
        self.assertIn(f'SetupIconFile={ico}', self.script(icon_path=ico))
        self.assertNotIn('SetupIconFile', self.script(icon_path=png))

    def test_awkward_names_cannot_break_the_script(self):
        text = self.script(display_name='Bob\'s {Cool} "App"', publisher='A "B" {C}')
        self.assertIn('AppName=Bob\'s (Cool) ""App""', text)
        self.assertNotIn('{Cool}', text)
        self.assertIn("MsgBox('Also delete the saved data and settings of Bob''s (Cool) \"\"App\"\"?'", text)

    def test_app_id_is_stable_per_app_and_different_between_apps(self):
        self.assertEqual(installer.app_guid('A'), installer.app_guid('A'))
        self.assertNotEqual(installer.app_guid('A'), installer.app_guid('B'))
        self.assertRegex(installer.app_guid('A'), r'^\{\{[0-9A-F]{8}(-[0-9A-F]{4}){3}-[0-9A-F]{12}\}$')

    def test_engine_resolution(self):
        with mock.patch.object(installer, 'find_inno', return_value=r'C:\x\ISCC.exe'):
            self.assertEqual(installer.resolve_engine('auto'), 'inno')
            self.assertEqual(installer.resolve_engine('inno'), 'inno')
            self.assertEqual(installer.resolve_engine('builtin'), 'builtin')
        with mock.patch.object(installer, 'find_inno', return_value=None):
            self.assertEqual(installer.resolve_engine('auto'), 'builtin')
            with self.assertRaises(RuntimeError) as ctx:
                installer.resolve_engine('inno')
            self.assertIn('jrsoftware.org', str(ctx.exception))

    @unittest.skipUnless(installer.find_inno(), 'Inno Setup is not installed')
    def test_the_generated_script_really_compiles_with_inno(self):
        """Compile a real installer around a dummy file and check the output exists and carries our metadata."""
        d = tempfile.mkdtemp(prefix='h2e-iss-')
        app = write(d, 'My_App.exe', b'FAKE-APP' * 1000)
        out = os.path.join(d, 'out')
        os.makedirs(out)
        script = os.path.join(d, 'setup.iss')
        with open(script, 'w', encoding='utf-8-sig') as fh:
            fh.write(installer.render_iss('My App', 'My_App', app, '1.2.3', 'Acme', None, out, 'My_App-Setup', 'My_App', 'H2E-My_App'))
        result = subprocess.run([installer.find_inno(), '/Q', script], capture_output=True, text=True, timeout=240)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        setup = os.path.join(out, 'My_App-Setup.exe')
        self.assertTrue(os.path.isfile(setup))
        company = subprocess.run(
            ['powershell', '-NoProfile', '-Command', '(Get-Item $env:F).VersionInfo | ForEach-Object { "$($_.CompanyName)|$($_.ProductName)|$($_.FileVersion)" }'],
            env=dict(os.environ, F=setup), capture_output=True, text=True).stdout.strip()
        parts = [x.strip() for x in company.split('|')]
        self.assertEqual(parts[:2], ['Acme', 'My App'], company)
        self.assertTrue(parts[2].startswith('1.2.3'), company)


class NativeShortcutTests(unittest.TestCase):
    def test_shortcut_without_powershell_has_target_workdir_description_and_icon(self):
        d = tempfile.mkdtemp(prefix='h2e-lnk-')
        target = write(d, 'Program Files Like/App.exe', b'x')
        lnk = os.path.join(d, 'Links', 'My App.lnk')
        self.assertTrue(winshell.create_shortcut(lnk, target, os.path.dirname(target), 'Hello there', target))
        info = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             '$l = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); '
             '"$($l.TargetPath)|$($l.WorkingDirectory)|$($l.Description)|$($l.IconLocation)"'],
            env=dict(os.environ, LNK=lnk), capture_output=True, text=True).stdout.strip().split('|')
        self.assertTrue(os.path.samefile(info[0], target))
        self.assertTrue(os.path.samefile(info[1], os.path.dirname(target)))
        self.assertEqual(info[2], 'Hello there')
        self.assertTrue(info[3].endswith(',0'))

    def test_failure_is_reported_not_raised(self):
        self.assertFalse(winshell.create_shortcut('Z:\\no\\such\\drive\\x.lnk', 'C:\\a.exe'))


if __name__ == '__main__':
    unittest.main()
