"""Find the icon of a project when the user did not choose one.

Looks at what a website or program usually ships: the ``<link rel="icon">`` of its HTML pages, a web app manifest,
and well-known file names (favicon, apple-touch-icon, logo, icon, app-icon...) in the usual folders. Every candidate
is opened with Pillow and scored: square images, 128 px and up, and names that really mean "the app icon" win.
Pure and read-only; ``find_icon`` returns the best candidate or ``None``.
"""
import base64
import io
import json
import os
import re
from urllib.parse import unquote, urlparse

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:  # pragma: no cover
    HAS_PILLOW = False

IMAGE_EXT = ('.ico', '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')
ICON_DIRS = ('', 'public', 'static', 'assets', 'asset', 'images', 'image', 'img', 'icons', 'icon', 'resources',
             'res', 'media', 'src', 'src/assets', 'src/images', 'src/img', 'app', 'src/app', 'public/images',
             'public/img', 'public/icons', 'public/assets', 'static/images', 'static/img', 'static/icons',
             'assets/images', 'assets/img', 'assets/icons', 'www', 'web', 'dist', 'build', 'out', 'wwwroot',
             'electron', 'build/icons')
SKIP_DIRS = {'node_modules', '.git', 'venv', '.venv', '__pycache__', 'vendor', '.next', '.nuxt', 'site-packages'}
# file stem -> base score (higher = more clearly "the icon of this app")
NAME_SCORES = (
    (re.compile(r'^(app[-_]?icon|application[-_]?icon|icon[-_]?(512|256|192|1024)|android-chrome-(512|192)x(512|192))$', re.I), 100),
    (re.compile(r'^(favicon|fav|icon|icons|app|logo|brand|logomark|logo[-_]?(icon|mark|square)|apple-touch-icon.*|mstile.*)$', re.I), 80),
    (re.compile(r'(^|[-_.])(icon|logo|favicon)([-_.]|$)', re.I), 60),
    (re.compile(r'(icon|logo|favicon)', re.I), 40),
)
BAD_WORDS = re.compile(r'(sprite|banner|hero|background|bg|screenshot|thumb|avatar|og[-_]?image|social|cover|'
                       r'placeholder|team|photo|slide|header|footer|wide|flag|emoji|badge|payment|partner)', re.I)
LINK_RE = re.compile(r'<link\b[^>]*>', re.I)
ATTR_RE = re.compile(r'([a-zA-Z-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')


def _attrs(tag):
    return {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4)) for m in ATTR_RE.finditer(tag)}


def _inside(base, path):
    base, path = os.path.realpath(base), os.path.realpath(path)
    return path == base or path.startswith(base + os.sep)


def _from_html(folder, html_path, hints):
    """``<link rel="icon">`` targets of one HTML file, resolved against the project."""
    try:
        with open(html_path, encoding='utf-8', errors='ignore') as fh:
            head = fh.read(200_000)
    except OSError:
        return
    for tag in LINK_RE.findall(head):
        attrs = _attrs(tag)
        rel = (attrs.get('rel') or '').lower()
        href = attrs.get('href') or ''
        if 'icon' not in rel or not href or href.startswith(('data:', 'http:', 'https:', '//')):
            continue
        href = unquote(urlparse(href).path)
        for root in (os.path.dirname(html_path), folder, os.path.join(folder, 'public'), os.path.join(folder, 'static')):
            candidate = os.path.normpath(os.path.join(root, href.lstrip('/\\')))
            if os.path.isfile(candidate) and _inside(folder, candidate):
                hints[candidate] = 'linked as the page icon'
                break


def _from_manifest(folder, manifest_path, hints):
    try:
        with open(manifest_path, encoding='utf-8-sig') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return
    best, best_size = None, 0
    for icon in data.get('icons', []) if isinstance(data, dict) else []:
        src = unquote(str(icon.get('src', '')))
        if not src or src.startswith(('http:', 'https:', 'data:')):
            continue
        sizes = re.findall(r'(\d+)x\d+', str(icon.get('sizes', '')))
        size = max([int(s) for s in sizes] or [0])
        for root in (os.path.dirname(manifest_path), folder, os.path.join(folder, 'public'), os.path.join(folder, 'static')):
            candidate = os.path.normpath(os.path.join(root, src.lstrip('/\\')))
            if os.path.isfile(candidate) and _inside(folder, candidate) and size >= best_size:
                best, best_size = candidate, size
                break
    if best:
        hints[best] = 'listed in the web app manifest'


def _candidates(folder):
    """``{absolute path: reason hint}`` of images that might be the icon."""
    hints = {}
    pages = []
    for sub in ICON_DIRS:
        base = os.path.join(folder, sub) if sub else folder
        if not os.path.isdir(base):
            continue
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            full = os.path.join(base, name)
            if not os.path.isfile(full):
                continue
            low = name.lower()
            if low.endswith(IMAGE_EXT):
                hints.setdefault(full, '')
            elif low.endswith(('.html', '.htm', '.php')) and len(pages) < 12 and sub in ('', 'public', 'static', 'src', 'app', 'www', 'web', 'dist', 'wwwroot'):
                pages.append(full)
            elif low in ('manifest.json', 'site.webmanifest', 'manifest.webmanifest'):
                _from_manifest(folder, full, hints)
    for page in pages:
        _from_html(folder, page, hints)
    # anywhere else, a few levels down (e.g. ``builder_ui/assets/logo.png``): only clearly icon-like names
    seen = 0
    root_depth = folder.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        if root.count(os.sep) - root_depth >= 4:
            dirs[:] = []
        for name in files:
            seen += 1
            if seen > 6000:
                return hints
            stem, ext = os.path.splitext(name)
            if ext.lower() in IMAGE_EXT and any(rx.search(stem) for rx, _pts in NAME_SCORES[:3]):
                hints.setdefault(os.path.join(root, name), '')
    return hints


def _score(path, hint, folder):
    """``(score, width, height)`` or ``None`` when the file is not usable as an icon."""
    stem = os.path.splitext(os.path.basename(path))[0]
    if BAD_WORDS.search(stem) and not hint:
        return None
    base = max((points for rx, points in NAME_SCORES if rx.search(stem)), default=0)
    if hint:
        base = max(base, 70) + 15
    if not base:
        return None
    try:
        with Image.open(path) as img:
            width, height = img.size
            if path.lower().endswith('.ico'):                       # .ico files hold several sizes: take the biggest
                sizes = getattr(img, 'info', {}).get('sizes') or {img.size}
                width, height = max(sizes, key=lambda s: s[0])
    except Exception:  # noqa: BLE001 - broken or unsupported image
        return None
    if min(width, height) < 16 or max(width, height) > 4096:
        return None
    ratio = min(width, height) / max(width, height)
    if ratio < 0.7:
        return None                                                  # banners and wide logos are not icons
    score = base + 25 * ratio
    score += 25 if min(width, height) >= 256 else 15 if min(width, height) >= 128 else 5 if min(width, height) >= 64 else -10
    depth = len(os.path.relpath(path, folder).replace('\\', '/').split('/')) - 1
    score -= 3 * depth
    if path.lower().endswith('.ico'):
        score += 3
    return score, width, height


def _preview(path):
    """A 256 px PNG data URI of the best frame of the image."""
    with Image.open(path) as img:
        if path.lower().endswith('.ico'):
            sizes = img.info.get('sizes') or {img.size}
            img.size = max(sizes, key=lambda s: s[0])
            img.load()
        img = img.convert('RGBA')
        img.thumbnail((256, 256), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def find_icon(folder, with_preview=True):
    """The most likely icon of a project folder: ``{'path', 'relative', 'width', 'height', 'reason', 'dataUri'}`` or ``None``."""
    if not HAS_PILLOW or not folder or not os.path.isdir(folder):
        return None
    folder = os.path.abspath(folder)
    best = None
    for path, hint in _candidates(folder).items():
        if any(part in SKIP_DIRS for part in os.path.relpath(path, folder).replace('\\', '/').split('/')):
            continue
        scored = _score(path, hint, folder)
        if scored and (best is None or scored[0] > best[0]):
            best = (scored[0], path, hint, scored[1], scored[2])
    if not best:
        return None
    _score_value, path, hint, width, height = best
    rel = os.path.relpath(path, folder).replace('\\', '/')
    reason = hint or 'named like an app icon'
    if min(width, height) < 64:
        reason += ' (small image, may look blurry)'
    result = {'path': path, 'relative': rel, 'width': width, 'height': height, 'reason': reason}
    if with_preview:
        try:
            result['dataUri'] = _preview(path)
        except Exception:  # noqa: BLE001
            return None
    return result


def auto_icon_data(folder):
    """The data URI to build with when the user chose no icon, plus a short description (or ``(None, '')``)."""
    found = find_icon(folder)
    if not found:
        return None, ''
    return found['dataUri'], f"{found['relative']} ({found['reason']})"
