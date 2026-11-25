"""Android (Capacitor) APK builder."""
import json
import os
import shutil
import subprocess
import sys

from . import jobs
from .security import project_dir_for

class AndroidBuilder:
    """Build web projects into Android APKs using Capacitor CLI"""

    @staticmethod
    def check_prerequisites():
        """Check Java JDK, Android SDK and Node.js availability"""
        import re
        import glob

        result = {
            'java':  {'ok': False, 'version': None, 'message': 'Not found'},
            'sdk':   {'ok': False, 'path': None,    'message': 'Not found'},
            'node':  {'ok': False, 'version': None, 'message': 'Not found'},
            'allOk': False,
        }

        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

        def run_cmd(cmd, **kwargs):
            """Run a command with shell=True for proper PATH resolution on Windows."""
            return subprocess.run(
                cmd, capture_output=True, text=True,
                shell=True, creationflags=flags, **kwargs
            )

        def parse_java_output(raw):
            m = re.search(r'version "(\d+)', raw)
            if m:
                major = int(m.group(1))
                vs = re.search(r'version "([^"]+)"', raw)
                return major, vs.group(1) if vs else raw.split('\n')[0]
            return None, None

        # --- Java ---
        # 1. Try java in PATH (shell=True ensures system PATH is inherited)
        r = run_cmd('java -version')
        raw = (r.stderr + r.stdout).strip()
        major, ver_str = parse_java_output(raw)

        # 2. Fallback: search common Windows install locations
        if major is None:
            candidates = []
            prog_files = [
                os.environ.get('ProgramFiles', r'C:\Program Files'),
                os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
            ]
            for pf in prog_files:
                candidates += glob.glob(os.path.join(pf, 'Eclipse Adoptium', 'jdk-*', 'bin', 'java.exe'))
                candidates += glob.glob(os.path.join(pf, 'Java', 'jdk-*', 'bin', 'java.exe'))
                candidates += glob.glob(os.path.join(pf, 'Microsoft', 'jdk-*', 'bin', 'java.exe'))
                candidates += glob.glob(os.path.join(pf, 'Android', 'Android Studio', 'jbr', 'bin', 'java.exe'))
            # Android Studio bundled JDK (user-local install)
            local_as = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Android Studio', 'jbr', 'bin', 'java.exe')
            if os.path.exists(local_as):
                candidates.insert(0, local_as)

            for java_exe in candidates:
                if os.path.exists(java_exe):
                    r2 = run_cmd(f'"{java_exe}" -version')
                    raw2 = (r2.stderr + r2.stdout).strip()
                    major, ver_str = parse_java_output(raw2)
                    if major:
                        break

        if major is not None:
            result['java']['version'] = ver_str
            if major >= 17:
                result['java']['ok'] = True
                result['java']['message'] = f'JDK {ver_str}'
            else:
                result['java']['message'] = f'JDK {ver_str} found — version 17+ required'
        else:
            result['java']['message'] = 'Java not found — install JDK 17+ from adoptium.net'

        # --- Android SDK ---
        # 1. Env vars
        sdk_path = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT', '')
        # 2. Default Android Studio SDK location (set even if ANDROID_HOME is missing)
        if not sdk_path or not os.path.isdir(sdk_path):
            default_sdk = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Sdk')
            if os.path.isdir(default_sdk):
                sdk_path = default_sdk
        # 3. adb in PATH
        if not sdk_path or not os.path.isdir(sdk_path):
            r = run_cmd('adb version')
            if r.returncode == 0:
                sdk_path = 'PATH'

        if sdk_path and (sdk_path == 'PATH' or os.path.isdir(sdk_path)):
            result['sdk']['ok'] = True
            result['sdk']['path'] = sdk_path
            result['sdk']['message'] = sdk_path if sdk_path != 'PATH' else 'Found via adb in PATH'
        else:
            result['sdk']['message'] = 'Android SDK not found — install Android Studio'

        # --- Node.js ---
        r = run_cmd('node --version')
        v = r.stdout.strip() or r.stderr.strip()
        if v.startswith('v'):
            result['node']['ok'] = True
            result['node']['version'] = v
            result['node']['message'] = v
        else:
            result['node']['message'] = 'Node.js not found — install from nodejs.org'

        result['allOk'] = result['java']['ok'] and result['sdk']['ok'] and result['node']['ok']
        return result

    def build(self, data):
        """Build a web project to Android APK using Capacitor"""
        import glob as _glob

        project_id   = data.get('projectId', '')
        folder_path  = data.get('folderPath', '')
        app_name     = data.get('appName', 'MyApp').strip()
        package_name = data.get('packageName', 'com.example.myapp').strip()
        log_lines    = []

        def log(msg):
            print(msg)
            log_lines.append(msg)

        # Fail fast with a clear message instead of running npm/Capacitor for minutes
        # and only then dying inside Gradle.
        prereqs = self.check_prerequisites()
        missing = [prereqs[key]['message'] for key in ('java', 'sdk', 'node') if not prereqs[key]['ok']]
        if missing:
            log('Cannot build an APK yet:')
            for line in missing:
                log(f'  - {line}')
            return {'success': False, 'log': log_lines,
                    'error': 'Cannot build an APK yet - missing: ' + '; '.join(missing)
                             + '. Open "System Check" to see what to install.'}

        # ── 0. Build a subprocess env with JAVA_HOME injected ─────────────
        def make_env():
            """Return os.environ copy with JAVA_HOME set to a Gradle-compatible JDK.
            Prefers Android Studio's bundled JBR (Java 17/21) over newer standalone
            JDKs (e.g. Java 25) which are not yet supported by Gradle."""
            env = os.environ.copy()

            pf_list = [
                env.get('ProgramFiles', r'C:\Program Files'),
                env.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
            ]
            local_app = env.get('LOCALAPPDATA', '')

            # Ordered by preference: Android Studio JBR first (Java 17/21, most
            # compatible), then versioned JDKs sorted newest-first as fallback.
            priority = []
            # 1. Android Studio JBR — preferred (bundled, always compatible)
            for pf in pf_list:
                jbr = os.path.join(pf, 'Android', 'Android Studio', 'jbr', 'bin', 'java.exe')
                if os.path.exists(jbr):
                    priority.append(jbr)
            local_jbr = os.path.join(local_app, 'Android', 'Android Studio', 'jbr', 'bin', 'java.exe')
            if os.path.exists(local_jbr):
                priority.insert(0, local_jbr)

            # 2. Versioned JDKs — sorted so lower (more compatible) versions come first
            versioned = []
            for pf in pf_list:
                versioned += _glob.glob(os.path.join(pf, 'Eclipse Adoptium', 'jdk-*', 'bin', 'java.exe'))
                versioned += _glob.glob(os.path.join(pf, 'Java', 'jdk-*', 'bin', 'java.exe'))
                versioned += _glob.glob(os.path.join(pf, 'Microsoft', 'jdk-*', 'bin', 'java.exe'))
            # Sort by path so jdk-17 < jdk-21 < jdk-25; pick lowest available
            versioned.sort()
            candidates = priority + versioned

            def _set_java(java_exe, source):
                java_home = os.path.dirname(os.path.dirname(java_exe))
                env['JAVA_HOME'] = java_home
                env['PATH'] = os.path.dirname(java_exe) + os.pathsep + env.get('PATH', '')
                log(f'JAVA_HOME ({source}): {java_home}')
                return env

            # If JAVA_HOME is already set, only keep it if it's ≤ Java 24
            existing_jh = env.get('JAVA_HOME', '')
            if existing_jh and os.path.isdir(existing_jh):
                java_exe = os.path.join(existing_jh, 'bin', 'java.exe')
                r = subprocess.run([java_exe, '-version'], capture_output=True, text=True)
                version_str = r.stderr or r.stdout  # java -version prints to stderr
                import re
                m = re.search(r'version "(\d+)', version_str)
                major = int(m.group(1)) if m else 99
                if major <= 24:
                    log(f'JAVA_HOME already set (Java {major}): {existing_jh}')
                    return env
                else:
                    log(f'Ignoring JAVA_HOME (Java {major} too new for Gradle): {existing_jh}')

            for java_exe in candidates:
                if os.path.exists(java_exe):
                    return _set_java(java_exe, 'auto-detected')

            # Last resort: `where java`
            r = subprocess.run('where java', capture_output=True, text=True, shell=True)
            if r.returncode == 0:
                java_exe = r.stdout.strip().splitlines()[0].strip()
                if os.path.exists(java_exe):
                    return _set_java(java_exe, 'PATH')

            return env

        try:
            # ── 1. Resolve web source folder ──────────────────────────────
            web_src = folder_path
            if project_id and not folder_path:
                user_home = os.path.expanduser('~')
                safe_dir = project_dir_for(project_id)
                if safe_dir is None:
                    return {'success': False, 'error': 'Invalid project ID', 'log': log_lines}
                meta_path = os.path.join(safe_dir, 'project.json')
                if not os.path.exists(meta_path):
                    return {'success': False, 'error': 'Project metadata not found', 'log': log_lines}
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                web_src = meta.get('downloadFolder', '')

            if not web_src or not os.path.isdir(web_src):
                return {'success': False, 'error': f'Web source folder not found: {web_src}', 'log': log_lines}

            log(f'Web source: {web_src}')

            # ── 2. Auto-build / locate static output for any framework ────
            # Helper: find the built static output folder
            def find_built_output(base):
                """Return path to the static build output dir, or None."""
                has_pkg_here = os.path.exists(os.path.join(base, 'package.json'))
                is_gatsby = (os.path.exists(os.path.join(base, 'gatsby-config.js')) or
                             os.path.exists(os.path.join(base, 'gatsby-config.ts')))

                # --- Well-known output directories (require index.html) ---
                for c in ('out', 'dist', 'build'):
                    p = os.path.join(base, c)
                    if not os.path.isdir(p):
                        continue
                    if os.path.exists(os.path.join(p, 'index.html')):
                        return p
                    # Next.js static export: has _next/ but root index may be missing
                    # (app-router without a root page)
                    if os.path.isdir(os.path.join(p, '_next')):
                        return p
                    # Any HTML files directly in the output folder
                    try:
                        if any(e.endswith('.html')
                               for e in os.listdir(p)
                               if os.path.isfile(os.path.join(p, e))):
                            return p
                    except OSError:
                        pass

                # Nuxt 3
                nuxt_p = os.path.join(base, '.output', 'public')
                if os.path.isdir(nuxt_p) and os.path.exists(os.path.join(nuxt_p, 'index.html')):
                    return nuxt_p

                # Gatsby only: public/ is the output dir
                if is_gatsby:
                    p = os.path.join(base, 'public')
                    if os.path.isdir(p) and os.path.exists(os.path.join(p, 'index.html')):
                        return p

                # Plain HTML project (no package.json) — base dir itself
                if not has_pkg_here and os.path.exists(os.path.join(base, 'index.html')):
                    return base

                # Angular v17+: dist/<name>/browser/   v15/16: dist/<name>/
                dist_p = os.path.join(base, 'dist')
                if os.path.isdir(dist_p):
                    try:
                        for sub in sorted(os.listdir(dist_p)):
                            sub_p = os.path.join(dist_p, sub)
                            if not os.path.isdir(sub_p):
                                continue
                            for ang in (os.path.join(sub_p, 'browser'), sub_p):
                                if os.path.exists(os.path.join(ang, 'index.html')):
                                    return ang
                    except OSError:
                        pass

                # SvelteKit adapter-static
                sk_p = os.path.join(base, '.svelte-kit', 'output', 'client')
                if os.path.isdir(sk_p) and os.path.exists(os.path.join(sk_p, 'index.html')):
                    return sk_p

                # Fallback: walk (skip heavy/source dirs) looking for index.html
                skip = {'node_modules', '.git', '.next', '.svelte-kit', 'src',
                        '__pycache__', '.venv', 'coverage', 'public'}
                for dirpath, dirnames, filenames in os.walk(base):
                    dirnames[:] = [d for d in dirnames
                                   if d not in skip and not d.startswith('.')]
                    if 'index.html' in filenames and dirpath != base:
                        return dirpath
                return None

            # ── Next.js helpers ───────────────────────────────────────────

            # Patch next.config.* to add output:'export' + images.unoptimized.
            # Also appends a CJS override block as a last-resort fallback.
            def patch_nextjs_config(base, backups):
                import re as _re
                for cfg in ('next.config.js', 'next.config.mjs',
                            'next.config.ts', 'next.config.cjs'):
                    cfg_p = os.path.join(base, cfg)
                    if not os.path.exists(cfg_p):
                        continue
                    with open(cfg_p, 'r', encoding='utf-8') as f:
                        original = f.read()
                    backups[cfg_p] = original
                    txt = original
                    # Add output:'export' if not already present
                    if "'export'" not in txt and '"export"' not in txt:
                        txt, n = _re.subn(
                            r"(output\s*:\s*)['\"][^'\"]*['\"]",
                            r"\1'export'", txt)
                        if n == 0:
                            txt, n = _re.subn(
                                r'((?:const|let|var)\s+\w+[^=\n]*=\s*\{'
                                r'|module\.exports\s*=\s*\{'
                                r'|export\s+default\s*\{)',
                                r"\1\n  output: 'export',",
                                txt, count=1)
                        if n == 0 or txt == original:
                            txt = txt.rstrip() + (
                                "\n// added by HTML2EXE\n"
                                "if (typeof module !== 'undefined'"
                                " && module.exports) {\n"
                                "  module.exports = {"
                                " ...module.exports, output: 'export' };\n"
                                "}\n")
                    # Add images.unoptimized (required for static export)
                    if 'unoptimized' not in txt:
                        txt = txt.rstrip() + (
                            "\nif (typeof module !== 'undefined'"
                            " && module.exports) {\n"
                            "  if (!module.exports.images)"
                            " module.exports.images = {};\n"
                            "  module.exports.images.unoptimized = true;\n"
                            "}\n")
                    with open(cfg_p, 'w', encoding='utf-8') as f:
                        f.write(txt)
                    log(f'next.config patched ({cfg})')
                    return True
                # No config file — create minimal one
                cfg_p = os.path.join(base, 'next.config.js')
                backups[cfg_p] = None  # mark as created
                with open(cfg_p, 'w', encoding='utf-8') as f:
                    f.write("/** @type {import('next').NextConfig} */\n"
                            "module.exports = {\n"
                            "  output: 'export',\n"
                            "  images: { unoptimized: true },\n"
                            "};\n")
                log('next.config.js created')
                return True

            # Build a static site from .next/ after a regular next build.
            # Copies .next/static/ + all pre-rendered .html from server/app/.
            def _extract_nextjs_static(base):
                next_dir = os.path.join(base, '.next')
                server_app = os.path.join(next_dir, 'server', 'app')
                static_dir = os.path.join(next_dir, 'static')
                if not os.path.isdir(static_dir):
                    return None, 'No .next/static found'
                out_dir = os.path.join(base, '_html2exe_out')
                if os.path.isdir(out_dir):
                    shutil.rmtree(out_dir)
                os.makedirs(out_dir)
                # Copy static assets (_next/static/)
                shutil.copytree(static_dir,
                                os.path.join(out_dir, '_next', 'static'))
                # Copy pre-rendered HTML from server/app/
                html_count = 0
                if os.path.isdir(server_app):
                    for root, _d, files in os.walk(server_app):
                        for fname in files:
                            if not fname.endswith('.html'):
                                continue
                            src = os.path.join(root, fname)
                            rel = os.path.relpath(src, server_app)
                            dst = os.path.join(out_dir, rel)
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)
                            html_count += 1
                if html_count == 0:
                    return None, 'No pre-rendered HTML in .next/server/app/'
                # Normalise filenames: page.html → index.html
                for root, _d, files in os.walk(out_dir):
                    for fname in files:
                        if fname == 'page.html':
                            old = os.path.join(root, fname)
                            new = os.path.join(root, 'index.html')
                            if not os.path.exists(new):
                                os.rename(old, new)
                # Ensure a root index.html
                root_html = os.path.join(out_dir, 'index.html')
                if not os.path.exists(root_html):
                    for root, _d, files in os.walk(out_dir):
                        for fname in files:
                            if fname.endswith('.html'):
                                shutil.copy2(os.path.join(root, fname),
                                             root_html)
                                break
                        if os.path.exists(root_html):
                            break
                log(f'Extracted {html_count} HTML pages from .next/')
                return out_dir, None

            # ── Main Next.js static build ─────────────────────────────────
            # Tier 1: output:'export' with all blockers stubbed.
            # Tier 2 fallback: regular next build + extract from .next/.
            def _build_nextjs_static(base):
                backups = {}

                def _bw(path, content):   # backup + write
                    if path not in backups:
                        try:
                            with open(path, 'r', encoding='utf-8') as fh:
                                backups[path] = fh.read()
                        except FileNotFoundError:
                            backups[path] = None
                    with open(path, 'w', encoding='utf-8') as fh:
                        fh.write(content)

                def _restore():
                    for path, original in backups.items():
                        try:
                            if original is None:
                                if os.path.exists(path):
                                    os.remove(path)
                            else:
                                with open(path, 'w', encoding='utf-8') as fh:
                                    fh.write(original)
                        except Exception:
                            pass

                # ── Stubs (zero external dependencies) ───────────────────
                # API route stub: satisfies output:export, returns empty JSON
                api_stub = (
                    "export const dynamic = 'force-static';\n"
                    "const _r = () => new Response('{}', {status:200,"
                    "headers:{'Content-Type':'application/json'}});\n"
                    "export const GET=_r, POST=_r, PUT=_r,"
                    " DELETE=_r, PATCH=_r;\n"
                )
                # Dynamic page/layout stubs — complete replacements so there
                # are NO imports that could fail or introduce side-effects.
                # generateStaticParams returning [] tells Next.js "export zero
                # static paths for this dynamic route" — valid for output:export.
                # All stubs are self-contained with no imports — avoids any
                # missing-module or implicit-any TypeScript errors.
                _stubs = {
                    'page': (
                        "// @ts-nocheck\n"
                        "export async function generateStaticParams()"
                        " { return []; }\n"
                        "export default function Page() { return null; }\n"
                    ),
                    'layout': (
                        "// @ts-nocheck\n"
                        "export async function generateStaticParams()"
                        " { return []; }\n"
                        "export default function Layout(props: any)"
                        " { return props.children ?? null; }\n"
                    ),
                    'loading': (
                        "// @ts-nocheck\n"
                        "export default function Loading()"
                        " { return null; }\n"
                    ),
                    'error': (
                        "// @ts-nocheck\n"
                        "'use client';\n"
                        "export default function Error()"
                        " { return null; }\n"
                    ),
                    'not-found': (
                        "// @ts-nocheck\n"
                        "export default function NotFound()"
                        " { return null; }\n"
                    ),
                }

                # ── File finders ──────────────────────────────────────────
                def _api_routes(app_dir):
                    out = []
                    api = os.path.join(app_dir, 'api')
                    if not os.path.isdir(api):
                        return out
                    for r, _d, fs in os.walk(api):
                        for f in fs:
                            if f.lower().startswith('route.'):
                                out.append(os.path.join(r, f))
                    return out

                def _dynamic_files(app_dir):
                    """All page/layout/loading/error files inside [param] dirs."""
                    out = []
                    if not os.path.isdir(app_dir):
                        return out
                    for root, _d, files in os.walk(app_dir):
                        parts = os.path.relpath(
                            root, app_dir).replace('\\', '/').split('/')
                        if any(p.startswith('[') and p.endswith(']')
                               for p in parts if p != '.'):
                            for fname in files:
                                stem = fname.split('.')[0]
                                ext  = fname.rsplit('.', 1)[-1]
                                if stem in _stubs and ext in (
                                        'tsx', 'ts', 'jsx', 'js'):
                                    out.append(
                                        (os.path.join(root, fname), stem))
                    return out

                try:
                    # ── TIER 1: output:export ─────────────────────────────
                    patch_nextjs_config(base, backups)
                    next_cache = os.path.join(base, '.next')
                    if os.path.isdir(next_cache):
                        shutil.rmtree(next_cache, ignore_errors=True)
                        log('Cleared .next cache')

                    app_dirs = [os.path.join(base, 'app'),
                                os.path.join(base, 'src', 'app')]
                    for ad in app_dirs:
                        for p in _api_routes(ad):
                            _bw(p, api_stub)
                            log(f'Stubbed API: {os.path.relpath(p, base)}')
                        for p, stem in _dynamic_files(ad):
                            _bw(p, _stubs[stem])
                            log(f'Stubbed {stem}: '
                                f'{os.path.relpath(p, base)}')

                    r = jobs.run('npm install', cwd=base,
                                       capture_output=True, text=True,
                                       shell=True)
                    if not jobs.current_job():
                        log(r.stdout[-2000:] if r.stdout else '')
                    if r.returncode != 0:
                        return None, f'npm install failed:\n{r.stderr}'

                    r = jobs.run('npm run build', cwd=base,
                                       capture_output=True, text=True,
                                       shell=True)
                    if not jobs.current_job():
                        log(r.stdout[-3000:] if r.stdout else '')

                    if r.returncode == 0:
                        result = (find_built_output(base)
                                  or os.path.join(base, 'out'))
                        if os.path.isdir(result):
                            log(f'Static export succeeded: {result}')
                            return result, None

                    # ── TIER 2 fallback: regular build + extract ──────────
                    log('Static export failed — trying regular build + '
                        'extract from .next/...')
                    # Restore ALL original files (stubs + config) first.
                    _restore()
                    backups.clear()  # prevent double-restore in outer finally
                    if os.path.isdir(next_cache):
                        shutil.rmtree(next_cache, ignore_errors=True)

                    # The original next.config may already contain
                    # output:'export' (that's why Tier 1 failed — the project
                    # itself has incompatible routes). For a regular build we
                    # MUST remove output:'export' so Next.js produces .next/.
                    import re as _re2
                    t2_cfg_path = None
                    t2_cfg_orig = None
                    for _cn in ('next.config.ts', 'next.config.js',
                                'next.config.mjs', 'next.config.cjs'):
                        _cp = os.path.join(base, _cn)
                        if not os.path.exists(_cp):
                            continue
                        with open(_cp, 'r', encoding='utf-8') as _fh:
                            t2_cfg_orig = _fh.read()
                        t2_cfg_path = _cp
                        _cleaned = _re2.sub(
                            r"\boutput\s*:\s*['\"]export['\"],?\s*\n?",
                            '', t2_cfg_orig)
                        # Remove any HTML2EXE-appended override blocks
                        _cleaned = _re2.sub(
                            r'\n// (?:added|output added) by HTML2EXE\n'
                            r'(?:.*\n)*?}\n',
                            '\n', _cleaned)
                        if _cleaned != t2_cfg_orig:
                            with open(_cp, 'w', encoding='utf-8') as _fh:
                                _fh.write(_cleaned)
                            log(f'Stripped output:export from {_cn} '
                                f'for regular build')
                        break

                    try:
                        r2 = jobs.run('npm run build', cwd=base,
                                            capture_output=True, text=True,
                                            shell=True)
                        if not jobs.current_job():
                            log(r2.stdout[-3000:] if r2.stdout else '')
                        if r2.returncode != 0:
                            return None, (
                                'Next.js build failed completely.\n'
                                f'Details:\n{r2.stderr[-2000:]}')

                        fallback, err = _extract_nextjs_static(base)
                        if fallback:
                            return fallback, None
                        return None, (
                            'Both static export and .next/ extraction '
                            'failed.\nExtraction error: ' + (err or ''))
                    finally:
                        # Always restore the original config
                        if t2_cfg_path and t2_cfg_orig is not None:
                            with open(t2_cfg_path, 'w',
                                      encoding='utf-8') as _fh:
                                _fh.write(t2_cfg_orig)

                except jobs.JobCancelled:
                    raise
                except Exception as exc:
                    return None, f'Next.js build error: {exc}'
                finally:
                    _restore()

            has_pkg = os.path.exists(os.path.join(web_src, 'package.json'))
            pkg_data = {}
            if has_pkg:
                try:
                    with open(os.path.join(web_src, 'package.json'),
                              'r', encoding='utf-8') as f:
                        pkg_data = json.load(f)
                except Exception:
                    pass
            all_deps = {**pkg_data.get('dependencies', {}),
                        **pkg_data.get('devDependencies', {})}
            has_build_script = 'build' in pkg_data.get('scripts', {})
            is_nextjs = 'next' in all_deps
            has_index_at_root = os.path.exists(os.path.join(web_src, 'index.html'))

            if has_pkg and has_build_script and not has_index_at_root:
                # It's a framework project that needs building
                built_dir = find_built_output(web_src)

                if is_nextjs:
                    if built_dir is not None:
                        log('Next.js out/ already exists — skipping rebuild')
                    else:
                        log('Next.js project — building with static export '
                            '(API routes will be stubbed)...')
                        built_dir, err = _build_nextjs_static(web_src)
                        if built_dir is None:
                            return {'success': False,
                                    'error': err,
                                    'log': log_lines}

                elif built_dir is None:
                    # Not yet built — run npm build
                    log('Source project detected — running npm build...')
                    r = jobs.run('npm install', cwd=web_src,
                                       capture_output=True, text=True, shell=True)
                    if not jobs.current_job():
                        log(r.stdout[-2000:] if r.stdout else '')
                    if r.returncode != 0:
                        return {'success': False,
                                'error': f'npm install failed:\n{r.stderr}',
                                'log': log_lines}
                    r = jobs.run('npm run build', cwd=web_src,
                                       capture_output=True, text=True, shell=True)
                    if not jobs.current_job():
                        log(r.stdout[-2000:] if r.stdout else '')
                    if r.returncode != 0:
                        return {'success': False,
                                'error': f'npm run build failed:\n{r.stderr}',
                                'log': log_lines}
                    built_dir = find_built_output(web_src)
                else:
                    log('Pre-built output found — skipping npm build')

                if not built_dir:
                    return {'success': False,
                            'error': (
                                'Build succeeded but no static output folder was found.\n'
                                'Expected one of: out/, dist/, build/, public/, .output/public/\n'
                                'Make sure your project is configured to produce a static site.'
                            ),
                            'log': log_lines}

                web_src = built_dir
                log(f'Using built output: {web_src}')

            elif has_pkg and not has_index_at_root:
                # package.json but no build script and no index.html
                # Try to find a pre-built output subfolder
                built_dir = find_built_output(web_src)
                if built_dir:
                    web_src = built_dir
                    log(f'Using output: {web_src}')
                # else: fall through and use web_src as-is (may fail later)


            # ── 3. Set up Capacitor working directory ─────────────────────
            user_home = os.path.expanduser('~')
            work_dir = os.path.join(user_home, 'Documents', 'HTML2EXE_Android', app_name)
            os.makedirs(work_dir, exist_ok=True)
            log(f'Working dir: {work_dir}')

            # ── 4. Copy web assets into work_dir/www ──────────────────────
            www_dir = os.path.join(work_dir, 'www')
            if os.path.exists(www_dir):
                shutil.rmtree(www_dir)
            shutil.copytree(web_src, www_dir)
            log(f'Copied web assets to www/')

            # If there's no index.html at root, create a redirect to the first page found
            root_index = os.path.join(www_dir, 'index.html')
            if not os.path.exists(root_index):
                # Find the first non-404 HTML file in the output
                first_html = None
                for dirpath, dirnames, filenames in os.walk(www_dir):
                    dirnames[:] = [d for d in dirnames if d not in ('node_modules', '.git')]
                    for fname in sorted(filenames):
                        if fname.endswith('.html') and fname != '404.html':
                            rel = os.path.relpath(
                                os.path.join(dirpath, fname), www_dir
                            ).replace('\\', '/')
                            first_html = '/' + rel
                            break
                    if first_html:
                        break
                if first_html:
                    with open(root_index, 'w', encoding='utf-8') as f:
                        f.write(
                            '<!DOCTYPE html><html><head>'
                            f'<meta http-equiv="refresh" content="0; url={first_html}">'
                            f'<script>window.location.replace("{first_html}")</script>'
                            '</head><body></body></html>'
                        )
                    log(f'Generated index.html → redirects to {first_html}')
                else:
                    log('WARNING: No HTML files found in output — app may show blank screen')

            # ── 5. Init npm project in work_dir ───────────────────────────
            pkg_json = os.path.join(work_dir, 'package.json')
            if not os.path.exists(pkg_json):
                r = jobs.run('npm init -y', cwd=work_dir, capture_output=True, text=True, shell=True)
                if r.returncode != 0:
                    return {'success': False, 'error': f'npm init failed:\n{r.stderr}', 'log': log_lines}
                log('npm init done')

            # ── 6. Install Capacitor ──────────────────────────────────────
            log('Installing Capacitor (this may take a few minutes on first run)...')
            r = jobs.run(
                'npm install @capacitor/cli @capacitor/core @capacitor/android',
                cwd=work_dir, capture_output=True, text=True, shell=True
            )
            if not jobs.current_job():
                log(r.stdout[-2000:] if r.stdout else '')
            if r.returncode != 0:
                return {'success': False, 'error': f'Capacitor install failed:\n{r.stderr}', 'log': log_lines}
            log('Capacitor installed')

            # ── 7. Init Capacitor project ─────────────────────────────────
            cap_config = os.path.join(work_dir, 'capacitor.config.json')
            if not os.path.exists(cap_config):
                r = jobs.run(
                    f'npx cap init "{app_name}" "{package_name}" --web-dir www',
                    cwd=work_dir, capture_output=True, text=True, shell=True
                )
                if not jobs.current_job():
                    log(r.stdout[-2000:] if r.stdout else '')
                if r.returncode != 0:
                    return {'success': False, 'error': f'cap init failed:\n{r.stderr}', 'log': log_lines}
                log('Capacitor project initialised')
            else:
                log('Existing Capacitor project found — skipping init')

            # Always overwrite capacitor.config.json with settings that allow
            # external navigation and mixed content (needed for CDN resources)
            cap_cfg_obj = {
                "appId": package_name,
                "appName": app_name,
                "webDir": "www",
                "server": {
                    "allowNavigation": ["*"],
                    "androidScheme": "http"
                },
                "android": {
                    "allowMixedContent": True
                }
            }
            with open(cap_config, 'w', encoding='utf-8') as f:
                json.dump(cap_cfg_obj, f, indent=2)
            log('capacitor.config.json updated (allowMixedContent + allowNavigation)')

            # ── 8. Add Android platform ───────────────────────────────────
            android_dir = os.path.join(work_dir, 'android')
            if not os.path.isdir(android_dir):
                log('Adding Android platform (Gradle will download on first run ~5-10 min)...')
                r = jobs.run(
                    'npx cap add android',
                    cwd=work_dir, capture_output=True, text=True, shell=True
                )
                if not jobs.current_job():
                    log(r.stdout[-2000:] if r.stdout else '')
                if r.returncode != 0:
                    return {'success': False, 'error': f'cap add android failed:\n{r.stderr}', 'log': log_lines}
                log('Android platform added')
            else:
                log('Android platform already present')

            # ── 8b. Patch AndroidManifest & add network security config ───
            # Android 9+ blocks HTTP traffic by default; this causes a blank
            # white screen when the HTML page loads resources from CDN/http URLs.
            manifest_path = os.path.join(android_dir, 'app', 'src', 'main', 'AndroidManifest.xml')
            net_cfg_dir   = os.path.join(android_dir, 'app', 'src', 'main', 'res', 'xml')
            net_cfg_path  = os.path.join(net_cfg_dir, 'network_security_config.xml')
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = f.read()
                changed = False
                # Enable cleartext traffic
                if 'android:usesCleartextTraffic' not in manifest:
                    manifest = manifest.replace(
                        '<application',
                        '<application\n        android:usesCleartextTraffic="true"',
                        1
                    )
                    changed = True
                # Point to network security config
                if 'android:networkSecurityConfig' not in manifest:
                    manifest = manifest.replace(
                        '<application',
                        '<application\n        android:networkSecurityConfig="@xml/network_security_config"',
                        1
                    )
                    changed = True
                if changed:
                    with open(manifest_path, 'w', encoding='utf-8') as f:
                        f.write(manifest)
                    log('AndroidManifest.xml patched (cleartext + network security config)')
            # Write network_security_config.xml allowing all cleartext
            os.makedirs(net_cfg_dir, exist_ok=True)
            with open(net_cfg_path, 'w', encoding='utf-8') as f:
                f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                        '<network-security-config>\n'
                        '    <base-config cleartextTrafficPermitted="true">\n'
                        '        <trust-anchors>\n'
                        '            <certificates src="system" />\n'
                        '        </trust-anchors>\n'
                        '    </base-config>\n'
                        '</network-security-config>\n')
            log('network_security_config.xml written')

            # ── 9. Copy web assets to android ─────────────────────────────
            # Use 'cap sync' (not 'cap copy') so Capacitor also regenerates
            # capacitor.settings.gradle and other native bridge files.
            log('Syncing web assets...')
            r = jobs.run(
                'npx cap sync android',
                cwd=work_dir, capture_output=True, text=True, shell=True
            )
            if r.returncode != 0:
                return {'success': False, 'error': f'cap sync failed:\n{r.stderr}', 'log': log_lines}
            log('Assets synced')

            # ── 10. Build APK ─────────────────────────────────────────────
            log('Running Gradle assembleDebug (may take several minutes)...')
            gradlew = os.path.join(android_dir, 'gradlew.bat')
            if not os.path.exists(gradlew):
                return {'success': False, 'error': 'gradlew.bat not found in android/ folder', 'log': log_lines}

            # Write local.properties with sdk.dir so Gradle can find the Android SDK
            local_props = os.path.join(android_dir, 'local.properties')
            sdk_path = (
                os.environ.get('ANDROID_HOME') or
                os.environ.get('ANDROID_SDK_ROOT') or
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Sdk')
            )
            if os.path.isdir(sdk_path):
                # Gradle requires forward slashes in local.properties
                sdk_path_fwd = sdk_path.replace('\\', '/')
                props_content = f'sdk.dir={sdk_path_fwd}\n'
                with open(local_props, 'w', encoding='utf-8') as f:
                    f.write(props_content)
                log(f'SDK location: {sdk_path}')
            else:
                log(f'WARNING: Android SDK not found at {sdk_path} — Gradle may fail')

            gradle_env = make_env()
            r = jobs.run(
                [gradlew, 'assembleDebug'],
                cwd=android_dir,
                capture_output=True, text=True,
                env=gradle_env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            if not jobs.current_job():
                log(r.stdout[-3000:] if r.stdout else '')
            if r.returncode != 0:
                return {'success': False, 'error': f'Gradle build failed:\n{r.stderr[-2000:]}', 'log': log_lines}
            log('Gradle build complete')

            # ── 11. Copy APK to Downloads ─────────────────────────────────
            apk_src = os.path.join(android_dir, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk')
            if not os.path.exists(apk_src):
                return {'success': False, 'error': 'APK not found after build', 'log': log_lines}

            downloads = os.path.join(user_home, 'Downloads')
            os.makedirs(downloads, exist_ok=True)
            safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in app_name)
            apk_dst = os.path.join(downloads, f'{safe_name}.apk')
            shutil.copy2(apk_src, apk_dst)
            log(f'APK saved to: {apk_dst}')

            return {
                'success': True,
                'apkPath': apk_dst,
                'apkFolder': downloads,
                'log': log_lines,
            }

        except jobs.JobCancelled:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            log(f'Error: {e}')
            return {'success': False, 'error': str(e), 'log': log_lines}
