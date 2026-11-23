"""Download and cache a portable PHP for Windows (used for PHP / Laravel EXEs)."""
import hashlib
import json
import os
import urllib.request
import zipfile

from .recipes import BuildError
from .security import projects_root

RELEASES_URL = 'https://windows.php.net/downloads/releases/releases.json'
DOWNLOAD_BASE = 'https://windows.php.net/downloads/releases/'
PREFERRED_SERIES = ('8.3', '8.4', '8.2')
UA = {'User-Agent': 'HTML2EXE-builder'}


def runtime_root():
    path = os.path.join(projects_root(), '_runtime')
    os.makedirs(path, exist_ok=True)
    return path


def _fetch(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout)


def _cached():
    root = runtime_root()
    found = sorted(d for d in os.listdir(root)
                   if d.startswith('php-') and os.path.isfile(os.path.join(root, d, 'php.exe')))
    return os.path.join(root, found[-1]) if found else None


def ensure_php(job):
    """Return the folder containing php.exe, downloading it on first use."""
    cached = _cached()
    if cached:
        job.log(f'Using cached PHP runtime: {cached}')
        return cached
    job.log('Downloading portable PHP (one time, ~30 MB)...')
    try:
        with _fetch(RELEASES_URL) as resp:
            releases = json.load(resp)
    except Exception as exc:
        raise BuildError(f'Could not download the PHP runtime list ({exc}). Check your internet connection.')
    entry = None
    series = None
    for series in PREFERRED_SERIES:
        candidate = releases.get(series) or {}
        if 'nts-vs16-x64' in candidate or 'nts-vs17-x64' in candidate:
            entry = candidate
            break
    if not entry:
        raise BuildError('No suitable PHP release found on windows.php.net.')
    build = entry.get('nts-vs16-x64') or entry.get('nts-vs17-x64')
    zip_info = build['zip']
    version = entry.get('version', series)
    target = os.path.join(runtime_root(), f'php-{version}')
    archive = target + '.zip'
    job.log(f'PHP {version}: {zip_info["path"]}')
    sha = hashlib.sha256()
    with _fetch(DOWNLOAD_BASE + zip_info['path'], timeout=120) as resp, open(archive, 'wb') as out:
        while True:
            job.check_cancelled()
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            sha.update(chunk)
            out.write(chunk)
    expected = (zip_info.get('sha256') or '').lower()
    if expected and sha.hexdigest().lower() != expected:
        os.remove(archive)
        raise BuildError('PHP download failed its checksum check. Please try again.')
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target)
    os.remove(archive)
    if not os.path.isfile(os.path.join(target, 'php.exe')):
        raise BuildError('The downloaded PHP archive did not contain php.exe.')
    job.log('PHP runtime ready')
    return target
