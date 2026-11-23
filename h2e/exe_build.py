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

from . import recipes
from .launcher import render_launcher
from .recipes import BuildError
from .security import project_dir_for

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:  # pragma: no cover
    HAS_PILLOW = False

STAGE_IGNORE = shutil.ignore_patterns('node_modules', '.git', '.github', '__pycache__', '.vscode', '.idea',
                                      '.env', '*.log')
PHP_STAGE_IGNORE = shutil.ignore_patterns('node_modules', '.git', '.github', '__pycache__', '.vscode',
                                          '.idea', '.env', '*.log', 'tests', '.phpunit.cache')


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


def build_exe(data, job):
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
    try:
        plan = recipes.prepare(project_folder, job)
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
    needs_stage = plan['kind'] == 'php' or any(
        os.path.isdir(os.path.join(source_dir, name)) for name in ('node_modules', '.git'))
    if needs_stage:
        job.log('Preparing a clean copy of the project to bundle...')
        source_dir = stage_copy(source_dir, os.path.join(build_dir, 'stage'),
                                PHP_STAGE_IGNORE if plan['kind'] == 'php' else STAGE_IGNORE)
    if not os.path.isdir(source_dir):
        return {'success': False, 'error': f'Nothing to bundle: {source_dir}'}

    php_dir = None
    if plan['kind'] == 'php':
        from .php_runtime import ensure_php
        try:
            php_dir = ensure_php(job)
        except BuildError as exc:
            return {'success': False, 'error': str(exc)}

    # -- launcher ------------------------------------------------------------
    config = {
        'title': project_name,
        'mode': plan['kind'],
        'app_id': 'H2E-' + exe_name,
        'build_id': uuid.uuid4().hex,
        'width': int(options.get('windowWidth') or 1100),
        'height': int(options.get('windowHeight') or 760),
        'resizable': options.get('resizable', True) is not False,
        'fullscreen': bool(options.get('fullscreen', False)),
        'php_framework': plan['php_framework'],
        'php_docroot': plan['php_docroot'],
    }
    launcher_path = os.path.join(build_dir, 'main.py')
    with open(launcher_path, 'w', encoding='utf-8') as fh:
        fh.write(render_launcher(config))

    icon_path = process_icon(data.get('iconData'), build_dir, exe_name, job)

    # -- PyInstaller -----------------------------------------------------------
    work = os.path.join(build_dir, 'work')
    os.makedirs(work, exist_ok=True)
    cmd = python_for_pyinstaller() + [
        '-m', 'PyInstaller', '--onefile', '--windowed', '--noupx', '-y',
        f'--name={exe_name}', f'--distpath={output_dir}', f'--workpath={work}', f'--specpath={build_dir}',
        '--hidden-import=webview', '--hidden-import=webview.js', '--hidden-import=winreg',
        f'--add-data={source_dir}{os.pathsep}_project',
    ]
    if php_dir:
        cmd.append(f'--add-data={php_dir}{os.pathsep}_php')
    if icon_path and os.path.exists(icon_path):
        cmd.append(f'--icon={os.path.abspath(icon_path)}')
    cmd.append(launcher_path)

    job.log('Packaging with PyInstaller (this takes 1-3 minutes)...')
    t0 = time.time()
    code = job.run_cmd(cmd, cwd=build_dir)
    if code != 0:
        return {'success': False, 'error': 'PyInstaller failed. See the log for details. '
                                           '(Is it installed? Run: pip install pyinstaller pywebview)'}

    exe_path = os.path.join(output_dir, exe_name + '.exe')
    if not os.path.isfile(exe_path):
        return {'success': False, 'error': 'PyInstaller finished but the EXE was not created.'}
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    job.log(f'EXE built in {time.time() - t0:.0f}s ({size_mb:.1f} MB): {exe_path}')

    result = {'success': True, 'message': 'EXE created successfully!', 'exePath': exe_path,
              'exeName': exe_name + '.exe', 'framework': plan['framework'], 'sizeMb': round(size_mb, 1),
              'notes': plan['notes']}
    result['selfTest'] = self_test(exe_path, build_dir, job)
    return result


def self_test(exe_path, build_dir, job, probes=('/',), timeout=90):
    """Start the built EXE in self-test mode and verify it serves the app."""
    out_file = os.path.join(build_dir, 'selftest.json')
    if os.path.exists(out_file):
        os.remove(out_file)
    job.log('Verifying the new EXE starts and serves your app...')
    try:
        subprocess.run([exe_path, f'--selftest-out={out_file}', '--selftest-probe=' + ','.join(probes)],
                       timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
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
