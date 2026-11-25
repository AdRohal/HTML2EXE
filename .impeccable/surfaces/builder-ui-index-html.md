---
version: 1
slug: "builder-ui-index-html"
primary_target: "builder_ui/index.html"
related_targets: []
---

# Builder UI (HTML2EXE desktop window)

Mode: Operate. Unattended run: the owner was away and asked not to be asked; the rolled direction was built
without a decision page. Surface = the whole app shell (Build, Projects, Python to EXE, Android APK, System check).
Owner decision after the first build: keep the ORIGINAL brand look (dark navy, violet, the HTML2EXE logo).

Audience / job: a Windows hobbyist or freelancer with a finished project folder who wants a working .exe in
one sitting. Frequency: a few builds per project. A build takes minutes, so progress, log and Cancel carry
the screen. Constraints: backend API fixed; frameless pywebview window; no JS framework, no build step.

Removed on purpose: Colors & Theme page, Dashboard, Create Project, Existing Project, Settings, help modal.

## Direction contract

THESIS: One screen turns a folder into an .exe and behaves like a label maker: every state is a strip of
printed tape (detected, queued, printing, done). Refuses the dashboard of stat cards and the wizard of five pages.

OWN-WORLD: Dark navy page (#0f172a), darker navy rail and title bar (#0d1526), slate cards (#1e293b, #162032,
#263248). Violet is the single accent (#a78bfa / #7c3aed); the primary button is a violet gradient with white text
and a neutral shadow, active nav is a violet tint. Status colours: mint success, amber warning, coral danger.
Tape strip: done #7c3aed, active #a78bfa with a sliding bar, fail coral, finished label mint. Bahnschrift
SemiCondensed caps for labels and tape, Segoe UI for text, Cascadia Mono for paths and the log. The HTML2EXE logo
sits at the top of the rail. Hairline borders, soft neutral shadows only (no coloured glow), drawn stroke icons, no emoji.

STORY: Pick the folder (Browse or paste a path). See what was detected and what will be printed (name, icon,
window). Press Build. Watch the tape feed through four stages with a live log and Cancel. Get a finished
label: file name, size, location, "starts and serves your app: verified", Open folder.

FIRST VIEWPORT: 244px navy rail with the logo block and five nav items, Build active as a violet tint. Main area:
heading "Build a Windows app", one wide dashed slot (Browse for folder button + path field), then "Recent
projects" with one-click Rebuild. After a folder is chosen the slot collapses to a summary row and a settings
panel opens beneath it with the primary action "Build EXE" (violet gradient) pinned at the bottom-right.

FORM: Operate shell, rail + single work area, standard controls (buttons, inputs, details, tables). World
lends type, palette, density and one signature move only: the progress strip. Position 3 of the ordered
grounded list (parcel waybill, crate handling marks, label-maker tape, packing list, timetable, dispensing
label, circulation card). seed:8d2b7f6db1b7e666

Signature move: build progress drawn as a strip of label tape feeding out, one printed segment per stage,
the finished build ends as a cut label carrying the exe name.

Unresolved: none blocking. Android flow cannot be exercised end to end on the dev machine (no JDK/SDK).
