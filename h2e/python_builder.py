"""Python script / project -> Windows EXE with PyInstaller.

``convert(data)`` returns ``(result_dict, http_status)``. Output goes through
``print`` so it lands in the live job log when run as a background job; the
PyInstaller process itself is streamed and cancellable via ``jobs.run``.
"""
import ast
import base64
import os
import re

from . import jobs
from .exe_build import python_for_pyinstaller

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
             '.idea', '.vscode'}
# Modules PyInstaller often misses because they are loaded dynamically.
HIDDEN_IMPORT_CANDIDATES = (
    'webview', 'flask', 'django', 'requests', 'numpy', 'pandas', 'PIL', 'cv2', 'tkinter',
    'PyQt5', 'PyQt6', 'PySide6', 'pygame', 'sqlalchemy', 'sqlite3', 'cryptography',
    'matplotlib', 'scipy', 'sklearn',
)


def safe_exe_name(name):
    """A file-system safe EXE name ('..', slashes and odd characters removed)."""
    cleaned = re.sub(r'[^A-Za-z0-9_. -]+', '_', str(name or '')).strip(' ._')
    return cleaned or 'MyApp'


def find_entry_point(folder):
    """Return the entry script (file name) and the list of .py files in ``folder``."""
    py_files = sorted(f for f in os.listdir(folder) if f.endswith('.py'))
    for name in ENTRY_NAMES:
        if name in py_files:
            return name, py_files
    return (py_files[0] if py_files else None), py_files


def detect_imports(folder, py_files):
    """Top-level module names imported by the project's scripts (via ``ast``)."""
    found = set()
    for name in py_files:
        try:
            with open(os.path.join(folder, name), encoding='utf-8', errors='ignore') as fh:
                tree = ast.parse(fh.read())
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split('.')[0])
    return found


def find_data_entries(folder):
    """PyInstaller ``datas`` as (source, dest) pairs: root data files + folders with assets."""
    entries = []
    for name in sorted(os.listdir(folder)):
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            if os.path.splitext(name)[1].lower() in DATA_EXTENSIONS:
                entries.append((full, '.'))
        elif name not in SKIP_DIRS and not name.startswith('.'):
            for _root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                if any(not f.endswith(('.py', '.pyc')) for f in files):
                    entries.append((full, name))
                    break
    return entries


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


def build_spec(entry_path, project_dir, exe_name, datas, hidden_imports, console, icon, single_file, optimize):
    """Return the text of a PyInstaller .spec file (all values go through ``repr``)."""
    common = (
        f"a = Analysis(\n    [{entry_path!r}],\n    pathex=[{project_dir!r}],\n    binaries=[],\n"
        f"    datas={[(s, d) for s, d in datas]!r},\n    hiddenimports={list(hidden_imports)!r},\n"
        f"    hookspath=[],\n    hooksconfig={{}},\n    runtime_hooks=[],\n    excludes=[],\n"
        f"    noarchive=False,\n    optimize={2 if optimize else -1},\n)\npyz = PYZ(a.pure)\n"
    )
    icon_line = f"    icon={icon!r},\n" if icon else ''
    if single_file:
        exe = (f"exe = EXE(\n    pyz,\n    a.scripts,\n    a.binaries,\n    a.datas,\n    [],\n"
               f"    name={exe_name!r},\n    debug=False,\n    strip=False,\n    upx=False,\n"
               f"    runtime_tmpdir=None,\n    console={bool(console)},\n{icon_line})\n")
    else:
        exe = (f"exe = EXE(\n    pyz,\n    a.scripts,\n    [],\n    exclude_binaries=True,\n"
               f"    name={exe_name!r},\n    debug=False,\n    strip=False,\n    upx=False,\n"
               f"    console={bool(console)},\n{icon_line})\n"
               f"coll = COLLECT(\n    exe,\n    a.binaries,\n    a.datas,\n    strip=False,\n"
               f"    upx=False,\n    name={exe_name!r},\n)\n")
    return "# -*- mode: python ; coding: utf-8 -*-\n\n" + common + "\n" + exe


def convert(data):
    """Run the whole conversion. Returns ``(result, status)``."""
    python_path = str(data.get('pythonPath', '') or '')
    exe_name = safe_exe_name(data.get('exeName', 'MyApp'))
    hide_console = bool(data.get('hideConsole', True))
    single_file = bool(data.get('singleFile', True))
    optimize = bool(data.get('optimize', False))

    print(f'Python project: {python_path}')
    print(f'EXE name: {exe_name}   hide console: {hide_console}   single file: {single_file}')

    if not python_path or not os.path.exists(python_path):
        return {'error': f'Python project path not found: {python_path}'}, 404
    python_path = os.path.abspath(python_path)

    if os.path.isfile(python_path):           # allow picking the script itself
        if not python_path.endswith('.py'):
            return {'error': 'Pick a .py file or a folder that contains one.'}, 400
        entry = os.path.basename(python_path)
        python_path = os.path.dirname(python_path)
        py_files = sorted(f for f in os.listdir(python_path) if f.endswith('.py'))
    else:
        entry, py_files = find_entry_point(python_path)
    if not entry:
        return {'error': 'No Python (.py) files found in the project folder. Please ensure your '
                         'project has a main.py, app.py, or other Python file.'}, 400
    entry_path = os.path.join(python_path, entry)
    print(f'Entry point: {entry}')

    imports = detect_imports(python_path, py_files)
    hidden = [m for m in HIDDEN_IMPORT_CANDIDATES if m in imports]
    for module in hidden:
        print(f'  Detected import: {module}')
    datas = find_data_entries(python_path)
    for src, dest in datas:
        print(f'  Bundling data: {os.path.basename(src)} -> {dest}')

    home = os.path.expanduser('~')
    build_dir = os.path.join(home, 'Documents', 'HTMLToExe_PythonBuilds', exe_name)
    output_dir = data.get('outputDir') or os.path.join(home, 'Downloads')
    os.makedirs(os.path.join(build_dir, 'build'), exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    icon = _prepare_icon(data.get('iconData', ''), build_dir, exe_name)
    spec_path = os.path.join(build_dir, f'{exe_name}.spec')
    with open(spec_path, 'w', encoding='utf-8') as fh:
        fh.write(build_spec(entry_path, python_path, exe_name, datas, hidden,
                            not hide_console, icon, single_file, optimize))
    print(f'Spec file: {spec_path}')

    cmd = python_for_pyinstaller() + [
        '-m', 'PyInstaller', f'--distpath={output_dir}',
        f'--workpath={os.path.join(build_dir, "build")}', '--noconfirm', '-y', spec_path]
    print('Running PyInstaller...')
    result = jobs.run(cmd, cwd=build_dir)
    if result.returncode != 0:
        tail = '\n'.join((result.stdout or '').strip().splitlines()[-10:])
        return {'error': f'PyInstaller build failed:\n{tail}'}, 500

    exe_path = (os.path.join(output_dir, f'{exe_name}.exe') if single_file
                else os.path.join(output_dir, exe_name, f'{exe_name}.exe'))
    if not os.path.isfile(exe_path):
        return {'error': f'The EXE was not created at {exe_path}. See the log for details.'}, 500
    size = os.path.getsize(exe_path) / (1024 * 1024)
    print(f'BUILD SUCCESSFUL: {exe_path} ({size:.2f} MB)')
    where = 'Downloads/' if single_file else f'Downloads/{exe_name}/'
    return {'success': True, 'message': f'Python to EXE conversion successful! EXE is in {where}',
            'exePath': exe_path, 'exeName': f'{exe_name}.exe', 'size': f'{size:.2f} MB'}, 200
