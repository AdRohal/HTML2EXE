"""Windows shell helpers shared by the generated installer and by the installed app's uninstaller.

``SNIPPET`` is plain Python source that is pasted into both generated programs (they are separate PyInstaller
executables and cannot import from the builder). It is also ``exec``-ed by the tests, so what ships is what is tested.
"""

SNIPPET = r'''
import ctypes
import os
import uuid

FOLDERID_DESKTOP = "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"
FOLDERID_PROGRAMS = "A77F5D77-2E2B-44C3-A6A2-ABA601054A51"
FOLDERID_COMMON_DESKTOP = "C4AA340D-F20F-4863-AFEF-F87EF2E6BA25"
FOLDERID_COMMON_PROGRAMS = "0139D44E-6AFE-49F2-8690-3DAFCAE6FFB8"
FOLDERID_PROGRAM_FILES = "905E63B6-C1BF-494E-B29C-65B732D3D21A"


def known_folder(guid):
    """Path of a Windows known folder (follows OneDrive-redirected desktops), or None."""
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8)]
    try:
        g = uuid.UUID(guid)
        data = GUID(g.time_low, g.time_mid, g.time_hi_version, (ctypes.c_ubyte * 8)(*g.bytes[8:]))
        out = ctypes.c_void_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(data), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return ctypes.wstring_at(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        return None


def desktop_dir():
    return known_folder(FOLDERID_DESKTOP) or os.path.join(os.path.expanduser("~"), "Desktop")


def start_menu_dir():
    return known_folder(FOLDERID_PROGRAMS) or os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")), "Microsoft", "Windows", "Start Menu", "Programs")


def common_desktop_dir():
    return known_folder(FOLDERID_COMMON_DESKTOP) or os.path.join(os.environ.get("PUBLIC", "C:\\Users\\Public"), "Desktop")


def common_start_menu_dir():
    return known_folder(FOLDERID_COMMON_PROGRAMS) or os.path.join(
        os.environ.get("ProgramData", "C:\\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs")


def program_files_dir():
    return known_folder(FOLDERID_PROGRAM_FILES) or os.environ.get("ProgramFiles", "C:\\Program Files")


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def create_shortcut(lnk, target, workdir="", description="", icon=None):
    """Create a .lnk with the Windows shell COM API directly (no PowerShell: hidden PowerShell is a malware tell)."""
    HRESULT = ctypes.c_long
    pvoid = ctypes.c_void_p

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8)]

    def guid(text):
        g = uuid.UUID(text)
        return GUID(g.time_low, g.time_mid, g.time_hi_version, (ctypes.c_ubyte * 8)(*g.bytes[8:]))

    def method(obj, index, *argtypes):
        vtable = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(pvoid))[0], ctypes.POINTER(pvoid))
        return ctypes.WINFUNCTYPE(HRESULT, pvoid, *argtypes)(vtable[index])

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    link = pvoid()
    persist = pvoid()
    try:
        clsid, iid_link, iid_file = (guid("00021401-0000-0000-C000-000000000046"),
                                     guid("000214F9-0000-0000-C000-000000000046"),
                                     guid("0000010B-0000-0000-C000-000000000046"))
        if ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid_link), ctypes.byref(link)) != 0:
            return False
        method(link, 20, ctypes.c_wchar_p)(link, target)                                  # SetPath
        if workdir:
            method(link, 9, ctypes.c_wchar_p)(link, workdir)                              # SetWorkingDirectory
        if description:
            method(link, 7, ctypes.c_wchar_p)(link, description)                          # SetDescription
        if icon:
            method(link, 17, ctypes.c_wchar_p, ctypes.c_int)(link, icon, 0)               # SetIconLocation
        if method(link, 0, ctypes.POINTER(GUID), ctypes.POINTER(pvoid))(
                link, ctypes.byref(iid_file), ctypes.byref(persist)) != 0:                 # QueryInterface(IPersistFile)
            return False
        os.makedirs(os.path.dirname(lnk), exist_ok=True)
        ok = method(persist, 6, ctypes.c_wchar_p, ctypes.c_int)(persist, lnk, 1) == 0     # Save
        return ok and os.path.isfile(lnk)
    except Exception:
        return False
    finally:
        for obj in (persist, link):
            if obj.value:
                method(obj, 2)(obj)                                                       # Release
        ole32.CoUninitialize()
'''


UNINSTALL_SNIPPET = r'''
# ---- uninstall: shortcuts, Apps & features entry, program folder (after exit) ----
import subprocess
import sys
UNINSTALL_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + CONFIG.get("app_key", "")


def _ask(text, default_yes=False):
    try:
        flags = 0x24 | (0 if default_yes else 0x100)         # MB_YESNO | MB_ICONQUESTION (| default button No)
        return ctypes.windll.user32.MessageBoxW(0, text, CONFIG.get("title", "App"), flags) == 6
    except Exception:
        return False


def _registered(install_dir=None):
    """``(location, scope)`` Windows has for this app (Apps & features): current user first, then all users."""
    import winreg
    for scope, hive in (("user", winreg.HKEY_CURRENT_USER), ("machine", winreg.HKEY_LOCAL_MACHINE)):
        try:
            with winreg.OpenKey(hive, UNINSTALL_KEY) as key:
                location = winreg.QueryValueEx(key, "InstallLocation")[0]
        except OSError:
            continue
        if install_dir is None or os.path.normcase(os.path.abspath(location)) == os.path.normcase(os.path.abspath(install_dir)):
            return location, scope
    return None, None


def _registered_location():
    """Where Windows believes this app is installed (Apps & features), or None."""
    return _registered()[0]


def _relaunch_elevated(args):
    """Run this program again with the Windows administrator prompt. Returns True when it was started."""
    try:
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, subprocess.list2cmdline(args), None, 1) > 32
    except Exception:
        return False


def _delete_script(folders, script_path):
    """A batch file that removes the folders once this program has exited, retrying while files are in use."""
    lines = ["@echo off"]
    for number, folder in enumerate(folders):
        lines += [
            "for /l %%i in (1,1,40) do (",
            '  rmdir /s /q "%s" >nul 2>&1' % folder,
            '  if not exist "%s" goto done%d' % (folder, number),
            "  ping -n 2 127.0.0.1 >nul",
            ")",
            ":done%d" % number,
        ]
    lines.append('(goto) 2>nul & del "%~f0"')
    with open(script_path, "w", encoding="utf-8") as fh:
        fh.write("\r\n".join(lines) + "\r\n")


def uninstall(quiet=False, install_dir=None, ask=None, spawn=None):
    """Remove the installed app: shortcuts, Apps & features entry and (after exit) its folder. Returns an exit code."""
    import winreg
    ask = ask or _ask
    spawn = spawn or subprocess.Popen
    title = CONFIG.get("title", "App")
    install_dir = os.path.abspath(install_dir or os.path.dirname(os.path.abspath(sys.executable)))
    registered, scope = _registered(install_dir)
    # Safety: only ever delete the folder Windows has registered for this app (never "wherever this exe happens to be").
    if not registered or os.path.dirname(install_dir) == install_dir:
        if not quiet:
            fatal("This copy of %s is not the installed one, so it will not remove anything. "
                  "Use Apps & features in Windows settings." % title)
        return 1
    if not quiet and not ask("Remove %s from this computer?" % title, True):
        return 0
    if scope == "machine" and not is_admin():              # an all-users install needs the administrator prompt
        if _relaunch_elevated(["--uninstall"] + (["--quiet"] if quiet else [])):
            return 0
        if not quiet:
            fatal("%s was installed for all users. Removing it needs administrator permission." % title)
        return 1
    folders = (common_desktop_dir(), common_start_menu_dir()) if scope == "machine" else (desktop_dir(), start_menu_dir())
    for folder in folders:
        try:
            os.remove(os.path.join(folder, title + ".lnk"))
        except OSError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE if scope == "machine" else winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    doomed = [install_dir]
    data_dir = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), CONFIG.get("app_id", "H2EApp"))
    if not quiet and os.path.isdir(data_dir) and ask("Also delete the saved data and settings of %s?" % title, False):
        doomed.append(data_dir)
    script = os.path.join(os.environ.get("TEMP", install_dir), CONFIG.get("app_key", "app") + "-uninstall.cmd")
    _delete_script(doomed, script)
    spawn(["cmd", "/c", script], creationflags=0x08000000 | 0x00000200, close_fds=True)
    return 0
'''

namespace = {}
exec(SNIPPET, namespace)                       # also usable directly from the builder / tests
known_folder = namespace['known_folder']
create_shortcut = namespace['create_shortcut']
desktop_dir = namespace['desktop_dir']
start_menu_dir = namespace['start_menu_dir']
