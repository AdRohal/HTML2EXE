// Background jobs: start a long task on the backend and stream its log.
// Usage: runJob('/api/build-project', payload, lines => appendLines(lines))
//        .then(({ status, data }) => ...)   // same shape as the old fetch flow

let currentJobId = null;

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function runJob(endpoint, payload, onLines) {
    const startResponse = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({}, payload, { async: true }))
    });
    const started = await startResponse.json();
    if (!started.jobId) {
        // Server answered directly (old behaviour or an early validation error)
        return { status: startResponse.status, data: started };
    }

    currentJobId = started.jobId;
    let since = 0;
    let failures = 0;
    try {
        while (true) {
            await sleep(700);
            let snap;
            try {
                const r = await fetch(`/api/job-status?id=${encodeURIComponent(started.jobId)}&since=${since}`);
                snap = await r.json();
                failures = 0;
            } catch (err) {
                if (++failures > 20) throw err;
                continue;
            }
            if (!snap.status) {
                return { status: 404, data: { success: false, error: snap.error || 'Build job was lost' } };
            }
            since = snap.next;
            if (snap.lines && snap.lines.length && onLines) onLines(snap.lines);
            if (snap.status !== 'running') {
                const data = snap.result || { success: false, error: 'The build ended without a result' };
                if (snap.status === 'cancelled') data.error = 'Build cancelled';
                return { status: snap.status === 'done' ? 200 : 400, data: data, job: snap };
            }
        }
    } finally {
        currentJobId = null;
        document.querySelectorAll('.cancel-job-btn').forEach(b => { b.style.display = 'none'; });
    }
}

function cancelCurrentJob() {
    if (!currentJobId) return;
    fetch('/api/job-cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: currentJobId })
    }).catch(() => {});
}

function showCancelButtons() {
    document.querySelectorAll('.cancel-job-btn').forEach(b => { b.style.display = 'inline-flex'; });
}

// Append backend log lines to a <div>/<pre> and keep it scrolled to the end
function appendLogLines(elementId, lines) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent += lines.join('\n') + '\n';
    el.scrollTop = el.scrollHeight;
}

// ---------------- System check page ----------------
function loadSystemCheck() {
    const list = document.getElementById('systemCheckList');
    const matrix = document.getElementById('supportMatrix');
    if (!list) return;
    list.innerHTML = '<div class="loading">Checking your system...</div>';
    fetch('/api/system-check')
        .then(r => r.json())
        .then(data => {
            list.innerHTML = '';
            data.checks.forEach(c => {
                const row = document.createElement('div');
                row.className = 'check-row ' + (c.ok ? 'ok' : 'missing');
                const dot = document.createElement('span');
                dot.className = 'check-dot';
                dot.textContent = c.ok ? 'OK' : 'Missing';
                const body = document.createElement('div');
                body.className = 'check-body';
                const title = document.createElement('strong');
                title.textContent = c.label;
                const detail = document.createElement('span');
                detail.textContent = c.detail;
                const need = document.createElement('small');
                need.textContent = 'Needed for: ' + c.neededFor + (c.ok || !c.fix ? '' : ' — fix: ' + c.fix);
                body.append(title, detail, need);
                row.append(dot, body);
                list.appendChild(row);
            });
            if (matrix && data.frameworks) {
                matrix.innerHTML = '';
                data.frameworks.forEach(f => {
                    const row = document.createElement('div');
                    row.className = 'matrix-row';
                    const name = document.createElement('span');
                    name.textContent = f.label;
                    const badge = document.createElement('span');
                    badge.className = 'support-badge ' + f.support;
                    badge.textContent = f.support === 'supported' ? 'Supported' : 'Experimental';
                    row.append(name, badge);
                    matrix.appendChild(row);
                });
            }
        })
        .catch(err => {
            list.textContent = 'Could not run the system check: ' + err.message;
        });
}
