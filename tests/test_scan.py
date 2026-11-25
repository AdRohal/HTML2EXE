"""Folder scan: a real React / Next project must be read in well under a second."""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import builder  # noqa: E402
from h2e import analyzer  # noqa: E402


def write(base, rel, text='x'):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


def next_project():
    base = tempfile.mkdtemp(prefix='h2e-scan-')
    write(base, 'package.json', json.dumps({'name': 'n', 'dependencies': {'next': '14.2.15', 'react': '18.3.1'},
                                            'scripts': {'build': 'next build'}}))
    write(base, 'app/page.js', 'export default function P(){return <h1>x</h1>}')
    return base


class WalkTests(unittest.TestCase):
    def test_heavy_folders_are_never_walked(self):
        base = next_project()
        for heavy in ('node_modules/react', '.next/cache', '.nuxt/dist', 'dist', 'build', 'out', 'coverage', 'vendor/pkg'):
            for i in range(5):
                write(base, f'{heavy}/f{i}.js', 'import React from "react"')
        seen = {os.path.relpath(os.path.join(r, n), base).replace('\\', '/') for r, n in analyzer.walk_project(base)}
        self.assertEqual(seen, {'package.json', 'app/page.js'})

    def test_walk_stops_at_the_file_cap(self):
        base = tempfile.mkdtemp(prefix='h2e-scan-')
        for i in range(50):
            write(base, f'src/f{i}.js')
        self.assertEqual(len(list(analyzer.walk_project(base, max_files=10))), 10)

    def test_read_head_skips_big_files_and_limits_small_ones(self):
        base = tempfile.mkdtemp(prefix='h2e-scan-')
        big = write(base, 'bundle.js', 'x=1;' * (analyzer.MAX_SIZE // 4 + 10))
        mid = write(base, 'mid.js', 'y' * (analyzer.MAX_READ + 5000))
        self.assertEqual(analyzer.read_head(big), '')
        self.assertEqual(len(analyzer.read_head(mid)), analyzer.MAX_READ)
        self.assertEqual(analyzer.read_head(os.path.join(base, 'missing.js')), '')


class ScanSpeedTests(unittest.TestCase):
    def test_next_project_with_a_huge_cache_scans_instantly(self):
        base = next_project()
        cache = os.path.join(base, '.next', 'cache')
        os.makedirs(cache)
        for i in range(400):                                   # many files + a bundle that must not be read
            with open(os.path.join(cache, f'f{i}.js'), 'w') as fh:
                fh.write('function a(){}\n' * 50)
        with open(os.path.join(cache, 'bundle.js'), 'w') as fh:
            fh.write('x=1;' * 2_000_000)                        # ~8 MB
        started = time.time()
        result = builder.HTMLToEXEBuilder().scan_folder(base)
        elapsed = time.time() - started
        self.assertTrue(result['success'], result)
        self.assertEqual(result['analysis']['framework'], 'nextjs')
        self.assertEqual(result['totalFiles'], 2)              # only package.json and app/page.js
        self.assertLess(elapsed, 2.0)

    def test_scan_still_finds_plain_html_projects(self):
        base = tempfile.mkdtemp(prefix='h2e-scan-')
        write(base, 'index.html', '<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>')
        write(base, 'css/site.scss', 'a{b:c}')
        result = builder.HTMLToEXEBuilder().scan_folder(base)
        self.assertEqual(result['entryFile'], 'index.html')
        self.assertIn('React', result['analysis']['frameworks'])
        self.assertIn('SASS', result['analysis']['technologies'])


if __name__ == '__main__':
    unittest.main()
