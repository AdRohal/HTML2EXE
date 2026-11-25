# Product

<!-- impeccable:product-schema 1 -->

> Written without an interview: the owner asked not to be asked and was away. Every statement below is
> inferred from the repository and the brief, and marked (inferred) where it is a judgement, not a fact.

## Platform

web

(The UI is HTML/CSS/JS served by a local Python server and shown in a frameless pywebview window on
Windows. It is a desktop tool, not a website.)

## Stack

Existing: plain HTML, CSS and vanilla JavaScript in `builder_ui/` (no framework, no build step). Keep it.

## Users

(inferred) Hobbyists, students and freelance developers on Windows who have a finished web project
(plain HTML, a React/Vue/Astro/Next/Nuxt/Angular/SvelteKit build, a PHP or Laravel app) or a Python
script, and want a double-clickable `.exe` (or an Android APK) to hand to someone else, without learning
PyInstaller, Electron or the command line. They use the tool a few times per project, in short sessions.

## Product Purpose

Turn a project folder into a Windows desktop app in as few steps as possible: pick the folder, see what
was detected, press build, watch it work, get the `.exe`. Success is a first-time user producing a working
`.exe` in under two minutes and understanding what happened if it fails.

## Positioning

Free, local, no account, no command line. It also detects the framework, runs the build for you, bundles
a PHP runtime when needed, and proves the finished `.exe` starts and serves the app before reporting success.

## Operating Context

- Frameless window with its own title bar (minimize / maximize / close are API calls).
- A build takes 1-10 minutes, so the live log, progress and Cancel matter more than anything else on screen.
- Machine requirements are uneven (Node, Java, Android SDK may be missing), so "what is missing and how to
  fix it" is part of the product.
- Output lands in the user's Downloads folder; project records live in Documents\HTML2EXE.

## Capabilities and Constraints

- Backend API contract in `builder.py` is fixed for this redesign (same endpoints and payloads).
- Web build -> EXE (static frameworks, PHP, Laravel experimental), Python -> EXE, Web -> Android APK (beta).
- System Check page lists tools and framework support.
- Per-build window options the backend already supports: width, height, resizable, fullscreen, icon, name.
- Next.js apps with API routes run as a server app (bundled Node.js). Secrets from .env files are shown by name only,
  encrypted into the app or left out, never logged; the UI must say plainly that this cannot stop a determined reverse engineer.
- Android needs JDK 17+, Android SDK, Node. Not available on the dev machine, so it cannot be exercised end to end.
- Project names are limited to letters, digits, `-` and `_` (backend rule).

## Brand Commitments

Name: "HTML to EXE Builder" (repo: HTML2EXE). Existing logo files live in `builder_ui/assets/`. MIT licensed.
No other binding brand or visual commitments were given; the old purple-gradient look is explicitly not
binding (owner: "remove the useless stuff, for example the colors").

## Evidence on Hand

Real data only: detected framework and support level from `/api/system-check` and `/api/projects`.
No testimonials, user counts or benchmarks exist; none may be invented.

## Product Principles

1. The primary path is one screen: folder in, EXE out. Everything else is secondary and out of the way.
2. Show what is happening: detected framework, current step, live log, and a plain-language result.
3. Failure states name the problem and the fix (missing Node, missing JDK, unsupported SSR), never a stack trace first.
4. No decoration without a job: no theme pickers, no gradients for their own sake, no dashboard filler.
5. Honest about maturity: Laravel and Android are labelled experimental/beta, with what is untested.

## Accessibility & Inclusion

Keyboard operable end to end (including folder picking, build, cancel), visible focus, WCAG AA contrast,
respect `prefers-reduced-motion`. Windows high-DPI. Plain English copy; many users are not native speakers
(inferred).
