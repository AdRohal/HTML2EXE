# HTML2EXE — Audit & Roadmap

Audit date: 2026-11-23 · Version audited: `f9944ac` · 26 stars · 1 release (v1.0) · no license · no tests · no CI

## 1. What the app really is today

| Feature | Real status | Evidence |
|---|---|---|
| Plain HTML → EXE | Works (PyWebView + local HTTP server + PyInstaller `--onefile`) | `builder.py` build-project |
| React/Vue/Svelte (Vite/CRA) → EXE | Mostly works *if* project has no client-side router | auto `npm install && npm run build`, then bundles `dist/build/out` |
| Next.js → EXE | Only works if user already set `output: 'export'`; no patching on the EXE path | Android path has patching, EXE path does not |
| Nuxt / Angular / Gatsby → EXE | Not handled (detected, but no build recipe) | |
| Astro | **Not supported at all** (not detected, not built) | no mention in code |
| PHP / Laravel | **Not supported** (needs a bundled PHP runtime) | no mention in code |
| Python → EXE | Works for simple scripts; imports guessed by keyword list | `convert-python-to-exe` |
| Web → Android APK (Capacitor) | Beta; React/Vue/Svelte/HTML OK, Next/Angular unfinished | README matrix |

## 2. Bugs and risks found (ordered by severity)

1. **Security: unauthenticated localhost API with `Access-Control-Allow-Origin: *`.** While the builder is open, *any website* in the user's browser can call `delete-project` (does `shutil.rmtree` on `Documents/HTML2EXE/<id>` — `projectId` is not sanitized, so `..` can escape), `open-folder`, `build-project`. Must fix before promoting the app further. Fix: random per-launch token + strict `Host`/`Origin` check, remove `*` CORS, validate ids with a whitelist regex.
2. **Generated apps break on client-side routing.** The embedded server is a plain `SimpleHTTPRequestHandler`: refreshing/navigating to `/about` in a React Router/Vue Router (history mode) app returns 404. Fix: SPA fallback to `index.html` when the path has no file extension.
3. **Import silently drops `dist/`, `build/` folders** (`shutil.copytree` ignore list at import). A pre-built project is imported *without* its build output, so every build re-runs `npm install` + `npm run build` — slow, and fails if Node is missing.
4. **Build is one blocking HTTP request** (PyInstaller can take minutes): UI has no live progress, can time out, and the log is only visible in the console. Fix: background job + polling `/api/jobs/<id>` with streamed log.
5. **Builder requires `pyinstaller` on PATH and Python installed.** No friendly doctor/check; failure messages are raw stderr. Add a "System check" screen (Python, PyInstaller, Node, WebView2, Java/SDK).
6. **No WebView2 handling in generated EXE.** Windows 10 machines without the Evergreen runtime get a blank/failed window. Detect and show an actionable message (or bootstrap).
7. **Code health:** one 2,600-line `builder.py`; `HTMLToEXEBuilder.create_project` is defined twice (lines ~2342 and ~2443); `project.json` written without `encoding='utf-8'` (non-ASCII names break); Python-to-EXE import detection is a hard-coded keyword list.
8. **Repo hygiene:** no `LICENSE` (README says "free to use", which is not a license — people can't legally reuse it), no tests, no CI, no releases after v1.0, no CONTRIBUTING/issue templates. Issue #4 is spam (an attached HTML file) — close it, don't open the attachment.
9. **Docs drift:** README duplicates a heading, mentions `projects/` and `sample_project/` which are git-ignored/not in the repo, and says Next.js APK is "partial".

## 3. Strategy

The honest pitch that fits the 26 stars and the "free, helps people" goal:

> **"Turn any web project into a Windows app or Android APK — free, no command line."**

Make the *static-output* story rock solid first (HTML, React, Vue, Svelte, **Astro static**, Next static export, Vite anything), because every one of those reduces to "find the built folder and serve it". Only then add the *runtime* frameworks (PHP/Laravel), which need a bundled runtime and are a much bigger project. Don't promise what isn't working; show a support matrix with real status in the UI.

## 4. Phased plan

### Phase 0 — Safety & trust (do first, ~1 day)
- Fix the localhost API exposure (token + origin check, remove `*` CORS, sanitize ids, confine paths).
- Add `LICENSE` (MIT recommended — matches "free for everyone"), `.github` issue templates, close spam issue.
- Add a pinned minimal smoke test + GitHub Actions (lint + import check on Windows).

### Phase 1 — Reliability of what already exists (~2–3 days)
- SPA fallback in generated server; keep `dist/build/out` on import; do not re-run npm when output exists.
- Background build jobs with live log streaming into the UI + cancel button.
- "System check" screen with one-click fix links; clear error messages.
- WebView2 detection in the generated EXE.
- Split `builder.py` into a package: `server/`, `analyzer.py`, `exe_builder.py`, `python_builder.py`, `android_builder.py`; remove duplicate method; UTF-8 everywhere.

### Phase 2 — Framework support that people asked for (~1 week)
- **Framework "recipes"** table-driven: detect → install → build → locate output → post-process.
  - React/Vue/Svelte/Vite/CRA: harden (set `base: './'` where needed).
  - **Astro**: detect `astro` dep / `astro.config.*`; run `astro build`; output `dist/` (static). SSR adapters flagged as unsupported with a clear message.
  - **Next.js**: reuse the existing Android `output:'export'` patcher on the EXE path (with backup/restore); warn on API routes.
  - **Nuxt** (`nuxt generate` → `.output/public`), **Angular** (`dist/<name>/browser`), **Gatsby** (`public`).
- Per-recipe test fixtures (tiny sample project per framework) so claims in the README are backed by a passing build.

### Phase 3 — PHP / Laravel (stretch, ~1–2 weeks)
- Bundle a portable PHP (`php -S 127.0.0.1:<port> -t public`) next to the app inside the EXE, start it from the launcher, point the WebView at it.
- Laravel: require pre-installed `vendor/`, ship SQLite by default, write `.env`/`storage` to `%APPDATA%/<app>` (the EXE's temp dir is read-only/ephemeral).
- Mark as **Experimental** until at least one real Laravel app passes end-to-end.

### Phase 4 — Polish & growth
- Per-project settings: window size, title, fullscreen, single-instance, app version/metadata in the EXE.
- Optional installer output (Inno Setup / MSIX) and portable-folder mode (faster startup than `--onefile`).
- Release the builder itself as a signed-or-documented EXE (v2.0), changelog, demo GIF in README, "Support matrix" badge row.

## 5. Order I recommend working in

1. Phase 0 security + license (cheap, protects users, makes the repo adoptable).
2. Phase 1 SPA fallback + keep-build-output + background jobs (biggest user-visible wins).
3. Phase 2 Astro + Next static on EXE path.
4. Then decide on Phase 3 based on demand.

## 6. Environment note

This machine currently has no real Python (only the Microsoft Store alias), so end-to-end testing of the builder needs a Python 3.12 install first. Node 24 is available.

## Phase 0 status (2026-11-23)
- [x] Local API locked down (token + Origin/Host checks, no wildcard CORS, id sanitising, static path-traversal fix)
- [x] MIT license, issue templates, CI, security tests
