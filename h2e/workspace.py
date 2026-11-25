"""Working copies of projects.

Every build works on a temporary copy of your project in ``Downloads\\<name>`` (so your original folder is never
touched by ``npm install``, config wrapping or build output). The copy is deleted when the build ends. Expensive
build caches (``node_modules``, ``.next`` ...) are parked in ``Documents\\HTML2EXE\\<name>\\cache`` between builds so
rebuilds stay fast and Downloads only ever contains what you asked for: the .exe or the installer.

Safety rules for deleting: only a folder that carries the builder's own marker file, is not the original source
folder, and sits directly inside the Downloads folder is ever removed.
"""
import os
import shutil
import stat

from . import secrets

MARKER = '.h2e-workspace'

# Never copied: dependencies (reinstalled during the build) and caches that can hold tens of thousands of files.
COPY_SKIP = ('node_modules', '.git', '.vscode', '.idea', '__pycache__', '.next', '.nuxt', '.svelte-kit',
             '.output', '.cache', '.turbo', '.parcel-cache', '.vercel', '.expo', 'coverage')
# Parked between builds (when the build created them in the working copy).
CACHE_DIRS = ('node_modules', '.next', '.nuxt', '.output', '.svelte-kit', '.astro', 'dist', 'build', 'out')
CACHE_FILES = ('.h2e-stamp.json',)


def downloads_root():
    return os.path.join(os.path.expanduser('~'), 'Downloads')


def _ignore(folder, names):
    skipped = set(shutil.ignore_patterns(*COPY_SKIP)(folder, names))
    skipped.update(n for n in names if secrets.is_env_file_name(n))        # env files are read from the original
    return skipped


def _rmtree(path):
    def fix(func, target, _exc):                                           # read-only files on Windows
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass
    shutil.rmtree(path, onerror=fix)


def sync_working_copy(source, dest, log=None):
    """Copy ``source`` into ``dest`` (replacing what is there) and mark ``dest`` as ours. Returns the item count."""
    os.makedirs(dest, exist_ok=True)
    count = 0
    for item in os.listdir(source):
        src, dst = os.path.join(source, item), os.path.join(dest, item)
        if item in COPY_SKIP or (os.path.isfile(src) and secrets.is_env_file_name(item)):
            if log and secrets.is_env_file_name(item):
                log(f'  Skipping {item} (environment files are read from the original folder)')
            continue
        if os.path.lexists(dst):
            if os.path.isdir(dst) and not os.path.islink(dst):
                _rmtree(dst)
            else:
                os.remove(dst)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=_ignore)
        else:
            shutil.copy2(src, dst)
        count += 1
    # Things deleted from the source must not survive in the copy (they would be bundled). The build caches stay.
    keep = set(os.listdir(source)) | set(CACHE_DIRS) | set(CACHE_FILES) | {MARKER}
    for item in os.listdir(dest):
        if item not in keep:
            _drop(os.path.join(dest, item))
    with open(os.path.join(dest, MARKER), 'w', encoding='utf-8') as fh:
        fh.write('Temporary working copy created by HTML2EXE. It is deleted after the build.\n')
    return count


def restore_cache(cache_dir, working):
    """Move parked caches back into the working copy (a rename, so it is instant on the same drive)."""
    if not cache_dir or not os.path.isdir(cache_dir):
        return
    for name in CACHE_DIRS + CACHE_FILES:
        parked, target = os.path.join(cache_dir, name), os.path.join(working, name)
        if os.path.lexists(parked) and not os.path.lexists(target):
            try:
                os.replace(parked, target)
            except OSError:                                               # different drive etc.: not worth copying
                _drop(parked)


def stash_cache(working, cache_dir):
    """Park the caches the build created outside Downloads."""
    if not cache_dir or not os.path.isdir(working):
        return
    os.makedirs(cache_dir, exist_ok=True)
    for name in CACHE_DIRS + CACHE_FILES:
        built, parked = os.path.join(working, name), os.path.join(cache_dir, name)
        if not os.path.lexists(built):
            continue
        _drop(parked)
        try:
            os.replace(built, parked)
        except OSError:
            pass                                                           # stays in the copy and is deleted with it


def _drop(path):
    if os.path.isdir(path) and not os.path.islink(path):
        _rmtree(path)
    elif os.path.lexists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def can_remove(working, source, root=None):
    """The guards, separately so they can be tested."""
    if not working or not os.path.isdir(working):
        return False
    real = os.path.realpath(working)
    if source and os.path.realpath(source) == real:
        return False                                                       # never the user's own folder
    if os.path.realpath(os.path.dirname(real)) != os.path.realpath(root or downloads_root()):
        return False                                                       # only directly inside Downloads
    return os.path.isfile(os.path.join(working, MARKER))                    # only copies we made


def remove_working_copy(working, source, root=None):
    """Delete the temporary working copy. Returns True when it was removed."""
    if not can_remove(working, source, root):
        return False
    _rmtree(working)
    return not os.path.isdir(working)


def clean_build_files(build_dir):
    """Delete the bulky intermediate folders of a finished build (staged bundle, PyInstaller work folder)."""
    for name in ('stage', 'work', 'dist', 'installer'):
        path = os.path.join(build_dir, name)
        if os.path.isdir(path):
            _rmtree(path)
