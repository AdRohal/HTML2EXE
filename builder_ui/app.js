'use strict';
/* HTML to EXE Builder - UI logic. Plain JS, no framework. Talks to the local API in builder.py.
   fetch('/api/...') calls are given the session token by a snippet the server injects into <head>. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ico = (id) => `<svg class="i" aria-hidden="true"><use href="#i-${id}"/></svg>`;

function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) node.append(kid);
  return node;
}

async function api(path, body) {
  const opts = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  try {
    const res = await fetch('/api/' + path, opts);
    const data = await res.json().catch(() => ({}));
    data._status = res.status;
    return data;
  } catch (err) {
    return { error: 'Could not reach the builder (' + err.message + ')', _status: 0 };
  }
}

function toast(message, bad = false) {
  const t = h('div', { class: 'toast' + (bad ? ' bad' : ''), text: message });
  $('#toasts').append(t);
  setTimeout(() => t.remove(), 3200);
}

const S = { projects: [], system: null, view: 'build' };
const REQUIRED_TOOLS = ['python', 'pyinstaller', 'pywebview', 'webview2'];
const NODE_FRAMEWORKS = ['vite', 'cra', 'astro', 'nextjs', 'nuxt', 'angular', 'gatsby', 'sveltekit', 'generic'];

/* ------------------------------------------------------------------ helpers */
const dirname = (p) => String(p || '').replace(/[\\/][^\\/]*$/, '');
const clean = (p) => String(p || '').trim().replace(/^["']+|["']+$/g, '');
const fmtTime = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const fmtDate = (iso) => { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); };
const ansi = (s) => String(s).replace(/\u001b\[[0-9;]*[A-Za-z]/g, '');
const BAD_NAME = /[\\/:*?"<>|]/;
const outputType = () => ($('input[name="outType"]:checked') || {}).value || 'portable';
function exeFileName(name) {
  // mirrors h2e/exe_build.py safe_exe_name: anything but letters, digits, _ . - becomes _
  const safe = String(name || '').trim().replace(/[^A-Za-z0-9_.-]+/g, '_').replace(/^[._]+|[._]+$/g, '');
  return (safe || 'App') + '.exe';
}
function suggestName(folderName) {
  const n = String(folderName || '').replace(/[\\/:*?"<>|]+/g, '-').trim();
  return n.slice(0, 60) || 'MyApp';
}
function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

/* ------------------------------------------------------------------ router */
const VIEWS = ['build', 'projects', 'python', 'android', 'system'];
function go(view, { focus = true } = {}) {
  if (!VIEWS.includes(view)) view = 'build';
  S.view = view;
  $$('.nav').forEach((n) => {
    if (n.dataset.view === view) n.setAttribute('aria-current', 'page'); else n.removeAttribute('aria-current');
  });
  VIEWS.forEach((v) => { $('#view-' + v).hidden = v !== view; });
  if (location.hash !== '#' + view) history.replaceState(null, '', '#' + view);
  $('#main').scrollTop = 0;
  if (view === 'projects') renderProjects();
  if (view === 'system') loadSystem();
  if (view === 'android') loadAndroid();
  if (view === 'build') renderRecent();
  if (focus) $('#h-' + view)?.focus({ preventScroll: true });
}
$$('.nav').forEach((n) => n.addEventListener('click', () => go(n.dataset.view)));

function stage(view, name) {
  const root = $('#view-' + view);
  $$('[data-stage]', root).forEach((s) => { s.hidden = s.dataset.stage !== name; });
  $('.lede', root).hidden = name === 'job';      // the job panel has its own title
}

/* inline field error (same pattern on every view): message under the field, aria-invalid, focus */
function fieldError(input, message) {
  const field = input.closest('.field');
  let p = $('.err', field);
  if (!p) { p = h('p', { class: 'err', role: 'alert' }); field.append(p); }
  p.textContent = message;
  input.setAttribute('aria-invalid', 'true');
  input.focus();
  input.addEventListener('input', () => { input.setAttribute('aria-invalid', 'false'); p.hidden = true; }, { once: true });
  p.hidden = false;
}

/* ------------------------------------------------------------------ window controls */
$('#winMin').addEventListener('click', () => api('minimize-window', {}));
$('#winMax').addEventListener('click', () => api('maximize-window', {}));
$('#winClose').addEventListener('click', () => api('close-window', {}));

/* ------------------------------------------------------------------ jobs: the tape strip */
/* cfg: { title, steps:[{label, rx}], start: async () => ({endpoint,payload}|{error}), result: (data) => {...}, retry, onDone } */
async function runJob(host, cfg) {
  host.replaceChildren($('#tpl-job').content.cloneNode(true));
  const root = $('.job', host);
  const title = $('.job-title', root), tape = $('.tape', root), now = $('.step-now', root);
  const resultBox = $('.result', root), logEl = $('.log', root), cancelBtn = $('.cancel', root), elapsedEl = $('.elapsed', root);
  title.textContent = cfg.title;
  title.focus({ preventScroll: true });

  const steps = cfg.steps.map((s, i) => h('li', { 'data-s': i === 0 ? 'active' : 'idle', html: ico('check') }, h('span', { text: s.label })));
  tape.append(...steps);
  let current = 0, jobId = null, cancelled = false;
  const t0 = Date.now();
  const timer = setInterval(() => { elapsedEl.textContent = fmtTime((Date.now() - t0) / 1000); }, 1000);
  const setStep = (idx) => {
    current = Math.max(current, idx);
    steps.forEach((li, i) => { li.dataset.s = i < current ? 'done' : i === current ? 'active' : 'idle'; });
  };

  $('.copy', root).addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(logEl.textContent); toast('Log copied'); } catch { toast('Could not copy the log', true); }
  });
  cancelBtn.addEventListener('click', async () => {
    cancelled = true;
    cancelBtn.disabled = true; cancelBtn.textContent = 'Cancelling...';
    if (jobId) await api('job-cancel', { id: jobId });
  });

  const addLines = (lines) => {
    const nearEnd = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 48;
    for (const raw of lines) {
      const line = ansi(raw);
      const cls = /^\$ /.test(line) ? 'l-cmd' : /(error|failed|traceback|ERR!|fatal)/i.test(line) ? 'l-err' : /(successful|passed|complete[d]?\b|ready)/i.test(line) ? 'l-ok' : '';
      logEl.append(cls ? h('span', { class: cls, text: line + '\n' }) : document.createTextNode(line + '\n'));
      cfg.steps.forEach((s, i) => { if (s.rx && s.rx.test(line)) setStep(i); });
      if (line.trim() && !/^\s*(INFO|WARNING|DEBUG)\b/.test(line)) now.textContent = line.trim().slice(0, 120);
    }
    if (nearEnd) logEl.scrollTop = logEl.scrollHeight;
  };

  const finish = (kind, data) => {
    clearInterval(timer);
    cancelBtn.hidden = true;
    now.textContent = '';
    if (kind === 'ok') steps.forEach((li) => { li.dataset.s = 'done'; });
    else steps[current].dataset.s = kind === 'stop' ? 'stop' : 'fail';
    resultBox.hidden = false;
    resultBox.dataset.kind = kind;
    resultBox.replaceChildren(...cfg.render(kind, data));
    title.textContent = kind === 'ok' ? 'Finished' : kind === 'stop' ? 'Cancelled' : 'Build failed';
    title.focus({ preventScroll: true });
    resultBox.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    if (kind === 'ok') { logEl.closest('details').open = false; }
  };

  // 1. preparatory step (e.g. register the project) then start the server-side job
  const started = await cfg.start(addLines);
  if (started.error) { finish('fail', { error: started.error }); return; }
  const res = await api(started.endpoint, { ...started.payload, async: true });
  if (!res.jobId) { finish(res.success === false || res.error ? 'fail' : 'ok', res); return; }
  jobId = res.jobId;

  let since = 0, misses = 0;
  while (true) {
    await new Promise((r) => setTimeout(r, 600));
    const snap = await api('job-status?id=' + encodeURIComponent(jobId) + '&since=' + since);
    if (!snap.status) { if (++misses > 15) { finish('fail', { error: snap.error || 'The builder stopped answering.' }); return; } continue; }
    misses = 0;
    since = snap.next;
    if (snap.lines?.length) addLines(snap.lines);
    if (snap.status === 'running') continue;
    const data = snap.result || {};
    if (snap.status === 'cancelled' || cancelled && /cancel/i.test(data.error || '')) finish('stop', data);
    else if (snap.status === 'done') finish('ok', data);
    else finish('fail', data);
    return;
  }
}

/* result blocks (the finished label) */
function resultBlock(kind, parts) {
  const strip = { ok: 'Done', fail: 'Failed', stop: 'Cancelled' }[kind];
  return [
    h('div', { class: 'result-strip', html: (kind === 'ok' ? ico('check') : kind === 'fail' ? ico('warn') : ico('close')) }, h('span', { text: strip })),
    h('div', { class: 'result-body' }, parts),
  ];
}
function failParts(data, again) {
  const msg = data.error || 'Something went wrong. The log below has the details.';
  const sysHint = /node\.?js|python|pyinstaller|java|android sdk|composer|jdk/i.test(msg);
  return [
    h('p', { class: 'result-text', text: msg }),
    h('div', { class: 'result-actions' },
      again && h('button', { class: 'btn btn-primary', type: 'button', onclick: again.fn, text: again.label }),
      sysHint && h('button', { class: 'btn', type: 'button', onclick: () => go('system'), text: 'Open System check' })),
  ];
}
const openFolder = (path) => api('open-folder', { folderPath: path }).then((r) => { if (r.success === false) toast(r.error || 'Could not open the folder', true); });

/* ================================================================== BUILD */
const B = { scan: null, folder: '', iconData: '', busy: false };
const bPath = $('#bPath'), bMsg = $('#bMsg');

async function browseFolder(into) {
  const res = await api('browse-folder', {});
  if (res.folderPath) { into.value = res.folderPath; return res.folderPath; }
  if (res.error) toast(res.error, true);
  return '';
}

async function scanFolder(path, name) {
  if (B.busy) { toast('A build is still running. Wait for it to finish or cancel it first.', true); return; }
  path = clean(path);
  bMsg.className = 'msg'; bMsg.textContent = '';
  if (!path) { bMsg.textContent = 'Choose a folder first.'; bPath.focus(); return; }
  bPath.value = path;
  bMsg.className = 'msg info'; bMsg.textContent = 'Reading the folder...';       // visible feedback for big projects
  $('#bBrowse').disabled = true;
  const res = await api('scan-folder', { folderPath: path });
  $('#bBrowse').disabled = false;
  bMsg.className = 'msg'; bMsg.textContent = '';
  if (!res.success) { bMsg.textContent = res.error === 'Invalid folder path' ? 'That folder does not exist. Check the path and try again.' : (res.error || 'Could not read that folder.'); return; }
  B.scan = res; B.folder = res.folderPath;
  enterReady(name);
}

function nodeMissing() {
  const c = S.system?.checks?.find((x) => x.id === 'node');
  return !!c && !c.ok;
}

function enterReady(presetName) {
  const a = B.scan.analysis || {};
  $('#rPath').textContent = B.folder;
  $('#rPath').title = B.folder;

  const detect = $('#rDetect');
  detect.replaceChildren(h('span', { class: 'chip chip-ink', text: a.frameworkLabel || a.projectType || 'Project' }));
  const sup = a.support || 'supported';
  detect.append(sup === 'supported'
    ? h('span', { class: 'chip chip-ok', html: ico('check') }, 'Supported')
    : h('span', { class: 'chip chip-warn', html: ico('warn') }, sup[0].toUpperCase() + sup.slice(1)));

  if (a.server) detect.append(h('span', { class: 'chip', html: ico('build') }, 'Runs a Node server'));
  const notes = [...(a.notes || [])];
  const fw = a.framework || 'static';
  if (fw === 'static' && !(B.scan.htmlFiles || []).length) notes.push('No .html files found in this folder. Pick the folder that contains your index.html, or a project with a build step.');
  if (NODE_FRAMEWORKS.includes(fw) && nodeMissing()) notes.push('This project needs Node.js to build, and it is not installed. Install it from System check first.');
  if (fw === 'laravel') notes.push('Laravel support is experimental: it needs a vendor folder (or Composer) and was tested on a stock app only.');
  $('#rNotes').replaceChildren(...notes.map((n) => {
    const info = /bundled Node\.js server/.test(n);          // explains what will happen, not a problem
    return h('li', { class: info ? 'note-info' : '', html: ico(info ? 'check' : 'warn') }, h('span', { text: n }));
  }));

  $('#rName').value = presetName || suggestName(B.scan.folderName);
  validateName();
  clearIcon();
  stage('build', 'ready');
  $('#main').scrollTop = 0;
  $('#rName').focus({ preventScroll: true });
  $('#rName').select();
  $('#rNextWrap').hidden = (a.framework || '') !== 'nextjs';
  $('#rNextMode').value = 'auto';
  loadEnv();
}

function validateName() {
  const input = $('#rName'), help = $('#rNameHelp');
  const name = input.value.trim();
  let err = '';
  if (!name) err = 'Give the app a name.';
  else if (BAD_NAME.test(name)) err = 'The name cannot contain / \\ : * ? " < > |';
  input.setAttribute('aria-invalid', err ? 'true' : 'false');
  help.classList.toggle('err', !!err);
  if (err) { help.textContent = err; return false; }
  const file = outputType() === 'installer' ? exeFileName(name).replace(/\.exe$/, '-Setup.exe') : exeFileName(name);
  help.replaceChildren('File name: ', h('b', { id: 'rFile', text: file }));
  const clash = S.projects.find((p) => p.id === name);
  if (clash && clash.sourceFolder && clash.sourceFolder.toLowerCase() !== B.folder.toLowerCase()) {
    help.append(' A project with this name already exists; building replaces it.');
  }
  return true;
}
$('#rName').addEventListener('input', validateName);
$$('input[name="outType"]').forEach((r) => r.addEventListener('change', () => {
  const installer = outputType() === 'installer';
  $('#rInstallerFields').hidden = !installer;
  $('#rInstallerEngine').hidden = !installer;
  if (installer) engineHint();
  $('#bBuild').firstChild.textContent = installer ? 'Build installer' : 'Build EXE';
  validateName();
}));

function clearIcon() { B.iconData = ''; $('#rIcon').value = ''; $('#rIconPrev').hidden = true; $('#rIconName').textContent = 'Default icon'; $('#rIconClear').hidden = true; }
$('#rIcon').addEventListener('change', async (e) => {
  const f = e.target.files[0];
  if (!f) return clearIcon();
  B.iconData = await readFileAsDataURL(f);
  $('#rIconPrev').src = B.iconData; $('#rIconPrev').hidden = false;
  $('#rIconName').textContent = f.name; $('#rIconClear').hidden = false;
});
$('#rIconClear').addEventListener('click', clearIcon);

$('#bBrowse').addEventListener('click', async () => { const p = await browseFolder(bPath); if (p) scanFolder(p); });
$('#bPathForm').addEventListener('submit', (e) => { e.preventDefault(); scanFolder(bPath.value); });
$('#rChange').addEventListener('click', () => { stage('build', 'choose'); $('#bBrowse').focus(); });

$('#bForm').addEventListener('submit', (e) => {
  e.preventDefault();
  if (!validateName()) return;
  if (outputType() === 'installer' && !/^\d+(\.\d+){0,3}$/.test($('#rVersion').value.trim())) {
    return fieldError($('#rVersion'), 'Use a version like 1.0.0 (numbers separated by dots).');
  }
  startBuild();
});

function startBuild() {
  const name = $('#rName').value.trim();
  const folder = B.folder, icon = B.iconData;
  const options = {
    windowWidth: Math.max(320, parseInt($('#rW').value, 10) || 1100),
    windowHeight: Math.max(240, parseInt($('#rH').value, 10) || 760),
    resizable: $('#rResize').checked,
    fullscreen: $('#rFull').checked,
    nextMode: ($('#rNextWrap').hidden ? 'auto' : $('#rNextMode').value),
    outputType: outputType(),
    appVersion: $('#rVersion').value.trim(),
    publisher: $('#rPublisher').value.trim(),
    ...envOptions(),
  };
  const again = { label: 'Change settings and try again', fn: () => { stage('build', 'ready'); $('#rName').focus(); } };
  stage('build', 'job');
  B.busy = true;
  runJob($('#view-build [data-stage="job"]'), {
    title: options.outputType === 'installer' ? `Building the installer for ${name}` : `Building ${name}`,
    steps: [
      { label: 'Prepare' },
      { label: 'Build site', rx: /Installing dependencies|Building with:|Using existing (build|static)|Downloading portable PHP|Composer|\$ npm/i },
      { label: 'Package', rx: /Preparing a clean copy|Packaging with PyInstaller|PyInstaller/i },
      { label: 'Verify', rx: /Verifying the new EXE/i },
      ...(options.outputType === 'installer' ? [{ label: 'Installer', rx: /installer/i }] : []),
    ],
    start: async (log) => {
      log(['Copying your project (dependencies and caches are skipped)...']);
      const made = await api('create-project', { name, folderPath: folder, author: '', version: '1.0.0', description: '' });
      if (!made.success) return { error: made.error || 'Could not register the project.' };
      loadProjects();
      return { endpoint: 'build-project', payload: { projectName: name, projectId: name, iconData: icon || undefined, options } };
    },
    render: (kind, data) => {
      if (kind === 'ok') {
        const verified = data.selfTest && data.selfTest.ok;
        return resultBlock('ok', [
          h('div', { class: 'result-name', text: data.exeName || exeFileName(name) }),
          h('div', { class: 'result-meta' }, data.sizeMb != null && h('span', { html: 'Size <b>' + data.sizeMb + ' MB</b>' }), data.kind === 'installer' && h('span', { html: 'Installer <b>v' + ((data.installer || {}).version || '1.0.0') + '</b>' }), h('span', { html: 'Type <b>' + (B.scan.analysis?.frameworkLabel || B.scan.analysis?.projectType || 'Web app') + '</b>' })),
          h('div', { class: 'verify ' + (verified ? 'good' : 'warn'), html: ico(verified ? 'check' : 'warn') }, verified ? 'Tested: the .exe starts and serves your app.' : 'Built, but the automatic start-up test did not pass. Run it once yourself.'),
          installerNote(data),
          serverNote(data, name),
          leakNote(data),
          h('div', { class: 'result-path', text: data.exePath || '' }),
          h('div', { class: 'result-actions' },
            h('button', { class: 'btn btn-primary', type: 'button', html: ico('folder'), onclick: () => openFolder(dirname(data.exePath)) }, 'Open folder'),
            h('button', { class: 'btn', type: 'button', onclick: resetBuild, text: 'Build another app' })),
        ]);
      }
      if (kind === 'stop') return resultBlock('stop', [h('p', { class: 'result-text', text: 'The build was cancelled. Nothing was changed in your project.' }), h('div', { class: 'result-actions' }, h('button', { class: 'btn btn-primary', type: 'button', onclick: again.fn, text: 'Back to settings' }))]);
      return resultBlock('fail', failParts(data, again));
    },
  }).finally(() => { B.busy = false; loadProjects(); });
}

function resetBuild() {
  B.scan = null; bPath.value = ''; bMsg.textContent = '';
  stage('build', 'choose'); renderRecent(); $('#bBrowse').focus();
}

/* recent list on the Build page */
function renderRecent() {
  const list = $('#bRecent'), first = $('#bFirstRun');
  const items = [...S.projects].sort((a, b) => String(b.created).localeCompare(String(a.created))).slice(0, 5);
  list.replaceChildren(...items.map((p) => h('li', {},
    h('div', { class: 'r-name' }, p.name, h('span', { class: 'r-path', text: p.sourceFolder || p.downloadFolder || '' })),
    h('span', { class: 'chip', text: projectKind(p) }),
    h('button', { class: 'btn btn-sm', type: 'button', onclick: () => rebuild(p), html: ico('refresh') }, 'Rebuild'))));
  list.hidden = !items.length;
  first.hidden = !!items.length;
  $('#h-recent').hidden = !items.length;
}
const projectKind = (p) => (p.analysis?.frameworkLabel?.split(' (')[0] || p.analysis?.projectType || 'Project').replace(/ \/ pre-built site/i, '');

function rebuild(p) {
  const path = (p.sourceFolder && p.sourceFolder.trim()) || p.downloadFolder;
  go('build', { focus: false });
  scanFolder(path, p.name);
}

function engineHint() {
  const inno = (S.system && S.system.checks || []).find((c) => c.id === 'inno');
  const el = $('#rInstallerEngine');
  if (!S.system) { el.textContent = ''; refreshSystem().then(engineHint); return; }
  el.textContent = inno && inno.ok
    ? 'Will be built with Inno Setup, the Windows standard installer compiler.'
    : 'Will be built with the built-in installer. Installing Inno Setup (System check) gives installers that antivirus programs flag less often.';
}

/* ================================================================== SECRETS (.env files)
   Only names, kinds and lengths ever reach this page; the values are read by the builder when it builds. */
function envOptions() {
  const out = { envMode: 'bundle', envExclude: [] };
  if ($('#rEnv').hidden) return out;
  out.envMode = ($('input[name="envMode"]:checked') || {}).value || 'bundle';
  out.envExclude = $$('#rEnvList input[type="checkbox"]').filter((c) => !c.checked).map((c) => c.value);
  return out;
}

function updateEnvWarning() {
  const mode = ($('input[name="envMode"]:checked') || {}).value;
  const risky = $$('#rEnvList input[type="checkbox"]').filter((c) => c.checked && c.dataset.risk === 'high');
  const warn = $('#rEnvWarn');
  warn.hidden = !(mode === 'bundle' && risky.length);
  if (!warn.hidden) {
    warn.textContent = `${risky.map((c) => c.value).join(', ')} ${risky.length === 1 ? 'looks like a credential' : 'look like credentials'}. Anyone who receives this .exe can ` +
      'extract values that are stored inside it. Keep database passwords and private keys on a server and let the app ' +
      'call it, or choose "Do not bundle" and give each person their own .env.';
  }
}

async function loadEnv() {
  const box = $('#rEnv'), info = $('#rEnvInfo');
  box.hidden = true; info.hidden = true;
  const folder = B.folder;
  const res = await api('env-scan', { folderPath: folder });
  if (folder !== B.folder || !res.success || !(res.vars || []).length) return;
  const n = res.vars.length, files = res.files.join(', ');
  const server = !!(B.scan && B.scan.analysis && B.scan.analysis.server);
  if (!server) {
    // Static sites only use variables while building (public ones are inlined into the page): nothing is stored.
    info.hidden = false;
    info.replaceChildren(h('span', { html: ico('check') }), `Found ${n} variable${n === 1 ? '' : 's'} in ${files}. They are used while building only; nothing secret is stored in the .exe.`);
    return;
  }
  $('#rEnvIntro').textContent = `Found ${n} variable${n === 1 ? '' : 's'} in ${files}. Values are never shown on screen or written to the log.`;
  $('#rEnvList').replaceChildren(...res.vars.map((v) => h('li', {},
    h('input', { type: 'checkbox', value: v.name, checked: true, 'aria-label': 'Include ' + v.name, 'data-risk': v.risk, onchange: updateEnvWarning }),
    h('span', { class: 'env-name', text: v.name, title: v.name }),
    v.kind === 'public' ? h('span', { class: 'chip', text: 'Public' })
      : v.risk === 'high' ? h('span', { class: 'chip chip-warn', html: ico('warn') }, 'Credential')
      : h('span', { class: 'chip chip-ink', text: 'Secret' }),
    h('span', { class: 'env-len', text: `${v.length} chars` }))));
  $$('input[name="envMode"]').forEach((r) => r.addEventListener('change', updateEnvWarning));
  box.hidden = false;
  updateEnvWarning();
}

function installerNote(data) {
  if (data.kind !== 'installer') return null;
  const i = data.installer || {};
  return h('p', { class: 'result-hint' }, 'Run it to install the app (current user, no administrator rights). Silent install: ',
    h('code', { text: (i.silent || 'Setup.exe /S') }), '. Installed apps can be removed in Windows settings under Apps. ',
    i.engine === 'inno' ? 'Built with Inno Setup.' : 'Built with the built-in installer; install Inno Setup (see System check) for installers that antivirus programs flag less often.',
    i.verified === false ? ' Warning: the installer check did not pass.' : '');
}

function leakNote(data) {
  const leaks = data.leaks || [];
  if (!leaks.length) return null;
  const names = leaks.map((l) => l.name).join(', ');
  return h('p', { class: 'env-warn', role: 'alert' },
    `${names} ${leaks.length === 1 ? 'was' : 'were'} found as plain text inside the built app (for example in ${leaks[0].files[0]}). ` +
    'It will be readable inside the .exe even though secrets are encrypted. Read it from the server side at run time instead of ' +
    'writing it into pages or code.');
}

function serverNote(data, name) {
  if (!data.server) return null;
  const s = data.secrets || {};
  const folder = '%LOCALAPPDATA%\\H2E-' + String(data.exeName || exeFileName(name)).replace(/\.exe$/i, '');
  let text;
  if (s.encrypted) text = h('span', {}, h('b', { text: `${s.bundled} variable${s.bundled === 1 ? '' : 's'}` }), ' encrypted (AES-256) and bundled. They are decrypted in memory when the app starts. To override a value, put a .env file in ', h('b', { text: folder }), '.');
  else if (s.mode === 'none') text = h('span', {}, h('b', { text: 'No secrets bundled.' }), ' The app reads its keys from a .env file in ', h('b', { text: folder }), '.');
  else text = h('span', { text: 'Runs its own local Node server. No secrets were found to bundle.' });
  return h('p', { class: 'result-secrets' }, text);
}

/* ================================================================== PROJECTS */
async function loadProjects() {
  const res = await api('projects');
  S.projects = res.projects || [];
  const c = $('#projCount');
  c.textContent = S.projects.length; c.hidden = !S.projects.length;
  if (S.view === 'projects') renderProjects();
  if (S.view === 'build' && !$('#view-build [data-stage="choose"]').hidden) renderRecent();
  renderAndroidRecent();
}

function renderProjects() {
  const host = $('#pTable');
  if (!S.projects.length) {
    host.replaceChildren(h('div', { class: 'empty' },
      h('h2', { text: 'No projects yet' }),
      h('p', { text: 'Build your first app and it will be listed here, so you can rebuild it after changing your code.' }),
      h('button', { class: 'btn btn-primary', type: 'button', onclick: () => go('build'), text: 'Build an app' })));
    return;
  }
  const rows = [...S.projects].sort((a, b) => String(b.created).localeCompare(String(a.created))).map((p) => {
    let armed = false;
    const del = h('button', { class: 'btn btn-sm btn-danger', type: 'button', 'aria-label': 'Delete ' + p.name, title: 'Delete', html: ico('trash') });
    const armedLabel = document.createTextNode('Confirm?');
    del.addEventListener('click', async () => {
      if (!armed) {
        armed = true; del.append(armedLabel); del.setAttribute('aria-label', 'Confirm delete ' + p.name);
        setTimeout(() => { armed = false; armedLabel.parentNode && armedLabel.parentNode.removeChild(armedLabel); del.setAttribute('aria-label', 'Delete ' + p.name); }, 3000);
        return;
      }
      const r = await api('delete-project', { projectId: p.id });
      if (r.success) { toast(`Deleted ${p.name}`); loadProjects(); } else toast(r.error || 'Could not delete the project', true);
    });
    return h('tr', {},
      h('td', {}, h('span', { class: 't-name', text: p.name }), h('span', { class: 't-sub', title: p.sourceFolder || p.downloadFolder, text: p.sourceFolder || p.downloadFolder || '' })),
      h('td', {}, h('span', { class: 'chip', text: projectKind(p) })),
      h('td', { class: 'num', text: fmtDate(p.created) }),
      h('td', {}, h('div', { class: 'row-actions' },
        h('button', { class: 'btn btn-sm', type: 'button', onclick: () => rebuild(p), html: ico('refresh') }, 'Rebuild'),
        h('button', { class: 'btn btn-sm icon-btn', type: 'button', 'aria-label': 'Open folder of ' + p.name, title: 'Open folder', onclick: () => openFolder((p.sourceFolder && p.sourceFolder.trim()) || p.downloadFolder), html: ico('folder') }),
        del)));
  });
  host.replaceChildren(h('table', { class: 'table' },
    h('thead', {}, h('tr', {}, h('th', { text: 'Project' }), h('th', { text: 'Type' }), h('th', { text: 'Created' }), h('th', { 'aria-label': 'Actions' }))),
    h('tbody', {}, rows)));
}

/* ================================================================== PYTHON */
const PY = { iconData: '' };
$('#pyBrowse').addEventListener('click', async () => { const p = await browseFolder($('#pyPath')); if (p && $('#pyName').value === 'MyApp') $('#pyName').value = suggestName(p.split(/[\\/]/).pop()); });
$('#pyIcon').addEventListener('change', async (e) => {
  const f = e.target.files[0];
  PY.iconData = f ? await readFileAsDataURL(f) : '';
  $('#pyIconPrev').hidden = !f; if (f) $('#pyIconPrev').src = PY.iconData;
  $('#pyIconName').textContent = f ? f.name : 'Default icon';
});
$('#pyForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const path = clean($('#pyPath').value), name = $('#pyName').value.trim();
  if (!path) return fieldError($('#pyPath'), 'Choose a script or project folder first.');
  if (!name) return fieldError($('#pyName'), 'Give the EXE a name.');
  const back = () => { stage('python', 'form'); };
  stage('python', 'job');
  runJob($('#view-python [data-stage="job"]'), {
    title: `Converting ${name}`,
    steps: [
      { label: 'Analyse' },
      { label: 'Package', rx: /Running PyInstaller|PyInstaller|Spec file/i },
      { label: 'Finish', rx: /BUILD SUCCESSFUL/i },
    ],
    start: async () => ({ endpoint: 'convert-python-to-exe', payload: { pythonPath: path, exeName: name, hideConsole: $('#pyHide').checked, singleFile: $('#pySingle').checked, optimize: $('#pyOpt').checked, iconData: PY.iconData || undefined } }),
    render: (kind, data) => {
      if (kind === 'ok') return resultBlock('ok', [
        h('div', { class: 'result-name', text: data.exeName || name + '.exe' }),
        h('div', { class: 'result-meta' }, data.size && h('span', { html: 'Size <b>' + data.size + '</b>' })),
        h('div', { class: 'result-path', text: data.exePath || '' }),
        h('div', { class: 'result-actions' },
          h('button', { class: 'btn btn-primary', type: 'button', html: ico('folder'), onclick: () => openFolder(dirname(data.exePath)) }, 'Open folder'),
          h('button', { class: 'btn', type: 'button', onclick: back, text: 'Convert another' })),
      ]);
      if (kind === 'stop') return resultBlock('stop', [h('p', { class: 'result-text', text: 'The conversion was cancelled.' }), h('div', { class: 'result-actions' }, h('button', { class: 'btn btn-primary', type: 'button', onclick: back, text: 'Back to settings' }))]);
      return resultBlock('fail', failParts(data, { label: 'Back to settings', fn: back }));
    },
  });
});

/* ================================================================== ANDROID */
const AN = { ok: false };
async function loadAndroid() {
  const box = $('#aPrereq');
  box.replaceChildren(h('span', { class: 'help', text: 'Checking Java, Android SDK and Node.js...' }));
  const r = await api('check-android-prereqs');
  const items = [['Java JDK 17+', r.java, 'https://adoptium.net'], ['Android SDK', r.sdk, 'https://developer.android.com/studio'], ['Node.js', r.node, 'https://nodejs.org']];
  AN.ok = !!r.allOk;
  box.replaceChildren(...items.map(([label, st, url]) => h('span', { class: 'p-item' },
    h('span', { class: 'chip ' + (st?.ok ? 'chip-ok' : 'chip-bad'), html: st?.ok ? ico('check') : ico('warn') }, st?.ok ? 'Ready' : 'Missing'),
    h('span', { text: label }),
    !st?.ok && h('button', { class: 'link', type: 'button', onclick: () => api('open-url', { url }), text: 'Install' }))),
    h('button', { class: 'btn btn-sm btn-quiet', type: 'button', onclick: loadAndroid, html: ico('refresh') }, 'Check again'));
  const missing = items.filter(([, st]) => !st?.ok).map(([l]) => l);
  $('#aGate').textContent = missing.length ? 'Install ' + missing.join(', ') + ' first, then check again.' : '';
  $('#aBuild').disabled = !AN.ok;
}
function renderAndroidRecent() {
  const box = $('#aRecent');
  if (!box) return;
  const items = [...S.projects].sort((a, b) => String(b.created).localeCompare(String(a.created))).slice(0, 6);
  box.replaceChildren(...items.map((p) => h('button', { class: 'chip chip-btn', type: 'button', onclick: () => { $('#aPath').value = (p.sourceFolder && p.sourceFolder.trim()) || p.downloadFolder; $('#aName').value = p.name; syncPkg(); }, text: p.name })));
}
const syncPkg = () => { $('#aPkg').value = 'com.example.' + (($('#aName').value || 'myapp').toLowerCase().replace(/[^a-z0-9]+/g, '') || 'myapp'); };
$('#aName').addEventListener('input', syncPkg);
$('#aBrowse').addEventListener('click', async () => { const p = await browseFolder($('#aPath')); if (p && $('#aName').value === 'MyApp') { $('#aName').value = suggestName(p.split(/[\\/]/).pop()); syncPkg(); } });
$('#aForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const path = clean($('#aPath').value), name = $('#aName').value.trim(), pkg = $('#aPkg').value.trim();
  if (!path) return fieldError($('#aPath'), 'Choose a web project folder first.');
  if (!/^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/.test(pkg)) { $('#aPkgHelp').textContent = 'Use a package id like com.example.myapp (lowercase letters and digits, dot separated).'; $('#aPkgHelp').classList.add('err'); $('#aPkg').setAttribute('aria-invalid', 'true'); $('#aPkg').focus(); return; }
  $('#aPkg').setAttribute('aria-invalid', 'false'); $('#aPkgHelp').classList.remove('err'); $('#aPkgHelp').textContent = 'Lowercase, dot separated.';
  const back = () => stage('android', 'form');
  stage('android', 'job');
  runJob($('#view-android [data-stage="job"]'), {
    title: `Building ${name} for Android`,
    steps: [
      { label: 'Prepare' },
      { label: 'Web build', rx: /npm (install|run build)|Stubbed|Next\.js|static export/i },
      { label: 'Capacitor', rx: /Capacitor|cap (init|sync|add)|npx cap/i },
      { label: 'Gradle', rx: /Gradle|assembleDebug/i },
    ],
    start: async () => ({ endpoint: 'build-android', payload: { folderPath: path, appName: name, packageName: pkg } }),
    render: (kind, data) => {
      if (kind === 'ok') return resultBlock('ok', [
        h('div', { class: 'result-name', text: name + '.apk' }),
        h('div', { class: 'result-path', text: data.apkPath || '' }),
        h('div', { class: 'result-actions' },
          h('button', { class: 'btn btn-primary', type: 'button', html: ico('folder'), onclick: () => openFolder(data.apkFolder || dirname(data.apkPath)) }, 'Open folder'),
          h('button', { class: 'btn', type: 'button', onclick: back, text: 'Build another' })),
      ]);
      if (kind === 'stop') return resultBlock('stop', [h('p', { class: 'result-text', text: 'The build was cancelled.' }), h('div', { class: 'result-actions' }, h('button', { class: 'btn btn-primary', type: 'button', onclick: back, text: 'Back to settings' }))]);
      return resultBlock('fail', failParts(data, { label: 'Back to settings', fn: back }));
    },
  });
});

/* ================================================================== SYSTEM */
async function loadSystem() {
  const body = $('#sysBody');
  if (!S.system) body.replaceChildren(h('p', { class: 'help', text: 'Checking this PC...' }));
  await refreshSystem();
  renderSystem();
}
async function refreshSystem() {
  const data = await api('system-check');
  if (data.checks) S.system = data;
  const bad = (S.system?.checks || []).filter((c) => REQUIRED_TOOLS.includes(c.id) && !c.ok);
  const dot = $('#healthDot');
  dot.dataset.s = !S.system ? '' : bad.length ? 'bad' : 'ok';
  dot.title = bad.length ? `${bad.length} required tool(s) missing` : 'Everything needed to build is installed';
}
function renderSystem() {
  const sys = S.system;
  const body = $('#sysBody');
  if (!sys) { body.replaceChildren(h('p', { class: 'err', text: 'The system check could not run.' })); return; }
  const rows = sys.checks.map((c) => {
    const optional = /optional/i.test(c.label) || /android/i.test(c.neededFor || '') && !REQUIRED_TOOLS.includes(c.id);
    const chip = c.ok ? h('span', { class: 'chip chip-ok', html: ico('check') }, 'OK') : h('span', { class: 'chip ' + (optional ? 'chip-warn' : 'chip-bad') }, optional ? 'Optional' : 'Missing');
    const isUrl = /^https:\/\//.test(c.fix || '');
    return h('div', { class: 'sys-row' }, chip,
      h('div', { class: 'sys-name', text: c.label.replace(/ \(optional\)/i, '') }),
      h('div', { class: 'sys-detail' }, c.ok ? c.detail : (isUrl ? c.detail : 'Run: ' + c.fix), h('small', { text: 'Needed for: ' + c.neededFor })),
      h('div', { class: 'sys-act' }, !c.ok && isUrl && h('button', { class: 'btn btn-sm', type: 'button', onclick: () => api('open-url', { url: c.fix }), html: ico('ext') }, 'Get')));
  });
  const fw = (sys.frameworks || []).map((f) => h('div', { class: 'sys-row' },
    h('span', { class: 'chip ' + (f.support === 'supported' ? 'chip-ok' : 'chip-warn'), text: f.support }),
    h('div', { class: 'sys-name', text: f.label.split(' (')[0] }),
    h('div', { class: 'sys-detail', text: f.label.includes(' (') ? '(' + f.label.split(' (').slice(1).join(' (') : '' }),
    h('div')));
  body.replaceChildren(
    h('div', { class: 'sys-group' }, h('h2', { class: 'sec', text: 'Tools' }), h('div', { class: 'sys-rows' }, rows)),
    h('div', { class: 'sys-group' }, h('h2', { class: 'sec', text: 'What you can build' }), h('div', { class: 'sys-rows' }, fw)));
}
$('#sysRefresh').addEventListener('click', async () => { S.system = null; await loadSystem(); toast('System checked'); });

/* ================================================================== start */
window.addEventListener('hashchange', () => { const v = location.hash.slice(1); if (v !== S.view) go(v, { focus: false }); });
(async function init() {
  go((location.hash || '#build').slice(1), { focus: false });
  await loadProjects();
  renderRecent();
  if (S.view === 'build') $('#bBrowse').focus({ preventScroll: true });
  refreshSystem();      // fills the health dot in the rail; does not block the UI
})();
