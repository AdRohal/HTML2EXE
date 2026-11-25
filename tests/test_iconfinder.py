import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PIL import Image  # noqa: E402
from h2e import iconfinder  # noqa: E402


def image(base, rel, size=(256, 256), fmt=None):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new('RGBA', size, (120, 60, 220, 255)).save(path, format=fmt)
    return path


def text(base, rel, body):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(body)


class FindIconTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='h2e-icon-')

    def test_nothing_found(self):
        text(self.dir, 'index.html', '<html></html>')
        image(self.dir, 'images/team-photo.png', (800, 800))
        self.assertIsNone(iconfinder.find_icon(self.dir))

    def test_html_link_wins(self):
        text(self.dir, 'index.html', '<link rel="shortcut icon" href="img/mark.png"><link rel="stylesheet" href="x.css">')
        image(self.dir, 'img/mark.png', (128, 128))
        image(self.dir, 'logo-small.png', (32, 32))
        found = iconfinder.find_icon(self.dir)
        self.assertEqual(found['relative'], 'img/mark.png')
        self.assertTrue(found['dataUri'].startswith('data:image/png;base64,'))

    def test_prefers_big_square_logo_over_banner_and_tiny_favicon(self):
        image(self.dir, 'favicon.png', (16, 16))
        image(self.dir, 'assets/logo.png', (512, 512))
        image(self.dir, 'assets/logo-wide.png', (900, 200))
        self.assertEqual(iconfinder.find_icon(self.dir)['relative'], 'assets/logo.png')

    def test_ico_and_next_app_dir(self):
        image(self.dir, 'app/favicon.ico', (64, 64), 'ICO')
        self.assertEqual(iconfinder.find_icon(self.dir)['relative'], 'app/favicon.ico')

    def test_manifest_icons(self):
        text(self.dir, 'public/manifest.json', '{"icons":[{"src":"/a.png","sizes":"48x48"},{"src":"/b.png","sizes":"512x512"}]}')
        image(self.dir, 'public/a.png', (48, 48))
        image(self.dir, 'public/b.png', (512, 512))
        self.assertEqual(iconfinder.find_icon(self.dir)['relative'], 'public/b.png')

    def test_ignores_node_modules_and_outside_links(self):
        image(self.dir, 'node_modules/pkg/logo.png', (512, 512))
        text(self.dir, 'index.html', '<link rel="icon" href="../../outside.png"><link rel="icon" href="https://x.y/f.ico">')
        self.assertIsNone(iconfinder.find_icon(self.dir))

    def test_broken_image_is_skipped(self):
        text(self.dir, 'favicon.png', 'not an image')
        image(self.dir, 'icon.png', (128, 128))
        self.assertEqual(iconfinder.find_icon(self.dir)['relative'], 'icon.png')


if __name__ == '__main__':
    unittest.main()
