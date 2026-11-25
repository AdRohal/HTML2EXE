"""Python script / project -> Windows program (portable .exe or installer) with PyInstaller.

``analyze(path)``  looks at a script or folder without changing anything: entry point candidates, GUI or console,
                   requirements, third-party packages and which of them this PC cannot import.
``convert(data)``  runs the whole build and returns ``(result_dict, http_status)``. It is meant to run inside a job:
                   output goes through ``print`` (live log) and every subprocess is streamed and cancellable.

What a build does, in order
---------------------------
1. analyse the project (entry point, imports, data files, requirements)
2. pick the Python to build with: a clean virtual environment with the project's own requirements installed
   (cached between builds, rebuilt only when the requirements change) or the builder's Python
3. write a PyInstaller spec (+ Windows version info, optional administrator manifest, icon)
4. run PyInstaller and scan its warnings for modules the program needs but could not find
5. portable output: ``Downloads\\<App>.exe`` (or a folder).  Installer output: ``<App>-Setup.exe`` (Inno Setup or the
   built-in installer), per user, with shortcuts and an Apps & features entry
6. register the project (so it shows up under Projects and can be rebuilt) and delete the bulky build folders
"""
import ast
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import time

from . import dashboard, iconfinder, installer, jobs, workspace
from .exe_build import python_for_pyinstaller
from .security import is_safe_project_id, project_dir_for

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:  # pragma: no cover - Pillow is in requirements.txt
    HAS_PILLOW = False

ENTRY_NAMES = ('main.py', 'app.py', 'run.py', '__main__.py')
DATA_EXTENSIONS = {'.json', '.yaml', '.yml', '.txt', '.config', '.conf', '.cfg', '.ini', '.xml',
                   '.csv', '.db', '.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.ico',
                   '.svg', '.md', '.sqlite', '.sqlite3', '.ttf', '.otf', '.wav', '.mp3'}
SKIP_DIRS = {'venv', '.venv', 'env', '__pycache__', '.git', 'build', 'dist', 'node_modules',
             '.idea', '.vscode', '.mypy_cache', '.pytest_cache', '.tox', 'site-packages'}
NOT_DATA = re.compile(r'^(requirements.*\.txt|readme.*|license.*|changelog.*|\.gitignore)$', re.I)
MAX_PY_FILES = 1500
MAX_PY_SIZE = 600_000

# Modules PyInstaller often misses because they are loaded dynamically.
HIDDEN_IMPORT_CANDIDATES = (
    'webview', 'flask', 'django', 'requests', 'numpy', 'pandas', 'PIL', 'cv2', 'tkinter',
    'PyQt5', 'PyQt6', 'PySide6', 'pygame', 'sqlalchemy', 'sqlite3', 'cryptography',
    'matplotlib', 'scipy', 'sklearn',
)
# Programs that open windows of their own: no console is wanted.
GUI_LIBS = {'tkinter', 'customtkinter', 'ttkbootstrap', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx', 'kivy',
            'pygame', 'webview', 'flet', 'dearpygui', 'toga', 'pyglet', 'arcade'}
# import name -> name on PyPI, for the usual suspects
IMPORT_TO_PACKAGE = {
    'PIL': 'Pillow', 'cv2': 'opencv-python', 'yaml': 'PyYAML', 'sklearn': 'scikit-learn', 'bs4': 'beautifulsoup4',
    'dotenv': 'python-dotenv', 'serial': 'pyserial', 'Crypto': 'pycryptodome', 'win32com': 'pywin32',
    'win32api': 'pywin32', 'win32gui': 'pywin32', 'docx': 'python-docx', 'dateutil': 'python-dateutil',
    'jwt': 'PyJWT', 'git': 'GitPython', 'OpenSSL': 'pyOpenSSL', 'attr': 'attrs', 'skimage': 'scikit-image',
    'usb': 'pyusb', 'zmq': 'pyzmq', 'fitz': 'PyMuPDF', 'magic': 'python-magic', 'wx': 'wxPython',
    'PyQt5': 'PyQt5', 'PyQt6': 'PyQt6', 'PySide6': 'PySide6', 'tkinterdnd2': 'tkinterdnd2',
}


# =============================================================================================== small helpers
def safe_exe_name(name):
    """A file-system safe EXE name ('..', slashes and odd characters removed)."""
    cleaned = re.sub(r'[^A-Za-z0-9_. -]+', '_', str(name or '')).strip(' ._')
    return cleaned or 'MyApp'


def _skip_dir(root, name):
    if name in SKIP_DIRS or name.startswith('.'):
        return True
    return os.path.isfile(os.path.join(root, name, 'pyvenv.cfg'))              # someone's virtual environment


def walk_py(folder, limit=MAX_PY_FILES):
    """Relative paths (posix) of the project's .py files; bounded, skipping environments and caches."""
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not _skip_dir(root, d))
        for name in sorted(files):
            if name.endswith('.py'):
                found.append(os.path.relpath(os.path.join(root, name), folder).replace(os.sep, '/'))
                if len(found) >= limit:
                    return found
    return found


def _parse(path):
    try:
        if os.path.getsize(path) > MAX_PY_SIZE:
            return None
        with open(path, encoding='utf-8', errors='ignore') as fh:
            return ast.parse(fh.read())
    except (SyntaxError, ValueError, OSError):
        return None


def _imports(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split('.')[0])
    return found


def _has_main_guard(tree):
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) \
                and node.test.left.id == '__name__':
            return True
    return False


def find_entry_point(folder):
    """The entry script (file name) and the list of .py files directly in ``folder``."""
    py_files = sorted(f for f in os.listdir(folder) if f.endswith('.py'))
    for name in ENTRY_NAMES:
        if name in py_files:
            return name, py_files
    return (py_files[0] if py_files else None), py_files


def detect_imports(folder, py_files):
    """Top-level module names imported by the given scripts (via ``ast``)."""
    found = set()
    for name in py_files:
        tree = _parse(os.path.join(folder, name))
        if tree is not None:
            found |= _imports(tree)
    return found


def entry_candidates(folder, py_files, trees=None):
    """Possible entry scripts, best first: ``[(relative path, why)]``."""
    ranked = []
    for rel in py_files:
        tree = (trees or {}).get(rel) or _parse(os.path.join(folder, rel))
        guard = tree is not None and _has_main_guard(tree)
        base = os.path.basename(rel)
        score = 0
        reasons = []
        if base in ENTRY_NAMES:
            score += 60 - 10 * ENTRY_NAMES.index(base)
            reasons.append('standard name')
        if guard:
            score += 30
            reasons.append("has an if __name__ == '__main__' block")
        if '/' not in rel:
            score += 20
        else:
            score -= 5 * rel.count('/')
        if score > 0:
            ranked.append((score, rel, ', '.join(reasons) or 'top-level script'))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [(rel, why) for _score, rel, why in ranked[:12]]


DEFAULT_EXCLUDES = ('tests', 'test', '__tests__', 'node_modules')     # never bundled as data, whatever the project


def find_data_entries(folder, exclude=()):
    """PyInstaller ``datas`` as (source, dest) pairs: root data files + folders with assets.

    ``exclude``: extra top-level file or folder names to leave out (case-insensitive), on top of ``DEFAULT_EXCLUDES``.
    """
    skip = {str(x).lower() for x in list(DEFAULT_EXCLUDES) + list(exclude or ())}
    entries = []
    for name in sorted(os.listdir(folder)):
        if name.lower() in skip:
            continue
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            if os.path.splitext(name)[1].lower() in DATA_EXTENSIONS and not NOT_DATA.match(name) \
                    and not name.lower().startswith('.env'):
                entries.append((full, '.'))
        elif not _skip_dir(folder, name):
            for _root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if not _skip_dir(_root, d)]
                if any(not f.endswith(('.py', '.pyc')) for f in files):
                    entries.append((full, name))
                    break
    return entries


def parse_requirements(folder):
    """``{'file': name or None, 'packages': [names], 'lines': [pip requirement lines]}``."""
    result = {'file': None, 'packages': [], 'lines': []}
    path = os.path.join(folder, 'requirements.txt')
    lines = []
    if os.path.isfile(path):
        result['file'] = 'requirements.txt'
        with open(path, encoding='utf-8-sig', errors='replace') as fh:
            for raw in fh:
                line = raw.split(' #')[0].strip()
                if line and not line.startswith('#'):
                    lines.append(line)
    elif os.path.isfile(os.path.join(folder, 'pyproject.toml')) and sys.version_info >= (3, 11):
        import tomllib
        try:
            with open(os.path.join(folder, 'pyproject.toml'), 'rb') as fh:
                deps = (tomllib.load(fh).get('project') or {}).get('dependencies') or []
        except (OSError, ValueError):
            deps = []
        if deps:
            result['file'] = 'pyproject.toml'
            lines = [str(d) for d in deps]
    result['lines'] = lines
    for line in lines:
        match = re.match(r'^([A-Za-z0-9][A-Za-z0-9_.-]*)', line)
        if match and not line.startswith(('-', '.', '/', 'http')):
            result['packages'].append(match.group(1))
    return result


def _importable(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


# =================================================================================================== analysis
def resolve_target(path):
    """``(project folder, entry hint or None)`` for a script or folder path; raises ValueError with a message."""
    path = os.path.abspath(str(path or ''))
    if not os.path.exists(path):
        raise FileNotFoundError(f'Python project path not found: {path}')
    if os.path.isfile(path):
        if not path.endswith('.py'):
            raise ValueError('Pick a .py file or a folder that contains one.')
        return os.path.dirname(path), os.path.basename(path)
    return path, None


def analyze(path):
    """Describe a Python project. Fast, bounded, changes nothing."""
    folder, hint = resolve_target(path)
    py_files = walk_py(folder)
    if not py_files:
        raise ValueError('No Python (.py) files found in the project folder. Please ensure your project has a '
                         'main.py, app.py, or other Python file.')
    trees = {rel: _parse(os.path.join(folder, rel)) for rel in py_files}
    candidates = entry_candidates(folder, py_files, trees)
    entry = hint if hint in py_files else (candidates[0][0] if candidates else py_files[0])
    imports = set()
    for tree in trees.values():
        if tree is not None:
            imports |= _imports(tree)
    local = {rel.split('/')[0][:-3] if '/' not in rel else rel.split('/')[0] for rel in py_files}
    stdlib = set(getattr(sys, 'stdlib_module_names', ())) | {'__future__'}
    third_party = sorted(m for m in imports if m not in stdlib and m not in local)
    gui_libs = sorted(m for m in imports if m in GUI_LIBS)
    reqs = parse_requirements(folder)
    missing = [m for m in third_party if not _importable(m)]
    data = find_data_entries(folder)
    warnings = []
    if trees.get(entry) is None:
        warnings.append(f'{entry} could not be read as Python (syntax error?).')
    if missing and not reqs['file']:
        warnings.append('Not installed on this PC and no requirements.txt to install them from: '
                        + ', '.join(f'{m} ({IMPORT_TO_PACKAGE.get(m, m)})' for m in missing)
                        + '. Add a requirements.txt so the build can install them.')
    if any(name.lower().startswith('.env') and os.path.isfile(os.path.join(folder, name)) for name in os.listdir(folder)):
        warnings.append('A .env file was found. It is not bundled (it would be readable inside the .exe); the program '
                        'will look for it next to itself when it runs.')
    return {
        'success': True, 'folder': folder, 'folderName': os.path.basename(folder), 'entry': entry,
        'candidates': [{'file': rel, 'why': why} for rel, why in candidates],
        'pyFiles': len(py_files), 'gui': bool(gui_libs), 'guiLibs': gui_libs, 'thirdParty': third_party,
        'missing': missing, 'requirements': {'file': reqs['file'], 'packages': reqs['packages']},
        'dataItems': len(data), 'warnings': warnings, 'python': sys.version.split()[0],
        'projectType': 'Python (window app)' if gui_libs else 'Python (command-line)',
    }


# ================================================================================================ build pieces
def _prepare_icon(icon_data, build_dir, exe_name):
    """Write the data-URI icon to disk (PNG -> ICO when Pillow is available)."""
    if not icon_data or not icon_data.startswith('data:') or ',' not in icon_data:
        return None
    header, payload = icon_data.split(',', 1)
    try:
        binary = base64.b64decode(payload)
    except ValueError:
        print('Warning: icon data was not valid base64 - building without an icon')
        return None
    ext = 'png' if 'png' in header else 'ico'
    raw = os.path.join(build_dir, f'temp_icon.{ext}')
    with open(raw, 'wb') as fh:
        fh.write(binary)
    if ext != 'png':
        return raw
    if not HAS_PILLOW:
        print('Warning: Pillow is not installed - PNG icons cannot be converted to ICO')
        return None
    ico = os.path.join(build_dir, f'{exe_name}.ico')
    try:
        img = Image.open(raw).convert('RGBA')
        img.save(ico, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        os.remove(raw)
        return ico
    except Exception as exc:  # noqa: BLE001
        print(f'Warning: icon conversion failed ({exc}) - building without an icon')
        return None


def version_info_text(name, version, publisher, exe_name):
    """PyInstaller ``--version-file`` text: what Windows shows in the file's Details tab."""
    nums = [int(x) for x in (installer.normalize_version(version).split('.') + ['0', '0', '0', '0'])[:4]]
    ver = '.'.join(str(n) for n in nums)
    strings = [('CompanyName', installer.clean_publisher(publisher)), ('FileDescription', name),
               ('FileVersion', ver), ('InternalName', exe_name), ('OriginalFilename', exe_name + '.exe'),
               ('ProductName', name), ('ProductVersion', ver)]
    body = ', '.join(f'StringStruct({k!r}, {v!r})' for k, v in strings)
    return (f"VSVersionInfo(\n  ffi=FixedFileInfo(filevers={tuple(nums)!r}, prodvers={tuple(nums)!r}, mask=0x3f, flags=0x0,"
            f" OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n  kids=[\n    StringFileInfo([StringTable('040904B0', "
            f"[{body}])]),\n    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n  ]\n)\n")


def build_spec(entry_path, project_dir, exe_name, datas, hidden_imports, console, icon, single_file, optimize,
               uac_admin=False, version_file=None, runtime_hooks=()):
    """Return the text of a PyInstaller .spec file (all values go through ``repr``)."""
    common = (
        f"a = Analysis(\n    [{entry_path!r}],\n    pathex=[{project_dir!r}],\n    binaries=[],\n"
        f"    datas={[(s, d) for s, d in datas]!r},\n    hiddenimports={list(hidden_imports)!r},\n"
        f"    hookspath=[],\n    hooksconfig={{}},\n    runtime_hooks={list(runtime_hooks)!r},\n    excludes=[],\n"
        f"    noarchive=False,\n    optimize={2 if optimize else -1},\n)\npyz = PYZ(a.pure)\n"
    )
    extras = ''
    if icon:
        extras += f"    icon={icon!r},\n"
    if version_file:
        extras += f"    version={version_file!r},\n"
    if uac_admin:
        extras += "    uac_admin=True,\n"
    if single_file:
        exe = (f"exe = EXE(\n    pyz,\n    a.scripts,\n    a.binaries,\n    a.datas,\n    [],\n"
               f"    name={exe_name!r},\n    debug=False,\n    strip=False,\n    upx=False,\n"
               f"    runtime_tmpdir=None,\n    console={bool(console)},\n{extras})\n")
    else:
        exe = (f"exe = EXE(\n    pyz,\n    a.scripts,\n    [],\n    exclude_binaries=True,\n"
               f"    name={exe_name!r},\n    debug=False,\n    strip=False,\n    upx=False,\n"
               f"    console={bool(console)},\n{extras})\n"
               f"coll = COLLECT(\n    exe,\n    a.binaries,\n    a.datas,\n    strip=False,\n"
               f"    upx=False,\n    name={exe_name!r},\n)\n")
    return "# -*- mode: python ; coding: utf-8 -*-\n\n" + common + "\n" + exe


def uninstall_hook_source(title, app_key):
    """PyInstaller runtime hook: lets an installed program remove itself (``App.exe --uninstall``).

    It only acts when it runs from the folder Windows has registered for the app; anywhere else the program's own
    command line is left alone.
    """
    from .winshell import SNIPPET, UNINSTALL_SNIPPET
    config = json.dumps({'title': title, 'app_key': app_key, 'app_id': 'H2E-' + app_key, 'installer': True})
    return ("# Generated by HTML2EXE (runtime hook)\n"
            f"import json as _json\nCONFIG = _json.loads({config!r})\n\n\n"
            "def fatal(message):\n"
            "    try:\n        import ctypes\n        ctypes.windll.user32.MessageBoxW(0, message, CONFIG['title'], 0x10)\n"
            "    except Exception:\n        pass\n\n"
            + SNIPPET + UNINSTALL_SNIPPET +
            "\n\nif '--uninstall' in sys.argv[1:]:\n"
            "    _where = _registered_location()\n"
            "    if _where and os.path.normcase(os.path.abspath(_where)) == os.path.normcase(os.path.dirname(os.path.abspath(sys.executable))):\n"
            "        sys.exit(uninstall('--quiet' in sys.argv))\n")


def read_warnings(work_dir, exe_name, local_modules):
    """Top-level modules PyInstaller could not find that the project's own code imports."""
    path = os.path.join(work_dir, exe_name, f'warn-{exe_name}.txt')
    missing = []
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                match = re.match(r'^missing module named (\S+) - imported by (.*)$', line.strip())
                if not match or 'top-level' not in match.group(2):
                    continue
                name = match.group(1).strip("'")
                importers = [part.strip().split(' ')[0] for part in match.group(2).split(',')]
                if '.' not in name and any(i.split('.')[0] in local_modules or i == '__main__' for i in importers) \
                        and name not in missing:
                    missing.append(name)
    except OSError:
        pass
    return missing[:10]


# ============================================================================================ environment
def _pyinstaller_version():
    try:
        from importlib.metadata import version
        return version('pyinstaller')
    except Exception:  # noqa: BLE001
        return ''


def prepare_python(job, folder, cache_dir, reqs, isolated):
    """The Python command to build with. Returns ``(command list, info dict)``.

    With a requirements file (and ``isolated``) the project gets its own cached virtual environment holding exactly
    its requirements plus PyInstaller, so the program is built from the packages it really uses and not from
    whatever this PC's Python happens to have installed.
    """
    base = python_for_pyinstaller()
    if not (isolated and reqs['file'] and reqs['lines']):
        return base, {'isolated': False, 'packages': 0}
    venv = os.path.join(cache_dir, 'venv')
    py = os.path.join(venv, 'Scripts', 'python.exe')
    stamp_path = os.path.join(venv, '.h2e-env-stamp')
    digest = hashlib.sha256()
    digest.update('\n'.join(reqs['lines']).encode('utf-8'))
    digest.update(f'|py{sys.version_info[:2]}|pyi{_pyinstaller_version()}'.encode())
    stamp = digest.hexdigest()
    try:
        with open(stamp_path, encoding='utf-8') as fh:
            current = fh.read().strip()
    except OSError:
        current = ''
    if os.path.isfile(py) and current == stamp:
        job.log('Requirements unchanged - reusing the project environment')
        return [py], {'isolated': True, 'packages': len(reqs['packages'])}

    job.log('Creating a clean environment for the project (first time, or the requirements changed)...')
    shutil.rmtree(venv, ignore_errors=True)
    os.makedirs(cache_dir, exist_ok=True)
    if job.run_cmd(base + ['-m', 'venv', venv]) != 0 or not os.path.isfile(py):
        raise RuntimeError('Could not create the virtual environment. See the log for the reason.')
    pip = [py, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input']
    pyi = _pyinstaller_version()
    if job.run_cmd(pip + [f'pyinstaller=={pyi}' if pyi else 'pyinstaller']) != 0:
        raise RuntimeError('Could not install PyInstaller into the project environment (no internet?).')
    req_file = os.path.join(cache_dir, 'requirements.h2e.txt')
    with open(req_file, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(reqs['lines']) + '\n')
    job.log(f'Installing {len(reqs["packages"])} requirement(s)...')
    if job.run_cmd(pip + ['-r', req_file], cwd=folder) != 0:
        shutil.rmtree(venv, ignore_errors=True)
        raise RuntimeError('pip could not install the project requirements. See the log above: a package may not '
                           'exist, may need a compiler, or there is no internet connection.')
    with open(stamp_path, 'w', encoding='utf-8') as fh:
        fh.write(stamp)
    return [py], {'isolated': True, 'packages': len(reqs['packages'])}


# ================================================================================================== the build
def _fail(message, status=500):
    return {'error': message}, status


def convert(data):
    """Run the whole conversion. Returns ``(result, status)``."""
    job = jobs.current_job() or jobs.Job('python')
    name = str(data.get('exeName') or 'MyApp').strip() or 'MyApp'
    exe_name = safe_exe_name(name)
    single_file = bool(data.get('singleFile', True))
    optimize = bool(data.get('optimize', False))
    uac_admin = bool(data.get('uacAdmin', False))
    isolated = data.get('isolated', True) is not False
    as_installer = data.get('outputType') == 'installer'
    version = data.get('appVersion') or '1.0.0'
    publisher = data.get('publisher') or ''
    keep = bool(data.get('keepWorkFiles'))

    try:
        info = analyze(data.get('pythonPath', ''))
    except FileNotFoundError as exc:
        return _fail(str(exc), 404)
    except ValueError as exc:
        return _fail(str(exc), 400)
    folder = info['folder']
    entry = str(data.get('entry') or info['entry']).replace('\\', '/')
    if not os.path.isfile(os.path.join(folder, entry)) or '..' in entry.split('/'):
        return _fail(f'The entry script {entry} was not found in the project.', 400)
    gui = info['gui']
    hide_console = gui if data.get('hideConsole') is None else bool(data.get('hideConsole'))
    print(f'Python project: {folder}')
    print(f'Entry point: {entry}   |   {info["projectType"]}   |   console window: {"hidden" if hide_console else "shown"}')

    project_id = name if is_safe_project_id(name) else exe_name
    metadata_dir = project_dir_for(project_id)
    if metadata_dir is None:
        return _fail('The app name cannot contain any of: / \\ : * ? " < > |', 400)
    build_dir = os.path.join(metadata_dir, 'build')
    cache_dir = os.path.join(metadata_dir, 'cache')
    output_dir = data.get('outputDir') or workspace.downloads_root()
    os.makedirs(build_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    engine = 'builtin'
    if as_installer:
        try:
            engine = installer.resolve_engine(data.get('installerEngine') or 'auto')
        except RuntimeError as exc:
            return _fail(str(exc), 400)
        print(f'Installer engine: {"Inno Setup" if engine == "inno" else "built-in"}')

    try:
        reqs = parse_requirements(folder)
        py_cmd, env_info = prepare_python(job, folder, cache_dir, reqs, isolated)
        job.check_cancelled()

        imports = detect_imports(folder, [e for e in walk_py(folder)])
        hidden = [m for m in HIDDEN_IMPORT_CANDIDATES if m in imports]
        extra_hidden = data.get('hiddenImports') or []
        if isinstance(extra_hidden, str):
            extra_hidden = [x.strip() for x in re.split(r'[,\s]+', extra_hidden) if x.strip()]
        hidden += [m for m in extra_hidden if re.match(r'^[A-Za-z_][\w.]*$', m) and m not in hidden]
        for module in hidden:
            print(f'  Detected import: {module}')
        datas = find_data_entries(folder, data.get('excludeData') or ())
        for rel in data.get('extraData') or ():
            full = os.path.join(folder, rel)
            if os.path.isfile(full) and '..' not in str(rel).replace(chr(92), '/').split('/'):
                datas.append((full, '.'))
        for src, dest in datas:
            print(f'  Bundling data: {os.path.basename(src)} -> {dest}')

        # icon: a new one from the page, or the one saved with the project
        icon_data = data.get('iconData', '')
        if not icon_data and data.get('autoIcon', True) is not False:
            icon_data, why = iconfinder.auto_icon_data(folder)
            print(f'No icon chosen - using the one found in your project: {why}' if icon_data
                  else 'No icon chosen and none found in the project - the program gets the default icon')
        icon = _prepare_icon(icon_data or '', build_dir, exe_name)
        saved = [os.path.join(metadata_dir, n) for n in ('icon.ico',) if os.path.isfile(os.path.join(metadata_dir, n))]
        if icon:
            shutil.copyfile(icon, os.path.join(metadata_dir, 'icon.ico'))
        elif saved and data.get('reuseIcon'):
            icon = saved[0]
            print('Using the icon saved with this project')

        version_file = os.path.join(build_dir, 'version-info.txt')
        with open(version_file, 'w', encoding='utf-8') as fh:
            fh.write(version_info_text(name, version, publisher, exe_name))
        hooks = []
        if as_installer and engine == 'builtin':
            hook = os.path.join(build_dir, 'h2e_uninstall_hook.py')
            with open(hook, 'w', encoding='utf-8') as fh:
                fh.write(uninstall_hook_source(name, exe_name))
            hooks.append(hook)

        spec_path = os.path.join(build_dir, f'{exe_name}.spec')
        with open(spec_path, 'w', encoding='utf-8') as fh:
            fh.write(build_spec(os.path.join(folder, entry), folder, exe_name, datas, hidden, not hide_console,
                                icon, single_file, optimize, uac_admin, version_file, hooks))
        print(f'Spec file: {spec_path}')

        app_out = os.path.join(build_dir, 'dist') if as_installer else output_dir
        os.makedirs(app_out, exist_ok=True)
        work = os.path.join(build_dir, 'work')
        shutil.rmtree(work, ignore_errors=True)
        cmd = py_cmd + ['-m', 'PyInstaller', f'--distpath={app_out}', f'--workpath={work}', '--noconfirm', '-y', spec_path]
        print('Running PyInstaller...')
        t0 = time.time()
        result = jobs.run(cmd, cwd=build_dir)
        if result.returncode != 0:
            tail = '\n'.join((result.stdout or '').strip().splitlines()[-10:])
            return _fail(f'PyInstaller build failed:\n{tail}')
        exe_path = (os.path.join(app_out, f'{exe_name}.exe') if single_file
                    else os.path.join(app_out, exe_name, f'{exe_name}.exe'))
        if not os.path.isfile(exe_path):
            return _fail(f'The EXE was not created at {exe_path}. See the log for details.')

        local_modules = {rel.split('/')[0][:-3] if '/' not in rel else rel.split('/')[0] for rel in walk_py(folder)}
        missing_modules = read_warnings(work, exe_name, local_modules)
        warnings = list(info['warnings'])
        if missing_modules:
            warnings.append('PyInstaller could not find: ' + ', '.join(missing_modules)
                            + '. If the program needs them, add them to requirements.txt (or list them under hidden imports).')
        size_mb = (os.path.getsize(exe_path) if single_file
                   else sum(os.path.getsize(os.path.join(r, f)) for r, _d, fs in os.walk(os.path.dirname(exe_path)) for f in fs)) / (1024 * 1024)
        print(f'Program built in {time.time() - t0:.0f}s ({size_mb:.1f} MB): {exe_path}')

        final_path, final_name, final_mb = exe_path, f'{exe_name}.exe', size_mb
        installer_info = None
        if as_installer:
            payload_dir = None if single_file else os.path.dirname(exe_path)
            try:
                setup_path = installer.build_installer(job, build_dir, exe_path, exe_name, name, version, publisher, icon,
                                                       output_dir, engine, payload_dir, '--uninstall',
                                                       data.get('brand') or None, data.get('setupName') or None)
            except RuntimeError as exc:
                return _fail(str(exc))
            check = installer.self_test(setup_path, build_dir, job) if engine == 'builtin' else {'ok': True}
            final_path, final_name = setup_path, os.path.basename(setup_path)
            final_mb = os.path.getsize(setup_path) / (1024 * 1024)
            installer_info = {'engine': engine, 'verified': check['ok'], 'version': installer.normalize_version(version),
                              'publisher': installer.clean_publisher(publisher),
                              'silent': final_name + (' /VERYSILENT' if engine == 'inno' else ' /S')}
            print(f'Installer ready ({final_mb:.1f} MB): {setup_path}')

        _register_project(metadata_dir, name, folder, data, entry, info, hide_console, single_file, version, publisher)
        if not keep:
            workspace.clean_build_files(build_dir)
    except RuntimeError as exc:
        return _fail(str(exc))

    dashboard.record_build(metadata_dir, {'exePath': final_path, 'sizeMb': round(final_mb, 1),
                                          'kind': 'installer' if as_installer else 'portable'})
    print(f'BUILD SUCCESSFUL: {final_path} ({final_mb:.2f} MB)')
    where = 'Downloads/' if (single_file or as_installer) else f'Downloads/{exe_name}/'
    return {'success': True, 'kind': 'installer' if as_installer else 'portable',
            'message': f'Python build successful! The result is in {where}',
            'exePath': final_path, 'exeName': final_name, 'size': f'{final_mb:.2f} MB', 'sizeMb': round(final_mb, 1),
            'appSizeMb': round(size_mb, 1), 'entry': entry, 'console': not hide_console, 'gui': gui,
            'isolated': env_info['isolated'], 'packages': env_info['packages'], 'warnings': warnings,
            'missingModules': missing_modules, 'installer': installer_info}, 200


def _register_project(metadata_dir, name, folder, data, entry, info, hide_console, single_file, version, publisher):
    """Save what is needed to rebuild: it shows up under Projects like a web project."""
    meta_path = os.path.join(metadata_dir, 'project.json')
    created = time.strftime('%Y-%m-%dT%H:%M:%S')
    try:
        with open(meta_path, encoding='utf-8') as fh:
            created = json.load(fh).get('created', created)
    except (OSError, ValueError):
        pass
    meta = {
        'name': name, 'kind': 'python', 'sourceFolder': folder, 'downloadFolder': '', 'pythonPath': str(data.get('pythonPath', '')),
        'entry': entry, 'version': installer.normalize_version(version), 'author': installer.clean_publisher(publisher),
        'description': '', 'created': created,
        'options': {'hideConsole': hide_console, 'singleFile': single_file, 'optimize': bool(data.get('optimize', False)),
                    'uacAdmin': bool(data.get('uacAdmin', False)), 'isolated': data.get('isolated', True) is not False,
                    'outputType': 'installer' if data.get('outputType') == 'installer' else 'portable',
                    'hiddenImports': data.get('hiddenImports') or ''},
        'hasIcon': os.path.isfile(os.path.join(metadata_dir, 'icon.ico')),
        'analysis': {'framework': 'python', 'frameworkLabel': 'Python app', 'projectType': info['projectType'],
                     'support': 'supported', 'notes': [], 'frameworks': [], 'technologies': info['guiLibs']},
    }
    with open(meta_path, 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
