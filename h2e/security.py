"""Security helpers for the builder's local API and project folders."""
import os
import re
import secrets

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------
# The builder exposes a local HTTP API that can delete folders and run builds.
# Every /api/ request must carry this per-launch secret (injected into our own
# page only) and must come from our own origin. A random website open in the
# user's browser can neither read the token nor pass the Origin/Host checks.
API_TOKEN = secrets.token_urlsafe(32)

_SAFE_ID_RE = re.compile(r'^[^\\/:*?"<>|\x00-\x1f]{1,100}$')


def projects_root():
    """Folder that holds project metadata."""
    return os.path.join(os.path.expanduser('~'), 'Documents', 'HTML2EXE')


def is_safe_project_id(value):
    """True if value is a plain folder name (no separators, no '..')."""
    return (isinstance(value, str) and value.strip() not in ('', '.', '..')
            and value == value.strip() and bool(_SAFE_ID_RE.match(value)))


def project_dir_for(project_id):
    """Return the metadata dir for a project id, or None if the id is unsafe."""
    if not is_safe_project_id(project_id):
        return None
    root = os.path.realpath(projects_root())
    path = os.path.realpath(os.path.join(root, project_id))
    if os.path.dirname(path) != root:
        return None
    return path
