import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from h2e import exe_build, jobs, workspace  # noqa: E402


def write(base, rel, text='x'):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return path


def tree(base):
    return {os.path.relpath(os.path.join(r, f), base).replace(os.sep, '/') for r, _d, fs in os.walk(base) for f in fs}


class SyncTests(unittest.TestCase):
    def test_copies_source_skips_dependencies_caches_and_env_files_at_every_depth(self):
        src = tempfile.mkdtemp(prefix='h2e-ws-src-')
        for rel in ('package.json', 'src/app.js', 'sub/.env.local', '.env', '.env.production', '.env.example',
                    'node_modules/x/i.js', '.next/cache/c.js', 'coverage/c.json', 'dist/index.html'):
            write(src, rel)
        dest = os.path.join(tempfile.mkdtemp(prefix='h2e-ws-dst-'), 'App')
        workspace.sync_working_copy(src, dest)
        self.assertEqual(tree(dest), {'package.json', 'src/app.js', '.env.example', 'dist/index.html', workspace.MARKER})

    def test_resync_replaces_changed_files_and_drops_deleted_ones(self):
        src = tempfile.mkdtemp(prefix='h2e-ws-src-')
        write(src, 'a.js', 'one')
        write(src, 'old/b.js')
        dest = os.path.join(tempfile.mkdtemp(prefix='h2e-ws-dst-'), 'App')
        workspace.sync_working_copy(src, dest)
        write(src, 'a.js', 'two')
        import shutil
        shutil.rmtree(os.path.join(src, 'old'))
        write(src, 'new.js')
        workspace.sync_working_copy(src, dest)
        with open(os.path.join(dest, 'a.js'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'two')
        self.assertEqual(tree(dest), {'a.js', 'new.js', workspace.MARKER})


class CacheTests(unittest.TestCase):
    def test_caches_are_parked_and_restored_by_renaming(self):
        work = tempfile.mkdtemp(prefix='h2e-ws-work-')
        cache = os.path.join(tempfile.mkdtemp(prefix='h2e-ws-cache-'), 'cache')
        write(work, 'node_modules/pkg/index.js', 'dep')
        write(work, '.next/standalone/server.js', 'srv')
        write(work, '.h2e-stamp.json', '{}')
        write(work, 'src/app.js', 'source')
        workspace.stash_cache(work, cache)
        self.assertEqual(tree(work), {'src/app.js'})                       # caches left the working copy
        self.assertEqual(tree(cache), {'node_modules/pkg/index.js', '.next/standalone/server.js', '.h2e-stamp.json'})
        fresh = tempfile.mkdtemp(prefix='h2e-ws-work-')
        workspace.restore_cache(cache, fresh)
        self.assertEqual(tree(fresh), {'node_modules/pkg/index.js', '.next/standalone/server.js', '.h2e-stamp.json'})
        self.assertEqual(tree(cache), set())

    def test_restore_never_overwrites_what_the_copy_already_has(self):
        work = tempfile.mkdtemp(prefix='h2e-ws-work-')
        cache = tempfile.mkdtemp(prefix='h2e-ws-cache-')
        write(work, 'dist/index.html', 'from source')
        write(cache, 'dist/index.html', 'stale cache')
        workspace.restore_cache(cache, work)
        with open(os.path.join(work, 'dist', 'index.html'), encoding='utf-8') as fh:
            self.assertEqual(fh.read(), 'from source')


class RemoveGuardTests(unittest.TestCase):
    def setUp(self):
        self.downloads = tempfile.mkdtemp(prefix='h2e-ws-dl-')
        self.source = tempfile.mkdtemp(prefix='h2e-ws-src-')
        write(self.source, 'index.html')
        self.working = os.path.join(self.downloads, 'App')
        workspace.sync_working_copy(self.source, self.working)

    def test_removes_our_copy_inside_downloads(self):
        self.assertTrue(workspace.remove_working_copy(self.working, self.source, root=self.downloads))
        self.assertFalse(os.path.exists(self.working))
        self.assertTrue(os.path.isfile(os.path.join(self.source, 'index.html')))   # the original is untouched

    def test_never_removes_the_original_folder(self):
        write(self.source, workspace.MARKER)
        self.assertFalse(workspace.can_remove(self.source, self.source, root=os.path.dirname(self.source)))
        self.assertTrue(os.path.isdir(self.source))

    def test_never_removes_a_folder_without_our_marker(self):
        os.remove(os.path.join(self.working, workspace.MARKER))
        self.assertFalse(workspace.remove_working_copy(self.working, self.source, root=self.downloads))
        self.assertTrue(os.path.isdir(self.working))

    def test_never_removes_a_folder_outside_downloads_or_nested_deeper(self):
        other = tempfile.mkdtemp(prefix='h2e-ws-other-')
        marked = os.path.join(other, 'App')
        workspace.sync_working_copy(self.source, marked)
        self.assertFalse(workspace.can_remove(marked, self.source, root=self.downloads))
        nested = os.path.join(self.downloads, 'a', 'b')
        workspace.sync_working_copy(self.source, nested)
        self.assertFalse(workspace.can_remove(nested, self.source, root=self.downloads))
        self.assertFalse(workspace.can_remove(self.downloads, self.source, root=os.path.dirname(self.downloads)))

    def test_missing_or_empty_paths_are_safe(self):
        self.assertFalse(workspace.remove_working_copy('', self.source, root=self.downloads))
        self.assertFalse(workspace.remove_working_copy(os.path.join(self.downloads, 'nope'), self.source, root=self.downloads))

    def test_clean_build_files_only_touches_the_known_bulky_folders(self):
        build = tempfile.mkdtemp(prefix='h2e-ws-build-')
        for rel in ('stage/a.js', 'work/b.bin', 'dist/c.exe', 'installer/d.py', 'main.py', 'Spec.spec'):
            write(build, rel)
        workspace.clean_build_files(build)
        self.assertEqual(tree(build), {'main.py', 'Spec.spec'})


class BuildExeWrapperTests(unittest.TestCase):
    """build_exe(): working copy lifecycle around the real build (which is replaced by a stub here)."""

    def setup_project(self):
        self.home = tempfile.mkdtemp(prefix='h2e-ws-home-')
        patcher = mock.patch.dict(os.environ, {'USERPROFILE': self.home, 'HOME': self.home})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = tempfile.mkdtemp(prefix='h2e-ws-src-')
        write(self.source, 'index.html', 'hello')
        self.downloads = os.path.join(self.home, 'Downloads')
        os.makedirs(self.downloads)
        self.working = os.path.join(self.downloads, 'App')
        self.meta_dir = os.path.join(self.home, 'Documents', 'HTML2EXE', 'App')
        os.makedirs(self.meta_dir)
        import json
        with open(os.path.join(self.meta_dir, 'project.json'), 'w', encoding='utf-8') as fh:
            json.dump({'name': 'App', 'downloadFolder': self.working, 'sourceFolder': self.source}, fh)

    def run_build(self, stub):
        with mock.patch.object(exe_build, '_build_exe', stub):
            return exe_build.build_exe({'projectName': 'App', 'projectId': 'App'}, jobs.Job('t'))

    def test_copy_is_created_for_the_build_and_deleted_afterwards_with_caches_kept(self):
        self.setup_project()
        seen = {}

        def stub(data, job):
            seen['existed'] = tree(self.working)
            write(self.working, 'node_modules/p/i.js', 'dep')          # what a build leaves behind
            write(self.working, '.h2e-stamp.json', '{}')
            return {'success': True}
        result = self.run_build(stub)
        self.assertTrue(result['success'])
        self.assertIn('index.html', seen['existed'])                     # created because it was missing
        self.assertFalse(os.path.exists(self.working))                   # Downloads is clean again
        self.assertEqual(os.listdir(self.downloads), [])
        self.assertTrue(os.path.isfile(os.path.join(self.meta_dir, 'cache', 'node_modules', 'p', 'i.js')))
        # second build: the cache comes back into the fresh working copy
        seen.clear()
        self.run_build(lambda d, j: seen.update(deps=tree(self.working)) or {'success': True})
        self.assertIn('node_modules/p/i.js', seen['deps'])
        self.assertFalse(os.path.exists(self.working))

    def test_copy_is_deleted_even_when_the_build_fails_or_raises(self):
        self.setup_project()
        self.assertFalse(self.run_build(lambda d, j: {'success': False, 'error': 'boom'})['success'])
        self.assertFalse(os.path.exists(self.working))

        def explode(d, j):
            raise jobs.JobCancelled()
        with self.assertRaises(jobs.JobCancelled):
            self.run_build(explode)
        self.assertFalse(os.path.exists(self.working))

    def test_a_project_that_works_in_place_is_never_deleted(self):
        self.setup_project()
        import json
        with open(os.path.join(self.meta_dir, 'project.json'), 'w', encoding='utf-8') as fh:   # template project
            json.dump({'name': 'App', 'downloadFolder': self.source, 'sourceFolder': self.source}, fh)
        self.assertTrue(self.run_build(lambda d, j: {'success': True})['success'])
        self.assertTrue(os.path.isfile(os.path.join(self.source, 'index.html')))

    def test_successful_build_cleans_the_bulky_build_folders_unless_asked_not_to(self):
        self.setup_project()
        build = os.path.join(self.meta_dir, 'build')
        for rel in ('stage/a.js', 'work/b.bin', 'main.py'):
            write(build, rel)
        self.run_build(lambda d, j: {'success': True})
        self.assertEqual(tree(build), {'main.py'})
        write(build, 'stage/a.js')
        with mock.patch.object(exe_build, '_build_exe', lambda d, j: {'success': True}):
            exe_build.build_exe({'projectName': 'App', 'projectId': 'App', 'options': {'keepWorkFiles': True}}, jobs.Job('t'))
        self.assertTrue(os.path.isfile(os.path.join(build, 'stage', 'a.js')))


if __name__ == '__main__':
    unittest.main()
