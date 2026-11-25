"""Framework recipes: detect a project, build it, and locate the static output.

Every recipe boils down to: *install -> build -> find the folder to serve*.
PHP/Laravel are the exception: they are not static, so the plan tells the EXE
builder to bundle a PHP runtime instead.
"""
import contextlib
import hashlib
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
def next_server_features(folder):
    """What in a Next.js app needs a running server: API routes, route handlers, middleware."""
    found = []
    for base in ('', 'src'):
        for sub in ('app', 'pages'):
            root = os.path.join(folder, base, sub)
            if not os.path.isdir(root):
                continue
            if os.path.isdir(os.path.join(root, 'api')):
                found.append('API routes')
            seen = 0
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for name in files:
                    seen += 1
                    if re.match(r'^route\.(js|jsx|ts|tsx|mjs)$', name) and sub == 'app':
                        found.append('route handlers')
                if seen > 3000:
                    break
        for name in ('middleware.ts', 'middleware.js', 'proxy.ts', 'proxy.js'):
            if os.path.isfile(os.path.join(folder, base, name)):
                found.append('middleware')
    return sorted(set(found))


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

    server_features = []
    if framework == 'nextjs':
        server_features = next_server_features(folder)
        if server_features:
            notes.append('This app uses server features (' + ', '.join(server_features) + '). It is packed with a '
                         'bundled Node.js server that runs inside the .exe (adds about 90 MB).')
    if framework == 'astro':
        cfg = _config_text(folder, 'astro')
        if re.search(r"output\s*:\s*['\"]server['\"]", cfg):
            notes.append("astro.config uses output: 'server' (SSR). Switch to the default static output to build an EXE.")

    label, support = FRAMEWORKS[framework]
    if framework == 'nextjs' and server_features:
        label = 'Next.js (server mode)'
    return {'framework': framework, 'label': label, 'support': support, 'notes': notes,
            'server': bool(server_features), 'serverFeatures': server_features}


# ---------------------------------------------------------------------------
# build steps
# ---------------------------------------------------------------------------
def _tool(name):
    return shutil.which(name) or shutil.which(name + '.cmd')


def _node_env(extra=None, job=None):
    env = os.environ.copy()
    env.update({'NEXT_TELEMETRY_DISABLED': '1', 'ASTRO_TELEMETRY_DISABLED': '1',
                'NUXT_TELEMETRY_DISABLED': '1', 'CI': 'false', 'FORCE_COLOR': '0',
                'NO_COLOR': '1', 'npm_config_fund': 'false', 'npm_config_audit': 'false'})
    # Variables from the project's .env files reach the build the way a shell would: they never override
    # the real environment. (The files themselves are not copied into the working copy.)
    for key, value in (getattr(job, 'build_env', None) or {}).items():
        env.setdefault(key, value)
    env.update(extra or {})
    return env


def _require_node():
    if not _tool('npm'):
        raise BuildError('Node.js is required to build this kind of project, but it was not found. '
                         'Install the LTS version from https://nodejs.org and try again.')


INSTALL_STAMP = '.h2e-install-hash'
LOCK_FILES = ('package.json', 'package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock', 'pnpm-lock.yaml')


def _install_hash(folder):
    digest = hashlib.sha256()
    for name in LOCK_FILES:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            with open(path, 'rb') as fh:
                digest.update(name.encode() + b'\0' + fh.read())
    return digest.hexdigest()


def _npm_install(folder, job):
    modules = os.path.join(folder, 'node_modules')
    stamp = os.path.join(modules, INSTALL_STAMP)
    want = _install_hash(folder)
    if os.path.isdir(modules):
        have = ''
        try:
            with open(stamp, encoding='utf-8') as fh:
                have = fh.read().strip()
        except OSError:
            pass
        if have == want:
            job.log('Dependencies unchanged - skipping install')
            return
        if not have:
            job.log('node_modules already present - skipping install')
            return
        job.log('package.json or the lock file changed - updating dependencies')
    _require_node()
    lock = os.path.isfile(os.path.join(folder, 'package-lock.json'))
    cmd = 'npm ci --no-audit --no-fund' if lock else 'npm install --no-audit --no-fund'
    job.log('Installing dependencies (first time can take a few minutes)...')
    code = job.run_cmd(cmd, cwd=folder, env=_node_env(job=job), shell=True)
    if code != 0 and lock:
        job.log('npm ci failed - retrying with npm install')
        code = job.run_cmd('npm install --no-audit --no-fund', cwd=folder, env=_node_env(job=job), shell=True)
    if code != 0:
        raise BuildError('npm install failed. See the log above for the reason.')
    try:
        with open(stamp, 'w', encoding='utf-8') as fh:
            fh.write(want)
    except OSError:
        pass


def _npm_script(folder, job, script, env=None, fallback_cmd=None):
    pkg = read_package_json(folder) or {}
    if script in (pkg.get('scripts') or {}):
        cmd = f'npm run {script}'
    elif fallback_cmd:
        cmd = fallback_cmd
    else:
        raise BuildError(f"package.json has no '{script}' script.")
    job.log(f'Building with: {cmd}')
    code = job.run_cmd(cmd, cwd=folder, env=_node_env(env, job), shell=True)
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


NEXT_CONFIG_NAMES = ('next.config.js', 'next.config.cjs', 'next.config.mjs', 'next.config.ts', 'next.config.mts')
STAMP_FILE = '.h2e-stamp.json'


def _recover_next_config(folder):
    """If an earlier build was killed half-way, put the user's next.config back before doing anything."""
    for name in NEXT_CONFIG_NAMES:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding='utf-8', errors='replace') as fh:
            head = fh.read(200)
        ext = name.rsplit('.', 1)[1]
        kept = os.path.join(folder, 'next.config.h2e-original.' + ext)
        if 'Generated by HTML2EXE' in head and os.path.isfile(kept):
            os.replace(kept, path)


@contextlib.contextmanager
def _next_config_output(folder, job, output):
    """Temporarily force Next's ``output`` ('export' or 'standalone'); the user's config is restored afterwards.

    Works for next.config.js / .cjs / .mjs / .ts / .mts: the original is moved aside and a small wrapper that
    imports it (and merges the one option) takes its place.
    """
    _recover_next_config(folder)
    original = next((n for n in NEXT_CONFIG_NAMES if os.path.isfile(os.path.join(folder, n))), None)
    original_path = os.path.join(folder, original) if original else None
    ext = original.rsplit('.', 1)[1] if original else ''
    backup = os.path.join(folder, 'next.config.h2e-original.' + ext) if original else None
    if output == 'export':
        merged = "{ ...base, output: 'export', images: { ...(base.images || {}), unoptimized: true } }"
        bare = "{ output: 'export', images: { unoptimized: true } }"
    else:
        merged = "{ ...base, output: 'standalone' }"
        bare = "{ output: 'standalone' }"
    wrapper = None
    try:
        if original:
            os.replace(original_path, backup)
        if original and ext in ('ts', 'mts'):
            wrapper = original_path
            source = ("// Generated by HTML2EXE - restored after the build\n"
                      "import original from './next.config.h2e-original';\n"
                      "export default async (phase: string, ctx: unknown) => {\n"
                      "  const base: any = typeof original === 'function' ? await (original as any)(phase, ctx) : (original || {});\n"
                      f"  return {merged};\n"
                      "};\n")
        elif original:
            wrapper = os.path.join(folder, 'next.config.mjs')
            source = ("// Generated by HTML2EXE - restored after the build\n"
                      f"import original from './next.config.h2e-original.{ext}';\n"
                      "export default async (phase, ctx) => {\n"
                      "  const base = typeof original === 'function' ? await original(phase, ctx) : (original || {});\n"
                      f"  return {merged};\n"
                      "};\n")
        else:
            wrapper = os.path.join(folder, 'next.config.mjs')
            source = f"// Generated by HTML2EXE - removed after the build\nexport default {bare};\n"
        with open(wrapper, 'w', encoding='utf-8') as fh:
            fh.write(source)
        yield
    finally:
        if wrapper and os.path.isfile(wrapper):
            os.remove(wrapper)
        if backup and os.path.isfile(backup):
            os.replace(backup, original_path)


def _env_fingerprint(job):
    """Identifies the build-time variables without storing any secret: public values + secret NAMES."""
    from . import secrets
    parts = []
    for key in sorted(getattr(job, 'build_env', None) or {}):
        kind = secrets.classify(key)[0]
        parts.append(key + '=' + (job.build_env[key] if kind == 'public' else '*'))
    return hashlib.sha256('\n'.join(parts).encode('utf-8')).hexdigest()[:16]


def _stamp_path(folder):
    return os.path.join(folder, STAMP_FILE)


def _stamp_read(folder):
    try:
        with open(_stamp_path(folder), encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _stamp_fresh(folder, mode, fingerprint):
    """True when the last ``mode`` build used the same variables and nothing in the sources is newer."""
    data = _stamp_read(folder)
    if data.get(mode) != fingerprint:
        return False
    try:
        return os.path.getmtime(_stamp_path(folder)) >= newest_mtime(folder)
    except OSError:
        return False


def _stamp_write(folder, mode, fingerprint):
    data = _stamp_read(folder)
    data[mode] = fingerprint
    with open(_stamp_path(folder), 'w', encoding='utf-8') as fh:
        json.dump(data, fh)


def _build_nextjs(folder, job):
    out = os.path.join(folder, 'out')
    fp = _env_fingerprint(job)
    if _is_site_dir(out) and output_is_fresh(folder, out) and _stamp_fresh(folder, 'export', fp):
        job.log(f'Using existing static export: {out}')
        return out
    _npm_install(folder, job)
    with _next_config_output(folder, job, 'export'):
        job.log('Temporarily configured Next.js for static export (restored afterwards)')
        _npm_script(folder, job, 'build', fallback_cmd='npx next build')
    if not _is_site_dir(out):
        raise BuildError('Next.js finished but produced no "out" folder. This usually means the app uses '
                         'server features (API routes, getServerSideProps, middleware) that cannot be '
                         'exported statically. Use server mode for such apps.')
    _stamp_write(folder, 'export', fp)
    return out


def _server_entry(standalone):
    """Relative path of the standalone ``server.js`` (shallowest one), or None."""
    if not os.path.isdir(standalone):
        return None
    best = None
    for root, dirs, files in os.walk(standalone):
        dirs[:] = [d for d in dirs if d != 'node_modules']
        if 'server.js' in files:
            rel = os.path.relpath(os.path.join(root, 'server.js'), standalone)
            if best is None or rel.count(os.sep) < best.count(os.sep):
                best = rel
        if root[len(standalone):].count(os.sep) >= 4:
            dirs[:] = []
    return best


def _copy_tree(src, dst):
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)


def _build_nextjs_server(folder, job):
    """Build with Next's standalone output. Returns ``(standalone_dir, relative_server_js)``."""
    standalone = os.path.join(folder, '.next', 'standalone')
    fp = _env_fingerprint(job)
    if _server_entry(standalone) and _stamp_fresh(folder, 'standalone', fp):
        job.log('Using existing server build')
    else:
        _npm_install(folder, job)
        shutil.rmtree(standalone, ignore_errors=True)
        with _next_config_output(folder, job, 'standalone'):
            job.log('Temporarily configured Next.js for a standalone server (restored afterwards)')
            _npm_script(folder, job, 'build', fallback_cmd='npx next build')
        if not _server_entry(standalone):
            raise BuildError('Next.js finished but produced no standalone server (.next/standalone/server.js). '
                             'Check the log above for build errors.')
        _stamp_write(folder, 'standalone', fp)
    entry = _server_entry(standalone)
    server_dir = os.path.dirname(os.path.join(standalone, entry))
    # Next does not copy these two into the standalone folder, but the server needs them.
    _copy_tree(os.path.join(folder, '.next', 'static'), os.path.join(server_dir, '.next', 'static'))
    _copy_tree(os.path.join(folder, 'public'), os.path.join(server_dir, 'public'))
    return standalone, entry


def _build_sveltekit(folder, job):
    deps = _deps(read_package_json(folder))
    if '@sveltejs/adapter-static' not in deps:
        raise BuildError('SvelteKit needs the static adapter to become a desktop app. Run '
                         '"npm i -D @sveltejs/adapter-static", use it as the adapter (in svelte.config.js, '
                         'or in the sveltekit() plugin options of vite.config for SvelteKit 3), add '
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


def long_path(path):
    """Expand Windows 8.3 short names (like USERNA~1) to the real long path.

    Some tools (SvelteKit/Vite) compare the short and long spelling of the same
    folder and fail with confusing "not found in manifest" errors.
    """
    if sys.platform != 'win32':
        return path
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetLongPathNameW(path, buf, len(buf))
        return buf.value if 0 < n < len(buf) else path
    except Exception:  # noqa: BLE001
        return path


def prepare(folder, job, next_mode='auto'):
    """Build whatever is needed and return the plan for the EXE builder.

    Plan keys: kind ('static'|'php'), framework, source_dir (folder to bundle),
    php_framework, php_docroot, notes.
    """
    folder = long_path(os.path.abspath(folder))
    info = detect(folder)
    framework = info['framework']
    job.log(f"Detected: {info['label']} [{info['support']}]")
    for note in info['notes']:
        job.log(f'NOTE: {note}')

    plan = {'framework': framework, 'kind': 'static', 'notes': list(info['notes']),
            'php_framework': None, 'php_docroot': '.', 'source_dir': folder, 'node_entry': None,
            'server_features': info.get('serverFeatures', [])}

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

    if framework == 'nextjs' and next_mode != 'static' and (next_mode == 'server' or info.get('server')):
        standalone, entry = _build_nextjs_server(folder, job)
        plan.update({'kind': 'node', 'source_dir': standalone, 'node_entry': entry})
        job.log(f'Server build ready: {os.path.join(standalone, entry)}')
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
