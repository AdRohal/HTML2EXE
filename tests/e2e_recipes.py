"""Real framework builds through the recipes (needs Node + internet; slow).

    python tests/e2e_recipes.py [vite] [astro] [nextjs] [nuxt] [angular] [gatsby] [sveltekit] [sveltekit3]

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


def lines(*parts):
    return chr(10).join(parts) + chr(10)


def make_angular(base):
    pkg(base, 'ng-app', {
        '@angular/animations': '^18.2.0', '@angular/common': '^18.2.0', '@angular/compiler': '^18.2.0',
        '@angular/core': '^18.2.0', '@angular/platform-browser': '^18.2.0', 'rxjs': '~7.8.0',
        'tslib': '^2.3.0', 'zone.js': '~0.14.10'},
        {'build': 'ng build'},
        {'@angular-devkit/build-angular': '^18.2.0', '@angular/cli': '^18.2.0',
         '@angular/compiler-cli': '^18.2.0', 'typescript': '~5.5.2'})
    write(base, 'angular.json', json.dumps({
        '$schema': './node_modules/@angular/cli/lib/config/schema.json', 'version': 1,
        'newProjectRoot': 'projects',
        'projects': {'ng-app': {
            'projectType': 'application', 'root': '', 'sourceRoot': 'src', 'prefix': 'app',
            'architect': {'build': {
                'builder': '@angular-devkit/build-angular:application',
                'options': {'outputPath': 'dist/ng-app', 'index': 'src/index.html',
                            'browser': 'src/main.ts', 'polyfills': ['zone.js'],
                            'tsConfig': 'tsconfig.app.json'},
                'configurations': {'production': {'outputHashing': 'all'}},
                'defaultConfiguration': 'production'}}}},
        'cli': {'analytics': False}}))
    write(base, 'tsconfig.json', json.dumps({'compileOnSave': False, 'compilerOptions': {
        'outDir': './dist/out-tsc', 'strict': True, 'skipLibCheck': True, 'target': 'ES2022',
        'module': 'ES2022', 'moduleResolution': 'bundler', 'experimentalDecorators': True,
        'importHelpers': True, 'lib': ['ES2022', 'dom']}}))
    write(base, 'tsconfig.app.json', json.dumps({'extends': './tsconfig.json', 'compilerOptions': {
        'outDir': './out-tsc/app', 'types': []}, 'files': ['src/main.ts'], 'include': ['src/**/*.d.ts']}))
    write(base, 'src/index.html', '<!doctype html><html><head><base href="/"><title>ng</title></head>'
                                  '<body><app-root></app-root></body></html>')
    write(base, 'src/main.ts', lines(
        "import { bootstrapApplication } from '@angular/platform-browser';",
        "import { AppComponent } from './app/app.component';",
        'bootstrapApplication(AppComponent).catch(console.error);'))
    write(base, 'src/app/app.component.ts', lines(
        "import { Component } from '@angular/core';",
        "@Component({ selector: 'app-root', standalone: true, template: '<h1>angular-ok</h1>' })",
        'export class AppComponent {}'))


def make_gatsby(base):
    pkg(base, 'g', {'gatsby': '^5.13.0', 'react': '^18.2.0', 'react-dom': '^18.2.0'},
        {'build': 'gatsby build'})
    write(base, 'gatsby-config.js', lines('module.exports = { siteMetadata: { title: "g" } }'))
    write(base, 'src/pages/index.js', lines(
        "import * as React from 'react'",
        'export default function Home(){ return <h1>gatsby-ok</h1> }'))
    write(base, 'src/pages/about.js', lines(
        "import * as React from 'react'",
        'export default function About(){ return <h1>gatsby-about</h1> }'))


def make_sveltekit(base, dev=None):
    dev = dev or {'@sveltejs/adapter-static': '^3.0.8', '@sveltejs/kit': '^2.20.0',
                  '@sveltejs/vite-plugin-svelte': '^5.0.0', 'svelte': '^5.0.0', 'vite': '^6.0.0'}
    write(base, 'package.json', json.dumps({
        'name': 'sk', 'version': '1.0.0', 'private': True, 'type': 'module',
        'scripts': {'build': 'vite build'}, 'devDependencies': dev}))
    write(base, 'svelte.config.js', lines(
        "import adapter from '@sveltejs/adapter-static';",
        "export default { kit: { adapter: adapter({ fallback: 'index.html' }) } };"))
    write(base, 'vite.config.js', lines(
        "import { sveltekit } from '@sveltejs/kit/vite';",
        'export default { plugins: [sveltekit()] };'))
    write(base, 'src/app.html', '<!doctype html><html><head>%sveltekit.head%</head>'
                                '<body><div>%sveltekit.body%</div></body></html>')
    write(base, 'src/routes/+layout.js', lines('export const prerender = true;'))
    write(base, 'src/routes/+page.svelte', '<h1>sveltekit-ok</h1>')
    write(base, 'src/routes/about/+page.svelte', '<h1>svelte-about</h1>')


def make_sveltekit3(base):
    # SvelteKit 3 no longer reads svelte.config.js: options go to the sveltekit() plugin.
    make_sveltekit(base, {'@sveltejs/adapter-static': '^4.0.0', '@sveltejs/kit': '^3.0.0',
                          '@sveltejs/vite-plugin-svelte': '^7.0.0', 'svelte': '^5.57.1', 'vite': '^8.0.0'})
    os.remove(os.path.join(base, 'svelte.config.js'))
    write(base, 'vite.config.js', lines(
        "import { sveltekit } from '@sveltejs/kit/vite';",
        "import adapter from '@sveltejs/adapter-static';",
        "export default { plugins: [sveltekit({ adapter: adapter({ fallback: 'index.html' }) })] };"))


CASES = {
    'vite': (make_vite, '*', 'vite-ok'),
    'astro': (make_astro, 'about/index.html', 'about-ok'),
    'nextjs': (make_next, 'index.html', 'next-ok'),
    'nuxt': (make_nuxt, 'index.html', 'nuxt-ok'),
    'angular': (make_angular, '*', 'angular-ok'),
    'gatsby': (make_gatsby, 'index.html', 'gatsby-ok'),
    'sveltekit': (make_sveltekit, '*', 'sveltekit-ok'),
    'sveltekit3': (make_sveltekit3, '*', 'sveltekit-ok'),
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
                leftovers = [n for n in os.listdir(base) if ('h2e' in n and n != '.h2e-stamp.json') or n == 'next.config.mjs']
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
