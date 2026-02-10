# HTML to EXE Builder

A professional desktop application that converts **HTML/CSS/JavaScript** web projects and **Python** projects into standalone Windows `.exe` executables. No coding or command-line knowledge required — everything is done through a sleek graphical interface.

![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![Python](https://img.shields.io/badge/Python-3.8%2B-green)

---

## What Does This App Do?

- **HTML to EXE** — Take any web project (HTML, CSS, JavaScript) and package it as a native Windows desktop application (`.exe`). Users can run it without a browser, without a web server, without anything installed.
- **Python to EXE** *(Beta)* — Convert Python scripts and projects into standalone `.exe` files. End users don't need Python installed on their machine.

---

## Features

| Feature | Description |
|---------|-------------|
| **Single `.exe` output** | Everything bundled into one file — just share it |
| **No dependencies for end users** | Recipients don't need Python, Node.js, or anything else |
| **Custom app icon** | Upload a `.png` or `.ico` file as your app icon |
| **Project management** | Create, import, and organize multiple projects |
| **Framework detection** | Auto-detects React, Vue, Angular, jQuery, Svelte, Bootstrap, Tailwind, etc. |
| **Python to EXE (Beta)** | Convert Python projects with auto-detected imports and data files |
| **Professional GUI** | Modern, frameless desktop interface built with PyWebView |
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

### For End Users (Running the Generated `.exe`)

| Requirement | Details |
|-------------|---------|
| **Operating System** | Windows 10 or Windows 11 (64-bit) |
| **Disk Space** | Depends on the app (~50–300 MB typical) |
| **No Python needed** | The `.exe` includes everything |
| **No installation needed** | Just double-click the `.exe` to run |

> **Note:** Some antivirus software may flag PyInstaller-generated `.exe` files as suspicious. Users may need to add an exception. This is a known false positive.

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

---

## What Works in the Generated EXE

### HTML to EXE

| Supported | Not Supported |
|-----------|---------------|
| HTML5 / CSS3 | Node.js / npm modules |
| Vanilla JavaScript | Back-end servers |
| DOM manipulation | Electron APIs |
| Canvas & SVG | Direct file system access |
| localStorage API | External API calls (CORS) |
| Fetch API (local) | |
| ES6+ features | |

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
html-to-exe/
├── builder.py              # Main application (backend + API + build logic)
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── Expertus.spec            # PyInstaller spec (for building the builder itself)
├── builder_ui/             # Frontend UI files
│   ├── index.html          # Main HTML interface
│   ├── style.css           # Styles
│   ├── script.js           # Frontend logic
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

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: No module named 'webview'` | Run `pip install pywebview` |
| `ModuleNotFoundError: No module named 'pkg_resources'` | Upgrade: `pip install pyinstaller>=6.10` |
| `ImportError: get_module_collection_mode` | Upgrade: `pip install pyinstaller>=6.10` |
| Antivirus blocks the `.exe` | Add an exception in your antivirus software |
| `.exe` shows "Failed to load Python DLL" | Rebuild using **single file** mode (default) |
| First launch of `.exe` is slow | Normal — single-file mode extracts to temp on first run |
| Build fails with path errors | Ensure project path has no special/unicode characters |
| Builder GUI won't start | Run `pip install -r requirements.txt --upgrade` |

---

## FAQ

**Q: Does the end user need Python installed?**
A: No. The `.exe` includes the Python runtime and all dependencies.

**Q: Does it work on Mac or Linux?**
A: No. This tool builds Windows `.exe` files only and requires Windows to run.

**Q: Why is the `.exe` file so large (~150–300 MB)?**
A: The entire Python runtime and all required libraries are bundled inside. This is normal for PyInstaller builds.

**Q: Can I use React/Vue/Angular projects?**
A: Yes! Import your **built** project folder (the `dist` or `build` output). The app auto-detects frameworks.

**Q: The `.exe` is flagged by antivirus. Is it safe?**
A: Yes. PyInstaller-generated executables are commonly flagged as false positives. You can submit them to your antivirus vendor for whitelisting.

**Q: The first launch of my EXE is slow. Is that normal?**
A: Yes. Single-file mode extracts files to a temporary folder on the first run. Subsequent launches are faster.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the builder
python builder.py

# 3. Import a folder or create from template
# 4. Configure and build your EXE
# 5. Share with users — they just double-click to run!
```

---

## License

Free to use for personal and commercial projects.

## Resources

- [PyWebView Documentation](https://pywebview.flowrl.com/)
- [PyInstaller Documentation](https://pyinstaller.org/)
- [HTML5 Reference](https://developer.mozilla.org/docs/Web/HTML)
- [CSS3 Reference](https://developer.mozilla.org/docs/Web/CSS)
