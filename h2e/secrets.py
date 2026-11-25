"""Environment files (.env.local ...): find them, classify the variables, and protect them.

What this module does, and what it does not do
----------------------------------------------
* Values never leave this module except to be (a) handed to the build process through its environment and
  (b) encrypted into the bundle. The UI only ever receives names, kinds and lengths (``describe``).
* ``encrypt_env`` uses AES-256-GCM (authenticated: a modified bundle fails to decrypt). The key is split in two
  random shares: one lives in the launcher, one in the encrypted file, so the key never appears as one string
  in the .exe and the data is bound to this exact build (AAD).
* This protects the secrets at rest against copying the file, ``strings`` and casual inspection. It cannot stop
  someone who reverse-engineers the .exe: any program that can decrypt its own secrets can be made to reveal
  them. Secrets that must stay secret from the people you give the .exe to belong on a server, not in the app.
"""
import hashlib
import json
import os
import re

MAGIC = b'H2ES'
VERSION = 1

# Next.js production load order, highest priority first.
ENV_FILE_ORDER = ('.env.production.local', '.env.local', '.env.production', '.env')
# Files that hold real values (never copied into working copies or bundles). *.example etc. are templates.
TEMPLATE_SUFFIXES = ('.example', '.sample', '.template', '.dist', '.defaults')

PUBLIC_PREFIXES = ('NEXT_PUBLIC_', 'VITE_', 'REACT_APP_', 'PUBLIC_', 'NUXT_PUBLIC_', 'EXPO_PUBLIC_', 'GATSBY_')
HIGH_RISK_NAME = re.compile(r'(DATABASE|(^|_)DB(_|$)|MONGO|POSTGRES|MYSQL|REDIS|SERVICE_ROLE|PRIVATE|PASSWORD|PASSWD|'
                            r'SECRET|JWT|CREDENTIAL|SIGNING)', re.I)
CREDENTIAL_URL = re.compile(r'^[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@', re.I)

_LINE = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s*=\s*(.*)$')


# ---------------------------------------------------------------------------- parsing
def is_env_file_name(name):
    """True for ``.env``, ``.env.local``, ``.env.production.local`` ... but not ``.env.example``."""
    return bool(re.match(r'^\.env(\..+)?$', name)) and not name.endswith(TEMPLATE_SUFFIXES)


def parse_env_text(text):
    """Parse dotenv text into an ordered dict. Supports quotes, comments, ``export``, multi-line values."""
    result = {}
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    i = 0
    while i < len(lines):
        match = _LINE.match(lines[i])
        i += 1
        if not match:
            continue
        key, raw = match.group(1), match.group(2)
        value = raw.strip()
        if value[:1] in ('"', "'"):
            quote = value[0]
            rest = value[1:]
            parts = []
            while True:
                end = _closing_quote(rest, quote)
                if end >= 0:
                    parts.append(rest[:end])
                    break
                parts.append(rest)
                if i >= len(lines):
                    break
                rest = lines[i]
                i += 1
            value = '\n'.join(parts)
            if quote == '"':
                value = value.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
        else:
            hash_at = re.search(r'\s#', value)
            if hash_at:
                value = value[:hash_at.start()]
            value = value.strip()
        result[key] = value
    return result


def _closing_quote(text, quote):
    """Index of the first unescaped closing quote in ``text``, or -1."""
    escaped = False
    for idx, ch in enumerate(text):
        if escaped:
            escaped = False
        elif ch == '\\' and quote == '"':
            escaped = True
        elif ch == quote:
            return idx
    return -1


def _expand(values):
    """${NAME} expansion against variables parsed earlier (dotenv-expand behaviour, no shell execution)."""
    pattern = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')
    for key in list(values):
        values[key] = pattern.sub(lambda m: values.get(m.group(1), os.environ.get(m.group(1), '')), values[key])
    return values


def load_project_env(folder):
    """Merge the env files of a project folder (Next.js production precedence).

    Returns ``(values, sources)``: values by name, and which file each came from.
    """
    values, sources = {}, {}
    if not folder or not os.path.isdir(folder):
        return values, sources
    for name in reversed(ENV_FILE_ORDER):                    # lowest priority first, later ones override
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8-sig', errors='replace') as fh:
                    parsed = parse_env_text(fh.read())
            except OSError:
                continue
            for key, value in parsed.items():
                values[key] = value
                sources[key] = name
    return _expand(values), sources


# ---------------------------------------------------------------------------- classification
def classify(name, value=''):
    """``('public'|'secret', 'normal'|'high')`` for a variable."""
    if name.startswith(PUBLIC_PREFIXES):
        return 'public', 'normal'
    risk = 'high' if (HIGH_RISK_NAME.search(name) or CREDENTIAL_URL.match(value or '')) else 'normal'
    return 'secret', risk


def describe(folder):
    """What the UI may show: names, kinds, lengths and source files. Never the values."""
    values, sources = load_project_env(folder)
    variables = []
    for name, value in values.items():
        kind, risk = classify(name, value)
        variables.append({'name': name, 'kind': kind, 'risk': risk, 'length': len(value), 'file': sources[name]})
    files = sorted({v['file'] for v in variables}, key=ENV_FILE_ORDER.index)
    return {'files': files, 'vars': variables}


def secret_values(values):
    """Values worth redacting from logs: real secrets of a length that cannot be a common word."""
    return {v for k, v in values.items() if classify(k, v)[0] == 'secret' and len(v) >= 8}


# ---------------------------------------------------------------------------- encryption
def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:                                # pragma: no cover - dependency is in requirements.txt
        raise RuntimeError('The "cryptography" package is required to protect secrets. '
                           'Run: pip install cryptography') from exc
    return AESGCM


def encrypt_env(values, aad):
    """Encrypt ``values`` (dict). Returns ``(blob, share)``.

    ``blob`` goes into the .exe as a data file, ``share`` goes into the launcher configuration (base64 it).
    """
    key, share = os.urandom(32), os.urandom(32)
    other = bytes(a ^ b for a, b in zip(key, share))
    nonce = os.urandom(12)
    payload = json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    ciphertext = _aesgcm()(key).encrypt(nonce, payload, aad.encode('utf-8'))
    return MAGIC + bytes([VERSION]) + other + nonce + ciphertext, share


def decrypt_env(blob, share, aad):
    """Inverse of :func:`encrypt_env`. Raises ``ValueError`` when the data was modified or is for another build."""
    if blob[:4] != MAGIC or blob[4] != VERSION:
        raise ValueError('unknown secrets format')
    other, nonce, ciphertext = blob[5:37], blob[37:49], blob[49:]
    key = bytes(a ^ b for a, b in zip(other, share))
    try:
        payload = _aesgcm()(key).decrypt(nonce, ciphertext, aad.encode('utf-8'))
    except Exception as exc:                                   # cryptography raises InvalidTag
        raise ValueError('the protected data was modified or belongs to another build') from exc
    return json.loads(payload.decode('utf-8'))


def fingerprint(values):
    """Stable hash of values, used to notice that build-time variables changed (never reversible)."""
    digest = hashlib.sha256()
    for key in sorted(values):
        digest.update(key.encode('utf-8') + b'\0' + values[key].encode('utf-8') + b'\0')
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------------------- leak scan
def find_leaks(folder, values, max_size=20_000_000):
    """Which secret values appear verbatim inside the files that are about to be bundled.

    Secrets are meant to travel encrypted, but build tools sometimes copy them into the output: prerendered pages,
    inlined constants, source maps. Returns ``{name: [relative paths]}`` (names only, never the values).
    """
    needles = {name: value.encode('utf-8') for name, value in values.items() if len(value) >= 8}
    found = {}
    if not needles or not os.path.isdir(folder):
        return found
    for root, _dirs, files in os.walk(folder):
        for filename in files:
            path = os.path.join(root, filename)
            try:
                if os.path.getsize(path) > max_size:
                    continue
                with open(path, 'rb') as fh:
                    data = fh.read()
            except OSError:
                continue
            for name, needle in needles.items():
                if needle in data:
                    found.setdefault(name, []).append(os.path.relpath(path, folder))
    return found
