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
PAYLOAD_KIND = CONFIG.get("payload_kind", "file")            # "file": one .exe, "dir": a whole program folder
PAYLOAD = os.path.join(BASE, "payload", EXE_NAME) if PAYLOAD_KIND == "file" else os.path.join(BASE, "payload")
UNINSTALL_ARG = CONFIG.get("uninstall_arg", "--uninstall")
BRAND = CONFIG.get("brand") or None              # branded wizard (colors, license, Ko-fi) when present
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


def default_dir(scope="user"):
    if scope == "machine":
        return os.path.join(program_files_dir(), NAME)
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", NAME)


def installed_dir():
    """Where this app is installed now (from Apps & features: this user first, then all users), or None."""
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, UNINSTALL_KEY) as key:
                    return winreg.QueryValueEx(key, "InstallLocation")[0]
            except OSError:
                continue
        return None
    except OSError:
        return None


def manifest():
    """Folder payloads: [relative path, size, sha256] of every file."""
    with open(os.path.join(BASE, "manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _file_ok(path, size, sha):
    try:
        if os.path.getsize(path) != size:
            return False
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest() == sha
    except OSError:
        return False


def payload_ok():
    """The payload is present, complete and unmodified."""
    if PAYLOAD_KIND == "dir":
        try:
            return all(_file_ok(os.path.join(PAYLOAD, rel), size, sha) for rel, size, sha in manifest())
        except (OSError, ValueError):
            return False
    return _file_ok(PAYLOAD, CONFIG["payload_size"], CONFIG["payload_sha256"])


def _copy_verified(src_path, dst, expected_sha, on_bytes, cancelled):
    """Copy next to the final name, verify the hash, then move into place."""
    part = dst + ".part"
    digest = hashlib.sha256()
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src_path, "rb") as src, open(part, "wb") as out:
            while True:
                if cancelled():
                    raise InstallError("Setup was cancelled.")
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                on_bytes(len(chunk))
        if digest.hexdigest() != expected_sha:
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


def copy_payload(target, progress, cancelled):
    """Copy the payload into ``target``. Returns the installed main .exe."""
    total = max(CONFIG["payload_size"], 1)
    done = [0]

    def on_bytes(count):
        done[0] += count
        progress(min(done[0] / total, 1.0))
    if PAYLOAD_KIND == "dir":
        for rel, _size, sha in manifest():
            if os.path.isabs(rel) or ".." in rel.split("/"):
                raise InstallError("This installer is damaged. Please download it again.")
            _copy_verified(os.path.join(PAYLOAD, rel), os.path.join(target, rel), sha, on_bytes, cancelled)
    else:
        _copy_verified(PAYLOAD, os.path.join(target, EXE_NAME), CONFIG["payload_sha256"], on_bytes, cancelled)
    return os.path.join(target, EXE_NAME)


def make_shortcuts(links, target, workdir):
    """Create .lnk files with the Windows shell API. A missing shortcut never fails the install."""
    for link in links:
        if not create_shortcut(link, target, workdir, NAME, target):
            log("could not create the shortcut " + link)


def register(dst, install_dir, scope="user"):
    """Add the app to Apps & features (this user, or every user when installed with administrator rights)."""
    import winreg
    size_kb = max(CONFIG["payload_size"] // 1024, 1)
    hive = winreg.HKEY_LOCAL_MACHINE if scope == "machine" else winreg.HKEY_CURRENT_USER
    brand = CONFIG.get("brand") or {}
    with winreg.CreateKeyEx(hive, UNINSTALL_KEY, 0, winreg.KEY_WRITE) as key:
        def put(name, value, kind=winreg.REG_SZ):
            winreg.SetValueEx(key, name, 0, kind, value)
        put("DisplayName", NAME)
        put("DisplayVersion", VERSION)
        if PUBLISHER:
            put("Publisher", PUBLISHER)
        put("InstallLocation", install_dir)
        put("DisplayIcon", dst)
        put("UninstallString", '"%s" %s' % (dst, UNINSTALL_ARG))
        put("QuietUninstallString", '"%s" %s --quiet' % (dst, UNINSTALL_ARG))
        put("InstallDate", time.strftime("%Y%m%d"))
        if brand.get("email"):
            put("Contact", brand["email"])
        if brand.get("website"):
            put("URLInfoAbout", brand["website"])
        put("EstimatedSize", size_kb, winreg.REG_DWORD)
        put("NoModify", 1, winreg.REG_DWORD)
        put("NoRepair", 1, winreg.REG_DWORD)


def install(opts, progress=None, cancelled=lambda: False):
    """Install the app. ``opts``: dir, desktop, startmenu, scope ("user" or "machine"). Returns the installed .exe path."""
    progress = progress or (lambda fraction, text: None)
    scope = opts.get("scope", "user")
    if scope == "machine" and not is_admin():
        raise InstallError("Installing for all users needs administrator permission.")
    target = os.path.abspath(opts.get("dir") or default_dir(scope))
    if os.path.dirname(target) == target:
        raise InstallError("Choose a folder for the app, not a whole drive.")
    log("installing %s %s to %s" % (NAME, VERSION, target))
    progress(0.0, "Preparing...")
    try:
        os.makedirs(target, exist_ok=True)
    except OSError as exc:
        raise InstallError("Setup cannot create %s (%s). Pick another folder." % (target, exc.strerror or exc))
    dst = copy_payload(target, lambda f: progress(0.02 + 0.88 * f, "Copying files..."), cancelled)
    links = []
    machine = scope == "machine"
    if opts.get("startmenu", True):
        links.append(os.path.join(common_start_menu_dir() if machine else start_menu_dir(), NAME + ".lnk"))
    if opts.get("desktop", True):
        links.append(os.path.join(common_desktop_dir() if machine else desktop_dir(), NAME + ".lnk"))
    progress(0.92, "Creating shortcuts...")
    make_shortcuts(links, dst, target)
    progress(0.97, "Registering the app...")
    register(dst, target, scope)
    progress(1.0, "Done")
    log("installed: " + dst)
    return dst


def parse_args(argv):
    o = {"silent": False, "dir": None, "desktop": True, "startmenu": True, "launch": False, "selftest": None,
         "scope": "user"}
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
        elif low in ("--allusers", "/allusers"):
            o["scope"] = "machine"
        elif low.startswith("--selftest-out="):
            o["selftest"] = arg.split("=", 1)[1].strip('"')
    return o


def launch(path):
    """Start the app the way Explorer does (ShellExecute), so a program that asks for administrator rights shows
    the normal Windows prompt instead of failing with 'CreateProcess failed; code 740'."""
    try:
        os.startfile(path, cwd=os.path.dirname(path))
        return
    except (OSError, TypeError) as exc:
        log("shell start failed (%s), trying a direct start" % exc)
    try:
        subprocess.Popen([path], cwd=os.path.dirname(path), creationflags=0x00000008 | NOWIN)
    except OSError as exc:
        log("could not start the app: %s" % exc)


def run_silent(o):
    try:
        dst = install({"dir": o["dir"], "desktop": o["desktop"], "startmenu": o["startmenu"], "scope": o["scope"]})
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


def run_elevated_install(opts):
    """Run this Setup again with the Windows administrator prompt, silently, for an all-users install.
    Returns (ok, message). Waits for it to finish."""
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]
    args = ["/S", "--allusers", "--dir=" + opts["dir"]]
    if not opts.get("desktop", True):
        args.append("--no-desktop")
    if not opts.get("startmenu", True):
        args.append("--no-startmenu")
    info = SHELLEXECUTEINFO()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40                                   # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = sys.executable
    info.lpParameters = subprocess.list2cmdline(args)
    info.nShow = 0
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        return False, "Administrator permission was not given. Choose \"Only for me\" to install without it."
    ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    code = wintypes.DWORD(1)
    ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(info.hProcess)
    if code.value != 0:
        return False, "The installation for all users did not finish. Details: %s" % LOG_PATH
    return True, os.path.join(opts["dir"], EXE_NAME)


def run_gui_brand(o):
    """The branded wizard: dark navy and violet like the app itself, license page, scope choice, Ko-fi on the end page."""
    import ctypes
    import tkinter as tk
    import webbrowser
    from tkinter import filedialog, ttk
    brand = BRAND
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    BG, SIDE, CARD, EDGE = "#0f172a", "#0d1526", "#1e293b", "#334155"
    TEXT, MUTED, VIOLET, VIOLET_LIGHT, GREEN, RED = "#e2e8f0", "#94a3b8", "#7c3aed", "#a78bfa", "#34d399", "#ff5e5b"
    root = tk.Tk()
    root.title("%s Setup" % NAME)
    root.resizable(False, False)
    root.configure(bg=BG)
    scale = max(root.winfo_fpixels("1i") / 96.0, 1.0)

    def S(value):
        return int(round(value * scale))
    width, height = S(700), S(470)
    root.geometry("%dx%d+%d+%d" % (width, height, (root.winfo_screenwidth() - width) // 2,
                                   (root.winfo_screenheight() - height) // 3))
    logo = None
    if brand.get("logo_b64"):
        try:
            logo = tk.PhotoImage(data=brand["logo_b64"])
            root.iconphoto(True, logo)
            if scale >= 1.75:
                logo = logo.zoom(2)
        except tk.TclError:
            logo = None
    F = "Segoe UI"
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Brand.Horizontal.TProgressbar", troughcolor=CARD, background=VIOLET, bordercolor=CARD,
                    lightcolor=VIOLET, darkcolor=VIOLET, thickness=S(10))
    existing = installed_dir()
    updating = bool(existing)
    admin_now = is_admin()

    def button(parent, text, command, primary=False, color=None, fg=None):
        bgc = color or (VIOLET if primary else CARD)
        b = tk.Button(parent, text=text, command=command, bg=bgc, fg=fg or "#ffffff" if primary or color else TEXT,
                      activebackground=VIOLET_LIGHT if primary else EDGE, activeforeground="#ffffff", relief="flat", bd=0,
                      font=(F, 10, "bold" if primary or color else "normal"), padx=S(18), pady=S(7), cursor="hand2",
                      disabledforeground="#64748b", highlightthickness=0)
        return b

    def label(parent, text, size=10, color=TEXT, bold=False, wrap=0, justify="left", **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", BG), fg=color, font=(F, size, "bold" if bold else "normal"),
                        wraplength=wrap, justify=justify, anchor="w", **kw)

    def check(parent, text, var, command=None):
        return tk.Checkbutton(parent, text=text, variable=var, command=command, bg=BG, fg=TEXT, selectcolor=CARD,
                              activebackground=BG, activeforeground=TEXT, font=(F, 10), anchor="w", highlightthickness=0,
                              bd=0, cursor="hand2")

    # ---------------------------------------------------------------- side panel with the steps
    side = tk.Frame(root, bg=SIDE, width=S(210))
    side.pack(side="left", fill="y")
    side.pack_propagate(False)
    if logo:
        tk.Label(side, image=logo, bg=SIDE).pack(anchor="w", padx=S(22), pady=(S(26), S(8)))
    label(side, NAME, 15, "#ffffff", True, bg=SIDE).pack(anchor="w", padx=S(22))
    label(side, "Version %s" % VERSION, 9, MUTED, bg=SIDE).pack(anchor="w", padx=S(22))
    steps_box = tk.Frame(side, bg=SIDE)
    steps_box.pack(anchor="w", padx=S(22), pady=(S(30), 0), fill="x")
    step_names = ("Welcome", "License", "Options", "Install", "Finish")
    step_labels = []
    for number, text in enumerate(step_names, 1):
        row = tk.Frame(steps_box, bg=SIDE)
        row.pack(fill="x", pady=S(5))
        dot = tk.Label(row, text=str(number), width=2, bg=CARD, fg=MUTED, font=(F, 9, "bold"))
        dot.pack(side="left")
        name = tk.Label(row, text=text, bg=SIDE, fg=MUTED, font=(F, 10), anchor="w")
        name.pack(side="left", padx=(S(10), 0))
        step_labels.append((dot, name))
    foot = tk.Frame(side, bg=SIDE)
    foot.pack(side="bottom", fill="x", padx=S(22), pady=S(18))
    label(foot, "by %s" % (PUBLISHER or "AdRohal"), 9, MUTED, bg=SIDE).pack(anchor="w")
    if brand.get("email"):
        label(foot, brand["email"], 8, "#64748b", bg=SIDE).pack(anchor="w")

    def mark(step):
        for number, (dot, name) in enumerate(step_labels):
            active, done = number == step, number < step
            dot.configure(bg=VIOLET if active else (GREEN if done else CARD), fg="#ffffff" if active or done else MUTED)
            name.configure(fg="#ffffff" if active else (TEXT if done else MUTED), font=(F, 10, "bold" if active else "normal"))

    # ---------------------------------------------------------------- content + buttons
    right = tk.Frame(root, bg=BG)
    right.pack(side="left", fill="both", expand=True)
    bar = tk.Frame(right, bg=BG)
    bar.pack(side="bottom", fill="x", padx=S(28), pady=S(20))
    tk.Frame(right, bg=EDGE, height=1).pack(side="bottom", fill="x")
    content = tk.Frame(right, bg=BG)
    content.pack(side="top", fill="both", expand=True, padx=S(28), pady=(S(26), S(8)))
    wrap = S(420)
    pages = {key: tk.Frame(content, bg=BG) for key in ("welcome", "license", "options", "progress", "done")}
    state = {"page": "welcome", "installed": None}

    cancel_btn = button(bar, "Cancel", lambda: close())
    back_btn = button(bar, "Back", lambda: go_back())
    next_btn = button(bar, "Next", lambda: go_next(), primary=True)
    cancel_btn.pack(side="left")
    next_btn.pack(side="right")
    back_btn.pack(side="right", padx=(0, S(10)))

    # welcome
    page = pages["welcome"]
    label(page, ("Update %s" if updating else "Welcome to %s") % NAME, 20, "#ffffff", True).pack(anchor="w")
    label(page, brand.get("tagline", ""), 11, VIOLET_LIGHT, wrap=wrap).pack(anchor="w", pady=(S(6), S(18)))
    for line in brand.get("points", []):
        row = tk.Frame(page, bg=BG)
        row.pack(anchor="w", fill="x", pady=S(3))
        tk.Label(row, text="✓", bg=BG, fg=GREEN, font=(F, 10, "bold")).pack(side="left")
        label(row, line, 10, TEXT, wrap=wrap - S(24)).pack(side="left", padx=(S(8), 0))
    label(page, ("%s is already installed; Setup will update it and keep your data." % NAME) if updating
          else "Click Next to read the license and choose where to install.", 9, MUTED, wrap=wrap).pack(anchor="w", pady=(S(22), 0))

    # license
    page = pages["license"]
    label(page, "License agreement", 16, "#ffffff", True).pack(anchor="w")
    label(page, "Please read and accept the license to continue.", 10, MUTED).pack(anchor="w", pady=(S(2), S(10)))
    box = tk.Frame(page, bg=EDGE, padx=1, pady=1)
    box.pack(fill="both", expand=True)
    text = tk.Text(box, bg=SIDE, fg=TEXT, relief="flat", wrap="word", font=("Consolas", 9), padx=S(10), pady=S(8),
                   highlightthickness=0, insertbackground=SIDE, height=10)
    scroll = tk.Scrollbar(box, command=text.yview, bg=CARD, troughcolor=SIDE, relief="flat", bd=0)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    text.insert("1.0", brand.get("license", ""))
    text.configure(state="disabled")
    accept_var = tk.BooleanVar(value=False)
    check(page, "I accept the license agreement", accept_var, lambda: refresh()).pack(anchor="w", pady=(S(10), 0))

    # options
    page = pages["options"]
    label(page, "Install options", 16, "#ffffff", True).pack(anchor="w")
    label(page, "Where should %s be installed?" % NAME, 10, MUTED).pack(anchor="w", pady=(S(2), S(8)))
    scope_var = tk.StringVar(value="machine" if admin_now else "user")
    dir_var = tk.StringVar()
    dir_touched = {"v": False}

    def default_for_scope():
        return o["dir"] or (existing if updating and not dir_touched["v"] else default_dir(scope_var.get()))

    def on_scope():
        if not dir_touched["v"]:
            dir_var.set(o["dir"] or default_dir(scope_var.get()))
        refresh()
    for value, title, note in (
            ("user", "Only for me", "No administrator permission needed. Recommended."),
            ("machine", "For all users of this PC", "Running as administrator." if admin_now else "Windows will ask for administrator permission.")):
        row = tk.Frame(page, bg=BG)
        row.pack(anchor="w", fill="x", pady=S(2))
        tk.Radiobutton(row, text=title, variable=scope_var, value=value, command=on_scope, bg=BG, fg=TEXT,
                       selectcolor=CARD, activebackground=BG, activeforeground=TEXT, font=(F, 10, "bold"),
                       highlightthickness=0, bd=0, cursor="hand2").pack(side="left")
        label(row, note, 9, MUTED).pack(side="left", padx=(S(8), 0))
    dir_var.set(default_for_scope())
    entry_row = tk.Frame(page, bg=BG)
    entry_row.pack(fill="x", pady=(S(12), S(10)))
    entry = tk.Entry(entry_row, textvariable=dir_var, bg=SIDE, fg=TEXT, insertbackground=TEXT, relief="flat",
                     font=(F, 10), highlightthickness=1, highlightbackground=EDGE, highlightcolor=VIOLET)
    entry.pack(side="left", fill="x", expand=True, ipady=S(5))
    entry.bind("<Key>", lambda e: dir_touched.__setitem__("v", True))

    def browse():
        chosen = filedialog.askdirectory(title="Choose the install folder", initialdir=dir_var.get() or None)
        if chosen:
            dir_touched["v"] = True
            dir_var.set(os.path.normpath(chosen if chosen.lower().endswith(NAME.lower()) else os.path.join(chosen, NAME)))
    button(entry_row, "Browse...", browse).pack(side="left", padx=(S(8), 0))
    desktop_var = tk.BooleanVar(value=o["desktop"])
    menu_var = tk.BooleanVar(value=o["startmenu"])
    check(page, "Create a desktop shortcut", desktop_var).pack(anchor="w", pady=2)
    check(page, "Create a Start menu shortcut", menu_var).pack(anchor="w", pady=2)
    size_mb = max(CONFIG["payload_size"] // (1024 * 1024), 1)
    label(page, "Needs about %d MB of disk space." % size_mb, 9, MUTED).pack(anchor="w", pady=(S(12), 0))

    # progress
    page = pages["progress"]
    status = tk.StringVar(value="Preparing...")
    label(page, "Installing %s" % NAME, 16, "#ffffff", True).pack(anchor="w")
    label(page, "This takes a moment.", 10, MUTED).pack(anchor="w", pady=(S(2), S(30)))
    tk.Label(page, textvariable=status, bg=BG, fg=TEXT, font=(F, 10), anchor="w").pack(anchor="w", pady=(0, S(8)), fill="x")
    progress_bar = ttk.Progressbar(page, maximum=100, style="Brand.Horizontal.TProgressbar")
    progress_bar.pack(fill="x")

    # done
    page = pages["done"]
    done_icon = tk.Label(page, text="✓", bg=BG, fg=GREEN, font=(F, 26, "bold"))
    done_icon.pack(anchor="w")
    done_title = tk.StringVar()
    done_text = tk.StringVar()
    tk.Label(page, textvariable=done_title, bg=BG, fg="#ffffff", font=(F, 16, "bold"), anchor="w").pack(anchor="w", fill="x")
    tk.Label(page, textvariable=done_text, bg=BG, fg=MUTED, font=(F, 10), wraplength=wrap, justify="left", anchor="w").pack(anchor="w", pady=(S(4), S(14)))
    launch_var = tk.BooleanVar(value=True)
    launch_check = check(page, "Start %s now" % NAME, launch_var)
    support = tk.Frame(page, bg=CARD)
    kofi_url = brand.get("kofi", "")
    if kofi_url:
        support.pack(anchor="w", fill="x", pady=(S(16), 0))
        label(support, "Free and made by one person. If it helps you, you can buy me a coffee.", 9, MUTED, wrap=wrap - S(30),
              bg=CARD).pack(anchor="w", padx=S(14), pady=(S(12), S(8)))
        button(support, "Support me on Ko-fi", lambda: webbrowser.open(kofi_url), color=RED, fg="#1b0a0a").pack(anchor="w", padx=S(14), pady=(0, S(12)))

    # ---------------------------------------------------------------- navigation
    order = ["welcome", "license", "options", "progress", "done"]
    cancel_event = threading.Event()

    def show(key):
        state["page"] = key
        for p in pages.values():
            p.pack_forget()
        pages[key].pack(fill="both", expand=True)
        mark({"welcome": 0, "license": 1, "options": 2, "progress": 3, "done": 4}[key])
        refresh()

    def refresh():
        key = state["page"]
        back_btn.pack_forget()
        next_btn.pack_forget()
        cancel_btn.pack_forget()
        if key == "progress":
            cancel_btn.pack(side="left")
            cancel_btn.configure(text="Cancel", command=cancel_event.set)
            return
        if key == "done":
            next_btn.configure(text="Finish", state="normal", command=finish)
            next_btn.pack(side="right")
            return
        cancel_btn.configure(text="Cancel", command=close)
        cancel_btn.pack(side="left")
        next_btn.pack(side="right")
        if key != "welcome":
            back_btn.pack(side="right", padx=(0, S(10)))
        if key == "license":
            next_btn.configure(text="Next", state="normal" if accept_var.get() else "disabled", command=go_next)
        elif key == "options":
            next_btn.configure(text="Update" if updating else "Install", state="normal", command=go_next)
        else:
            next_btn.configure(text="Next", state="normal", command=go_next)

    def go_back():
        show(order[max(order.index(state["page"]) - 1, 0)])

    def go_next():
        if state["page"] == "options":
            start()
        else:
            show(order[order.index(state["page"]) + 1])

    def close():
        cancel_event.set()
        root.destroy()

    def finish():
        if state["installed"] and launch_var.get():
            launch(state["installed"])
        root.destroy()

    # ---------------------------------------------------------------- install in a thread
    messages = queue.Queue()

    def work(opts):
        try:
            if opts["scope"] == "machine" and not admin_now:
                messages.put(("p", 0.05, "Waiting for administrator permission..."))
                ok, result = run_elevated_install(opts)
                messages.put(("ok", result) if ok else ("err", result))
                return
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
                    progress_bar["value"] = message[1] * 100
                    status.set(message[2])
                elif message[0] == "ok":
                    state["installed"] = message[1]
                    done_icon.configure(text="✓", fg=GREEN)
                    done_title.set("%s is installed" % NAME)
                    done_text.set("You can start it from the Start menu%s." % (" or the desktop" if desktop_var.get() else ""))
                    launch_check.pack(anchor="w")
                    show("done")
                    return
                else:
                    state["installed"] = None
                    done_icon.configure(text="!", fg=RED)
                    done_title.set("Setup could not finish")
                    done_text.set(message[1])
                    launch_check.pack_forget()
                    support.pack_forget()
                    show("done")
                    return
        except queue.Empty:
            pass
        root.after(60, poll)

    def start():
        if not payload_ok():
            state["installed"] = None
            done_icon.configure(text="!", fg=RED)
            done_title.set("Setup could not finish")
            done_text.set("This installer is damaged (its checksum does not match). Please download it again.")
            launch_check.pack_forget()
            show("done")
            return
        scope = scope_var.get()
        opts = {"dir": dir_var.get().strip() or default_dir(scope), "desktop": desktop_var.get(),
                "startmenu": menu_var.get(), "scope": scope}
        show("progress")
        threading.Thread(target=work, args=(opts,), daemon=True).start()
        poll()

    root.protocol("WM_DELETE_WINDOW", close)
    show("welcome")
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
    return run_gui_brand(o) if BRAND else run_gui(o)


if __name__ == "__main__":
    sys.exit(main())
'''


def render_installer(config):
    """Source of the installer program with its configuration embedded."""
    payload = base64.b64encode(json.dumps(config).encode('utf-8')).decode('ascii')
    return INSTALLER_SOURCE.replace('__CONFIG_B64__', payload).replace('__WINSHELL__', winshell.SNIPPET)


def tree_manifest(folder):
    """[relative posix path, size, sha256] for every file under ``folder`` (sorted)."""
    items = []
    for root, _dirs, files in os.walk(folder):
        for name in files:
            full = os.path.join(root, name)
            items.append([os.path.relpath(full, folder).replace(os.sep, '/'), os.path.getsize(full), file_sha256(full)])
    return sorted(items)


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
               data_folder, payload_dir=None):
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
        (f'Source: "{payload_dir}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs'
         if payload_dir else f'Source: "{app_exe}"; DestDir: "{{app}}"; Flags: ignoreversion'),
        '',
        '[Icons]',
        f'Name: "{{autoprograms}}\\{_iss(display_name)}"; Filename: "{{app}}\\{exe_file}"',
        f'Name: "{{autodesktop}}\\{_iss(display_name)}"; Filename: "{{app}}\\{exe_file}"; Tasks: desktopicon',
        '',
        '[Run]',
        f'Filename: "{{app}}\\{exe_file}"; Description: "Start {_iss(display_name)}"; Flags: nowait postinstall skipifsilent shellexec',
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


def build_inno_installer(job, build_dir, app_exe, exe_name, display_name, version, publisher, icon_path, output_dir,
                         payload_dir=None):
    iscc = find_inno()
    work = os.path.join(build_dir, 'installer')
    os.makedirs(work, exist_ok=True)
    setup_name = exe_name + '-Setup'
    script = os.path.join(work, 'setup.iss')
    with open(script, 'w', encoding='utf-8-sig') as fh:                    # BOM: Inno reads UTF-8 only with one
        fh.write(render_iss(display_name, exe_name, app_exe, normalize_version(version), clean_publisher(publisher),
                            icon_path, output_dir, setup_name, exe_name, 'H2E-' + exe_name, payload_dir))
    job.log('Compiling the installer with Inno Setup...')
    code = job.run_cmd([iscc, '/Q', script], cwd=work)
    setup_path = os.path.join(output_dir, setup_name + '.exe')
    if code != 0 or not os.path.isfile(setup_path):
        raise RuntimeError('Inno Setup could not compile the installer. See the log for details.')
    return setup_path


def build_installer(job, build_dir, app_exe, exe_name, display_name, version, publisher, icon_path, output_dir,
                    engine='builtin', payload_dir=None, uninstall_arg='--uninstall', brand=None, setup_name=None):
    """Package an app into ``<exe_name>-Setup.exe`` in ``output_dir``. Returns its path.

    ``app_exe`` is the app's main .exe. For a one-folder app pass ``payload_dir`` (the folder that contains it):
    the whole folder is installed. ``uninstall_arg`` is what the app's own .exe understands to uninstall itself
    (built-in engine only; Inno writes its own uninstaller).
    """
    if engine == 'inno':
        return build_inno_installer(job, build_dir, app_exe, exe_name, display_name, version, publisher, icon_path,
                                    output_dir, payload_dir)
    from .exe_build import python_for_pyinstaller      # lazy: exe_build imports this module
    work = os.path.join(build_dir, 'installer')
    os.makedirs(work, exist_ok=True)
    config = {
        'name': display_name,
        'exe_name': exe_name + '.exe',
        'app_key': exe_name,
        'version': normalize_version(version),
        'publisher': clean_publisher(publisher),
        'payload_kind': 'dir' if payload_dir else 'file',
        'uninstall_arg': uninstall_arg,
    }
    if brand:
        config['brand'] = brand
    extra_data = []
    if payload_dir:
        items = tree_manifest(payload_dir)
        config['payload_size'] = sum(item[1] for item in items)
        manifest_path = os.path.join(work, 'manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as fh:
            json.dump(items, fh)
        extra_data = [f'--add-data={payload_dir}{os.pathsep}payload', f'--add-data={manifest_path}{os.pathsep}.']
    else:
        config['payload_size'] = os.path.getsize(app_exe)
        config['payload_sha256'] = file_sha256(app_exe)
        extra_data = [f'--add-data={app_exe}{os.pathsep}payload']
    source = os.path.join(work, 'setup_main.py')
    with open(source, 'w', encoding='utf-8') as fh:
        fh.write(render_installer(config))
    setup_name = setup_name or (exe_name + '-Setup')
    cmd = python_for_pyinstaller() + [
        '-m', 'PyInstaller', '--onefile', '--windowed', '--noupx', '-y',
        f'--name={setup_name}', f'--distpath={output_dir}', f'--workpath={os.path.join(work, "work")}',
        f'--specpath={work}',
    ] + extra_data
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
