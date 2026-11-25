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

namespace = {}
exec(SNIPPET, namespace)                       # also usable directly from the builder / tests
known_folder = namespace['known_folder']
create_shortcut = namespace['create_shortcut']
desktop_dir = namespace['desktop_dir']
start_menu_dir = namespace['start_menu_dir']
