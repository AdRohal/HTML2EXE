# HTML to EXE Builder

A professional desktop application that converts **HTML/CSS/JavaScript** web projects into Windows `.exe` desktop apps, **Python** scripts into standalone executables, and **web frameworks** into Android APKs. No coding or command-line knowledge required — everything is done through a sleek graphical interface.

![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Python](https://img.shields.io/badge/Python-3.8%2B-green)
![Android](https://img.shields.io/badge/Android-APK-brightgreen)

---

## What Does This App Do?

- **HTML to EXE** — Take any web project (HTML, CSS, JavaScript) and package it as a native Windows desktop application (`.exe`). Users can run it without a browser, without a web server, without anything installed.
- **Python to EXE** *(Beta)* — Convert Python scripts and projects into standalone `.exe` files. End users don't need Python installed on their machine.
- **Web to Android APK** *(Beta)* — Convert HTML, React, Vue, and other web projects into native Android APK files. Works best with plain HTML/CSS/JS and React projects.

---

## Features

| Feature | Description |
|---------|-------------|
| **Single `.exe` output** | Everything bundled into one file — just share it |
| **No dependencies for end users** | Recipients don't need Python, Node.js, or anything else |
| **Custom app icon** | Upload a `.png` or `.ico` file as your app icon |
| **Project management** | Create, import, and organize multiple projects |
| **Framework detection** | Auto-detects React, Vue, Angular, jQuery, Svelte, Bootstrap, Tailwind, Next.js, etc. |
| **Python to EXE (Beta)** | Convert Python projects with auto-detected imports and data files |
| **Web to Android APK (Beta)** | Convert web projects to native Android APKs using Capacitor |
| **Professional GUI** | Modern, frameless dark-themed desktop interface built with PyWebView |
| **Color & Theme panel** | Manage and explore color palettes for your projects |

---

## System Requirements

### To Run the Builder App (Developer Machine)

| Requirement | Details |
|-------------|---------|
| **Operating System** | Windows 10 or Windows 11 (64-bit) |
| **Python** | Version **3.8 to 3.12** recommended. Python 3.13+ works but requires PyInstaller 6.10+ |
| **pip** | Python package manager (included with Python) |
| **Disk Space** | ~500 MB free (for Python packages and build output) |
| **RAM** | 4 GB minimum, 8 GB recommended |
| **Internet** | Required only for initial package installation |

### For Android APK Building (Web to Android)

These are **optional** — only needed if using the Web to Android feature:

| Requirement | Details |
|-------------|---------|
| **Java Development Kit (JDK)** | Java 17–24 (bundled with Android Studio JBR is auto-detected) |
| **Android SDK** | Installed at `%LOCALAPPDATA%\Android\Sdk` (Android Studio handles this) |
| **Node.js** | v18+ (required for npm and web framework builds) |
| **Gradle** | Auto-downloaded on first build (~500 MB) |

> **Tip:** Install [Android Studio](https://developer.android.com/studio) for the easiest setup. It includes JDK, SDK, and Gradle. The builder auto-detects these.

### For End Users (Running the Generated Files)

| File Type | Requirements |
|-----------|--------------|
| **Windows `.exe`** | Windows 10+ (64-bit) — no Python, no install needed |
| **Android `.apk`** | Android 6.0+ device — install like any app |
| **Python `.exe`** | Windows 10+ (64-bit) — no Python, no install needed |

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/AdRohal/HTML2EXE.git
cd HTML2EXE
```

### 2. Create a Virtual Environment (Recommended)

```bash
python -m venv .venv
```

Activate it:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- **pywebview** (>= 5.0) — Desktop GUI framework (renders the HTML interface)
- **pyinstaller** (>= 6.10) — Packages Python apps into standalone executables
- **Pillow** (>= 10.0) — Image processing (converts PNG icons to ICO format)

### 4. Run the App

```bash
python builder.py
```

The builder GUI will open automatically.

---

## How to Use

### Converting HTML to EXE

1. Open the app (`python builder.py`)
2. Go to **Existing Project** in the sidebar
3. Click **Browse Folder** and select your HTML project folder
4. Fill in the project name, author, and description
5. Click **Add Existing Project**
6. Go to **Build System** in the sidebar
7. Select your project from the dropdown
8. Optionally set a custom icon (`.png` or `.ico`)
9. Click **Start Building**
10. Your `.exe` will be saved to your **Downloads** folder

### Converting Python to EXE (Beta)

1. Open the app (`python builder.py`)
2. Go to **Python to EXE** in the sidebar
3. Click **Browse Project** and select your Python project folder
4. Set the executable name and optional icon
5. Configure options (hide console, single file, etc.)
6. Click **Start Conversion**
7. Your `.exe` will be saved to your **Downloads** folder

> **Tip:** Your Python project should have a `main.py`, `app.py`, or `run.py` as the entry point. If none of these exist, the first `.py` file found will be used.

### Converting Web to Android APK (Beta)

1. Open the app (`python builder.py`)
2. Go to **Web to Android** in the sidebar
3. Check **Prerequisites** — ensure Java, Android SDK, and Node.js are installed (green checkmarks)
4. Under **Web Source**, select your web project folder (HTML, React, Vue, etc.)
5. Fill in package name (e.g., `com.example.myapp`) and app name
6. Click **Build APK**
7. The builder will:
   - Detect your framework (plain HTML, React, Vue, etc.)
   - Build the web project (if needed)
   - Initialize Capacitor and Gradle
   - Compile the APK
8. Your `.apk` file will be saved to `Documents\HTML2EXE_Android\<app_name>\android\app\build\outputs\apk\debug\`

> **Note:** The first APK build takes **5–15 minutes** — Gradle downloads 1+ GB of dependencies. Subsequent builds are faster.

### Web to Android Support Matrix

| Framework | Status | Notes |
|-----------|--------|-------|
| **Plain HTML/CSS/JS** | ✅ Fully Supported | Works perfectly |
| **React (Vite, Create React App)** | ✅ Fully Supported | Detects and builds automatically |
| **Vue (Vite)** | ✅ Fully Supported | Works out of the box |
| **Svelte / SvelteKit** | ✅ Fully Supported | Builds to static site |
| **Angular** | 🚧 In Development | API routes block static export; need workaround |
| **Next.js 13+ (App Router)** | 🚧 In Development | API routes / dynamic routes require stubbing; fallback uses `.next/server/app` |
| **Nuxt 3** | ⚠️ Experimental | Should work; not fully tested |
| **Gatsby** | ⚠️ Experimental | Limited testing |

> **Limitations:** 
> - No server-side features (API routes, SSR, form submission to backend)
> - No external API calls (CORS blocks requests)
> - localStorage and sessionStorage work fine
> - Web Workers and Service Workers untested

---

## What Works in the Generated Files

### HTML to EXE & Web to Android APK

### HTML to EXE & Web to Android APK

| Supported | Not Supported |
|-----------|---------------|
| HTML5 / CSS3 | Node.js / npm modules |
| Vanilla JavaScript | Back-end servers / API routes |
| DOM manipulation | Electron-specific APIs |
| Canvas & SVG | Direct file system access (except Android storage) |
| localStorage API | CORS-blocked external API calls |
| sessionStorage API | Server-side rendering (SSR) |
| Fetch API (local) | WebSockets |
| ES6+ features | Backend form submission |
| React, Vue, Svelte | External CDN resources (must be bundled) |
| CSS animations & transitions | Plugins that require server |

> **For Android:** Capacitor provides limited file system and device access APIs. Most web projects work unchanged, but server-dependent features won't function without a backend.

### Python to EXE

| Supported | Notes |
|-----------|-------|
| Standard Python scripts | Auto-detects entry point |
| Third-party packages | Auto-detected from imports |
| Data files (JSON, YAML, CSV, etc.) | Bundled automatically |
| GUI frameworks (tkinter, PyQt, etc.) | Works out of the box |
| Web frameworks (Flask, Django) | Requires proper configuration |

---

## Project Structure

```
HTML2EXE/
├── builder.py              # Main application (backend + API + build logic)
│                           # Includes: HTML→EXE, Python→EXE, Web→Android APK builders
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── builder_ui/             # Frontend UI files
│   ├── index.html          # Main HTML interface (Dashboard, Build System, Python to EXE, Web to Android)
│   ├── style.css           # Dark theme styling
│   ├── script.js           # Frontend logic & event handlers
│   ├── api.js              # API communication layer
│   └── assets/             # Images, logos, etc.
├── projects/               # Local project templates
└── sample_project/         # Example HTML project
    ├── index.html
    ├── style.css
    ├── script.js
    └── project.json
```

---

## Storage Locations

| What | Where |
|------|-------|
| Project metadata | `Documents\HTML2EXE\<project_name>\project.json` |
| Project files (copied) | `Downloads\<project_name>\` |
| Built `.exe` files | `Downloads\` |
| Python build cache | `Documents\HTMLToExe_PythonBuilds\` |
| Android build working dir | `Documents\HTML2EXE_Android\<app_name>\` |
| Built `.apk` file | `Documents\HTML2EXE_Android\<app_name>\android\app\build\outputs\apk\debug\` |

---

## Troubleshooting

### General

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'webview'` | Run `pip install pywebview` |
| `ModuleNotFoundError: No module named 'pkg_resources'` | Upgrade: `pip install pyinstaller>=6.10` |
| `ImportError: get_module_collection_mode` | Upgrade: `pip install pyinstaller>=6.10` |
| Builder GUI won't start | Run `pip install -r requirements.txt --upgrade` |
| Build fails with path errors | Ensure project path has no special/unicode characters |

### HTML to EXE

| Problem | Solution |
|---------|----------|
| Antivirus blocks the `.exe` | Add an exception in your antivirus software |
| `.exe` shows "Failed to load Python DLL" | Rebuild using **single file** mode (default) |
| First launch of `.exe` is slow | Normal — single-file mode extracts to temp on first run |

### Python to EXE (Beta)

| Problem | Solution |
|---------|----------|
| Missing module errors in `.exe` | Add module to **data files** if it's not auto-detected |
| `.exe` won't find config files | Use relative paths or ship files in project root |

### Web to Android APK (Beta)

| Problem | Solution |
|---------|----------|
| `JAVA_HOME is not set` | Install Android Studio; builder auto-detects JBR or set `JAVA_HOME` manually |
| `Android SDK not found` | Install Android Studio or set `ANDROID_HOME` environment variable |
| Gradle build timeout (>30 min) | First build downloads 1+ GB — this is normal; check disk space |
| White screen / blank APK | Web project didn't build correctly; check build logs for errors |
| APK install fails on device | Device must be Android 6.0+; allow installation from unknown sources |
| API routes don't work in APK | By design — APKs are static sites; no backend server available |
| Next.js/Angular APK fails | Framework needs more work; stick to plain HTML/React/Vue for now |

---

## FAQ

**Q: Does the end user need Python installed?**
A: No. The `.exe` includes the Python runtime and all dependencies.

**Q: Does it work on Mac or Linux?**
A: No. This tool builds Windows `.exe` files only and requires Windows to run. However, generated APKs work on any Android device.

**Q: Why is the `.exe` file so large (~150–300 MB)?**
A: The entire Python runtime and all required libraries are bundled inside. This is normal for PyInstaller builds.

**Q: Can I use React/Vue/Angular projects?**
A: Yes! Import your **built** project folder (the `dist` or `build` output) for EXE. For APK, React and Vue work great; Angular is still in development.

**Q: The `.exe` is flagged by antivirus. Is it safe?**
A: Yes. PyInstaller-generated executables are commonly flagged as false positives. You can submit them to your antivirus vendor for whitelisting.

**Q: The first launch of my EXE is slow. Is that normal?**
A: Yes. Single-file mode extracts files to a temporary folder on the first run. Subsequent launches are faster.

**Q: What's the difference between HTML to EXE and Web to Android APK?**
A: **EXE** packages web apps as Windows desktop apps (Windows 10+). **APK** packages the same web app as a native mobile app (Android 6.0+).

**Q: Does the APK require an internet connection?**
A: No. The app is entirely self-contained. However, any features that call external APIs will need internet.

**Q: Why don't API routes work in the APK?**
A: APKs are static sites — there's no Node.js backend. Server-side features (API routes, database calls, etc.) won't work. Use a real backend service if needed.

**Q: Can I use Next.js or Angular with APK?**
A: Partially. Plain Next.js/Angular apps work as fallback (extracted from `.next/server/app`). However, features like dynamic routes, API routes, and SSR won't fully work. We're working to improve this.

**Q: How much storage does the APK use?**
A: Typically 30–150 MB depending on the web project. Larger with images/videos.

**Q: Can I distribute the APK on Google Play Store?**
A: Yes, but you'll need a Play Store developer account, signing key, and to follow their guidelines. The APK is just a regular app from a Play Store perspective.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the builder
python builder.py

# 3a. Convert HTML to EXE
#     - Go to "Build System" → import project → build
#
# 3b. Convert Python to EXE
#     - Go to "Python to EXE" → select script → build
#
# 3c. Convert Web to Android APK
#     - Go to "Web to Android" → select web project → build APK
#     - (Requires Android SDK, Java, Node.js — builder checks for you)

# 4. Share the output file with users — they just double-click to run!
```

---

## Version History

- **v2.0** (Current) — Web to Android APK support, dark theme redesign, copy log output, improved Next.js handling
- **v1.0** — Initial release with HTML to EXE and Python to EXE

---

## License

Free to use for personal and commercial projects.

## Resources

### General
- [PyWebView Documentation](https://pywebview.flowrl.com/)
- [PyInstaller Documentation](https://pyinstaller.org/)
- [HTML5 Reference](https://developer.mozilla.org/docs/Web/HTML)
- [CSS3 Reference](https://developer.mozilla.org/docs/Web/CSS)

### Web to Android (Capacitor)
- [Capacitor Documentation](https://capacitorjs.com/)
- [Capacitor Android Guide](https://capacitorjs.com/docs/android)
- [Gradle Documentation](https://gradle.org/docs/)
- [Android Developer Docs](https://developer.android.com/)
- [Next.js Static Export](https://nextjs.org/docs/advanced-features/static-html-export)
