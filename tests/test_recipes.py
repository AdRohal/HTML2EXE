"""Fast tests for framework detection, output lookup and the generated launcher."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from h2e import jobs, recipes  # noqa: E402
from h2e.launcher import render_launcher  # noqa: E402


def make(base, files):
    for rel, text in files.items():
        path = os.path.join(base, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
    return base


def pkg(**kw):
    return json.dumps({'name': 'x', 'scripts': kw.pop('scripts', {'build': 'echo'}),
                       'dependencies': kw.pop('deps', {}), 'devDependencies': kw.pop('dev', {})})


class DetectTests(unittest.TestCase):
    def detect(self, files):
        with tempfile.TemporaryDirectory() as d:
            make(d, files)
            return recipes.detect(d)

    def test_each_framework(self):
        cases = {
            'nextjs': {'package.json': pkg(deps={'next': '14', 'react': '18'})},
            'astro': {'package.json': pkg(deps={'astro': '4'})},
            'nuxt': {'package.json': pkg(deps={'nuxt': '3'})},
            'angular': {'package.json': pkg(deps={'@angular/core': '17'})},
            'gatsby': {'package.json': pkg(deps={'gatsby': '5'})},
            'sveltekit': {'package.json': pkg(dev={'@sveltejs/kit': '2'})},
            'cra': {'package.json': pkg(deps={'react-scripts': '5'})},
            'vite': {'package.json': pkg(dev={'vite': '5'})},
            'generic': {'package.json': pkg(scripts={'build': 'webpack'})},
            'static': {'index.html': '<html></html>'},
            'php': {'index.php': '<?php echo 1;'},
            'laravel': {'artisan': '', 'composer.json': '{"require":{"laravel/framework":"^11"}}',
                        'public/index.php': '<?php'},
        }
        for expected, files in cases.items():
            self.assertEqual(self.detect(files)['framework'], expected, expected)

    def test_next_wins_over_react_and_vite(self):
        info = self.detect({'package.json': pkg(deps={'next': '14', 'react': '18'}, dev={'vite': '5'})})
        self.assertEqual(info['framework'], 'nextjs')

    def test_next_api_routes_produce_warning(self):
        info = self.detect({'package.json': pkg(deps={'next': '14'}), 'app/api/hello/route.js': ''})
        self.assertTrue(info['notes'])

    def test_matrix_flags_php_as_experimental(self):
        self.assertEqual(recipes.FRAMEWORKS['laravel'][1], 'experimental')
        self.assertEqual(recipes.FRAMEWORKS['astro'][1], 'supported')


class OutputTests(unittest.TestCase):
    def test_find_output_variants(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {'dist/index.html': 'x'})
            self.assertTrue(recipes.find_output(d).endswith('dist'))
        with tempfile.TemporaryDirectory() as d:
            make(d, {'dist/myapp/browser/index.html': 'x'})
            self.assertTrue(recipes.find_output(d).replace('\\', '/').endswith('dist/myapp/browser'))
        with tempfile.TemporaryDirectory() as d:
            make(d, {'.output/public/index.html': 'x'})
            self.assertTrue(recipes.find_output(d, 'nuxt').replace('\\', '/').endswith('.output/public'))
        with tempfile.TemporaryDirectory() as d:
            make(d, {'out/_next/static/a.js': 'x'})
            self.assertTrue(recipes.find_output(d).endswith('out'))
        with tempfile.TemporaryDirectory() as d:
            make(d, {'src/a.js': 'x'})
            self.assertIsNone(recipes.find_output(d))

    def test_fresh_build_is_reused_and_stale_is_not(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {'package.json': pkg(), 'src/a.js': 'a', 'dist/index.html': 'x'})
            now = os.path.getmtime(os.path.join(d, 'src', 'a.js'))
            for name in ('package.json',):
                os.utime(os.path.join(d, name), (now, now))
            os.utime(os.path.join(d, 'dist', 'index.html'), (now + 100, now + 100))
            self.assertTrue(recipes.output_is_fresh(d, os.path.join(d, 'dist')))
            os.utime(os.path.join(d, 'src', 'a.js'), (now + 500, now + 500))
            self.assertFalse(recipes.output_is_fresh(d, os.path.join(d, 'dist')))


class PrepareTests(unittest.TestCase):
    def test_plain_html_uses_folder_itself(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {'index.html': '<html></html>'})
            plan = recipes.prepare(d, jobs.Job('t'))
            self.assertEqual(plan['kind'], 'static')
            self.assertEqual(os.path.normpath(plan['source_dir']),
                             os.path.normpath(recipes.long_path(d)))

    def test_long_path_expands_short_names_and_ignores_missing(self):
        with tempfile.TemporaryDirectory() as d:
            expanded = recipes.long_path(d)
            self.assertTrue(os.path.samefile(expanded, d))
            self.assertNotIn('~', expanded.split(os.sep)[2] if sys.platform == 'win32' else '')
        missing = os.path.join(d, 'definitely-missing')
        self.assertEqual(recipes.long_path(missing), missing)

    def test_prebuilt_dist_is_used_without_running_npm(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {'package.json': pkg(dev={'vite': '5'}), 'src/main.js': 'a', 'dist/index.html': 'x'})
            future = max(os.path.getmtime(os.path.join(d, n)) for n in ('package.json', 'src/main.js')) + 100
            os.utime(os.path.join(d, 'dist', 'index.html'), (future, future))
            with mock.patch.object(recipes, '_npm_install', side_effect=AssertionError('npm must not run')):
                plan = recipes.prepare(d, jobs.Job('t'))
            self.assertTrue(plan['source_dir'].endswith('dist'))

    def test_folder_without_index_gives_friendly_error(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {'notes.txt': 'hi'})
            with self.assertRaises(recipes.BuildError):
                recipes.prepare(d, jobs.Job('t'))

    def test_astro_ssr_is_rejected_with_explanation(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {'package.json': pkg(deps={'astro': '4'}),
                     'astro.config.mjs': "export default { output: 'server' }"})
            with self.assertRaises(recipes.BuildError) as ctx:
                recipes.prepare(d, jobs.Job('t'))
            self.assertIn('server-side rendering', str(ctx.exception))

    def test_sveltekit_without_static_adapter_explains_fix(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {'package.json': pkg(dev={'@sveltejs/kit': '2'})})
            with self.assertRaises(recipes.BuildError) as ctx:
                recipes.prepare(d, jobs.Job('t'))
            self.assertIn('adapter-static', str(ctx.exception))

    def test_laravel_plan_uses_public_docroot(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {'artisan': '', 'composer.json': '{"require":{"laravel/framework":"^11"}}',
                     'vendor/autoload.php': '<?php', 'public/index.php': '<?php'})
            plan = recipes.prepare(d, jobs.Job('t'))
            self.assertEqual((plan['kind'], plan['php_framework'], plan['php_docroot']),
                             ('php', 'laravel', 'public'))

    def test_laravel_without_vendor_and_composer_explains(self):
        with tempfile.TemporaryDirectory() as d:
            make(d, {'artisan': '', 'composer.json': '{"require":{"laravel/framework":"^11"}}'})
            with mock.patch.object(recipes, '_tool', return_value=None):
                with self.assertRaises(recipes.BuildError) as ctx:
                    recipes.prepare(d, jobs.Job('t'))
            self.assertIn('composer install', str(ctx.exception))


class LauncherTests(unittest.TestCase):
    """Run the generated launcher in --selftest mode against a fixture site."""

    def run_launcher(self, site, probes):
        with tempfile.TemporaryDirectory() as work:
            main = os.path.join(work, 'main.py')
            with open(main, 'w', encoding='utf-8') as fh:
                fh.write(render_launcher({'mode': 'static', 'title': 'T', 'dev_project': site}))
            out = os.path.join(work, 'out.json')
            subprocess.run([sys.executable, '-I', main, f'--selftest-out={out}',
                            '--selftest-probe=' + ','.join(probes)], check=True, timeout=60)
            with open(out, encoding='utf-8') as fh:
                return {r['path']: r for r in json.load(fh)['results']}

    def test_spa_fallback_html_pages_and_404s(self):
        with tempfile.TemporaryDirectory() as site:
            make(site, {'index.html': '<h1>home</h1>', 'about.html': '<h1>about</h1>',
                        'assets/app.js': 'console.log(1)', 'docs/index.html': '<h1>docs</h1>'})
            res = self.run_launcher(site, ['/', '/about', '/docs/', '/some/client/route', '/assets/app.js',
                                           '/missing.js', '/assets/missing.css'])
        self.assertEqual(res['/']['status'], 200)
        self.assertEqual(res['/about']['status'], 200)
        self.assertEqual(res['/about']['bytes'], len('<h1>about</h1>'))      # about.html, not index
        self.assertEqual(res['/docs/']['bytes'], len('<h1>docs</h1>'))
        self.assertEqual(res['/some/client/route']['status'], 200)           # SPA fallback
        self.assertEqual(res['/some/client/route']['bytes'], len('<h1>home</h1>'))
        self.assertIn('javascript', res['/assets/app.js']['type'])
        self.assertEqual(res['/missing.js']['status'], 404)                  # real 404 for files
        self.assertEqual(res['/assets/missing.css']['status'], 404)


if __name__ == '__main__':
    unittest.main()
