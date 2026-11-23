"""Real framework builds through the recipes (needs Node + internet; slow).

    python tests/e2e_recipes.py [vite] [astro] [nextjs] [nuxt]

Each case writes a tiny project into a temp folder, runs recipes.prepare()
(npm install + build) and checks the produced static folder.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ROOT)
from h2e import jobs, recipes  # noqa: E402


def write(base, rel, text):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


def pkg(base, name, deps, scripts, dev=None):
    write(base, 'package.json', json.dumps(
        {'name': name, 'version': '1.0.0', 'private': True, 'scripts': scripts,
         'dependencies': deps, 'devDependencies': dev or {}}))


def make_vite(base):
    pkg(base, 'v', {}, {'build': 'vite build'}, {'vite': '^5.4.0'})
    write(base, 'index.html', '<!doctype html><html><body><div id="a"></div><script type="module" src="/main.js"></script></body></html>')
    write(base, 'main.js', "document.getElementById('a').textContent='vite-ok'")


def make_astro(base):
    pkg(base, 'a', {'astro': '^4.16.0'}, {'build': 'astro build'})
    write(base, 'src/pages/index.astro', '---\n---\n<html><body><h1>astro-ok</h1></body></html>')
    write(base, 'src/pages/about.astro', '---\n---\n<html><body><h1>about-ok</h1></body></html>')


def make_next(base):
    pkg(base, 'n', {'next': '14.2.15', 'react': '18.3.1', 'react-dom': '18.3.1'}, {'build': 'next build'})
    write(base, 'app/layout.js', 'export default function L({children}){return <html><body>{children}</body></html>}')
    write(base, 'app/page.js', 'export default function P(){return <h1>next-ok</h1>}')
    write(base, 'app/about/page.js', 'export default function P(){return <h1>next-about</h1>}')
    # an existing config the recipe must preserve and restore
    write(base, 'next.config.js', "module.exports = { reactStrictMode: true };\n")


def make_nuxt(base):
    pkg(base, 'x', {'nuxt': '^3.13.0', 'vue': 'latest'}, {'build': 'nuxt build', 'generate': 'nuxt generate'})
    write(base, 'app.vue', '<template><h1>nuxt-ok</h1></template>')
    write(base, 'nuxt.config.ts', 'export default defineNuxtConfig({ telemetry: false })\n')


CASES = {
    'vite': (make_vite, '*', 'vite-ok'),
    'astro': (make_astro, 'about/index.html', 'about-ok'),
    'nextjs': (make_next, 'index.html', 'next-ok'),
    'nuxt': (make_nuxt, 'index.html', 'nuxt-ok'),
}


def main():
    wanted = sys.argv[1:] or ['vite', 'astro', 'nextjs']
    failures = 0
    for name in wanted:
        maker, probe_file, needle = CASES[name]
        base = tempfile.mkdtemp(prefix=f'h2e-{name}-')
        maker(base)
        job = jobs.Job('e2e')
        status = 'PASS'
        try:
            plan = recipes.prepare(base, job)
            src = plan['source_dir']
            found = None
            for dirpath, _dirs, files in os.walk(src):
                for f in files:
                    full = os.path.join(dirpath, f)
                    if probe_file == '*' or full.replace('\\', '/').endswith(probe_file) or f == probe_file:
                        with open(full, encoding='utf-8', errors='replace') as fh:
                            if needle in fh.read():
                                found = full
            if not found:
                status = f'FAIL (no file containing {needle!r} under {src})'
            elif name == 'nextjs':
                leftovers = [n for n in os.listdir(base) if 'h2e' in n or n == 'next.config.mjs']
                with open(os.path.join(base, 'next.config.js'), encoding='utf-8') as fh:
                    restored = 'reactStrictMode' in fh.read()
                if leftovers or not restored:
                    status = f'FAIL (config not restored: leftovers={leftovers}, restored={restored})'
        except Exception as exc:  # noqa: BLE001
            status = f'FAIL ({type(exc).__name__}: {exc})'
        if status != 'PASS':
            failures += 1
            print('\n'.join(job.snapshot()['lines'][-30:]))
        print(f'== {name}: {status}  [{base}]', flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
