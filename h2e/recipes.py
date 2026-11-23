"""Framework recipes: detect a project, build it, and locate the static output.

Every recipe boils down to: *install -> build -> find the folder to serve*.
PHP/Laravel are the exception: they are not static, so the plan tells the EXE
builder to bundle a PHP runtime instead.
"""
import json
import os
import re
import shutil
import sys

SKIP_DIRS = {'node_modules', '.git', '.next', '.nuxt', '.svelte-kit', '.astro', '.output',
             '__pycache__', '.venv', 'venv', 'coverage', '.idea', '.vscode'}
OUTPUT_DIR_NAMES = ('dist', 'build', 'out', 'public')

# framework id -> (label, support level)
FRAMEWORKS = {
    'static':    ('Plain HTML / pre-built site', 'supported'),
    'vite':      ('Vite (React / Vue / Svelte / Solid / Preact)', 'supported'),
    'cra':       ('Create React App', 'supported'),
    'astro':     ('Astro (static output)', 'supported'),
    'nextjs':    ('Next.js (static export)', 'supported'),
    'nuxt':      ('Nuxt (nuxt generate)', 'supported'),
    'angular':   ('Angular', 'supported'),
    'gatsby':    ('Gatsby', 'supported'),
    'sveltekit': ('SvelteKit (adapter-static)', 'supported'),
    'generic':   ('Node project with a build script', 'supported'),
    'php':       ('PHP', 'experimental'),
    'laravel':   ('Laravel', 'experimental'),
}


class BuildError(Exception):
    """A build problem with a message that is safe to show to the user."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def read_package_json(folder):
    path = os.path.join(folder, 'package.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8-sig') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _deps(pkg):
    out = {}
    for key in ('dependencies', 'devDependencies'):
        out.update((pkg or {}).get(key, {}) or {})
    return out


def _exists(folder, *parts):
    return os.path.exists(os.path.join(folder, *parts))


def _has_html(folder):
    try:
        return any(name.lower().endswith('.html') for name in os.listdir(folder)
                   if os.path.isfile(os.path.join(folder, name)))
    except OSError:
        return False


def _is_site_dir(folder):
    return os.path.isdir(folder) and (_exists(folder, 'index.html') or _has_html(folder)
                                      or _exists(folder, '_next') or _exists(folder, '_nuxt')
                                      or _exists(folder, '_astro'))


def _read_text(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def _config_text(folder, stem):
    for ext in ('js', 'mjs', 'cjs', 'ts', 'mts'):
        path = os.path.join(folder, f'{stem}.config.{ext}')
        if os.path.isfile(path):
            return _read_text(path)
    return ''


def newest_mtime(folder, names=None):
    """Newest modification time of source files (skips build output & deps)."""
    newest = 0.0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d not in OUTPUT_DIR_NAMES]
        for name in files:
            if names and root == folder and name not in names and not name.endswith(('.js', '.ts', '.mjs', '.cjs', '.json', '.html')):
                continue
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
            except OSError:
                pass
    return newest


def output_is_fresh(folder, output):
    index = os.path.join(output, 'index.html')
    stamp = os.path.getmtime(index) if os.path.isfile(index) else 0
    return stamp > 0 and stamp >= newest_mtime(folder)


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------
def detect(folder):
    """Return ``{'framework': id, 'label': str, 'support': str, 'notes': [...]}``."""
    folder = os.path.abspath(folder)
    notes = []
    pkg = read_package_json(folder)
    deps = _deps(pkg)
    scripts = (pkg or {}).get('scripts', {}) or {}

    framework = None
    if _exists(folder, 'artisan') or 'laravel/framework' in _read_text(os.path.join(folder, 'composer.json')):
        framework = 'laravel'
    elif pkg is None and (_exists(folder, 'index.php') or _exists(folder, 'public', 'index.php')):
        framework = 'php'
    elif pkg is not None:
        if 'next' in deps:
            framework = 'nextjs'
        elif 'astro' in deps:
            framework = 'astro'
        elif 'nuxt' in deps or 'nuxt3' in deps:
            framework = 'nuxt'
        elif '@angular/core' in deps:
            framework = 'angular'
        elif 'gatsby' in deps:
            framework = 'gatsby'
        elif '@sveltejs/kit' in deps:
            framework = 'sveltekit'
        elif 'react-scripts' in deps:
            framework = 'cra'
        elif 'vite' in deps:
            framework = 'vite'
        elif 'build' in scripts:
            framework = 'generic'
        else:
            framework = 'static'
    else:
        framework = 'static'

    if framework in ('nextjs',) and (_exists(folder, 'app', 'api') or _exists(folder, 'pages', 'api')
                                     or _exists(folder, 'src', 'app', 'api') or _exists(folder, 'src', 'pages', 'api')):
        notes.append('This Next.js app has API routes. They do not work in a desktop EXE '
                     '(there is no server) and can make the static export fail.')
    if framework == 'astro':
        cfg = _config_text(folder, 'astro')
        if re.search(r"output\s*:\s*['\"]server['\"]", cfg):
            notes.append("astro.config uses output: 'server' (SSR). Switch to the default static output to build an EXE.")

    label, support = FRAMEWORKS[framework]
    return {'framework': framework, 'label': label, 'support': support, 'notes': notes}


# ---------------------------------------------------------------------------
# build steps
# ---------------------------------------------------------------------------
def _tool(name):
    return shutil.which(name) or shutil.which(name + '.cmd')


def _node_env(extra=None):
    env = os.environ.copy()
    env.update({'NEXT_TELEMETRY_DISABLED': '1', 'ASTRO_TELEMETRY_DISABLED': '1',
                'NUXT_TELEMETRY_DISABLED': '1', 'CI': 'false', 'FORCE_COLOR': '0',
                'NO_COLOR': '1', 'npm_config_fund': 'false', 'npm_config_audit': 'false'})
    env.update(extra or {})
    return env


def _require_node():
    if not _tool('npm'):
        raise BuildError('Node.js is required to build this kind of project, but it was not found. '
                         'Install the LTS version from https://nodejs.org and try again.')


def _npm_install(folder, job):
    if os.path.isdir(os.path.join(folder, 'node_modules')):
        job.log('node_modules already present - skipping install')
        return
    _require_node()
    lock = os.path.isfile(os.path.join(folder, 'package-lock.json'))
    cmd = 'npm ci --no-audit --no-fund' if lock else 'npm install --no-audit --no-fund'
    job.log('Installing dependencies (first time can take a few minutes)...')
    code = job.run_cmd(cmd, cwd=folder, env=_node_env(), shell=True)
    if code != 0 and lock:
        job.log('npm ci failed - retrying with npm install')
        code = job.run_cmd('npm install --no-audit --no-fund', cwd=folder, env=_node_env(), shell=True)
    if code != 0:
        raise BuildError('npm install failed. See the log above for the reason.')


def _npm_script(folder, job, script, env=None, fallback_cmd=None):
    pkg = read_package_json(folder) or {}
    if script in (pkg.get('scripts') or {}):
        cmd = f'npm run {script}'
    elif fallback_cmd:
        cmd = fallback_cmd
    else:
        raise BuildError(f"package.json has no '{script}' script.")
    job.log(f'Building with: {cmd}')
    code = job.run_cmd(cmd, cwd=folder, env=_node_env(env), shell=True)
    if code != 0:
        raise BuildError(f'"{cmd}" failed. See the log above for the reason.')


def find_output(folder, framework=None):
    """Locate the static build output for a project folder, or None."""
    candidates = []
    if framework == 'nuxt':
        candidates += [os.path.join(folder, '.output', 'public'), os.path.join(folder, 'dist')]
    if framework == 'sveltekit':
        candidates += [os.path.join(folder, 'build')]
    if framework == 'gatsby':
        candidates += [os.path.join(folder, 'public')]
    for name in ('out', 'dist', 'build'):
        candidates.append(os.path.join(folder, name))
    candidates += [os.path.join(folder, 'dist', 'client'), os.path.join(folder, '.output', 'public')]
    for path in candidates:
        if _is_site_dir(path):
            return path
    # Angular: dist/<project>/browser  or  dist/<project>
    dist = os.path.join(folder, 'dist')
    if os.path.isdir(dist):
        for sub in sorted(os.listdir(dist)):
            for path in (os.path.join(dist, sub, 'browser'), os.path.join(dist, sub)):
                if os.path.isdir(path) and _exists(path, 'index.html'):
                    return path
    return None


def _build_generic(folder, job, framework, env=None):
    """install -> build -> locate output (reusing a fresh earlier build)."""
    out = find_output(folder, framework)
    pkg = read_package_json(folder) or {}
    has_build = 'build' in (pkg.get('scripts') or {})
    if out and (output_is_fresh(folder, out) or not has_build):
        job.log(f'Using existing build output: {out}')
        return out
    _npm_install(folder, job)
    _npm_script(folder, job, 'build', env=env)
    out = find_output(folder, framework)
    if not out:
        raise BuildError('The build finished but no output folder (dist, build, out ...) with an '
                         'index.html was found.')
    return out


def _build_astro(folder, job):
    cfg = _config_text(folder, 'astro')
    if re.search(r"output\s*:\s*['\"]server['\"]", cfg):
        raise BuildError("This Astro project uses output: 'server' (server-side rendering). A desktop EXE has "
                         "no server, so please switch astro.config to the default static output "
                         "(remove the adapter and the output: 'server' line) and try again.")
    return _build_generic(folder, job, 'astro')


def _build_nextjs(folder, job):
    out = os.path.join(folder, 'out')
    pkg = read_package_json(folder) or {}
    if _is_site_dir(out) and output_is_fresh(folder, out):
        job.log(f'Using existing static export: {out}')
        return out
    _npm_install(folder, job)

    backups = []          # (kept_original_path, original_path)
    wrapper_path = os.path.join(folder, 'next.config.mjs')
    if os.path.isfile(os.path.join(folder, 'next.config.ts')):
        raise BuildError('next.config.ts is not supported yet. Rename it to next.config.mjs (or .js) '
                         'and set output: "export", then try again.')
    original_name = None
    for name in ('next.config.js', 'next.config.mjs', 'next.config.cjs'):
        if os.path.isfile(os.path.join(folder, name)):
            original_name = name
            break
    try:
        if original_name:
            ext = original_name.rsplit('.', 1)[1]
            kept = os.path.join(folder, f'next.config.h2e-original.{ext}')
            os.replace(os.path.join(folder, original_name), kept)
            backups.append((kept, os.path.join(folder, original_name)))
            source = (
                "// Generated by HTML2EXE - restored after the build\n"
                f"import original from './next.config.h2e-original.{ext}';\n"
                "export default async (phase, ctx) => {\n"
                "  const base = typeof original === 'function' ? await original(phase, ctx) : (original || {});\n"
                "  return { ...base, output: 'export', images: { ...(base.images || {}), unoptimized: true } };\n"
                "};\n")
        else:
            source = ("// Generated by HTML2EXE - removed after the build\n"
                      "export default { output: 'export', images: { unoptimized: true } };\n")
        with open(wrapper_path, 'w', encoding='utf-8') as fh:
            fh.write(source)
        job.log('Temporarily configured Next.js for static export (restored afterwards)')
        _npm_script(folder, job, 'build', fallback_cmd='npx next build')
    finally:
        if os.path.isfile(wrapper_path):
            os.remove(wrapper_path)
        for kept, original in backups:
            if os.path.isfile(kept):
                os.replace(kept, original)
    if not _is_site_dir(out):
        raise BuildError('Next.js finished but produced no "out" folder. This usually means the app uses '
                         'server features (API routes, getServerSideProps, middleware) that cannot be '
                         'exported statically.')
    return out


def _build_sveltekit(folder, job):
    deps = _deps(read_package_json(folder))
    if '@sveltejs/adapter-static' not in deps:
        raise BuildError('SvelteKit needs the static adapter to become a desktop app. Run '
                         '"npm i -D @sveltejs/adapter-static", use it in svelte.config.js, add '
                         '"export const prerender = true" to src/routes/+layout.js, then try again.')
    return _build_generic(folder, job, 'sveltekit')


def _build_nuxt(folder, job):
    out = find_output(folder, 'nuxt')
    if out and output_is_fresh(folder, out):
        job.log(f'Using existing build output: {out}')
        return out
    _npm_install(folder, job)
    scripts = (read_package_json(folder) or {}).get('scripts') or {}
    if 'generate' in scripts:
        _npm_script(folder, job, 'generate')
    else:
        _npm_script(folder, job, 'build', fallback_cmd='npx nuxt generate')
        if not find_output(folder, 'nuxt'):
            job.log('npm run build did not produce static files - trying: npx nuxt generate')
            _npm_script(folder, job, 'generate', fallback_cmd='npx nuxt generate')
    out = find_output(folder, 'nuxt')
    if not out:
        raise BuildError('Nuxt did not produce static output. Make sure "nuxt generate" works for your app.')
    return out


def _build_laravel(folder, job):
    if not _exists(folder, 'vendor', 'autoload.php'):
        composer = _tool('composer')
        if not composer:
            raise BuildError('This Laravel project has no vendor/ folder and Composer was not found. '
                             'Run "composer install --no-dev" in the project first (https://getcomposer.org), '
                             'then try again.')
        job.log('Installing PHP dependencies with Composer...')
        code = job.run_cmd('composer install --no-dev --optimize-autoloader --no-interaction',
                           cwd=folder, shell=True)
        if code != 0:
            raise BuildError('composer install failed. See the log above.')
    pkg = read_package_json(folder)
    if pkg and 'build' in (pkg.get('scripts') or {}) and not _exists(folder, 'public', 'build'):
        job.log('Building front-end assets (npm run build)...')
        try:
            _npm_install(folder, job)
            _npm_script(folder, job, 'build')
        except BuildError as exc:
            job.log(f'WARNING: front-end build failed ({exc}). The app may be missing CSS/JS.')
    return folder


def prepare(folder, job):
    """Build whatever is needed and return the plan for the EXE builder.

    Plan keys: kind ('static'|'php'), framework, source_dir (folder to bundle),
    php_framework, php_docroot, notes.
    """
    folder = os.path.abspath(folder)
    info = detect(folder)
    framework = info['framework']
    job.log(f"Detected: {info['label']} [{info['support']}]")
    for note in info['notes']:
        job.log(f'NOTE: {note}')

    plan = {'framework': framework, 'kind': 'static', 'notes': list(info['notes']),
            'php_framework': None, 'php_docroot': '.', 'source_dir': folder}

    if framework in ('php', 'laravel'):
        plan['kind'] = 'php'
        plan['php_framework'] = framework
        if framework == 'laravel':
            _build_laravel(folder, job)
            plan['php_docroot'] = 'public'
        else:
            plan['php_docroot'] = 'public' if _exists(folder, 'public', 'index.php') else '.'
        return plan

    if framework == 'static':
        pkg = read_package_json(folder)
        if pkg is None and not _is_site_dir(folder):
            # A project folder that only contains a build output sub-folder
            out = find_output(folder)
            if out:
                plan['source_dir'] = out
                return plan
            raise BuildError('No index.html found in this folder. Pick the folder that contains your '
                             'index.html (for React/Vue/etc. pick the project folder itself).')
        out = find_output(folder) if not _exists(folder, 'index.html') else None
        plan['source_dir'] = out or folder
        return plan

    builders = {
        'astro': _build_astro, 'nextjs': _build_nextjs, 'sveltekit': _build_sveltekit,
        'nuxt': _build_nuxt,
        'vite': lambda f, j: _build_generic(f, j, 'vite'),
        'angular': lambda f, j: _build_generic(f, j, 'angular'),
        'gatsby': lambda f, j: _build_generic(f, j, 'gatsby'),
        'generic': lambda f, j: _build_generic(f, j, 'generic'),
        'cra': lambda f, j: _build_generic(f, j, 'cra', env={'PUBLIC_URL': '', 'GENERATE_SOURCEMAP': 'false'}),
    }
    plan['source_dir'] = builders[framework](folder, job)
    job.log(f"Static site folder: {plan['source_dir']}")
    return plan
