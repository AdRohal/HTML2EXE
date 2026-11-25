"""Build a Windows EXE from a web / PHP project."""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

from . import installer, jobs, recipes, secrets, workspace
from .launcher import render_launcher
from .recipes import BuildError
from .security import project_dir_for

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:  # pragma: no cover
    HAS_PILLOW = False

def _ignore_with_env(*patterns):
    """shutil ignore function: the given patterns plus every real env file (.env, .env.local ...)."""
    base = shutil.ignore_patterns(*patterns)

    def ignore(folder, names):
        skipped = set(base(folder, names))
        skipped.update(n for n in names if secrets.is_env_file_name(n))
        return skipped
    return ignore


STAGE_IGNORE = _ignore_with_env('node_modules', '.git', '.github', '__pycache__', '.vscode', '.idea', '*.log')
PHP_STAGE_IGNORE = _ignore_with_env('node_modules', '.git', '.github', '__pycache__', '.vscode', '.idea', '*.log',
                                    'tests', '.phpunit.cache')
# A standalone Next.js server needs its own (trimmed) node_modules.
NODE_STAGE_IGNORE = _ignore_with_env('.git', '.github', '__pycache__', '.vscode', '.idea', '*.log')


def prepare_node_runtime(build_dir, job):
    """Copy the node.exe that built the project next to the build; returns (folder, version)."""
    node = shutil.which('node')
    if not node:
        raise BuildError('Node.js is required to pack a server app, but it was not found. '
                         'Install the LTS version from https://nodejs.org and try again.')
    target = os.path.join(build_dir, '_node')
    os.makedirs(target, exist_ok=True)
    dst = os.path.join(target, 'node.exe')
    if not (os.path.isfile(dst) and os.path.getsize(dst) == os.path.getsize(node)):
        job.log(f'Copying the Node.js runtime ({os.path.getsize(node) / (1024 * 1024):.0f} MB)...')
        shutil.copy2(node, dst)
    try:
        version = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        version = ''
    return target, version


def safe_exe_name(name):
    cleaned = re.sub(r'[^A-Za-z0-9_.-]+', '_', name.strip()).strip('._')
    return cleaned or 'App'


def python_for_pyinstaller():
    """Return the python command that has PyInstaller (never the frozen builder)."""
    if not getattr(sys, 'frozen', False):
        return [sys.executable]
    for candidate in ('python', 'py'):
        path = shutil.which(candidate)
        if path:
            return [path]
    raise BuildError('Python was not found on PATH. Install Python 3.8+ and run: pip install pyinstaller pywebview')


def process_icon(icon_data, build_dir, exe_name, job):
    """Turn a data-URI (.ico/.png) into an .ico file; returns its path or None."""
    if not icon_data or not icon_data.startswith('data:'):
        return None
    try:
        header, b64 = icon_data.split(',', 1)
        raw = base64.b64decode(b64)
        is_png = 'png' in header
        tmp = os.path.join(build_dir, 'temp_icon.' + ('png' if is_png else 'ico'))
        with open(tmp, 'wb') as fh:
            fh.write(raw)
        if is_png:
            if not HAS_PILLOW:
                job.log('WARNING: Pillow is missing, so the PNG icon cannot be converted. Use an .ico file.')
                return None
            img = Image.open(tmp).convert('RGBA')
            side = max(img.size)
            square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
            square.paste(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
            ico = os.path.join(build_dir, exe_name + '.ico')
            square.save(ico, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
            os.remove(tmp)
            job.log('Icon converted to .ico')
            return ico
        return tmp
    except Exception as exc:
        job.log(f'WARNING: could not use the icon ({exc}); building without it')
        return None


def stage_copy(src, dst, ignore):
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=ignore)
    return dst


def _build_exe(data, job):
    """Run the whole HTML/framework/PHP -> EXE pipeline. Returns a result dict."""
    project_name = (data.get('projectName') or '').strip()
    project_id = data.get('projectId') or ''
    options = data.get('options') or {}
    if not project_name or not project_id:
        return {'success': False, 'error': 'Project name and ID are required'}

    metadata_dir = project_dir_for(project_id)
    if metadata_dir is None:
        return {'success': False, 'error': 'Invalid project ID'}
    meta_path = os.path.join(metadata_dir, 'project.json')
    if not os.path.isfile(meta_path):
        return {'success': False, 'error': 'Project metadata not found'}
    with open(meta_path, 'r', encoding='utf-8') as fh:
        meta = json.load(fh)

    project_folder = meta.get('downloadFolder', '')
    if not os.path.isdir(project_folder):
        alt = meta.get('sourceFolder', '')
        if alt and os.path.isdir(alt):
            job.log(f'Working copy missing, using the original folder: {alt}')
            project_folder = alt
        else:
            return {'success': False, 'error': f'Project folder not found: {project_folder}'}

    job.log(f'Building "{project_name}" from {project_folder}')

    # -- environment files ------------------------------------------------------------------------------
    # Read from the ORIGINAL folder and handed to the build through its environment. They are never copied
    # into the working copy, the staged bundle or the log (values are redacted).
    source_folder = meta.get('sourceFolder') or ''
    env_values, env_sources = secrets.load_project_env(source_folder)
    source_exists = bool(source_folder) and os.path.isdir(source_folder)
    working_is_source = source_exists and os.path.realpath(source_folder) == os.path.realpath(project_folder)
    if source_exists and not working_is_source:
        for name in os.listdir(project_folder):               # copies left by older versions
            full = os.path.join(project_folder, name)
            if secrets.is_env_file_name(name) and os.path.isfile(full):
                os.remove(full)
    elif not env_values:
        env_values, env_sources = secrets.load_project_env(project_folder)
    job.build_env = dict(env_values)
    job.add_secrets(secrets.secret_values(env_values))
    if env_values:
        files = ', '.join(sorted(set(env_sources.values())))
        job.log(f'Found {len(env_values)} environment variable(s) in {files}. Values are never shown or logged.')

    try:
        plan = recipes.prepare(project_folder, job, options.get('nextMode') or 'auto')
    except BuildError as exc:
        return {'success': False, 'error': str(exc)}
    job.check_cancelled()

    build_dir = os.path.join(metadata_dir, 'build')
    os.makedirs(build_dir, exist_ok=True)
    exe_name = safe_exe_name(project_name)
    output_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
    os.makedirs(output_dir, exist_ok=True)

    # -- decide what to bundle ----------------------------------------------
    source_dir = plan['source_dir']
    needs_stage = plan['kind'] in ('php', 'node') or any(
        os.path.isdir(os.path.join(source_dir, name)) for name in ('node_modules', '.git'))
    if needs_stage:
        job.log('Preparing a clean copy of the project to bundle...')
        ignore = {'php': PHP_STAGE_IGNORE, 'node': NODE_STAGE_IGNORE}.get(plan['kind'], STAGE_IGNORE)
        source_dir = stage_copy(source_dir, os.path.join(build_dir, 'stage'), ignore)
    if not os.path.isdir(source_dir):
        return {'success': False, 'error': f'Nothing to bundle: {source_dir}'}

    # -- secrets must not be sitting in plain text inside the files we are about to bundle --------------------
    leaks = []
    if plan['kind'] in ('static', 'node') and env_values:
        real_secrets = {k: v for k, v in env_values.items() if secrets.classify(k, v)[0] == 'secret'}
        for name, files in sorted(secrets.find_leaks(source_dir, real_secrets).items()):
            leaks.append({'name': name, 'files': files[:3], 'count': len(files)})
            job.log(f'WARNING: the value of {name} appears as plain text in {len(files)} built file(s), '
                    f'for example {files[0]}. It will be readable inside the .exe.')

    php_dir = None
    if plan['kind'] == 'php':
        from .php_runtime import ensure_php
        try:
            php_dir = ensure_php(job)
        except BuildError as exc:
            return {'success': False, 'error': str(exc)}

    node_dir = None
    if plan['kind'] == 'node':
        try:
            node_dir, node_version = prepare_node_runtime(build_dir, job)
        except BuildError as exc:
            return {'success': False, 'error': str(exc)}
        job.log(f'Server app: Node.js {node_version} will run inside the .exe')

    # -- launcher ------------------------------------------------------------
    app_id = 'H2E-' + exe_name
    build_id = uuid.uuid4().hex
    as_installer = options.get('outputType') == 'installer'
    engine = 'builtin'
    if as_installer:
        try:
            engine = installer.resolve_engine(options.get('installerEngine') or 'auto')
        except RuntimeError as exc:
            return {'success': False, 'error': str(exc)}
        job.log(f'Installer engine: {"Inno Setup" if engine == "inno" else "built-in"}')
    config = {
        'title': project_name,
        'mode': plan['kind'],
        'app_id': app_id,
        'build_id': build_id,
        'width': int(options.get('windowWidth') or 1100),
        'height': int(options.get('windowHeight') or 760),
        'resizable': options.get('resizable', True) is not False,
        'fullscreen': bool(options.get('fullscreen', False)),
        'php_framework': plan['php_framework'],
        'php_docroot': plan['php_docroot'],
        'node_entry': (plan.get('node_entry') or '').replace('/', os.sep),
        'user_env': plan['kind'] == 'node',
        'installer': as_installer and engine == 'builtin',     # the built-in installer's app can uninstall itself
        'app_key': exe_name,
    }

    # -- secrets: encrypted at build time, decrypted in memory by the launcher ------------------------------
    secrets_blob = os.path.join(build_dir, 'secrets.bin')
    if os.path.isfile(secrets_blob):
        os.remove(secrets_blob)                                # never reuse a blob from an earlier build
    secret_report = {'bundled': 0, 'excluded': 0, 'encrypted': False, 'mode': options.get('envMode') or 'bundle'}
    if plan['kind'] == 'node' and env_values:
        exclude = set(options.get('envExclude') or [])
        runtime = {k: v for k, v in env_values.items() if k not in exclude}
        secret_report['excluded'] = len(env_values) - len(runtime)
        if secret_report['mode'] != 'none' and runtime:
            blob, share = secrets.encrypt_env(runtime, f'{app_id}:{build_id}')
            with open(secrets_blob, 'wb') as fh:
                fh.write(blob)
            config['has_secrets'] = True
            config['secret_share'] = base64.b64encode(share).decode('ascii')
            secret_report.update(bundled=len(runtime), encrypted=True)
            job.log(f'{len(runtime)} variable(s) encrypted (AES-256-GCM) and bundled into the app')
        elif secret_report['mode'] == 'none':
            job.log('Secrets are NOT bundled: the app reads its own .env file from its data folder')
    launcher_path = os.path.join(build_dir, 'main.py')
    with open(launcher_path, 'w', encoding='utf-8') as fh:
        fh.write(render_launcher(config))

    icon_path = process_icon(data.get('iconData'), build_dir, exe_name, job)

    # -- PyInstaller -----------------------------------------------------------
    work = os.path.join(build_dir, 'work')
    os.makedirs(work, exist_ok=True)
    app_out = os.path.join(build_dir, 'dist') if as_installer else output_dir
    os.makedirs(app_out, exist_ok=True)
    cmd = python_for_pyinstaller() + [
        '-m', 'PyInstaller', '--onefile', '--windowed', '--noupx', '-y',
        f'--name={exe_name}', f'--distpath={app_out}', f'--workpath={work}', f'--specpath={build_dir}',
        '--hidden-import=webview', '--hidden-import=webview.js', '--hidden-import=winreg',
        f'--add-data={source_dir}{os.pathsep}_project',
    ]
    if php_dir:
        cmd.append(f'--add-data={php_dir}{os.pathsep}_php')
    if node_dir:
        cmd.append(f'--add-data={node_dir}{os.pathsep}_node')
    if secret_report['encrypted']:
        cmd += [f'--add-data={secrets_blob}{os.pathsep}_secrets',
                '--hidden-import=cryptography.hazmat.primitives.ciphers.aead']
    if icon_path and os.path.exists(icon_path):
        cmd.append(f'--icon={os.path.abspath(icon_path)}')
    cmd.append(launcher_path)

    job.log('Packaging with PyInstaller (this takes 1-3 minutes)...')
    t0 = time.time()
    code = job.run_cmd(cmd, cwd=build_dir)
    if code != 0:
        return {'success': False, 'error': 'PyInstaller failed. See the log for details. '
                                           '(Is it installed? Run: pip install pyinstaller pywebview)'}

    exe_path = os.path.join(app_out, exe_name + '.exe')
    if not os.path.isfile(exe_path):
        return {'success': False, 'error': 'PyInstaller finished but the EXE was not created.'}
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    job.log(f'EXE built in {time.time() - t0:.0f}s ({size_mb:.1f} MB): {exe_path}')

    result = {'success': True, 'message': 'EXE created successfully!', 'exePath': exe_path,
              'exeName': exe_name + '.exe', 'framework': plan['framework'], 'sizeMb': round(size_mb, 1),
              'notes': plan['notes'], 'server': plan['kind'] == 'node', 'secrets': secret_report, 'leaks': leaks}
    result['selfTest'] = self_test(exe_path, build_dir, job,
                                   timeout=300 if plan['kind'] in ('php', 'node') else 90)
    result['kind'] = 'installer' if as_installer else 'portable'
    if as_installer:
        version = options.get('appVersion') or meta.get('version') or '1.0.0'
        publisher = options.get('publisher') or meta.get('author') or ''
        try:
            setup_path = installer.build_installer(job, build_dir, exe_path, exe_name, project_name, version,
                                                   publisher, icon_path, output_dir, engine)
        except RuntimeError as exc:
            return {'success': False, 'error': str(exc)}
        setup_mb = os.path.getsize(setup_path) / (1024 * 1024)
        check = installer.self_test(setup_path, build_dir, job) if engine == 'builtin' else {'ok': True}
        job.log(f'Installer ready ({setup_mb:.1f} MB): {setup_path}')
        result.update({'message': 'Installer created successfully!', 'exePath': setup_path,
                       'exeName': os.path.basename(setup_path), 'sizeMb': round(setup_mb, 1),
                       'appSizeMb': round(size_mb, 1),
                       'installer': {'verified': check['ok'], 'version': installer.normalize_version(version),
                                     'publisher': installer.clean_publisher(publisher),
                                     'engine': engine,
                                     'silent': os.path.basename(setup_path) + (' /VERYSILENT' if engine == 'inno' else ' /S')}})
    return result


def build_exe(data, job):
    """Build the EXE (or installer) for a project. Returns a result dict.

    The working copy in Downloads is temporary: it is (re)created here, build caches are restored from
    ``Documents\\HTML2EXE\\<name>\\cache`` and parked there again afterwards, and the copy is deleted.
    """
    options = data.get('options') or {}
    metadata_dir = project_dir_for(data.get('projectId') or '')
    meta, working, source, cache_dir = {}, '', '', ''
    if metadata_dir and os.path.isfile(os.path.join(metadata_dir, 'project.json')):
        try:
            with open(os.path.join(metadata_dir, 'project.json'), 'r', encoding='utf-8') as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            meta = {}
        working, source = meta.get('downloadFolder') or '', meta.get('sourceFolder') or ''
        cache_dir = os.path.join(metadata_dir, 'cache')
    separate = bool(working and source and os.path.isdir(source)
                    and os.path.realpath(working) != os.path.realpath(source))
    try:
        if separate:
            if not os.path.isdir(working):
                job.log('Preparing a fresh working copy of your project...')
                workspace.sync_working_copy(source, working, log=job.log)
            workspace.restore_cache(cache_dir, working)
        result = _build_exe(data, job)
    finally:
        if separate:
            workspace.stash_cache(working, cache_dir)
            if workspace.remove_working_copy(working, source):
                job.log('Temporary working copy removed from Downloads')
    if result.get('success') and metadata_dir and not options.get('keepWorkFiles'):
        workspace.clean_build_files(os.path.join(metadata_dir, 'build'))
    return result


def self_test(exe_path, build_dir, job, probes=('/',), timeout=90):
    """Start the built EXE in self-test mode and verify it serves the app."""
    out_file = os.path.join(build_dir, 'selftest.json')
    if os.path.exists(out_file):
        os.remove(out_file)
    job.log('Verifying the new EXE starts and serves your app...')
    try:
        proc = subprocess.Popen([exe_path, f'--selftest-out={out_file}', '--selftest-probe=' + ','.join(probes)],
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            jobs._kill_tree(proc)        # also stops a php.exe child, not just the launcher
            proc.wait()
            raise
        with open(out_file, 'r', encoding='utf-8') as fh:
            report = json.load(fh)
    except Exception as exc:
        job.log(f'WARNING: self-test could not run ({exc}).')
        return {'ok': False, 'error': str(exc)}
    bad = [r for r in report['results'] if r.get('status') != 200]
    ok = not bad
    job.log('Self-test passed: the EXE serves your app.' if ok
            else f'WARNING: self-test got non-200 responses: {bad}')
    return {'ok': ok, 'results': report['results']}
