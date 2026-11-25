"""Builds a real Windows installer (``<App>-Setup.exe``) around a finished app .exe.

Two engines:

* ``inno`` - when Inno Setup 6 is installed (``ISCC.exe``), the installer is compiled by it. Preferred: Inno
  installers are the Windows standard, look native, and are rarely flagged by antivirus.
* ``builtin`` - always available, no external tool: a small generated program packed with PyInstaller that carries
  the app .exe as its payload. Unsigned PyInstaller programs are sometimes flagged by antivirus *heuristics*
  (false positives), which is why Inno is preferred when present.

Both: per-user install, shortcuts, an Apps & features entry, silent mode, and in-place updates.

What the installer does
-----------------------
* Per-user install (no administrator rights): default folder ``%LOCALAPPDATA%\\Programs\\<App>``.
* Wizard (folder, desktop shortcut, Start menu shortcut, launch when done) or silent: ``Setup.exe /S``
  (``/D=<folder>``, ``--no-desktop``, ``--no-startmenu``, ``--launch``).
* Verifies the payload's SHA-256 while copying; a damaged installer refuses to install and leaves nothing behind.
* Registers the app in *Apps & features* (HKCU ... Uninstall). The uninstall command is the installed app itself
  (``App.exe --uninstall``), handled by the launcher, so there is no second copy of the payload on disk.
* Updating over an existing install keeps the user's data (it lives in ``%LOCALAPPDATA%\\H2E-<App>``, not in
  the install folder).
"""
import base64
import hashlib
import json
import os
import re
import subprocess

from . import winshell

INSTALLER_SOURCE = r'''
import base64
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback

CONFIG = json.loads(base64.b64decode("__CONFIG_B64__").decode("utf-8"))
NAME = CONFIG["name"]
EXE_NAME = CONFIG["exe_name"]
VERSION = CONFIG.get("version") or "1.0.0"
PUBLISHER = CONFIG.get("publisher") or ""
APP_KEY = CONFIG["app_key"]
UNINSTALL_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + APP_KEY
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BASE = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.join(BASE, "payload", EXE_NAME)
LOG_PATH = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), APP_KEY + "-setup.log")

__WINSHELL__


def log(message):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%H:%M:%S ") + str(message) + "\n")
    except OSError:
        pass


class InstallError(Exception):
    """A problem with a message that can be shown to the user."""


def default_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", NAME)


def installed_dir():
    """Where this app is installed now (from Apps & features), or None."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return winreg.QueryValueEx(key, "InstallLocation")[0]
    except OSError:
        return None


def payload_ok():
    """The payload is present, complete and unmodified."""
    try:
        if os.path.getsize(PAYLOAD) != CONFIG["payload_size"]:
            return False
        digest = hashlib.sha256()
        with open(PAYLOAD, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest() == CONFIG["payload_sha256"]
    except OSError:
        return False


def copy_payload(dst, progress, cancelled):
    """Copy the payload next to its final name, verify its hash, then move it into place."""
    part = dst + ".part"
    total = max(os.path.getsize(PAYLOAD), 1)
    done = 0
    digest = hashlib.sha256()
    try:
        with open(PAYLOAD, "rb") as src, open(part, "wb") as out:
            while True:
                if cancelled():
                    raise InstallError("Setup was cancelled.")
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                progress(done / total)
        if digest.hexdigest() != CONFIG["payload_sha256"]:
            raise InstallError("This installer is damaged (its checksum does not match). Please download it again.")
        os.replace(part, dst)
    except PermissionError:
        raise InstallError("%s is running. Close it and run Setup again." % NAME)
    finally:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass


def make_shortcuts(links, target, workdir):
    """Create .lnk files with the Windows shell API. A missing shortcut never fails the install."""
    for link in links:
        if not create_shortcut(link, target, workdir, NAME, target):
            log("could not create the shortcut " + link)


def register(dst, install_dir):
    """Add the app to Apps & features (current user)."""
    import winreg
    size_kb = max(os.path.getsize(dst) // 1024, 1)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_WRITE) as key:
        def put(name, value, kind=winreg.REG_SZ):
            winreg.SetValueEx(key, name, 0, kind, value)
        put("DisplayName", NAME)
        put("DisplayVersion", VERSION)
        if PUBLISHER:
            put("Publisher", PUBLISHER)
        put("InstallLocation", install_dir)
        put("DisplayIcon", dst)
        put("UninstallString", '"%s" --uninstall' % dst)
        put("QuietUninstallString", '"%s" --uninstall --quiet' % dst)
        put("InstallDate", time.strftime("%Y%m%d"))
        put("EstimatedSize", size_kb, winreg.REG_DWORD)
        put("NoModify", 1, winreg.REG_DWORD)
        put("NoRepair", 1, winreg.REG_DWORD)


def install(opts, progress=None, cancelled=lambda: False):
    """Install the app. ``opts``: dir, desktop, startmenu. Returns the installed .exe path."""
    progress = progress or (lambda fraction, text: None)
    target = os.path.abspath(opts.get("dir") or default_dir())
    if os.path.dirname(target) == target:
        raise InstallError("Choose a folder for the app, not a whole drive.")
    log("installing %s %s to %s" % (NAME, VERSION, target))
    progress(0.0, "Preparing...")
    try:
        os.makedirs(target, exist_ok=True)
    except OSError as exc:
        raise InstallError("Setup cannot create %s (%s). Pick another folder." % (target, exc.strerror or exc))
    dst = os.path.join(target, EXE_NAME)
    copy_payload(dst, lambda f: progress(0.02 + 0.88 * f, "Copying files..."), cancelled)
    links = []
    if opts.get("startmenu", True):
        links.append(os.path.join(start_menu_dir(), NAME + ".lnk"))
    if opts.get("desktop", True):
        links.append(os.path.join(desktop_dir(), NAME + ".lnk"))
    progress(0.92, "Creating shortcuts...")
    make_shortcuts(links, dst, target)
    progress(0.97, "Registering the app...")
    register(dst, target)
    progress(1.0, "Done")
    log("installed: " + dst)
    return dst


def parse_args(argv):
    o = {"silent": False, "dir": None, "desktop": True, "startmenu": True, "launch": False, "selftest": None}
    argv = list(argv)
    i = 0
    while i < len(argv):
        arg = argv[i]
        low = arg.lower()
        i += 1
        if low in ("/s", "/silent", "/verysilent", "--silent", "-s"):
            o["silent"] = True
        elif low.startswith("/d=") or low.startswith("--dir="):
            value = arg.split("=", 1)[1]
            # An unquoted path with spaces (/D=C:\My Apps\Tool, the usual installer convention) arrives as several
            # words: join them until the next switch.
            while i < len(argv) and not argv[i].startswith(("/", "-")):
                value += " " + argv[i]
                i += 1
            o["dir"] = value.strip('"')
        elif low == "--no-desktop":
            o["desktop"] = False
        elif low == "--no-startmenu":
            o["startmenu"] = False
        elif low == "--launch":
            o["launch"] = True
        elif low.startswith("--selftest-out="):
            o["selftest"] = arg.split("=", 1)[1].strip('"')
    return o


def launch(path):
    try:
        subprocess.Popen([path], cwd=os.path.dirname(path), creationflags=0x00000008 | NOWIN)
    except OSError as exc:
        log("could not start the app: %s" % exc)


def run_silent(o):
    try:
        dst = install({"dir": o["dir"], "desktop": o["desktop"], "startmenu": o["startmenu"]})
    except InstallError as exc:
        log("FAILED: %s" % exc)
        return 1
    except Exception:
        log("FAILED: " + traceback.format_exc())
        return 1
    if o["launch"]:
        launch(dst)
    return 0


def run_gui(o):
    import ctypes
    import tkinter as tk
    from tkinter import filedialog, ttk
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    root.title("%s Setup" % NAME)
    root.resizable(False, False)
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    root.option_add("*Font", ("Segoe UI", 10))
    existing = installed_dir()
    updating = bool(existing)
    width, height = 540, 420
    root.geometry("%dx%d+%d+%d" % (width, height, (root.winfo_screenwidth() - width) // 2,
                                   (root.winfo_screenheight() - height) // 3))

    header = tk.Frame(root, bg="#1e293b", height=84)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text=("Update %s" if updating else "Install %s") % NAME, bg="#1e293b", fg="#ffffff",
             font=("Segoe UI Semibold", 16)).pack(anchor="w", padx=24, pady=(16, 0))
    sub = "Version %s" % VERSION + ("   -   %s" % PUBLISHER if PUBLISHER else "")
    tk.Label(header, text=sub, bg="#1e293b", fg="#cbd5e1", font=("Segoe UI", 10)).pack(anchor="w", padx=24)

    body = ttk.Frame(root, padding=(24, 18, 24, 18))
    body.pack(fill="both", expand=True)
    pages = {}
    for key in ("options", "progress", "done"):
        pages[key] = ttk.Frame(body)

    def show(key):
        for page in pages.values():
            page.pack_forget()
        pages[key].pack(fill="both", expand=True)

    # ------------------------------------------------------------------ options page
    page = pages["options"]
    ttk.Label(page, text="Install location").pack(anchor="w")
    row = ttk.Frame(page)
    row.pack(fill="x", pady=(4, 12))
    dir_var = tk.StringVar(value=o["dir"] or existing or default_dir())
    ttk.Entry(row, textvariable=dir_var).pack(side="left", fill="x", expand=True)

    def browse():
        chosen = filedialog.askdirectory(title="Choose the install folder", initialdir=dir_var.get() or None)
        if chosen:
            dir_var.set(os.path.normpath(os.path.join(chosen, NAME)) if not chosen.lower().endswith(NAME.lower()) else os.path.normpath(chosen))
    ttk.Button(row, text="Browse...", command=browse).pack(side="left", padx=(8, 0))
    desktop_var = tk.BooleanVar(value=o["desktop"])
    menu_var = tk.BooleanVar(value=o["startmenu"])
    ttk.Checkbutton(page, text="Create a desktop shortcut", variable=desktop_var).pack(anchor="w", pady=2)
    ttk.Checkbutton(page, text="Create a Start menu shortcut", variable=menu_var).pack(anchor="w", pady=2)
    size_mb = max(CONFIG["payload_size"] // (1024 * 1024), 1)
    note = "Needs about %d MB. Installs for your Windows account only; no administrator rights are needed." % size_mb
    if updating:
        note = "%s is already installed. Setup will update it and keep your data. " % NAME + note
    ttk.Label(page, text=note, wraplength=480, foreground="#475569").pack(anchor="w", pady=(14, 0))
    buttons = ttk.Frame(page)
    buttons.pack(side="bottom", fill="x")
    ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right")
    install_button = ttk.Button(buttons, text="Update" if updating else "Install")
    install_button.pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------ progress page
    page = pages["progress"]
    status = tk.StringVar(value="Preparing...")
    ttk.Label(page, textvariable=status).pack(anchor="w", pady=(24, 8))
    bar = ttk.Progressbar(page, maximum=100, length=480)
    bar.pack(fill="x")
    cancel_event = threading.Event()
    ttk.Button(page, text="Cancel", command=cancel_event.set).pack(side="bottom", anchor="e")

    # ------------------------------------------------------------------ done page
    page = pages["done"]
    result_title = tk.StringVar()
    result_text = tk.StringVar()
    ttk.Label(page, textvariable=result_title, font=("Segoe UI Semibold", 13)).pack(anchor="w", pady=(18, 6))
    ttk.Label(page, textvariable=result_text, wraplength=480, justify="left").pack(anchor="w")
    launch_var = tk.BooleanVar(value=True)
    launch_check = ttk.Checkbutton(page, text="Start %s now" % NAME, variable=launch_var)
    finish = ttk.Button(page, text="Finish")
    finish.pack(side="bottom", anchor="e")
    installed_path = {"path": None}

    def on_finish():
        if installed_path["path"] and launch_var.get():
            launch(installed_path["path"])
        root.destroy()
    finish.configure(command=on_finish)

    # ------------------------------------------------------------------ run the install in a thread
    messages = queue.Queue()

    def work(opts):
        try:
            dst = install(opts, lambda f, t: messages.put(("p", f, t)), cancel_event.is_set)
            messages.put(("ok", dst))
        except InstallError as exc:
            messages.put(("err", str(exc)))
        except Exception:
            log(traceback.format_exc())
            messages.put(("err", "Something unexpected went wrong. Details: %s" % LOG_PATH))

    def poll():
        try:
            while True:
                message = messages.get_nowait()
                if message[0] == "p":
                    bar["value"] = message[1] * 100
                    status.set(message[2])
                elif message[0] == "ok":
                    installed_path["path"] = message[1]
                    result_title.set("%s is installed" % NAME)
                    result_text.set("You can start it from the Start menu%s." % (" or the desktop" if desktop_var.get() else ""))
                    launch_check.pack(anchor="w", pady=(14, 0))
                    show("done")
                    return
                else:
                    result_title.set("Setup could not finish")
                    result_text.set(message[1])
                    launch_check.pack_forget()
                    show("done")
                    return
        except queue.Empty:
            pass
        root.after(60, poll)

    def start():
        if not payload_ok():
            result_title.set("Setup could not finish")
            result_text.set("This installer is damaged (its checksum does not match). Please download it again.")
            launch_check.pack_forget()
            show("done")
            return
        show("progress")
        opts = {"dir": dir_var.get().strip(), "desktop": desktop_var.get(), "startmenu": menu_var.get()}
        threading.Thread(target=work, args=(opts,), daemon=True).start()
        poll()
    install_button.configure(command=start)

    root.protocol("WM_DELETE_WINDOW", lambda: (cancel_event.set(), root.destroy()))
    show("options")
    root.mainloop()
    return 0


def main():
    o = parse_args(sys.argv[1:])
    if o["selftest"]:
        ok = payload_ok()
        with open(o["selftest"], "w", encoding="utf-8") as fh:
            json.dump({"ok": ok, "name": NAME, "version": VERSION, "app_key": APP_KEY,
                       "default_dir": default_dir()}, fh)
        return 0 if ok else 1
    if o["silent"]:
        return run_silent(o)
    return run_gui(o)


if __name__ == "__main__":
    sys.exit(main())
'''


def render_installer(config):
    """Source of the installer program with its configuration embedded."""
    payload = base64.b64encode(json.dumps(config).encode('utf-8')).decode('ascii')
    return INSTALLER_SOURCE.replace('__CONFIG_B64__', payload).replace('__WINSHELL__', winshell.SNIPPET)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_version(value):
    """A dotted numeric version (``1.2.3``); anything else becomes ``1.0.0``."""
    text = str(value or '').strip()
    return text if re.match(r'^\d+(\.\d+){0,3}$', text) else '1.0.0'


def clean_publisher(value):
    text = re.sub(r'[\r\n\t]+', ' ', str(value or '')).strip()[:80]
    return '' if text.lower() in ('unknown', 'none', 'n/a') else text


# ------------------------------------------------------------------------------------------------ Inno Setup engine
def find_inno():
    """Path of ISCC.exe (Inno Setup 6 compiler) or None."""
    import shutil
    candidates = [shutil.which('iscc')]
    for root in (os.environ.get('LOCALAPPDATA'), os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles')):
        if root:
            candidates.append(os.path.join(root, 'Programs' if root == os.environ.get('LOCALAPPDATA') else '',
                                           'Inno Setup 6', 'ISCC.exe'))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def resolve_engine(requested='auto'):
    """``'inno'`` or ``'builtin'``. Raises RuntimeError when Inno is demanded but missing."""
    inno = find_inno()
    if requested == 'inno' and not inno:
        raise RuntimeError('Inno Setup 6 was requested but ISCC.exe was not found. Install it from '
                           'https://jrsoftware.org/isdl.php or choose the built-in installer.')
    if requested == 'builtin':
        return 'builtin'
    return 'inno' if inno else 'builtin'


def _iss(value):
    """Escape text for an Inno Setup script string/constant."""
    return str(value).replace('"', '""').replace('{', '{{')


def app_guid(app_key):
    """A stable id per app so a newer Setup updates the installed one instead of installing a second copy."""
    import uuid
    return '{{' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'html2exe:' + app_key)).upper() + '}'


def render_iss(display_name, exe_name, app_exe, version, publisher, icon_path, output_dir, setup_name, app_key,
               data_folder):
    """The Inno Setup script for a per-user installer around ``app_exe``."""
    display_name = re.sub(r'[{}]', lambda m: '(' if m.group() == '{' else ')', display_name)   # braces are Inno syntax
    exe_file = exe_name + '.exe'
    lines = [
        '; Generated by HTML2EXE',
        '[Setup]',
        f'AppId={app_guid(app_key)}',
        f'AppName={_iss(display_name)}',
        f'AppVersion={version}',
        f'AppVerName={_iss(display_name)} {version}',
    ]
    if publisher:
        lines.append(f'AppPublisher={_iss(publisher)}')
    lines += [
        f'DefaultDirName={{autopf}}\\{_iss(display_name)}',
        f'DefaultGroupName={_iss(display_name)}',
        'DisableProgramGroupPage=yes',
        'PrivilegesRequired=lowest',
        'UsePreviousAppDir=yes',
        f'OutputDir={output_dir}',
        f'OutputBaseFilename={setup_name}',
        'Compression=lzma2',
        'SolidCompression=yes',
        'WizardStyle=modern',
        'CloseApplications=yes',
        'RestartApplications=no',
        'ArchitecturesInstallIn64BitMode=x64compatible',
        f'UninstallDisplayName={_iss(display_name)}',
        f'UninstallDisplayIcon={{app}}\\{exe_file}',
        f'VersionInfoVersion={version}',
        f'VersionInfoProductName={_iss(display_name)}',
    ]
    if publisher:
        lines.append(f'VersionInfoCompany={_iss(publisher)}')
    if icon_path and icon_path.lower().endswith('.ico') and os.path.isfile(icon_path):
        lines.append(f'SetupIconFile={icon_path}')
    lines += [
        '',
        '[Tasks]',
        'Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"',
        '',
        '[Files]',
        f'Source: "{app_exe}"; DestDir: "{{app}}"; Flags: ignoreversion',
        '',
        '[Icons]',
        f'Name: "{{autoprograms}}\\{_iss(display_name)}"; Filename: "{{app}}\\{exe_file}"',
        f'Name: "{{autodesktop}}\\{_iss(display_name)}"; Filename: "{{app}}\\{exe_file}"; Tasks: desktopicon',
        '',
        '[Run]',
        f'Filename: "{{app}}\\{exe_file}"; Description: "Start {_iss(display_name)}"; Flags: nowait postinstall skipifsilent',
        '',
        '[Code]',
        '// The app keeps its settings and data outside the install folder; ask before deleting them.',
        'procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);',
        'var Dir: String;',
        'begin',
        '  if CurUninstallStep = usPostUninstall then',
        '  begin',
        f"    Dir := ExpandConstant('{{localappdata}}\\{_iss(data_folder)}');",
        '    if DirExists(Dir) and (not UninstallSilent) then',
        f"      if MsgBox('Also delete the saved data and settings of {_iss(display_name).replace(chr(39), chr(39) * 2)}?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then",
        '        DelTree(Dir, True, True, True);',
        '  end;',
        'end;',
        '',
    ]
    return '\r\n'.join(lines)


def build_inno_installer(job, build_dir, app_exe, exe_name, display_name, version, publisher, icon_path, output_dir):
    iscc = find_inno()
    work = os.path.join(build_dir, 'installer')
    os.makedirs(work, exist_ok=True)
    setup_name = exe_name + '-Setup'
    script = os.path.join(work, 'setup.iss')
    with open(script, 'w', encoding='utf-8-sig') as fh:                    # BOM: Inno reads UTF-8 only with one
        fh.write(render_iss(display_name, exe_name, app_exe, normalize_version(version), clean_publisher(publisher),
                            icon_path, output_dir, setup_name, exe_name, 'H2E-' + exe_name))
    job.log('Compiling the installer with Inno Setup...')
    code = job.run_cmd([iscc, '/Q', script], cwd=work)
    setup_path = os.path.join(output_dir, setup_name + '.exe')
    if code != 0 or not os.path.isfile(setup_path):
        raise RuntimeError('Inno Setup could not compile the installer. See the log for details.')
    return setup_path


def build_installer(job, build_dir, app_exe, exe_name, display_name, version, publisher, icon_path, output_dir,
                    engine='builtin'):
    """Package ``app_exe`` into ``<exe_name>-Setup.exe`` in ``output_dir``. Returns its path."""
    if engine == 'inno':
        return build_inno_installer(job, build_dir, app_exe, exe_name, display_name, version, publisher, icon_path,
                                    output_dir)
    from .exe_build import python_for_pyinstaller      # lazy: exe_build imports this module
    work = os.path.join(build_dir, 'installer')
    os.makedirs(work, exist_ok=True)
    config = {
        'name': display_name,
        'exe_name': exe_name + '.exe',
        'app_key': exe_name,
        'version': normalize_version(version),
        'publisher': clean_publisher(publisher),
        'payload_size': os.path.getsize(app_exe),
        'payload_sha256': file_sha256(app_exe),
    }
    source = os.path.join(work, 'setup_main.py')
    with open(source, 'w', encoding='utf-8') as fh:
        fh.write(render_installer(config))
    setup_name = exe_name + '-Setup'
    cmd = python_for_pyinstaller() + [
        '-m', 'PyInstaller', '--onefile', '--windowed', '--noupx', '-y',
        f'--name={setup_name}', f'--distpath={output_dir}', f'--workpath={os.path.join(work, "work")}',
        f'--specpath={work}', f'--add-data={app_exe}{os.pathsep}payload',
    ]
    if icon_path and os.path.exists(icon_path):
        cmd.append(f'--icon={os.path.abspath(icon_path)}')
    cmd.append(source)
    job.log('Packaging the installer with PyInstaller...')
    code = job.run_cmd(cmd, cwd=work)
    setup_path = os.path.join(output_dir, setup_name + '.exe')
    if code != 0 or not os.path.isfile(setup_path):
        raise RuntimeError('PyInstaller could not build the installer. See the log for details.')
    return setup_path


def self_test(setup_path, build_dir, job, timeout=120):
    """Run the installer's own check: the payload inside it is present, complete and unmodified."""
    out_file = os.path.join(build_dir, 'installer-selftest.json')
    if os.path.exists(out_file):
        os.remove(out_file)
    job.log('Verifying the installer...')
    try:
        subprocess.run([setup_path, f'--selftest-out={out_file}'], timeout=timeout,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with open(out_file, 'r', encoding='utf-8') as fh:
            report = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        job.log(f'WARNING: installer check could not run ({exc}).')
        return {'ok': False, 'error': str(exc)}
    job.log('Installer verified: its contents are complete.' if report.get('ok')
            else 'WARNING: the installer check failed: its payload is damaged.')
    return {'ok': bool(report.get('ok')), 'defaultDir': report.get('default_dir')}
