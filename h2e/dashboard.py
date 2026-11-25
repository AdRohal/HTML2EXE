"""Numbers for the Dashboard: projects, built apps, average size, recent builds.

Every successful build stores ``lastBuild`` in its ``project.json``; the dashboard only counts builds whose output
file still exists, so deleting an .exe in Explorer is reflected here.
"""
import json
import os
import platform
import sys
import time

from .security import project_dir_for, projects_root

APP_VERSION = '2.5'


def record_build(metadata_dir, result):
    """Remember the output of a successful build in ``project.json`` (never raises)."""
    try:
        path = os.path.join(metadata_dir, 'project.json')
        with open(path, encoding='utf-8') as fh:
            meta = json.load(fh)
        history = [b for b in meta.get('builds', []) if isinstance(b, dict)][-19:]
        entry = {'exePath': result.get('exePath', ''), 'sizeMb': result.get('sizeMb'),
                 'kind': result.get('kind', 'portable'), 'at': time.strftime('%Y-%m-%dT%H:%M:%S')}
        meta['lastBuild'] = entry
        meta['builds'] = history + [entry]
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(meta, fh, indent=2, ensure_ascii=False)
    except (OSError, ValueError, TypeError):
        pass


def record_for_project(project_id, result):
    folder = project_dir_for(project_id or '')
    if folder and result.get('success'):
        record_build(folder, result)


def stats():
    root = projects_root()
    projects, built, sizes, recent = 0, 0, [], []
    python_projects = 0
    if os.path.isdir(root):
        for name in os.listdir(root):
            meta_path = os.path.join(root, name, 'project.json')
            if not os.path.isfile(meta_path):
                continue
            try:
                with open(meta_path, encoding='utf-8') as fh:
                    meta = json.load(fh)
            except (OSError, ValueError):
                continue
            projects += 1
            if (meta.get('analysis') or {}).get('framework') == 'python':
                python_projects += 1
            last = meta.get('lastBuild') or {}
            exe = last.get('exePath') or ''
            if exe and os.path.isfile(exe):
                built += 1
                try:
                    sizes.append(os.path.getsize(exe) / (1024 * 1024))
                except OSError:
                    pass
                recent.append({'name': meta.get('name', name), 'exePath': exe, 'kind': last.get('kind', 'portable'),
                               'sizeMb': round(sizes[-1], 1) if sizes else None, 'at': last.get('at', ''),
                               'python': (meta.get('analysis') or {}).get('framework') == 'python'})
    recent.sort(key=lambda r: r['at'], reverse=True)
    return {
        'success': True, 'version': APP_VERSION, 'projects': projects, 'pythonProjects': python_projects,
        'builtApps': built, 'avgSizeMb': round(sum(sizes) / len(sizes), 1) if sizes else None,
        'python': platform.python_version(), 'recent': recent[:5],
        'frozen': bool(getattr(sys, 'frozen', False)),
    }
