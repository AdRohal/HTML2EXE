"""Source code of the generated desktop launcher (the ``main.py`` inside every EXE).

The launcher is kept as a template string so it can be (a) written next to a
build, (b) tested by running it with ``--selftest`` and (c) bundled into the
builder itself without extra data files.

Modes
-----
static : serve the bundled web build over a local HTTP server (with SPA and
         ``page.html`` fallbacks) and show it in a WebView2 window.
php    : start a bundled portable PHP built-in server (PHP / Laravel) and show
         it in the same kind of window.
node   : start a bundled Node.js server (Next.js standalone output with API routes), give it the
         secrets decrypted in memory, and show it in the same kind of window.
"""
import base64
import json

LAUNCHER_SOURCE = r'''
import atexit
import base64
import importlib
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

CONFIG = json.loads(base64.b64decode("__CONFIG_B64__").decode("utf-8"))

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PROJECT_DIR = os.path.join(BASE_DIR, "_project")
if not os.path.isdir(PROJECT_DIR) and CONFIG.get("dev_project"):
    PROJECT_DIR = CONFIG["dev_project"]

_children = []


def _cleanup():
    for proc in _children:
        try:
            proc.terminate()
        except Exception:
            pass


atexit.register(_cleanup)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def app_data_dir():
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(root, CONFIG.get("app_id", "H2EApp"))
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------- static mode
class StaticHandler(SimpleHTTPRequestHandler):
    extensions_map = dict(
        SimpleHTTPRequestHandler.extensions_map,
        **{
            ".js": "text/javascript",
            ".mjs": "text/javascript",
            ".css": "text/css",
            ".json": "application/json",
            ".wasm": "application/wasm",
            ".svg": "image/svg+xml",
            ".webmanifest": "application/manifest+json",
            ".map": "application/json",
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PROJECT_DIR, **kwargs)

    def log_message(self, format, *args):
        pass

    def send_head(self):
        url_path = unquote(urlsplit(self.path).path)
        fs_path = self.translate_path(self.path)
        if not os.path.exists(fs_path):
            # /about  ->  about.html   (Next.js / Astro / Nuxt static exports)
            if os.path.isfile(fs_path + ".html"):
                self.path = url_path.rstrip("/") + ".html"
            # /any/client/route  ->  index.html   (React/Vue/Angular routers)
            elif "." not in url_path.rsplit("/", 1)[-1]:
                self.path = "/index.html"
        elif os.path.isdir(fs_path) and not os.path.isfile(os.path.join(fs_path, "index.html")):
            self.path = "/index.html"
        return super().send_head()


def start_static():
    port = find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), StaticHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d/" % port, server.shutdown


# ------------------------------------------------------------------- php mode
PRESERVE = ("storage", ".env", "database/database.sqlite")


def _copy_app(src, dst):
    """Copy the bundled app to a writable folder, keeping user data on update."""
    marker = os.path.join(dst, ".h2e-build")
    if os.path.isfile(marker):
        with open(marker, encoding="utf-8") as fh:
            if fh.read().strip() == CONFIG.get("build_id"):
                return
    keep = {os.path.normpath(os.path.join(dst, p)) for p in PRESERVE}

    def ignore(folder, names):
        skipped = []
        for name in names:
            target = os.path.normpath(os.path.join(dst, os.path.relpath(os.path.join(folder, name), src)))
            if target in keep and os.path.exists(target):
                skipped.append(name)
        return skipped

    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write(CONFIG.get("build_id", ""))


def _php_ini(php_dir, data_dir):
    ext_dir = os.path.join(php_dir, "ext")
    wanted = ["curl", "fileinfo", "gd", "intl", "mbstring", "exif", "mysqli",
              "openssl", "pdo_mysql", "pdo_sqlite", "sqlite3", "zip", "sodium"]
    lines = [
        "extension_dir=\"%s\"" % ext_dir,
        "memory_limit=512M",
        "upload_max_filesize=64M",
        "post_max_size=64M",
        "date.timezone=UTC",
        "display_errors=Off",
        "log_errors=On",
        "error_log=\"%s\"" % os.path.join(data_dir, "php-error.log"),
    ]
    for name in wanted:
        if os.path.isfile(os.path.join(ext_dir, "php_%s.dll" % name)):
            lines.append("extension=%s" % name)
    path = os.path.join(data_dir, "php.ini")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def _prepare_laravel(php, ini, app_dir):
    env_path = os.path.join(app_dir, ".env")
    example = os.path.join(app_dir, ".env.example")
    if not os.path.isfile(env_path) and os.path.isfile(example):
        shutil.copyfile(example, env_path)
    if not os.path.isfile(env_path) or not os.path.isfile(os.path.join(app_dir, "artisan")):
        return
    with open(env_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if "APP_KEY=base64:" not in text:
        subprocess.run([php, "-c", ini, "artisan", "key:generate", "--force"], cwd=app_dir,
                       capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    db_dir = os.path.join(app_dir, "database")
    if os.path.isdir(db_dir):
        sqlite_file = os.path.join(db_dir, "database.sqlite")
        if not os.path.exists(sqlite_file):
            open(sqlite_file, "a").close()
    for sub in ("framework/cache", "framework/sessions", "framework/views", "logs"):
        os.makedirs(os.path.join(app_dir, "storage", sub), exist_ok=True)
    os.makedirs(os.path.join(app_dir, "bootstrap", "cache"), exist_ok=True)
    # Create / update the SQLite tables once per build (sessions, cache, users ...)
    stamp = os.path.join(app_dir, ".h2e-migrated")
    done = ""
    if os.path.isfile(stamp):
        with open(stamp, encoding="utf-8") as fh:
            done = fh.read().strip()
    if done != CONFIG.get("build_id"):
        subprocess.run([php, "-c", ini, "artisan", "migrate", "--force"], cwd=app_dir,
                       capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with open(stamp, "w", encoding="utf-8") as fh:
            fh.write(CONFIG.get("build_id", ""))


def start_php():
    php_dir = os.path.join(BASE_DIR, "_php")
    php = os.path.join(php_dir, "php.exe")
    data_dir = app_data_dir()
    app_dir = os.path.join(data_dir, "app")
    _copy_app(PROJECT_DIR, app_dir)
    ini = _php_ini(php_dir, data_dir)
    if CONFIG.get("php_framework") == "laravel":
        _prepare_laravel(php, ini, app_dir)
    docroot = os.path.join(app_dir, CONFIG.get("php_docroot", "."))
    port = find_free_port()
    env = dict(os.environ, PHP_CLI_SERVER_WORKERS="4")
    proc = subprocess.Popen(
        [php, "-c", ini, "-S", "127.0.0.1:%d" % port, "-t", docroot],
        cwd=app_dir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _children.append(proc)
    url = "http://127.0.0.1:%d/" % port
    from urllib.request import urlopen
    for _ in range(100):
        try:
            urlopen(url, timeout=1).close()
            break
        except Exception as exc:
            if getattr(exc, "code", None):  # an HTTP error still means it is up
                break
            time.sleep(0.1)
    return url, proc.terminate


# ------------------------------------------------------------------ uninstall (installer builds)
__WINSHELL__

UNINSTALL_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + CONFIG.get("app_key", "")


def _ask(text, default_yes=False):
    try:
        flags = 0x24 | (0 if default_yes else 0x100)         # MB_YESNO | MB_ICONQUESTION (| default button No)
        return ctypes.windll.user32.MessageBoxW(0, text, CONFIG.get("title", "App"), flags) == 6
    except Exception:
        return False


def _registered_location():
    """Where Windows believes this app is installed (Apps & features), or None."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return winreg.QueryValueEx(key, "InstallLocation")[0]
    except OSError:
        return None


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
    registered = _registered_location()
    # Safety: only ever delete the folder Windows has registered for this app (never "wherever this exe happens to be").
    if not registered or os.path.normcase(os.path.abspath(registered)) != os.path.normcase(install_dir) \
            or os.path.dirname(install_dir) == install_dir:
        if not quiet:
            fatal("This copy of %s is not the installed one, so it will not remove anything. "
                  "Use Apps & features in Windows settings." % title)
        return 1
    if not quiet and not ask("Remove %s from this computer?" % title, True):
        return 0
    for folder in (desktop_dir(), start_menu_dir()):
        try:
            os.remove(os.path.join(folder, title + ".lnk"))
        except OSError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
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


# ------------------------------------------------------------------- node mode
START_ERROR = ""
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _kill_tree(proc):
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, creationflags=NOWIN)
    except Exception:
        pass


def _parse_env(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _bundled_env():
    """Decrypt the secrets bundled at build time. They only ever exist in memory and in the server's environment."""
    if not CONFIG.get("has_secrets"):
        return {}
    with open(os.path.join(BASE_DIR, "_secrets", "secrets.bin"), "rb") as fh:
        blob = fh.read()
    if blob[:4] != b"H2ES" or blob[4] != 1:
        raise ValueError("unknown format")
    share = base64.b64decode(CONFIG["secret_share"])
    other, nonce, ciphertext = blob[5:37], blob[37:49], blob[49:]
    key = bytes(a ^ b for a, b in zip(other, share))
    aead = importlib.import_module("cryptography.hazmat.primitives.ciphers.aead")
    aad = (CONFIG["app_id"] + ":" + CONFIG["build_id"]).encode("utf-8")
    try:
        data = aead.AESGCM(key).decrypt(nonce, ciphertext, aad)
    except Exception:
        raise ValueError("the data was modified or does not belong to this build")
    return json.loads(data.decode("utf-8"))


def _user_env(data_dir):
    """Optional .env the user keeps in the app's data folder; it overrides the bundled values."""
    path = os.path.join(data_dir, ".env")
    if CONFIG.get("user_env") and os.path.isfile(path):
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            return _parse_env(fh.read())
    return {}


def start_node():
    global START_ERROR
    node = os.path.join(BASE_DIR, "_node", "node.exe")
    entry = os.path.join(PROJECT_DIR, CONFIG.get("node_entry") or "server.js")
    data_dir = app_data_dir()
    env = dict(os.environ)
    try:
        env.update(_bundled_env())
    except Exception as exc:
        START_ERROR = "The app's protected settings could not be read (%s)." % exc
        return "http://127.0.0.1:1/", (lambda: None)
    env.update(_user_env(data_dir))
    port = find_free_port()
    env.update({"PORT": str(port), "HOSTNAME": "127.0.0.1", "NODE_ENV": "production",
                "NEXT_TELEMETRY_DISABLED": "1"})
    log_path = os.path.join(data_dir, "server.log")
    mode = "wb" if os.path.isfile(log_path) and os.path.getsize(log_path) > 1000000 else "ab"
    log = open(log_path, mode)
    proc = subprocess.Popen([node, entry], cwd=os.path.dirname(entry), env=env, stdout=log, stderr=log,
                            creationflags=NOWIN)
    _children.append(proc)
    url = "http://127.0.0.1:%d/" % port
    from urllib.request import urlopen
    for _ in range(600):                                   # up to about a minute
        if proc.poll() is not None:
            START_ERROR = "The app's server stopped while starting (exit code %s). Details: %s" % (proc.returncode, log_path)
            break
        try:
            urlopen(url, timeout=1).close()
            break
        except Exception as exc:
            if getattr(exc, "code", None):                 # an HTTP error still means it is up
                break
            time.sleep(0.1)
    else:
        START_ERROR = "The app's server did not answer within a minute. Details: %s" % log_path
    return url, (lambda: _kill_tree(proc))


def fatal(message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, CONFIG.get("title", "App"), 0x10)
    except Exception:
        print(message)


# ------------------------------------------------------------------ WebView2
def webview2_installed():
    if sys.platform != "win32":
        return True
    try:
        import winreg
    except ImportError:
        return True
    guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    places = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients" + chr(92) + guid),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients" + chr(92) + guid),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\EdgeUpdate\Clients" + chr(92) + guid),
    ]
    for hive, sub in places:
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, _ = winreg.QueryValueEx(key, "pv")
                if value and value != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False


def ask_install_webview2():
    import ctypes
    text = (
        "%s needs the Microsoft Edge WebView2 Runtime, which is not installed on this PC.\n\n"
        "Open the download page now? (It is free and takes about a minute.)" % CONFIG.get("title", "This app")
    )
    answer = ctypes.windll.user32.MessageBoxW(0, text, CONFIG.get("title", "App"), 0x4 | 0x20)
    if answer == 6:  # Yes
        webbrowser.open("https://developer.microsoft.com/microsoft-edge/webview2/")


# ---------------------------------------------------------------------- main
def main():
    args = sys.argv[1:]
    selftest_out = None
    probes = ["/"]
    for arg in args:
        if arg.startswith("--selftest-out="):
            selftest_out = arg.split("=", 1)[1]
        elif arg.startswith("--selftest-probe="):
            probes = arg.split("=", 1)[1].split(",")

    if "--uninstall" in args and CONFIG.get("installer"):
        return uninstall("--quiet" in args)

    mode = CONFIG.get("mode")
    if mode == "php":
        url, stop = start_php()
    elif mode == "node":
        url, stop = start_node()
    else:
        url, stop = start_static()
    if START_ERROR and not selftest_out:
        fatal(START_ERROR)
        stop()
        return 4

    if selftest_out:
        from urllib.error import HTTPError
        from urllib.request import urlopen
        results = []
        for path in probes:
            try:
                with urlopen(url.rstrip("/") + path, timeout=15) as resp:
                    body = resp.read()
                    results.append({"path": path, "status": resp.status, "bytes": len(body),
                                    "type": resp.headers.get("Content-Type", "")})
            except HTTPError as err:
                results.append({"path": path, "status": err.code, "bytes": 0, "type": ""})
            except Exception as err:
                results.append({"path": path, "status": 0, "error": str(err)})
        with open(selftest_out, "w", encoding="utf-8") as fh:
            json.dump({"url": url, "results": results, "startError": START_ERROR}, fh)
        stop()
        return 0

    if not webview2_installed():
        ask_install_webview2()
        stop()
        return 3

    import webview
    webview.create_window(
        CONFIG.get("title", "App"), url,
        width=int(CONFIG.get("width", 1100)), height=int(CONFIG.get("height", 760)),
        resizable=bool(CONFIG.get("resizable", True)),
        fullscreen=bool(CONFIG.get("fullscreen", False)),
        background_color=CONFIG.get("background", "#ffffff"),
    )
    webview.start(debug=False)
    stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def render_launcher(config):
    """Return launcher source with ``config`` (a JSON-able dict) embedded."""
    payload = base64.b64encode(json.dumps(config).encode('utf-8')).decode('ascii')
    from .winshell import SNIPPET
    return LAUNCHER_SOURCE.replace('__CONFIG_B64__', payload).replace('__WINSHELL__', SNIPPET)
