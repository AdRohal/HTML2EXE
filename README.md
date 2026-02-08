# HTML to EXE Converter - GUI Builder

Convert HTML, CSS, and JavaScript projects into standalone Windows EXE applications with our professional desktop GUI. No installation required for end users!

## Features

✅ **Beautiful Desktop GUI** - Professional interface for managing projects  
✅ **Import Any Project** - Scan folders with any structure (handles 1000+ nested folders)  
✅ **Smart File Discovery** - Auto-finds HTML, CSS, JS files recursively  
✅ **Color Customization** - Build your own color themes with live preview  
✅ **Template Support** - Start with blank, modern UI, dashboard, or calculator templates  
✅ **Single EXE Output** - Creates standalone executable file  
✅ **No Dependencies** - End users don't need Python installed  

## System Requirements

- **Windows 7 or later** (for the built EXE)
- **Python 3.8+** (for running the builder)
- **pip** (Python package manager)

## Installation & Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Launch the Builder GUI

```bash
python builder.py
```

The builder opens in a desktop window. Start creating your projects!

## Creating a Project

### Option 1: Import Your Own Folder
1. Click **"Browse Folder"** in the Import section
2. Select a folder containing your HTML project
3. The app automatically scans and finds:
   - All HTML files (including nested ones)
   - All CSS files
   - All JavaScript files
   - Assets and images
4. Give your project a name and click **Create Project**

### Option 2: Use a Template
1. Select a template (Blank, Modern UI, Dashboard, or Calculator)
2. Enter project details (name, author, version)
3. Click **Create Project**

## Building an EXE

1. Go to **Build System** section
2. Select your project from the dropdown
3. Configure build options:
   - **Hide console window** (recommended)
   - **Single file** (all-in-one EXE)
   - **Optimize size** (minimize file size)
   - **Debug mode** (show console for troubleshooting)
4. Click **Start Building**
5. Your EXE will be created in the `dist/` folder

## Project Structure

Your HTML project folder can have any structure. The app will find:
- ✅ **index.html** (recommended as entry point)
- ✅ **Any nested HTML/CSS/JS files** (automatically discovered)
- ✅ **Assets** (images, fonts, etc.)
- ✅ **project.json** (optional metadata)

### Example Project Structure

```
my_web_app/
├── index.html
├── css/
│   ├── style.css
│   └── components.css
├── js/
│   ├── app.js
│   └── utils/
│       └── helpers.js
├── assets/
│   ├── logo.png
│   └── favicon.ico
└── project.json (optional)
```

### Optional: project.json

Create a `project.json` file in your project root:

```json
{
    "name": "My Application",
    "description": "Description of your app",
    "version": "1.0.0",
    "author": "Your Name",
    "main": "index.html"
}
```

## GUI Features

### Dashboard
- View project statistics
- See total projects and built applications
- Quick access to main functions

### Projects
- Browse all your projects
- Search by name or description
- View project details

### Build Options
- **HTML to EXE** ✅ - Fully implemented
  - Convert HTML/CSS/JS projects to standalone EXE
  - Custom icons and window titles
  - Single-file executable output
  
- **Python to EXE** ✅ - Now fully implemented
  - Convert Python projects to standalone EXE
  - Automatic entry point detection (main.py, app.py, etc.)
  - Custom application icons
  - Hide console window option
  - Single-file or directory package output

### Colors & Theme
- ROJO (red) & GHOST WHITE theme
- Add custom colors with visual color picker
- Copy hex codes to clipboard
- Save colors for reuse

### Settings
- Server configuration
- Build preferences
- Application settings

## Using the Generated EXE

Distribute the EXE to end users. They can run it directly without:
- Installing Python
- Any development tools
- Dependencies

Users can also run the EXE with a custom project folder:

```bash
MyApp.exe C:\path\to\html\project
```

## What Works in EXE

✅ HTML5 / CSS3  
✅ Vanilla JavaScript  
✅ DOM manipulation  
✅ Events & listeners  
✅ Canvas & SVG  
✅ localStorage API  
✅ Fetch API (with proxy for CORS)  
✅ ES6+ features  

## Limitations

❌ Node.js / npm modules  
❌ Back-end servers  
❌ Electron APIs  
❌ File system access (browser security)  
❌ External API calls (CORS restrictions)  

**Solution for APIs:** Use a CORS proxy or configure CORS headers on your API server.

## Troubleshooting

### Feature Status
This tool is actively under development. Here's what's currently available:

**✅ Working Features:**
- HTML/CSS/JavaScript to EXE conversion
- Python project to EXE conversion
- Project management and scanning
- Custom application icons
- PyInstaller-based packaging
- Single-file or directory executable generation
- Automatic project entry point detection
- Console window control

**🚧 Coming Soon:**
- Advanced optimization options
- Code signing for EXE files
- Multiple architecture support (32-bit/64-bit)
- UPX compression support

### Builder Won't Start
```bash
pip install -r requirements.txt --upgrade
python --version  # Must be 3.8+
```

### EXE Won't Run
- Ensure Python 3.8+ is installed
- Run `pip install -r requirements.txt`
- Windows Defender may block first-time execution - click "Run anyway"

### Folder Scan Fails
- Ensure folder path exists and is readable
- Check permissions on the folder
- Avoid network drives (use local folders)

### CORS Issues in EXE
Use a proxy service or add CORS headers to your API:
```
Access-Control-Allow-Origin: *
```

## Performance Tips

1. **Optimize Images** - Compress before adding
2. **Minify Code** - Use minifiers for production
3. **Lazy Loading** - Load resources on demand
4. **Code Splitting** - Break large JS into smaller files

## License

Free to use for personal and commercial projects.

## Resources

- [PyWebView Documentation](https://pywebview.kivy.org/)
- [PyInstaller Documentation](https://pyinstaller.org/)
- [HTML5 Documentation](https://developer.mozilla.org/docs/Web/HTML)
- [CSS3 Documentation](https://developer.mozilla.org/docs/Web/CSS)

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the builder
python builder.py

# 3. Import a folder or create from template
# 4. Configure and build your EXE
# 5. Share with users!
```

---

**Convert web apps to desktop apps with ease!**
