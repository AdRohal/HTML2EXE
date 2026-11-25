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

(Written during the audit.) Python 3.12 and Node 24 are now installed on the dev machine, so the end-to-end tests in `tests/e2e_*.py` run here. PHP, Composer, a JDK and the Android SDK are not installed system-wide: the Laravel test downloads its own portable PHP and Composer, and the Android build cannot be run end-to-end until a JDK and SDK are installed.

## Phase 0 status (2026-11-23)
- [x] Local API locked down (token + Origin/Host checks, no wildcard CORS, id sanitising, static path-traversal fix)
- [x] MIT license, issue templates, CI, security tests

## Phase 1-3 status (2026-11-24, verified)

Every item below was run for real; "real build" means a real `npm`/Composer build, a real PyInstaller
EXE, and the EXE started and probed. Run the slow ones with `python tests/e2e_*.py`; the quick suite is
`python -m unittest discover -s tests` (56 tests).

**Phase 1 - reliability**
- [x] SPA fallback + `page.html` routing + correct MIME types in generated apps (real EXE, `e2e_build.py`)
- [x] Imports keep `dist/`/`build/`; fresh builds are reused, stale ones rebuilt
- [x] Background jobs with live log and Cancel for **all** build types (HTML, Python, Android). Subprocesses
      stream into the log and Cancel kills the whole process tree; a cancel is reported as "cancelled",
      not as an HTTP 500 (regression test in `test_jobs.py`)
- [x] System Check page + support matrix; WebView2 check in generated EXEs
- [x] Module split finished: `builder.py` now only holds the HTTP handler and the window; the engine lives in
      `h2e/` (recipes, exe_build, launcher, php_runtime, python_builder, android_builder, analyzer, templates,
      jobs, security, syscheck). `builder.py` went from 2,600 to ~830 lines
- [x] Fixed: duplicate `create_project`, UTF-8 everywhere (incl. templates), PyInstaller no longer needs PATH
- [x] Python-to-EXE rewritten as `h2e/python_builder.py`: imports found with `ast` (not substring matching),
      root-level data files bundled, EXE name sanitised (a `..` in the name could escape the output folder),
      and the "Single file" / "Optimize" checkboxes now actually work (they were ignored)
- [x] Android build fails fast with a clear message when Java / Android SDK / Node are missing
      (it used to run npm + Capacitor for minutes before dying in Gradle)
- [x] "Create Project" with a starter template now works: the page never called the backend, and the four
      templates (dead code) overwrote their own `index.html`. Templates are in `h2e/templates.py`
- [x] Removed dead front-end code (`api.js`, a WebSocket that retried `ws://localhost:8000` forever)
- [x] UI clicked through in a real browser: all 9 pages, System Check, Create (template) -> Build -> EXE,
      Build + Cancel, Python to EXE (the produced EXE runs), Android prerequisite failure. No JS errors

**Phase 2 - framework recipes (all real builds, `tests/e2e_recipes.py`)**
- [x] Vite, Astro, Next.js (export patch + config restored), Nuxt
- [x] Angular 18 (`dist/<name>/browser`), Gatsby 5 (`public/`)
- [x] SvelteKit 2 (Svelte 5, Vite 6) and SvelteKit 3 (Svelte 5, Vite 8, adapter set in `vite.config`)
- [x] Fixed: Windows 8.3 short paths (like `LONGNA~1` in the user folder) broke SvelteKit builds; the folder is
      now expanded to its long path before building
- [ ] Create React App has unit tests only (the tool is deprecated upstream)

**Phase 3 - PHP / Laravel**
- [x] Plain PHP: portable PHP bundled, real EXE passes
- [x] Laravel: real `composer create-project laravel/laravel` -> 82 MB EXE; `/` and `/up` return 200;
      `.env` + `APP_KEY` created and SQLite migrated per user (`tests/e2e_laravel.py`)
- [x] Self-test allows 5 minutes for PHP apps (first start copies the app and migrates) and kills the whole
      process tree on timeout, so no stray `php -S` is left behind
- Still marked **Experimental** in the UI: only one stock Laravel app has been tested, not apps with queues,
  Vite assets built at install time, or MySQL

**Known limits / not done**
- [ ] Android APK was not built end-to-end on this PC (no JDK or Android SDK installed); only the
      fail-fast path and the UI were exercised
- [ ] The Build page's "console mode / single file / optimize" checkboxes are not sent for HTML builds
      (Phase 4: per-project settings)
- [ ] impeccable design findings in `builder_ui` (contrast, accent borders) are still open


## Server apps and secrets (2026-11-24, verified)

Goal: apps with API routes and a database or third-party keys (read from `.env.local`) must work inside the
.exe, with the secrets stored encrypted and understood by the app, and the builder faster and safer.

- [x] Next.js **server mode**: detected from API routes / route handlers / middleware, built with `output: 'standalone'`,
      packed with the Node.js runtime; the .exe starts its own server on `127.0.0.1` (real build with Next 16.4.6,
      `next.config.ts`, two API routes; `tests/e2e_nextserver.py`, 19 checks)
- [x] `next.config.ts` / `.mts` / `.js` / `.cjs` / `.mjs` all supported for both static export and server mode
      (the old static path refused `.ts`); the user's config is restored byte for byte, also after a crash
- [x] `.env` handling: Next's load order, quotes / comments / multi-line / `${VAR}` expansion; the UI shows names,
      kinds and lengths only
- [x] Secrets encrypted with AES-256-GCM (key split in two shares, bound to the build); decrypted in memory by the
      launcher and handed to the server through its environment; tamper / wrong build fails to decrypt
- [x] "Do not bundle" mode + an optional `.env` in `%LOCALAPPDATA%\H2E-<app>` (verified: API 500 without, 200 with)
- [x] Hygiene: env files never copied into the working copy / stage / .exe, leftovers from older versions deleted,
      secret values redacted in logs and error text, leak scan of the built files with a named warning
- [x] Speed: dependency install keyed on package.json + lock file (reinstalls only when they change), build reuse keyed
      on sources + build-time variables, standalone bundle (about 23 MB) instead of the whole `node_modules`
- [x] Found by the real build: `TMDB_API_KEY` was classified as a database credential (matched "DB_"); fixed
- Known limits: encryption cannot protect a secret from someone who reverse-engineers the .exe (documented in the
  UI and README); only Next.js has a server mode so far (Express / Nuxt / Remix are not handled)
- [ ] Single-file startup of a server app unpacks about 100 MB each launch; a "portable folder" output would start faster


## Installer output and a clean Downloads folder (2026-11-24, verified)

- [x] **Downloads stays clean.** The temporary working copy in `Downloads\<name>` is created for the build and deleted
      afterwards (also when the build fails or is cancelled). It is only ever removed when it carries the builder's own
      marker, is not the original folder, and sits directly in Downloads. Build caches (`node_modules`, `.next` ...) are
      parked in `Documents\HTML2EXE\<name>\cache`, so rebuilds stay fast. Bulky build folders (stage, PyInstaller work)
      are deleted after a successful build. Found by the new tests: files deleted from the source used to survive in the
      working copy and were bundled; the sync now drops them.
- [x] **Choice: portable .exe or installer.** Per-user `<App>-Setup.exe`, wizard or silent, Apps & features entry with
      name / version / publisher, in-place updates that keep user data, clean uninstall.
- [x] Engines: **Inno Setup 6** when installed (preferred), otherwise a **built-in installer** (tkinter wizard, SHA-256
      check of its payload, native COM shortcuts, the installed app uninstalls itself and only deletes the folder Windows
      has registered for it). `tests/e2e_installer.py [inno|builtin]` builds, installs silently, runs the installed app,
      updates, uninstalls and verifies the registry, with real executables.
- [x] Found by the real build: Windows Defender flagged the first built-in Setup.exe (`Trojan:Win32/Bearfoos.B!ml`, a
      machine-learning false positive typical for unsigned PyInstaller programs). Mitigations: Inno preferred; the built-in
      installer no longer calls hidden PowerShell (a strong malware tell) and creates shortcuts through the shell COM API.
      Not solvable without code signing, which needs a certificate and is out of scope.
- [ ] The built-in uninstaller still uses a short-lived `cmd` helper to delete the program folder after exit
