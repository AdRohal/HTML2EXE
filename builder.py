"""
HTML to EXE Builder - GUI Application
Professional UI for managing projects and building EXEs
"""

import os
import sys
import json
import uuid
import webview
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import argparse
import subprocess
import shutil
from datetime import datetime
import tkinter as tk
from tkinter import filedialog
import base64
import io

# Force UTF-8 encoding for console output to support emojis and Unicode
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


class BuilderHTTPHandler(SimpleHTTPRequestHandler):
    """HTTP handler for serving builder UI and API"""
    
    builder_root = None

    def handle_error(self, request, client_address):
        """Suppress harmless connection-aborted errors (client closed window)."""
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, ConnectionAbortedError):
            return
        super().handle_error(request, client_address)
    
    def do_GET(self):
        """Handle GET requests"""
        # Parse URL
        parsed = urlparse(self.path)
        path = parsed.path
        
        # API endpoints
        if path.startswith('/api/'):
            self.handle_api_request(path[5:], 'GET')
            return
        
        # Serve builder UI
        if path == '/' or path == '/index.html':
            self.serve_file('builder_ui/index.html')
            return
        
        # Serve static files
        static_files = {
            '/style.css': 'builder_ui/style.css',
            '/script.js': 'builder_ui/script.js',
            '/api.js': 'builder_ui/api.js',
        }
        
        # Serve assets (images, etc)
        if path.startswith('/assets/'):
            asset_path = 'builder_ui' + path
            self.serve_file(asset_path)
            return
        
        if path in static_files:
            self.serve_file(static_files[path])
            return
        
        self.send_error(404, "Not Found")
    
    def do_POST(self):
        """Handle POST requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith('/api/'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            self.handle_api_request(path[5:], 'POST', body)
            return
        
        self.send_error(404, "Not Found")
    
    def do_PUT(self):
        """Handle PUT requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith('/api/'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            self.handle_api_request(path[5:], 'PUT', body)
            return
        
        self.send_error(404, "Not Found")
    
    def do_DELETE(self):
        """Handle DELETE requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith('/api/'):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            self.handle_api_request(path[5:], 'DELETE', body)
            return
        
        self.send_error(404, "Not Found")
    
    def handle_api_request(self, endpoint, method, body=None):
        """Handle API requests"""
        try:
            if endpoint == 'projects' and method == 'GET':
                # List all existing projects from Documents/HTML2EXE folder
                try:
                    projects = []
                    user_home = os.path.expanduser('~')
                    projects_dir = os.path.join(user_home, 'Documents', 'HTML2EXE')
                    
                    print(f"\n📂 Searching for projects in: {projects_dir}")
                    
                    if os.path.exists(projects_dir):
                        project_list = os.listdir(projects_dir)
                        print(f"Found {len(project_list)} project folder(s)")
                        
                        for project_name in project_list:
                            project_path = os.path.join(projects_dir, project_name)
                            if os.path.isdir(project_path):
                                # Check if it has project.json
                                project_json_path = os.path.join(project_path, 'project.json')
                                project_meta = {}
                                
                                print(f"  ✓ Loading: {project_name}")
                                
                                if os.path.exists(project_json_path):
                                    try:
                                        with open(project_json_path, 'r', encoding='utf-8') as f:
                                            project_meta = json.load(f)
                                    except Exception as e:
                                        print(f"    ⚠️  Error reading metadata: {e}")
                                
                                project_info = {
                                    'id': project_name,
                                    'name': project_meta.get('name', project_name),
                                    'path': project_path,
                                    'downloadFolder': project_meta.get('downloadFolder', ''),
                                    'description': project_meta.get('description', ''),
                                    'version': project_meta.get('version', 'unknown'),
                                    'author': project_meta.get('author', ''),
                                    'created': project_meta.get('created', ''),
                                    'analysis': project_meta.get('analysis', {
                                        'projectType': 'Unknown',
                                        'frameworks': [],
                                        'technologies': []
                                    })
                                }
                                projects.append(project_info)
                    else:
                        print(f"  Projects directory does not exist yet")
                    
                    print(f"Returning {len(projects)} project(s)\n")
                    self.send_json({'success': True, 'projects': projects})
                except Exception as e:
                    print(f"❌ Error listing projects: {e}")
                    self.send_json({'error': str(e)}, 500)
            
            elif endpoint == 'system-info' and method == 'GET':
                info = {
                    'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    'platform': sys.platform,
                    'pywebview_version': webview.__version__,
                }
                self.send_json(info)
            
            elif endpoint == 'settings' and method == 'GET':
                self.send_json({
                    'serverPort': 8000,
                    'windowWidth': 1024,
                    'windowHeight': 768,
                })
            
            elif endpoint == 'scan-folder' and method == 'POST':
                # Get folder path from request body
                if body:
                    # body is already decoded as string
                    data = json.loads(body)
                    folder_path = data.get('folderPath', '')
                    
                    # Create builder instance to scan folder
                    builder = HTMLToEXEBuilder()
                    result = builder.scan_folder(folder_path)
                    self.send_json(result)
                else:
                    self.send_json({'error': 'No folder path provided'}, 400)
            
            elif endpoint == 'analyze-project' and method == 'POST':
                # Analyze a project folder
                if body:
                    data = json.loads(body)
                    folder_path = data.get('folderPath', '')
                    
                    analyzer = ProjectAnalyzer(folder_path)
                    analysis = analyzer.analyze()
                    self.send_json({'success': True, 'analysis': analysis})
                else:
                    self.send_json({'error': 'No folder path provided'}, 400)
            
            elif endpoint == 'browse-folder' and method == 'POST':
                # Open Windows folder browser dialog
                try:
                    # Hide the root window
                    root = tk.Tk()
                    root.withdraw()
                    root.attributes('-topmost', True)
                    
                    # Open folder dialog
                    folder_path = filedialog.askdirectory(
                        title='Select a folder containing your HTML project',
                        initialdir=os.path.expanduser('~')
                    )
                    
                    root.destroy()
                    
                    if folder_path:
                        self.send_json({'success': True, 'folderPath': folder_path})
                    else:
                        self.send_json({'success': False, 'cancelled': True})
                except Exception as e:
                    self.send_json({'error': f'Failed to open folder dialog: {str(e)}'}, 500)
            
            elif endpoint == 'build-project' and method == 'POST':
                # Build project to EXE using PyInstaller
                if body:
                    try:
                        data = json.loads(body)
                        project_name = data.get('projectName', '')
                        project_id = data.get('projectId', '')
                        icon_path = data.get('iconPath', '')
                        
                        print(f"\n{'='*60}")
                        print(f"🔨 BUILDING EXE: {project_name}")
                        print(f"{'='*60}")
                        print(f"Project ID: {project_id}")
                        if icon_path:
                            print(f"Icon: {icon_path}")
                        
                        if not project_name or not project_id:
                            self.send_json({'error': 'Project name and ID required'}, 400)
                            return
                        
                        user_home = os.path.expanduser('~')
                        metadata_dir = os.path.join(user_home, 'Documents', 'HTML2EXE', project_id)
                        project_json_path = os.path.join(metadata_dir, 'project.json')
                        
                        print(f"\n📂 Looking for metadata: {project_json_path}")
                        
                        # Read project metadata
                        if not os.path.exists(project_json_path):
                            print(f"❌ Metadata not found!")
                            self.send_json({'error': f'Project metadata not found'}, 404)
                            return
                        
                        print(f"✅ Metadata found")
                        
                        with open(project_json_path, 'r') as f:
                            project_meta = json.load(f)
                        
                        project_folder = project_meta.get('downloadFolder', '')
                        print(f"📦 Project folder: {project_folder}")
                        
                        if not os.path.isdir(project_folder):
                            print(f"❌ Project folder not found!")
                            self.send_json({'error': f'Project folder not found: {project_folder}'}, 404)
                            return
                        
                        print(f"✅ Project folder exists")

                        # Auto-build if this is a source project (React/Vue/Angular/etc.)
                        has_package_json = os.path.exists(os.path.join(project_folder, 'package.json'))
                        has_src_dir = os.path.isdir(os.path.join(project_folder, 'src'))
                        has_dist = os.path.isdir(os.path.join(project_folder, 'dist'))
                        has_build_out = os.path.isdir(os.path.join(project_folder, 'build'))
                        is_source_project = has_package_json and has_src_dir and not (has_dist or has_build_out)

                        if is_source_project:
                            print(f"\n📦 Source project detected — running npm build automatically...")
                            try:
                                # Run npm install
                                print(f"  → npm install ...")
                                r1 = subprocess.run(
                                    'npm install',
                                    cwd=project_folder,
                                    capture_output=True, text=True,
                                    shell=True
                                )
                                if r1.returncode != 0:
                                    self.send_json({'error': f'npm install failed:\n{r1.stderr}'}, 500)
                                    return
                                print(f"  ✅ npm install done")

                                # Run npm run build
                                print(f"  → npm run build ...")
                                r2 = subprocess.run(
                                    'npm run build',
                                    cwd=project_folder,
                                    capture_output=True, text=True,
                                    shell=True
                                )
                                if r2.returncode != 0:
                                    self.send_json({'error': f'npm run build failed:\n{r2.stderr}'}, 500)
                                    return
                                print(f"  ✅ npm run build done")

                                # Find the output folder (dist/ or build/)
                                if os.path.isdir(os.path.join(project_folder, 'dist')):
                                    project_folder = os.path.join(project_folder, 'dist')
                                elif os.path.isdir(os.path.join(project_folder, 'build')):
                                    project_folder = os.path.join(project_folder, 'build')
                                elif os.path.isdir(os.path.join(project_folder, 'out')):
                                    project_folder = os.path.join(project_folder, 'out')
                                else:
                                    self.send_json({'error': 'npm build succeeded but no dist/, build/, or out/ folder was found.'}, 500)
                                    return
                                print(f"  📂 Using built output: {project_folder}")
                            except FileNotFoundError:
                                self.send_json({'error': 'npm not found. Please install Node.js from https://nodejs.org/ and try again.'}, 500)
                                return
                            except Exception as e:
                                self.send_json({'error': f'npm build error: {str(e)}'}, 500)
                                return

                        
                        # Create build directory
                        build_dir = os.path.join(metadata_dir, 'build')
                        os.makedirs(build_dir, exist_ok=True)
                        
                        print(f"\n🔧 Creating build script...")
                        
                        # Create a Python script that serves the HTML project via HTTP
                        build_script = f'''
import os
import sys
import threading
import webview
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Locate project directory — bundled inside EXE or original path
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
    PROJECT_DIR = os.path.join(BASE_DIR, "_project")
else:
    PROJECT_DIR = r"{project_folder}"

class SilentHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PROJECT_DIR, **kwargs)
    def log_message(self, format, *args):
        pass  # Suppress server logs

def find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

if __name__ == "__main__":
    port = find_free_port()
    server = HTTPServer(("127.0.0.1", port), SilentHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    window = webview.create_window(
        title="{project_name}",
        url=f"http://127.0.0.1:{{port}}/index.html",
        width=1024,
        height=768,
        resizable=True,
        background_color="#0f172a"
    )

    webview.start(debug=False)
    server.shutdown()
'''
                        
                        build_script_path = os.path.join(build_dir, 'main.py')
                        with open(build_script_path, 'w') as f:
                            f.write(build_script)
                        
                        print(f"✅ Build script created: {build_script_path}")
                        
                        # Build EXE using PyInstaller
                        output_dir = os.path.join(user_home, 'Downloads')
                        exe_name = project_name.replace(' ', '_')
                        
                        print(f"\n⚙️  Running PyInstaller...")
                        print(f"Output directory: {output_dir}")
                        print(f"EXE name: {exe_name}.exe")
                        
                        # Handle icon if provided (from base64 encoded file data)
                        final_icon_path = None
                        if data.get('iconData'):
                            try:
                                icon_data_uri = data.get('iconData', '')
                                # Parse data URI to get base64 content
                                if icon_data_uri.startswith('data:'):
                                    # Extract base64 content from data URI
                                    base64_content = icon_data_uri.split(',')[1]
                                    icon_binary = base64.b64decode(base64_content)
                                    
                                    # Determine file extension from data URI
                                    mime_type = icon_data_uri.split(';')[0].split(':')[1]
                                    if 'png' in mime_type:
                                        icon_ext = 'png'
                                    elif 'x-icon' in mime_type or 'vnd.microsoft.icon' in mime_type or 'ico' in mime_type:
                                        icon_ext = 'ico'
                                    else:
                                        icon_ext = 'ico'  # Default to ICO
                                    
                                    # Save temporary icon file with explicit binary mode
                                    temp_icon_path = os.path.join(build_dir, f'temp_icon.{icon_ext}')
                                    with open(temp_icon_path, 'wb') as f:
                                        bytes_written = f.write(icon_binary)
                                        f.flush()  # Force flush to disk
                                        os.fsync(f.fileno())  # Ensure sync to disk
                                    
                                    # Ensure file is written to disk
                                    import time
                                    time.sleep(0.2)  # Wait for disk write
                                    
                                    print(f"📥 Received icon file: {temp_icon_path} ({icon_ext.upper()})")
                                    print(f"   File size: {os.path.getsize(temp_icon_path)} bytes (wrote {bytes_written} bytes)")
                                    print(f"   MIME type detected: {mime_type}")
                                    
                                    # Convert PNG to ICO if necessary
                                    if icon_ext == 'png' and HAS_PILLOW:
                                        ico_path = os.path.join(build_dir, f'{exe_name}.ico')
                                        try:
                                            print(f"🎨 Converting PNG to ICO format...")
                                            img = Image.open(temp_icon_path)
                                            # Ensure image is at least 256x256 for better quality
                                            if img.size[0] < 256 or img.size[1] < 256:
                                                print(f"  Scaling icon to 256x256")
                                                img = img.resize((256, 256), Image.Resampling.LANCZOS)
                                            # Convert to RGB if needed (PNG may have alpha channel)
                                            if img.mode in ('RGBA', 'LA', 'P'):
                                                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                                                if img.mode == 'RGBA':
                                                    rgb_img.paste(img, mask=img.split()[-1])
                                                else:
                                                    rgb_img.paste(img)
                                                rgb_img.save(ico_path, 'ICO')
                                            else:
                                                img.save(ico_path, 'ICO')
                                            final_icon_path = ico_path
                                            print(f"✅ ICO created from PNG: {ico_path}")
                                            os.remove(temp_icon_path)  # Clean up temp PNG
                                        except Exception as e:
                                            print(f"Warning: Failed to convert PNG to ICO: {e}")
                                            final_icon_path = temp_icon_path  # Use PNG as fallback
                                    else:
                                        # Already ICO or Pillow not available
                                        final_icon_path = temp_icon_path
                                        print(f"✅ Using icon file: {final_icon_path}")
                            except Exception as e:
                                print(f"Warning: Failed to process icon data: {e}")
                        
                        # Create build subdirectories
                        os.makedirs(os.path.join(build_dir, 'build'), exist_ok=True)

                        # PyInstaller command (use absolute Windows paths)
                        cmd = [
                            'pyinstaller',
                            '--onefile',
                            '--windowed',
                            '--noupx',
                            '-y',  # Overwrite without asking
                            f'--name={exe_name}',
                            f'--distpath={output_dir}',
                            f'--workpath={os.path.join(build_dir, "build")}',
                            f'--specpath={build_dir}',
                            '--hidden-import=webview',
                            '--hidden-import=webview.js',
                            # Bundle the project HTML/CSS/JS files inside the EXE
                            f'--add-data={project_folder}{os.pathsep}_project',
                        ]
                        
                        # Add icon if available - use absolute path for Windows
                        if final_icon_path and os.path.exists(final_icon_path):
                            abs_icon_path = os.path.abspath(final_icon_path)
                            print(f"📌 Icon file ready for PyInstaller:")
                            print(f"   Path: {abs_icon_path}")
                            print(f"   Exists: {os.path.exists(abs_icon_path)}")
                            print(f"   Size: {os.path.getsize(abs_icon_path)} bytes")
                            
                            # PyInstaller handles Windows paths with backslashes correctly
                            cmd.append(f'--icon={abs_icon_path}')
                        
                        cmd.append(build_script_path)
                        
                        print(f"Full PyInstaller command:")
                        print(f"  {' '.join(cmd)}\n")
                        
                        # Run PyInstaller
                        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        
                        print(f"PyInstaller output:\n{result.stdout}")
                        
                        if result.stderr and result.stderr.strip():
                            print(f"PyInstaller warnings/errors:\n{result.stderr}")
                        
                        if result.returncode != 0:
                            print(f"\n❌ Build failed!")
                            print(f"Error: {result.stderr}")
                            self.send_json({
                                'error': f'Build failed: {result.stderr}'
                            }, 500)
                            return
                        
                        exe_path = os.path.join(output_dir, f'{exe_name}.exe')
                        
                        print(f"\n✅ PyInstaller completed successfully")
                        print(f"Checking for EXE at: {exe_path}")
                        
                        if os.path.exists(exe_path):
                            print(f"✨ EXE CREATED SUCCESSFULLY!")
                            print(f"Size: {os.path.getsize(exe_path) / (1024*1024):.2f} MB")
                            print(f"Location: {exe_path}")
                            print(f"{'='*60}\n")
                            
                            self.send_json({
                                'success': True,
                                'message': f'EXE created successfully!',
                                'exePath': exe_path,
                                'exeName': f'{exe_name}.exe'
                            })
                        else:
                            print(f"❌ EXE was not created at expected location!")
                            self.send_json({
                                'error': 'EXE was not created'
                            }, 500)
                    
                    except Exception as e:
                        print(f"\n❌ BUILD ERROR: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        self.send_json({'error': f'Build error: {str(e)}'}, 500)
                else:
                    self.send_json({'error': 'No build data provided'}, 400)
            
            elif endpoint == 'create-project' and method == 'POST':
                # Create/register a new project
                if body:
                    try:
                        data = json.loads(body)
                        project_name = data.get('name', '')
                        folder_path = data.get('folderPath', '')
                        author = data.get('author', '')
                        version = data.get('version', '1.0.0')
                        description = data.get('description', '')
                        
                        print(f"\n{'='*60}")
                        print(f"📦 CREATING PROJECT: {project_name}")
                        print(f"{'='*60}")
                        print(f"Source folder: {folder_path}")
                        print(f"Author: {author}")
                        print(f"Version: {version}")
                        
                        if not project_name:
                            self.send_json({'error': 'Project name is required'}, 400)
                            return
                        
                        # Get user's Downloads and Documents folders
                        user_home = os.path.expanduser('~')
                        downloads_dir = os.path.join(user_home, 'Downloads', project_name)
                        documents_dir = os.path.join(user_home, 'Documents', 'HTML2EXE')
                        metadata_dir = os.path.join(documents_dir, project_name)
                        
                        print(f"\n📁 Creating directories...")
                        print(f"  Downloads path: {downloads_dir}")
                        print(f"  Metadata path: {metadata_dir}")
                        
                        # Create necessary directories
                        os.makedirs(downloads_dir, exist_ok=True)
                        os.makedirs(metadata_dir, exist_ok=True)
                        
                        print(f"✅ Directories created")
                        
                        # Analyze project for framework and version info
                        analyzer = ProjectAnalyzer(folder_path)
                        analysis = analyzer.analyze()
                        
                        # Create project.json metadata in Documents
                        project_meta = {
                            'name': project_name,
                            'author': author,
                            'version': version,
                            'description': description,
                            'sourceFolder': folder_path,
                            'downloadFolder': downloads_dir,
                            'created': datetime.now().isoformat(),
                            'analysis': analysis
                        }
                        
                        # Write project metadata
                        metadata_file = os.path.join(metadata_dir, 'project.json')
                        print(f"\n💾 Saving metadata to: {metadata_file}")
                        with open(metadata_file, 'w') as f:
                            json.dump(project_meta, f, indent=2)
                        
                        print(f"✅ Metadata saved")
                        
                        # Copy all files to Downloads folder
                        if folder_path and os.path.isdir(folder_path):
                            print(f"\n📋 Copying files from source...")
                            file_count = 0
                            for item in os.listdir(folder_path):
                                src = os.path.join(folder_path, item)
                                dst = os.path.join(downloads_dir, item)
                                
                                # Skip if destination already exists
                                if os.path.exists(dst):
                                    if os.path.isdir(dst):
                                        shutil.rmtree(dst)
                                    else:
                                        os.remove(dst)
                                
                                if os.path.isdir(src):
                                    if item not in ['node_modules', '.git', 'dist', 'build', '.vscode', '__pycache__']:
                                        print(f"  📂 Copying folder: {item}")
                                        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('node_modules', '.git', 'dist', 'build', '.vscode', '__pycache__'))
                                        file_count += 1
                                else:
                                    print(f"  📄 Copying file: {item}")
                                    shutil.copy2(src, dst)
                                    file_count += 1
                            
                            print(f"✅ Copied {file_count} items")
                        
                        print(f"\n{'='*60}")
                        print(f"✨ PROJECT CREATED SUCCESSFULLY!")
                        print(f"{'='*60}\n")
                        
                        self.send_json({
                            'success': True, 
                            'message': f'Project "{project_name}" created successfully!', 
                            'downloadFolder': downloads_dir,
                            'metadataFolder': metadata_dir
                        })
                    except Exception as e:
                        print(f"\n❌ ERROR: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        self.send_json({'error': f'Failed to create project: {str(e)}'}, 500)
                else:
                    self.send_json({'error': 'No project data provided'}, 400)
            
            elif endpoint == 'minimize-window' and method == 'POST':
                """Minimize the window"""
                try:
                    if hasattr(BuilderHTTPHandler, 'window_instance') and BuilderHTTPHandler.window_instance:
                        BuilderHTTPHandler.window_instance.minimize()
                        self.send_json({'success': True, 'message': 'Window minimized'})
                    else:
                        self.send_json({'success': False, 'message': 'Window instance not available'})
                except Exception as e:
                    self.send_json({'error': f'Failed to minimize window: {str(e)}'}, 500)
            
            elif endpoint == 'maximize-window' and method == 'POST':
                """Maximize/toggle fullscreen the window"""
                try:
                    if hasattr(BuilderHTTPHandler, 'window_instance') and BuilderHTTPHandler.window_instance:
                        window = BuilderHTTPHandler.window_instance
                        # Toggle between normal and maximized state
                        if hasattr(window, 'toggle_fullscreen'):
                            window.toggle_fullscreen()
                        else:
                            # Fallback: use set_fullscreen
                            current_state = getattr(window, 'fullscreen', False)
                            window.set_fullscreen(not current_state)
                        self.send_json({'success': True, 'message': 'Window toggled'})
                    else:
                        self.send_json({'success': False, 'message': 'Window instance not available'})
                except Exception as e:
                    self.send_json({'error': f'Failed to maximize window: {str(e)}'}, 500)
            
            elif endpoint == 'close-window' and method == 'POST':
                """Close the application"""
                try:
                    if hasattr(BuilderHTTPHandler, 'window_instance') and BuilderHTTPHandler.window_instance:
                        BuilderHTTPHandler.window_instance.destroy()
                    self.send_json({'success': True, 'message': 'Window closed'})
                except Exception as e:
                    self.send_json({'error': f'Window close error: {str(e)}'}, 500)
            
            elif endpoint == 'convert-python-to-exe' and method == 'POST':
                """Convert Python script/project to EXE"""
                if body:
                    try:
                        data = json.loads(body)
                        python_path = data.get('pythonPath', '')
                        exe_name = data.get('exeName', 'MyApp')
                        hide_console = data.get('hideConsole', True)
                        single_file = data.get('singleFile', True)
                        optimize = data.get('optimize', False)
                        icon_data = data.get('iconData', '')
                        
                        print(f"\n{'='*60}")
                        print(f"🔨 PYTHON TO EXE CONVERSION")
                        print(f"{'='*60}")
                        print(f"Python Project: {python_path}")
                        print(f"EXE Name: {exe_name}")
                        print(f"Hide Console: {hide_console}")
                        print(f"Single File: {single_file}")
                        
                        # Validate Python project path
                        if not os.path.exists(python_path):
                            self.send_json({'error': f'Python project path not found: {python_path}'}, 404)
                            return
                        
                        python_path = os.path.abspath(python_path)
                        
                        # Find entry point (main.py, app.py, or first .py file)
                        entry_point = None
                        py_files = []
                        
                        for file in os.listdir(python_path):
                            if file.endswith('.py'):
                                py_files.append(file)
                                if file in ['main.py', 'app.py', 'run.py']:
                                    entry_point = file
                        
                        # If no standard entry point found, use first Python file
                        if not entry_point and py_files:
                            entry_point = py_files[0]
                        
                        if not entry_point:
                            self.send_json({
                                'error': 'No Python (.py) files found in the project folder. Please ensure your project has a main.py, app.py, or other Python file.'
                            }, 400)
                            return
                        
                        entry_point_path = os.path.join(python_path, entry_point)
                        print(f"✓ Entry point: {entry_point}")
                        
                        # Check for requirements.txt
                        requirements_path = os.path.join(python_path, 'requirements.txt')
                        has_requirements = os.path.exists(requirements_path)
                        if has_requirements:
                            print(f"✓ Dependencies file found: requirements.txt")
                        
                        # Analyze project for data files and dependencies
                        print(f"\n📊 Analyzing project structure...")
                        datas_list = []
                        binaries_list = []
                        hidden_imports = []
                        
                        # Scan Python files for imports to auto-detect hidden imports
                        import_keywords = {
                            'webview': 'webview',
                            'flask': 'flask',
                            'django': 'django',
                            'requests': 'requests',
                            'numpy': 'numpy',
                            'pandas': 'pandas',
                            'PIL': 'PIL',
                            'cv2': 'cv2',
                            'tkinter': 'tkinter',
                            'PyQt5': 'PyQt5',
                            'PyQt6': 'PyQt6',
                            'PySide6': 'PySide6',
                            'pygame': 'pygame',
                            'sqlalchemy': 'sqlalchemy',
                            'sqlite3': 'sqlite3',
                            'cryptography': 'cryptography',
                            'matplotlib': 'matplotlib',
                            'scipy': 'scipy',
                            'sklearn': 'sklearn',
                        }
                        
                        for py_file in py_files:
                            try:
                                with open(os.path.join(python_path, py_file), 'r', encoding='utf-8', errors='ignore') as f:
                                    content = f.read()
                                for keyword, module in import_keywords.items():
                                    if keyword in content and module not in hidden_imports:
                                        hidden_imports.append(module)
                                        print(f"  🔍 Detected import: {module}")
                            except Exception:
                                pass
                        
                        # Find all data files (json, yaml, txt, config, etc.)
                        data_extensions = {'.json', '.yaml', '.yml', '.txt', '.config', '.conf', '.cfg', '.ini', '.xml', '.csv', '.db'}
                        non_python_files = {}
                        
                        for root, dirs, files in os.walk(python_path):
                            # Skip virtual envs and build folders
                            dirs[:] = [d for d in dirs if d not in {'venv', '.venv', 'env', '__pycache__', '.git', 'build', 'dist', 'node_modules'}]
                            
                            for file in files:
                                file_path = os.path.join(root, file)
                                rel_path = os.path.relpath(file_path, python_path)
                                
                                # Check if it's a data file
                                _, ext = os.path.splitext(file)
                                if ext.lower() in data_extensions or (not file.endswith('.py') and not file.endswith('.pyc')):
                                    folder = os.path.dirname(rel_path)
                                    if folder and folder not in {'__pycache__'}:
                                        if folder not in non_python_files:
                                            non_python_files[folder] = []
                                        non_python_files[folder].append(file)
                        
                        # Create datas entries for PyInstaller
                        for folder, files in non_python_files.items():
                            folder_path_full = os.path.join(python_path, folder)
                            # Format: (source_folder, destination_folder(relative to exe))
                            datas_list.append((folder_path_full, folder))
                            print(f"  📦 Data folder: {folder}")
                        
                        # Create build directory
                        user_home = os.path.expanduser('~')
                        build_base_dir = os.path.join(user_home, 'Documents', 'HTMLToExe_PythonBuilds')
                        build_dir = os.path.join(build_base_dir, exe_name)
                        output_dir = os.path.join(user_home, 'Downloads')
                        
                        os.makedirs(build_dir, exist_ok=True)
                        os.makedirs(os.path.join(build_dir, 'build'), exist_ok=True)
                        
                        print(f"\n📁 Build directory: {build_dir}")
                        
                        # Handle icon if provided
                        final_icon_path = None
                        if data.get('iconData'):
                            try:
                                icon_data_uri = data.get('iconData', '')
                                if icon_data_uri.startswith('data:'):
                                    base64_content = icon_data_uri.split(',')[1]
                                    icon_binary = base64.b64decode(base64_content)
                                    
                                    mime_type = icon_data_uri.split(';')[0].split(':')[1]
                                    if 'png' in mime_type:
                                        icon_ext = 'png'
                                    else:
                                        icon_ext = 'ico'
                                    
                                    temp_icon_path = os.path.join(build_dir, f'temp_icon.{icon_ext}')
                                    with open(temp_icon_path, 'wb') as f:
                                        f.write(icon_binary)
                                        f.flush()
                                        os.fsync(f.fileno())
                                    
                                    print(f"📥 Icon file received: {icon_ext.upper()}")
                                    
                                    # Convert PNG to ICO if necessary
                                    if icon_ext == 'png' and HAS_PILLOW:
                                        ico_path = os.path.join(build_dir, f'{exe_name}.ico')
                                        try:
                                            print(f"🎨 Converting PNG to ICO format...")
                                            img = Image.open(temp_icon_path)
                                            if img.size[0] < 256 or img.size[1] < 256:
                                                img = img.resize((256, 256), Image.Resampling.LANCZOS)
                                            if img.mode in ('RGBA', 'LA', 'P'):
                                                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                                                if img.mode == 'RGBA':
                                                    rgb_img.paste(img, mask=img.split()[-1])
                                                else:
                                                    rgb_img.paste(img)
                                                rgb_img.save(ico_path, 'ICO')
                                            else:
                                                img.save(ico_path, 'ICO')
                                            final_icon_path = ico_path
                                            print(f"✅ ICO created: {ico_path}")
                                            os.remove(temp_icon_path)
                                        except Exception as e:
                                            print(f"⚠️  Icon conversion failed: {e}")
                                            final_icon_path = temp_icon_path
                                    else:
                                        final_icon_path = temp_icon_path
                            except Exception as e:
                                print(f"⚠️  Icon processing failed: {e}")
                        
                        # Generate PyInstaller spec file
                        print(f"\n📝 Generating PyInstaller spec file...")
                        spec_path = os.path.join(build_dir, f'{exe_name}.spec')
                        
                        # Create datas string for spec file
                        datas_string = "[]"
                        if datas_list:
                            # Use forward slashes to avoid escape character issues
                            datas_entries = [f"(r'{src}', '{dest.replace(chr(92), '/')}')" for src, dest in datas_list]
                            datas_string = "[" + ", ".join(datas_entries) + "]"
                        
                        # Create hidden imports string
                        hidden_imports_string = str(hidden_imports)
                        
                        icon_statement = ""
                        if final_icon_path and os.path.exists(final_icon_path):
                            icon_path_escaped = final_icon_path.replace('\\', '\\\\')
                            icon_statement = f",\n    icon=r'{icon_path_escaped}'"
                        
                        console_value = 'False' if hide_console else 'True'
                        spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    [r'{entry_point_path}'],
    pathex=[r'{python_path}'],
    binaries=[],
    datas={datas_string},
    hiddenimports={hidden_imports_string},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=r'{exe_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console={console_value}{icon_statement}
)
"""
                        
                        with open(spec_path, 'w') as f:
                            f.write(spec_content)
                        
                        print(f"✅ Spec file created: {spec_path}")
                        
                        # Create PyInstaller command using spec file
                        cmd = [
                            'pyinstaller',
                            f'--distpath={output_dir}',
                            f'--workpath={os.path.join(build_dir, "build")}',
                            '--noconfirm',
                            '-y',
                            spec_path
                        ]
                        
                        print(f"\n⚙️  Running PyInstaller with spec file...")
                        print(f"Spec file: {spec_path}\n")
                        
                        # Run PyInstaller
                        result = subprocess.run(cmd, capture_output=True, text=True, cwd=build_dir, creationflags=subprocess.CREATE_NO_WINDOW)
                        
                        print(f"PyInstaller output:\n{result.stdout}")
                        
                        if result.stderr and result.stderr.strip():
                            print(f"PyInstaller warnings:\n{result.stderr}")
                        
                        if result.returncode != 0:
                            print(f"\n❌ Build failed!")
                            # Extract the actual error from the output (last few lines)
                            error_output = result.stderr.strip() if result.stderr else result.stdout.strip()
                            error_lines = error_output.split('\n')
                            # Get only the last 10 lines which contain the actual error
                            actual_error = '\n'.join(error_lines[-10:]) if len(error_lines) > 10 else error_output
                            self.send_json({
                                'error': f'PyInstaller build failed: {actual_error}'
                            }, 500)
                            return
                        
                        exe_path = os.path.join(output_dir, f'{exe_name}.exe')
                        
                        if os.path.exists(exe_path):
                            exe_size = os.path.getsize(exe_path) / (1024*1024)
                            print(f"\n✨ BUILD SUCCESSFUL!")
                            print(f"EXE File: {exe_path}")
                            print(f"Size: {exe_size:.2f} MB")
                            print(f"{'='*60}\n")
                            
                            self.send_json({
                                'success': True,
                                'message': f'Python to EXE conversion successful! EXE is in Downloads/',
                                'exePath': exe_path,
                                'exeName': f'{exe_name}.exe',
                                'size': f'{exe_size:.2f} MB'
                            })
                        else:
                            print(f"❌ EXE was not created at expected location!")
                            print(f"Checked: {exe_path}")
                            self.send_json({
                                'error': 'EXE was not created. Check the build output above for errors.'
                            }, 500)
                    
                    except Exception as e:
                        print(f"\n❌ BUILD ERROR: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        self.send_json({'error': f'Build error: {str(e)}'}, 500)
                else:
                    self.send_json({'error': 'No project data provided'}, 400)
            
            elif endpoint == 'open-folder' and method == 'POST':
                try:
                    data = json.loads(body) if body else {}
                    folder_path = data.get('folderPath', '')
                    relative = data.get('relative', False)
                    if relative:
                        user_home = os.path.expanduser('~')
                        folder_path = os.path.join(user_home, folder_path.replace('/', os.sep))
                    if folder_path and os.path.exists(folder_path):
                        subprocess.Popen(['explorer', os.path.abspath(folder_path)])
                        self.send_json({'success': True})
                    elif folder_path:
                        parent = os.path.dirname(folder_path)
                        if os.path.exists(parent):
                            subprocess.Popen(['explorer', os.path.abspath(parent)])
                            self.send_json({'success': True})
                        else:
                            self.send_json({'success': False, 'error': 'Folder not found'})
                    else:
                        self.send_json({'success': False, 'error': 'No folder path provided'})
                except Exception as e:
                    self.send_json({'error': str(e)}, 500)

            elif endpoint == 'delete-project' and method == 'POST':
                try:
                    data = json.loads(body) if body else {}
                    project_id = data.get('projectId', '')
                    if not project_id:
                        self.send_json({'error': 'No project ID provided'}, 400)
                        return
                    user_home = os.path.expanduser('~')
                    metadata_dir = os.path.join(user_home, 'Documents', 'HTML2EXE', project_id)
                    if os.path.exists(metadata_dir):
                        shutil.rmtree(metadata_dir)
                        print(f"✅ Deleted project: {project_id}")
                        self.send_json({'success': True, 'message': f'Project {project_id} deleted'})
                    else:
                        self.send_json({'success': True, 'message': 'Project not found on disk (already removed)'})
                except Exception as e:
                    self.send_json({'error': str(e)}, 500)

            elif endpoint == 'check-android-prereqs' and method == 'GET':
                result = AndroidBuilder.check_prerequisites()
                self.send_json(result)

            elif endpoint == 'build-android' and method == 'POST':
                if body:
                    try:
                        data = json.loads(body)
                        builder = AndroidBuilder()
                        result = builder.build(data)
                        self.send_json(result)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        self.send_json({'success': False, 'error': str(e)}, 500)
                else:
                    self.send_json({'error': 'No build data provided'}, 400)

            else:
                self.send_json({'error': 'Endpoint not found'}, 404)
        
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
    def serve_file(self, file_path):
        """Serve a static file"""
        full_path = os.path.join(self.builder_root, file_path)
        
        if not os.path.exists(full_path):
            self.send_error(404, "File Not Found")
            return
        
        try:
            with open(full_path, 'rb') as f:
                content = f.read()
            
            # Set content type
            content_type = self.guess_type(file_path)
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, str(e))
    
    def send_json(self, data, status=200):
        """Send JSON response"""
        response = json.dumps(data).encode('utf-8')
        try:
            self.send_response(status)
            self.send_header('Content-type', 'application/json')
            self.send_header('Content-Length', len(response))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass  # Client closed connection (e.g. window destroyed) — harmless
    
    def guess_type(self, path):
        """Guess MIME type"""
        if path.endswith('.css'):
            return 'text/css'
        elif path.endswith('.js'):
            return 'application/javascript'
        elif path.endswith('.json'):
            return 'application/json'
        elif path.endswith('.html'):
            return 'text/html'
        else:
            return 'application/octet-stream'
    
    def log_message(self, format, *args):
        """Suppress server logging"""
        pass


class ProjectAnalyzer:
    """Analyze project to detect framework, version, and technology stack"""
    
    def __init__(self, folder_path):
        self.folder_path = os.path.abspath(folder_path)
        self.frameworks = []
        self.versions = {}
        self.dependencies = {}
        self.project_type = 'Unknown'
    
    def analyze(self):
        """Run comprehensive analysis on project"""
        analysis = {
            'frameworks': [],
            'versions': {},
            'dependencies': {},
            'projectType': 'Vanilla JavaScript',
            'technologies': []
        }
        
        # Check package.json first
        self._analyze_package_json(analysis)
        
        # Check HTML files for framework indicators
        self._analyze_html_files(analysis)
        
        # Check JS files for imports and framework usage
        self._analyze_js_files(analysis)
        
        # Analyze CSS files
        self._analyze_css_files(analysis)
        
        # Determine project type
        self._determine_project_type(analysis)
        
        return analysis
    
    def _analyze_package_json(self, analysis):
        """Analyze package.json for dependencies"""
        package_path = os.path.join(self.folder_path, 'package.json')
        
        if os.path.exists(package_path):
            try:
                with open(package_path, 'r', encoding='utf-8') as f:
                    package_data = json.load(f)
                
                dependencies = package_data.get('dependencies', {})
                dev_dependencies = package_data.get('devDependencies', {})
                
                all_deps = {**dependencies, **dev_dependencies}
                analysis['dependencies'] = all_deps
                
                # Detect frameworks from dependencies
                if 'react' in all_deps:
                    analysis['frameworks'].append('React')
                    analysis['versions']['React'] = all_deps.get('react', 'unknown')
                    analysis['technologies'].append('React')
                
                if 'vue' in all_deps:
                    analysis['frameworks'].append('Vue.js')
                    analysis['versions']['Vue.js'] = all_deps.get('vue', 'unknown')
                    analysis['technologies'].append('Vue.js')
                
                if '@angular/core' in all_deps:
                    analysis['frameworks'].append('Angular')
                    analysis['versions']['Angular'] = all_deps.get('@angular/core', 'unknown')
                    analysis['technologies'].append('Angular')
                
                if 'svelte' in all_deps:
                    analysis['frameworks'].append('Svelte')
                    analysis['versions']['Svelte'] = all_deps.get('svelte', 'unknown')
                    analysis['technologies'].append('Svelte')
                
                if 'next' in all_deps:
                    analysis['frameworks'].append('Next.js')
                    analysis['versions']['Next.js'] = all_deps.get('next', 'unknown')
                    analysis['technologies'].append('Next.js')
                
                if 'nuxt' in all_deps:
                    analysis['frameworks'].append('Nuxt.js')
                    analysis['versions']['Nuxt.js'] = all_deps.get('nuxt', 'unknown')
                    analysis['technologies'].append('Nuxt.js')
                
                if 'jquery' in all_deps:
                    analysis['frameworks'].append('jQuery')
                    analysis['versions']['jQuery'] = all_deps.get('jquery', 'unknown')
                    analysis['technologies'].append('jQuery')
                
                if 'bootstrap' in all_deps:
                    analysis['technologies'].append('Bootstrap')
                
                if 'tailwindcss' in all_deps or 'tailwind' in all_deps:
                    analysis['technologies'].append('Tailwind CSS')
                
                if 'typescript' in dev_dependencies:
                    analysis['technologies'].append('TypeScript')
                    analysis['versions']['TypeScript'] = dev_dependencies.get('typescript', 'unknown')
                
                if 'webpack' in dev_dependencies:
                    analysis['technologies'].append('Webpack')
                
                if 'babel' in all_deps or '@babel/core' in dev_dependencies:
                    analysis['technologies'].append('Babel')
            
            except json.JSONDecodeError:
                pass
    
    def _analyze_html_files(self, analysis):
        """Analyze HTML files for framework indicators"""
        for root, dirs, files in os.walk(self.folder_path):
            dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', 'dist', 'build']]
            
            for file in files:
                if file.endswith('.html'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        # Check for framework CDN/imports (look for specific CDN URLs or import statements)
                        if 'unpkg.com/react' in content or 'cdnjs.cloudflare.com/ajax/libs/react' in content:
                            if 'React' not in analysis['frameworks']:
                                analysis['frameworks'].append('React')
                        
                        if 'unpkg.com/vue' in content or 'cdnjs.cloudflare.com/ajax/libs/vue' in content:
                            if 'Vue.js' not in analysis['frameworks']:
                                analysis['frameworks'].append('Vue.js')
                        
                        if 'unpkg.com/@angular' in content or 'cdnjs.cloudflare.com/ajax/libs/angular' in content:
                            if 'Angular' not in analysis['frameworks']:
                                analysis['frameworks'].append('Angular')
                        
                        if 'code.jquery.com' in content or 'cdnjs.cloudflare.com/ajax/libs/jquery' in content:
                            if 'jQuery' not in analysis['frameworks']:
                                analysis['frameworks'].append('jQuery')
                        
                        if 'unpkg.com/svelte' in content or '@sveltejs' in content:
                            if 'Svelte' not in analysis['frameworks']:
                                analysis['frameworks'].append('Svelte')
                        
                        if 'bootstrap.min.css' in content or 'bootstrap.css' in content:
                            if 'Bootstrap' not in analysis['technologies']:
                                analysis['technologies'].append('Bootstrap')
                        
                        if 'tailwindcss' in content:
                            if 'Tailwind CSS' not in analysis['technologies']:
                                analysis['technologies'].append('Tailwind CSS')
                    
                    except Exception:
                        pass
    
    def _analyze_js_files(self, analysis):
        """Analyze JS files for imports and framework usage"""
        js_patterns = {
            'React': ['import react', 'from "react"', 'from \'react\'', 'require("react")', 'JSX', 'ReactDOM'],
            'Vue.js': ['import vue', 'from "vue"', 'from \'vue\'', 'Vue.component', 'new Vue({'],
            'Angular': ['@angular/', 'from \'@angular', 'import.*from \'@angular', 'NgModule'],
            'jQuery': ['jQuery(', 'require("jquery")', 'import.*jquery'],
            'Svelte': ['svelte/', '@sveltejs', 'import.*svelte'],
            'TypeScript': ['.ts', '.tsx'],
        }
        
        for root, dirs, files in os.walk(self.folder_path):
            dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', 'dist', 'build']]
            
            for file in files:
                if file.endswith(('.js', '.jsx', '.ts', '.tsx')):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        # Check for framework imports (case-sensitive for accuracy)
                        for framework, patterns in js_patterns.items():
                            for pattern in patterns:
                                if pattern in content:  # Case-sensitive matching
                                    if framework not in analysis['frameworks'] and framework not in analysis['technologies']:
                                        if framework in ['React', 'Vue.js', 'Angular', 'jQuery', 'Svelte']:
                                            if framework not in analysis['frameworks']:
                                                analysis['frameworks'].append(framework)
                                        else:
                                            if framework not in analysis['technologies']:
                                                analysis['technologies'].append(framework)
                    
                    except Exception:
                        pass
    
    def _analyze_css_files(self, analysis):
        """Analyze CSS files for preprocessors and frameworks"""
        for root, dirs, files in os.walk(self.folder_path):
            dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', 'dist', 'build']]
            
            for file in files:
                if file.endswith(('.scss', '.sass', '.less')):
                    ext = file.split('.')[-1]
                    tech_name = 'SASS' if ext in ['scss', 'sass'] else 'Less'
                    if tech_name not in analysis['technologies']:
                        analysis['technologies'].append(tech_name)
    
    def _determine_project_type(self, analysis):
        """Determine overall project type"""
        frameworks = analysis['frameworks']
        
        if not frameworks:
            analysis['projectType'] = 'Vanilla JavaScript'
        elif 'React' in frameworks:
            if 'Next.js' in frameworks:
                analysis['projectType'] = 'Next.js (React SSR)'
            else:
                analysis['projectType'] = 'React SPA'
        elif 'Vue.js' in frameworks:
            if 'Nuxt.js' in frameworks:
                analysis['projectType'] = 'Nuxt.js (Vue SSR)'
            else:
                analysis['projectType'] = 'Vue SPA'
        elif 'Angular' in frameworks:
            analysis['projectType'] = 'Angular SPA'
        elif 'Svelte' in frameworks:
            analysis['projectType'] = 'Svelte App'
        elif 'jQuery' in frameworks:
            analysis['projectType'] = 'jQuery Application'


class AndroidBuilder:
    """Build web projects into Android APKs using Capacitor CLI"""

    @staticmethod
    def check_prerequisites():
        """Check Java JDK, Android SDK and Node.js availability"""
        import re
        import glob

        result = {
            'java':  {'ok': False, 'version': None, 'message': 'Not found'},
            'sdk':   {'ok': False, 'path': None,    'message': 'Not found'},
            'node':  {'ok': False, 'version': None, 'message': 'Not found'},
            'allOk': False,
        }

        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

        def run_cmd(cmd, **kwargs):
            """Run a command with shell=True for proper PATH resolution on Windows."""
            return subprocess.run(
                cmd, capture_output=True, text=True,
                shell=True, creationflags=flags, **kwargs
            )

        def parse_java_output(raw):
            m = re.search(r'version "(\d+)', raw)
            if m:
                major = int(m.group(1))
                vs = re.search(r'version "([^"]+)"', raw)
                return major, vs.group(1) if vs else raw.split('\n')[0]
            return None, None

        # --- Java ---
        # 1. Try java in PATH (shell=True ensures system PATH is inherited)
        r = run_cmd('java -version')
        raw = (r.stderr + r.stdout).strip()
        major, ver_str = parse_java_output(raw)

        # 2. Fallback: search common Windows install locations
        if major is None:
            candidates = []
            prog_files = [
                os.environ.get('ProgramFiles', r'C:\Program Files'),
                os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
            ]
            for pf in prog_files:
                candidates += glob.glob(os.path.join(pf, 'Eclipse Adoptium', 'jdk-*', 'bin', 'java.exe'))
                candidates += glob.glob(os.path.join(pf, 'Java', 'jdk-*', 'bin', 'java.exe'))
                candidates += glob.glob(os.path.join(pf, 'Microsoft', 'jdk-*', 'bin', 'java.exe'))
                candidates += glob.glob(os.path.join(pf, 'Android', 'Android Studio', 'jbr', 'bin', 'java.exe'))
            # Android Studio bundled JDK (user-local install)
            local_as = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Android Studio', 'jbr', 'bin', 'java.exe')
            if os.path.exists(local_as):
                candidates.insert(0, local_as)

            for java_exe in candidates:
                if os.path.exists(java_exe):
                    r2 = run_cmd(f'"{java_exe}" -version')
                    raw2 = (r2.stderr + r2.stdout).strip()
                    major, ver_str = parse_java_output(raw2)
                    if major:
                        break

        if major is not None:
            result['java']['version'] = ver_str
            if major >= 17:
                result['java']['ok'] = True
                result['java']['message'] = f'JDK {ver_str}'
            else:
                result['java']['message'] = f'JDK {ver_str} found — version 17+ required'
        else:
            result['java']['message'] = 'Java not found — install JDK 17+ from adoptium.net'

        # --- Android SDK ---
        # 1. Env vars
        sdk_path = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT', '')
        # 2. Default Android Studio SDK location (set even if ANDROID_HOME is missing)
        if not sdk_path or not os.path.isdir(sdk_path):
            default_sdk = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Sdk')
            if os.path.isdir(default_sdk):
                sdk_path = default_sdk
        # 3. adb in PATH
        if not sdk_path or not os.path.isdir(sdk_path):
            r = run_cmd('adb version')
            if r.returncode == 0:
                sdk_path = 'PATH'

        if sdk_path and (sdk_path == 'PATH' or os.path.isdir(sdk_path)):
            result['sdk']['ok'] = True
            result['sdk']['path'] = sdk_path
            result['sdk']['message'] = sdk_path if sdk_path != 'PATH' else 'Found via adb in PATH'
        else:
            result['sdk']['message'] = 'Android SDK not found — install Android Studio'

        # --- Node.js ---
        r = run_cmd('node --version')
        v = r.stdout.strip() or r.stderr.strip()
        if v.startswith('v'):
            result['node']['ok'] = True
            result['node']['version'] = v
            result['node']['message'] = v
        else:
            result['node']['message'] = 'Node.js not found — install from nodejs.org'

        result['allOk'] = result['java']['ok'] and result['sdk']['ok'] and result['node']['ok']
        return result

    def build(self, data):
        """Build a web project to Android APK using Capacitor"""
        import glob as _glob

        project_id   = data.get('projectId', '')
        folder_path  = data.get('folderPath', '')
        app_name     = data.get('appName', 'MyApp').strip()
        package_name = data.get('packageName', 'com.example.myapp').strip()
        log_lines    = []

        def log(msg):
            print(msg)
            log_lines.append(msg)

        # ── 0. Build a subprocess env with JAVA_HOME injected ─────────────
        def make_env():
            """Return os.environ copy with JAVA_HOME set to a Gradle-compatible JDK.
            Prefers Android Studio's bundled JBR (Java 17/21) over newer standalone
            JDKs (e.g. Java 25) which are not yet supported by Gradle."""
            env = os.environ.copy()

            pf_list = [
                env.get('ProgramFiles', r'C:\Program Files'),
                env.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
            ]
            local_app = env.get('LOCALAPPDATA', '')

            # Ordered by preference: Android Studio JBR first (Java 17/21, most
            # compatible), then versioned JDKs sorted newest-first as fallback.
            priority = []
            # 1. Android Studio JBR — preferred (bundled, always compatible)
            for pf in pf_list:
                jbr = os.path.join(pf, 'Android', 'Android Studio', 'jbr', 'bin', 'java.exe')
                if os.path.exists(jbr):
                    priority.append(jbr)
            local_jbr = os.path.join(local_app, 'Android', 'Android Studio', 'jbr', 'bin', 'java.exe')
            if os.path.exists(local_jbr):
                priority.insert(0, local_jbr)

            # 2. Versioned JDKs — sorted so lower (more compatible) versions come first
            versioned = []
            for pf in pf_list:
                versioned += _glob.glob(os.path.join(pf, 'Eclipse Adoptium', 'jdk-*', 'bin', 'java.exe'))
                versioned += _glob.glob(os.path.join(pf, 'Java', 'jdk-*', 'bin', 'java.exe'))
                versioned += _glob.glob(os.path.join(pf, 'Microsoft', 'jdk-*', 'bin', 'java.exe'))
            # Sort by path so jdk-17 < jdk-21 < jdk-25; pick lowest available
            versioned.sort()
            candidates = priority + versioned

            def _set_java(java_exe, source):
                java_home = os.path.dirname(os.path.dirname(java_exe))
                env['JAVA_HOME'] = java_home
                env['PATH'] = os.path.dirname(java_exe) + os.pathsep + env.get('PATH', '')
                log(f'JAVA_HOME ({source}): {java_home}')
                return env

            # If JAVA_HOME is already set, only keep it if it's ≤ Java 24
            existing_jh = env.get('JAVA_HOME', '')
            if existing_jh and os.path.isdir(existing_jh):
                java_exe = os.path.join(existing_jh, 'bin', 'java.exe')
                r = subprocess.run([java_exe, '-version'], capture_output=True, text=True)
                version_str = r.stderr or r.stdout  # java -version prints to stderr
                import re
                m = re.search(r'version "(\d+)', version_str)
                major = int(m.group(1)) if m else 99
                if major <= 24:
                    log(f'JAVA_HOME already set (Java {major}): {existing_jh}')
                    return env
                else:
                    log(f'Ignoring JAVA_HOME (Java {major} too new for Gradle): {existing_jh}')

            for java_exe in candidates:
                if os.path.exists(java_exe):
                    return _set_java(java_exe, 'auto-detected')

            # Last resort: `where java`
            r = subprocess.run('where java', capture_output=True, text=True, shell=True)
            if r.returncode == 0:
                java_exe = r.stdout.strip().splitlines()[0].strip()
                if os.path.exists(java_exe):
                    return _set_java(java_exe, 'PATH')

            return env

        try:
            # ── 1. Resolve web source folder ──────────────────────────────
            web_src = folder_path
            if project_id and not folder_path:
                user_home = os.path.expanduser('~')
                meta_path = os.path.join(user_home, 'Documents', 'HTML2EXE', project_id, 'project.json')
                if not os.path.exists(meta_path):
                    return {'success': False, 'error': 'Project metadata not found', 'log': log_lines}
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                web_src = meta.get('downloadFolder', '')

            if not web_src or not os.path.isdir(web_src):
                return {'success': False, 'error': f'Web source folder not found: {web_src}', 'log': log_lines}

            log(f'Web source: {web_src}')

            # ── 2. Auto-build / locate static output for any framework ────
            # Helper: find the built static output folder
            def find_built_output(base):
                """Return path to the static build output dir, or None."""
                has_pkg_here = os.path.exists(os.path.join(base, 'package.json'))
                is_gatsby = (os.path.exists(os.path.join(base, 'gatsby-config.js')) or
                             os.path.exists(os.path.join(base, 'gatsby-config.ts')))

                # --- Well-known output directories (require index.html) ---
                for c in ('out', 'dist', 'build'):
                    p = os.path.join(base, c)
                    if not os.path.isdir(p):
                        continue
                    if os.path.exists(os.path.join(p, 'index.html')):
                        return p
                    # Next.js static export: has _next/ but root index may be missing
                    # (app-router without a root page)
                    if os.path.isdir(os.path.join(p, '_next')):
                        return p
                    # Any HTML files directly in the output folder
                    try:
                        if any(e.endswith('.html')
                               for e in os.listdir(p)
                               if os.path.isfile(os.path.join(p, e))):
                            return p
                    except OSError:
                        pass

                # Nuxt 3
                nuxt_p = os.path.join(base, '.output', 'public')
                if os.path.isdir(nuxt_p) and os.path.exists(os.path.join(nuxt_p, 'index.html')):
                    return nuxt_p

                # Gatsby only: public/ is the output dir
                if is_gatsby:
                    p = os.path.join(base, 'public')
                    if os.path.isdir(p) and os.path.exists(os.path.join(p, 'index.html')):
                        return p

                # Plain HTML project (no package.json) — base dir itself
                if not has_pkg_here and os.path.exists(os.path.join(base, 'index.html')):
                    return base

                # Angular v17+: dist/<name>/browser/   v15/16: dist/<name>/
                dist_p = os.path.join(base, 'dist')
                if os.path.isdir(dist_p):
                    try:
                        for sub in sorted(os.listdir(dist_p)):
                            sub_p = os.path.join(dist_p, sub)
                            if not os.path.isdir(sub_p):
                                continue
                            for ang in (os.path.join(sub_p, 'browser'), sub_p):
                                if os.path.exists(os.path.join(ang, 'index.html')):
                                    return ang
                    except OSError:
                        pass

                # SvelteKit adapter-static
                sk_p = os.path.join(base, '.svelte-kit', 'output', 'client')
                if os.path.isdir(sk_p) and os.path.exists(os.path.join(sk_p, 'index.html')):
                    return sk_p

                # Fallback: walk (skip heavy/source dirs) looking for index.html
                skip = {'node_modules', '.git', '.next', '.svelte-kit', 'src',
                        '__pycache__', '.venv', 'coverage', 'public'}
                for dirpath, dirnames, filenames in os.walk(base):
                    dirnames[:] = [d for d in dirnames
                                   if d not in skip and not d.startswith('.')]
                    if 'index.html' in filenames and dirpath != base:
                        return dirpath
                return None

            # ── Next.js helpers ───────────────────────────────────────────

            # Patch next.config.* to add output:'export' + images.unoptimized.
            # Also appends a CJS override block as a last-resort fallback.
            def patch_nextjs_config(base, backups):
                import re as _re
                for cfg in ('next.config.js', 'next.config.mjs',
                            'next.config.ts', 'next.config.cjs'):
                    cfg_p = os.path.join(base, cfg)
                    if not os.path.exists(cfg_p):
                        continue
                    with open(cfg_p, 'r', encoding='utf-8') as f:
                        original = f.read()
                    backups[cfg_p] = original
                    txt = original
                    # Add output:'export' if not already present
                    if "'export'" not in txt and '"export"' not in txt:
                        txt, n = _re.subn(
                            r"(output\s*:\s*)['\"][^'\"]*['\"]",
                            r"\1'export'", txt)
                        if n == 0:
                            txt, n = _re.subn(
                                r'((?:const|let|var)\s+\w+[^=\n]*=\s*\{'
                                r'|module\.exports\s*=\s*\{'
                                r'|export\s+default\s*\{)',
                                r"\1\n  output: 'export',",
                                txt, count=1)
                        if n == 0 or txt == original:
                            txt = txt.rstrip() + (
                                "\n// added by HTML2EXE\n"
                                "if (typeof module !== 'undefined'"
                                " && module.exports) {\n"
                                "  module.exports = {"
                                " ...module.exports, output: 'export' };\n"
                                "}\n")
                    # Add images.unoptimized (required for static export)
                    if 'unoptimized' not in txt:
                        txt = txt.rstrip() + (
                            "\nif (typeof module !== 'undefined'"
                            " && module.exports) {\n"
                            "  if (!module.exports.images)"
                            " module.exports.images = {};\n"
                            "  module.exports.images.unoptimized = true;\n"
                            "}\n")
                    with open(cfg_p, 'w', encoding='utf-8') as f:
                        f.write(txt)
                    log(f'next.config patched ({cfg})')
                    return True
                # No config file — create minimal one
                cfg_p = os.path.join(base, 'next.config.js')
                backups[cfg_p] = None  # mark as created
                with open(cfg_p, 'w', encoding='utf-8') as f:
                    f.write("/** @type {import('next').NextConfig} */\n"
                            "module.exports = {\n"
                            "  output: 'export',\n"
                            "  images: { unoptimized: true },\n"
                            "};\n")
                log('next.config.js created')
                return True

            # Build a static site from .next/ after a regular next build.
            # Copies .next/static/ + all pre-rendered .html from server/app/.
            def _extract_nextjs_static(base):
                next_dir = os.path.join(base, '.next')
                server_app = os.path.join(next_dir, 'server', 'app')
                static_dir = os.path.join(next_dir, 'static')
                if not os.path.isdir(static_dir):
                    return None, 'No .next/static found'
                out_dir = os.path.join(base, '_html2exe_out')
                if os.path.isdir(out_dir):
                    shutil.rmtree(out_dir)
                os.makedirs(out_dir)
                # Copy static assets (_next/static/)
                shutil.copytree(static_dir,
                                os.path.join(out_dir, '_next', 'static'))
                # Copy pre-rendered HTML from server/app/
                html_count = 0
                if os.path.isdir(server_app):
                    for root, _d, files in os.walk(server_app):
                        for fname in files:
                            if not fname.endswith('.html'):
                                continue
                            src = os.path.join(root, fname)
                            rel = os.path.relpath(src, server_app)
                            dst = os.path.join(out_dir, rel)
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)
                            html_count += 1
                if html_count == 0:
                    return None, 'No pre-rendered HTML in .next/server/app/'
                # Normalise filenames: page.html → index.html
                for root, _d, files in os.walk(out_dir):
                    for fname in files:
                        if fname == 'page.html':
                            old = os.path.join(root, fname)
                            new = os.path.join(root, 'index.html')
                            if not os.path.exists(new):
                                os.rename(old, new)
                # Ensure a root index.html
                root_html = os.path.join(out_dir, 'index.html')
                if not os.path.exists(root_html):
                    for root, _d, files in os.walk(out_dir):
                        for fname in files:
                            if fname.endswith('.html'):
                                shutil.copy2(os.path.join(root, fname),
                                             root_html)
                                break
                        if os.path.exists(root_html):
                            break
                log(f'Extracted {html_count} HTML pages from .next/')
                return out_dir, None

            # ── Main Next.js static build ─────────────────────────────────
            # Tier 1: output:'export' with all blockers stubbed.
            # Tier 2 fallback: regular next build + extract from .next/.
            def _build_nextjs_static(base):
                backups = {}

                def _bw(path, content):   # backup + write
                    if path not in backups:
                        try:
                            with open(path, 'r', encoding='utf-8') as fh:
                                backups[path] = fh.read()
                        except FileNotFoundError:
                            backups[path] = None
                    with open(path, 'w', encoding='utf-8') as fh:
                        fh.write(content)

                def _restore():
                    for path, original in backups.items():
                        try:
                            if original is None:
                                if os.path.exists(path):
                                    os.remove(path)
                            else:
                                with open(path, 'w', encoding='utf-8') as fh:
                                    fh.write(original)
                        except Exception:
                            pass

                # ── Stubs (zero external dependencies) ───────────────────
                # API route stub: satisfies output:export, returns empty JSON
                api_stub = (
                    "export const dynamic = 'force-static';\n"
                    "const _r = () => new Response('{}', {status:200,"
                    "headers:{'Content-Type':'application/json'}});\n"
                    "export const GET=_r, POST=_r, PUT=_r,"
                    " DELETE=_r, PATCH=_r;\n"
                )
                # Dynamic page/layout stubs — complete replacements so there
                # are NO imports that could fail or introduce side-effects.
                # generateStaticParams returning [] tells Next.js "export zero
                # static paths for this dynamic route" — valid for output:export.
                # All stubs are self-contained with no imports — avoids any
                # missing-module or implicit-any TypeScript errors.
                _stubs = {
                    'page': (
                        "// @ts-nocheck\n"
                        "export async function generateStaticParams()"
                        " { return []; }\n"
                        "export default function Page() { return null; }\n"
                    ),
                    'layout': (
                        "// @ts-nocheck\n"
                        "export async function generateStaticParams()"
                        " { return []; }\n"
                        "export default function Layout(props: any)"
                        " { return props.children ?? null; }\n"
                    ),
                    'loading': (
                        "// @ts-nocheck\n"
                        "export default function Loading()"
                        " { return null; }\n"
                    ),
                    'error': (
                        "// @ts-nocheck\n"
                        "'use client';\n"
                        "export default function Error()"
                        " { return null; }\n"
                    ),
                    'not-found': (
                        "// @ts-nocheck\n"
                        "export default function NotFound()"
                        " { return null; }\n"
                    ),
                }

                # ── File finders ──────────────────────────────────────────
                def _api_routes(app_dir):
                    out = []
                    api = os.path.join(app_dir, 'api')
                    if not os.path.isdir(api):
                        return out
                    for r, _d, fs in os.walk(api):
                        for f in fs:
                            if f.lower().startswith('route.'):
                                out.append(os.path.join(r, f))
                    return out

                def _dynamic_files(app_dir):
                    """All page/layout/loading/error files inside [param] dirs."""
                    out = []
                    if not os.path.isdir(app_dir):
                        return out
                    for root, _d, files in os.walk(app_dir):
                        parts = os.path.relpath(
                            root, app_dir).replace('\\', '/').split('/')
                        if any(p.startswith('[') and p.endswith(']')
                               for p in parts if p != '.'):
                            for fname in files:
                                stem = fname.split('.')[0]
                                ext  = fname.rsplit('.', 1)[-1]
                                if stem in _stubs and ext in (
                                        'tsx', 'ts', 'jsx', 'js'):
                                    out.append(
                                        (os.path.join(root, fname), stem))
                    return out

                try:
                    # ── TIER 1: output:export ─────────────────────────────
                    patch_nextjs_config(base, backups)
                    next_cache = os.path.join(base, '.next')
                    if os.path.isdir(next_cache):
                        shutil.rmtree(next_cache, ignore_errors=True)
                        log('Cleared .next cache')

                    app_dirs = [os.path.join(base, 'app'),
                                os.path.join(base, 'src', 'app')]
                    for ad in app_dirs:
                        for p in _api_routes(ad):
                            _bw(p, api_stub)
                            log(f'Stubbed API: {os.path.relpath(p, base)}')
                        for p, stem in _dynamic_files(ad):
                            _bw(p, _stubs[stem])
                            log(f'Stubbed {stem}: '
                                f'{os.path.relpath(p, base)}')

                    r = subprocess.run('npm install', cwd=base,
                                       capture_output=True, text=True,
                                       shell=True)
                    log(r.stdout[-2000:] if r.stdout else '')
                    if r.returncode != 0:
                        return None, f'npm install failed:\n{r.stderr}'

                    r = subprocess.run('npm run build', cwd=base,
                                       capture_output=True, text=True,
                                       shell=True)
                    log(r.stdout[-3000:] if r.stdout else '')

                    if r.returncode == 0:
                        result = (find_built_output(base)
                                  or os.path.join(base, 'out'))
                        if os.path.isdir(result):
                            log(f'Static export succeeded: {result}')
                            return result, None

                    # ── TIER 2 fallback: regular build + extract ──────────
                    log('Static export failed — trying regular build + '
                        'extract from .next/...')
                    # Restore ALL original files (stubs + config) first.
                    _restore()
                    backups.clear()  # prevent double-restore in outer finally
                    if os.path.isdir(next_cache):
                        shutil.rmtree(next_cache, ignore_errors=True)

                    # The original next.config may already contain
                    # output:'export' (that's why Tier 1 failed — the project
                    # itself has incompatible routes). For a regular build we
                    # MUST remove output:'export' so Next.js produces .next/.
                    import re as _re2
                    t2_cfg_path = None
                    t2_cfg_orig = None
                    for _cn in ('next.config.ts', 'next.config.js',
                                'next.config.mjs', 'next.config.cjs'):
                        _cp = os.path.join(base, _cn)
                        if not os.path.exists(_cp):
                            continue
                        with open(_cp, 'r', encoding='utf-8') as _fh:
                            t2_cfg_orig = _fh.read()
                        t2_cfg_path = _cp
                        _cleaned = _re2.sub(
                            r"\boutput\s*:\s*['\"]export['\"],?\s*\n?",
                            '', t2_cfg_orig)
                        # Remove any HTML2EXE-appended override blocks
                        _cleaned = _re2.sub(
                            r'\n// (?:added|output added) by HTML2EXE\n'
                            r'(?:.*\n)*?}\n',
                            '\n', _cleaned)
                        if _cleaned != t2_cfg_orig:
                            with open(_cp, 'w', encoding='utf-8') as _fh:
                                _fh.write(_cleaned)
                            log(f'Stripped output:export from {_cn} '
                                f'for regular build')
                        break

                    try:
                        r2 = subprocess.run('npm run build', cwd=base,
                                            capture_output=True, text=True,
                                            shell=True)
                        log(r2.stdout[-3000:] if r2.stdout else '')
                        if r2.returncode != 0:
                            return None, (
                                'Next.js build failed completely.\n'
                                f'Details:\n{r2.stderr[-2000:]}')

                        fallback, err = _extract_nextjs_static(base)
                        if fallback:
                            return fallback, None
                        return None, (
                            'Both static export and .next/ extraction '
                            'failed.\nExtraction error: ' + (err or ''))
                    finally:
                        # Always restore the original config
                        if t2_cfg_path and t2_cfg_orig is not None:
                            with open(t2_cfg_path, 'w',
                                      encoding='utf-8') as _fh:
                                _fh.write(t2_cfg_orig)

                except Exception as exc:
                    return None, f'Next.js build error: {exc}'
                finally:
                    _restore()

            has_pkg = os.path.exists(os.path.join(web_src, 'package.json'))
            pkg_data = {}
            if has_pkg:
                try:
                    with open(os.path.join(web_src, 'package.json'),
                              'r', encoding='utf-8') as f:
                        pkg_data = json.load(f)
                except Exception:
                    pass
            all_deps = {**pkg_data.get('dependencies', {}),
                        **pkg_data.get('devDependencies', {})}
            has_build_script = 'build' in pkg_data.get('scripts', {})
            is_nextjs = 'next' in all_deps
            has_index_at_root = os.path.exists(os.path.join(web_src, 'index.html'))

            if has_pkg and has_build_script and not has_index_at_root:
                # It's a framework project that needs building
                built_dir = find_built_output(web_src)

                if is_nextjs:
                    if built_dir is not None:
                        log('Next.js out/ already exists — skipping rebuild')
                    else:
                        log('Next.js project — building with static export '
                            '(API routes will be stubbed)...')
                        built_dir, err = _build_nextjs_static(web_src)
                        if built_dir is None:
                            return {'success': False,
                                    'error': err,
                                    'log': log_lines}

                elif built_dir is None:
                    # Not yet built — run npm build
                    log('Source project detected — running npm build...')
                    r = subprocess.run('npm install', cwd=web_src,
                                       capture_output=True, text=True, shell=True)
                    log(r.stdout[-2000:] if r.stdout else '')
                    if r.returncode != 0:
                        return {'success': False,
                                'error': f'npm install failed:\n{r.stderr}',
                                'log': log_lines}
                    r = subprocess.run('npm run build', cwd=web_src,
                                       capture_output=True, text=True, shell=True)
                    log(r.stdout[-2000:] if r.stdout else '')
                    if r.returncode != 0:
                        return {'success': False,
                                'error': f'npm run build failed:\n{r.stderr}',
                                'log': log_lines}
                    built_dir = find_built_output(web_src)
                else:
                    log('Pre-built output found — skipping npm build')

                if not built_dir:
                    return {'success': False,
                            'error': (
                                'Build succeeded but no static output folder was found.\n'
                                'Expected one of: out/, dist/, build/, public/, .output/public/\n'
                                'Make sure your project is configured to produce a static site.'
                            ),
                            'log': log_lines}

                web_src = built_dir
                log(f'Using built output: {web_src}')

            elif has_pkg and not has_index_at_root:
                # package.json but no build script and no index.html
                # Try to find a pre-built output subfolder
                built_dir = find_built_output(web_src)
                if built_dir:
                    web_src = built_dir
                    log(f'Using output: {web_src}')
                # else: fall through and use web_src as-is (may fail later)


            # ── 3. Set up Capacitor working directory ─────────────────────
            user_home = os.path.expanduser('~')
            work_dir = os.path.join(user_home, 'Documents', 'HTML2EXE_Android', app_name)
            os.makedirs(work_dir, exist_ok=True)
            log(f'Working dir: {work_dir}')

            # ── 4. Copy web assets into work_dir/www ──────────────────────
            www_dir = os.path.join(work_dir, 'www')
            if os.path.exists(www_dir):
                shutil.rmtree(www_dir)
            shutil.copytree(web_src, www_dir)
            log(f'Copied web assets to www/')

            # If there's no index.html at root, create a redirect to the first page found
            root_index = os.path.join(www_dir, 'index.html')
            if not os.path.exists(root_index):
                # Find the first non-404 HTML file in the output
                first_html = None
                for dirpath, dirnames, filenames in os.walk(www_dir):
                    dirnames[:] = [d for d in dirnames if d not in ('node_modules', '.git')]
                    for fname in sorted(filenames):
                        if fname.endswith('.html') and fname != '404.html':
                            rel = os.path.relpath(
                                os.path.join(dirpath, fname), www_dir
                            ).replace('\\', '/')
                            first_html = '/' + rel
                            break
                    if first_html:
                        break
                if first_html:
                    with open(root_index, 'w', encoding='utf-8') as f:
                        f.write(
                            '<!DOCTYPE html><html><head>'
                            f'<meta http-equiv="refresh" content="0; url={first_html}">'
                            f'<script>window.location.replace("{first_html}")</script>'
                            '</head><body></body></html>'
                        )
                    log(f'Generated index.html → redirects to {first_html}')
                else:
                    log('WARNING: No HTML files found in output — app may show blank screen')

            # ── 5. Init npm project in work_dir ───────────────────────────
            pkg_json = os.path.join(work_dir, 'package.json')
            if not os.path.exists(pkg_json):
                r = subprocess.run('npm init -y', cwd=work_dir, capture_output=True, text=True, shell=True)
                if r.returncode != 0:
                    return {'success': False, 'error': f'npm init failed:\n{r.stderr}', 'log': log_lines}
                log('npm init done')

            # ── 6. Install Capacitor ──────────────────────────────────────
            log('Installing Capacitor (this may take a few minutes on first run)...')
            r = subprocess.run(
                'npm install @capacitor/cli @capacitor/core @capacitor/android',
                cwd=work_dir, capture_output=True, text=True, shell=True
            )
            log(r.stdout[-2000:] if r.stdout else '')
            if r.returncode != 0:
                return {'success': False, 'error': f'Capacitor install failed:\n{r.stderr}', 'log': log_lines}
            log('Capacitor installed')

            # ── 7. Init Capacitor project ─────────────────────────────────
            cap_config = os.path.join(work_dir, 'capacitor.config.json')
            if not os.path.exists(cap_config):
                r = subprocess.run(
                    f'npx cap init "{app_name}" "{package_name}" --web-dir www',
                    cwd=work_dir, capture_output=True, text=True, shell=True
                )
                log(r.stdout[-2000:] if r.stdout else '')
                if r.returncode != 0:
                    return {'success': False, 'error': f'cap init failed:\n{r.stderr}', 'log': log_lines}
                log('Capacitor project initialised')
            else:
                log('Existing Capacitor project found — skipping init')

            # Always overwrite capacitor.config.json with settings that allow
            # external navigation and mixed content (needed for CDN resources)
            cap_cfg_obj = {
                "appId": package_name,
                "appName": app_name,
                "webDir": "www",
                "server": {
                    "allowNavigation": ["*"],
                    "androidScheme": "http"
                },
                "android": {
                    "allowMixedContent": True
                }
            }
            with open(cap_config, 'w', encoding='utf-8') as f:
                json.dump(cap_cfg_obj, f, indent=2)
            log('capacitor.config.json updated (allowMixedContent + allowNavigation)')

            # ── 8. Add Android platform ───────────────────────────────────
            android_dir = os.path.join(work_dir, 'android')
            if not os.path.isdir(android_dir):
                log('Adding Android platform (Gradle will download on first run ~5-10 min)...')
                r = subprocess.run(
                    'npx cap add android',
                    cwd=work_dir, capture_output=True, text=True, shell=True
                )
                log(r.stdout[-2000:] if r.stdout else '')
                if r.returncode != 0:
                    return {'success': False, 'error': f'cap add android failed:\n{r.stderr}', 'log': log_lines}
                log('Android platform added')
            else:
                log('Android platform already present')

            # ── 8b. Patch AndroidManifest & add network security config ───
            # Android 9+ blocks HTTP traffic by default; this causes a blank
            # white screen when the HTML page loads resources from CDN/http URLs.
            manifest_path = os.path.join(android_dir, 'app', 'src', 'main', 'AndroidManifest.xml')
            net_cfg_dir   = os.path.join(android_dir, 'app', 'src', 'main', 'res', 'xml')
            net_cfg_path  = os.path.join(net_cfg_dir, 'network_security_config.xml')
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = f.read()
                changed = False
                # Enable cleartext traffic
                if 'android:usesCleartextTraffic' not in manifest:
                    manifest = manifest.replace(
                        '<application',
                        '<application\n        android:usesCleartextTraffic="true"',
                        1
                    )
                    changed = True
                # Point to network security config
                if 'android:networkSecurityConfig' not in manifest:
                    manifest = manifest.replace(
                        '<application',
                        '<application\n        android:networkSecurityConfig="@xml/network_security_config"',
                        1
                    )
                    changed = True
                if changed:
                    with open(manifest_path, 'w', encoding='utf-8') as f:
                        f.write(manifest)
                    log('AndroidManifest.xml patched (cleartext + network security config)')
            # Write network_security_config.xml allowing all cleartext
            os.makedirs(net_cfg_dir, exist_ok=True)
            with open(net_cfg_path, 'w', encoding='utf-8') as f:
                f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                        '<network-security-config>\n'
                        '    <base-config cleartextTrafficPermitted="true">\n'
                        '        <trust-anchors>\n'
                        '            <certificates src="system" />\n'
                        '        </trust-anchors>\n'
                        '    </base-config>\n'
                        '</network-security-config>\n')
            log('network_security_config.xml written')

            # ── 9. Copy web assets to android ─────────────────────────────
            # Use 'cap sync' (not 'cap copy') so Capacitor also regenerates
            # capacitor.settings.gradle and other native bridge files.
            log('Syncing web assets...')
            r = subprocess.run(
                'npx cap sync android',
                cwd=work_dir, capture_output=True, text=True, shell=True
            )
            if r.returncode != 0:
                return {'success': False, 'error': f'cap sync failed:\n{r.stderr}', 'log': log_lines}
            log('Assets synced')

            # ── 10. Build APK ─────────────────────────────────────────────
            log('Running Gradle assembleDebug (may take several minutes)...')
            gradlew = os.path.join(android_dir, 'gradlew.bat')
            if not os.path.exists(gradlew):
                return {'success': False, 'error': 'gradlew.bat not found in android/ folder', 'log': log_lines}

            # Write local.properties with sdk.dir so Gradle can find the Android SDK
            local_props = os.path.join(android_dir, 'local.properties')
            sdk_path = (
                os.environ.get('ANDROID_HOME') or
                os.environ.get('ANDROID_SDK_ROOT') or
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Sdk')
            )
            if os.path.isdir(sdk_path):
                # Gradle requires forward slashes in local.properties
                sdk_path_fwd = sdk_path.replace('\\', '/')
                props_content = f'sdk.dir={sdk_path_fwd}\n'
                with open(local_props, 'w', encoding='utf-8') as f:
                    f.write(props_content)
                log(f'SDK location: {sdk_path}')
            else:
                log(f'WARNING: Android SDK not found at {sdk_path} — Gradle may fail')

            gradle_env = make_env()
            r = subprocess.run(
                [gradlew, 'assembleDebug'],
                cwd=android_dir,
                capture_output=True, text=True,
                env=gradle_env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            log(r.stdout[-3000:] if r.stdout else '')
            if r.returncode != 0:
                return {'success': False, 'error': f'Gradle build failed:\n{r.stderr[-2000:]}', 'log': log_lines}
            log('Gradle build complete')

            # ── 11. Copy APK to Downloads ─────────────────────────────────
            apk_src = os.path.join(android_dir, 'app', 'build', 'outputs', 'apk', 'debug', 'app-debug.apk')
            if not os.path.exists(apk_src):
                return {'success': False, 'error': 'APK not found after build', 'log': log_lines}

            downloads = os.path.join(user_home, 'Downloads')
            os.makedirs(downloads, exist_ok=True)
            safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in app_name)
            apk_dst = os.path.join(downloads, f'{safe_name}.apk')
            shutil.copy2(apk_src, apk_dst)
            log(f'APK saved to: {apk_dst}')

            return {
                'success': True,
                'apkPath': apk_dst,
                'apkFolder': downloads,
                'log': log_lines,
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            log(f'Error: {e}')
            return {'success': False, 'error': str(e), 'log': log_lines}


class HTMLToEXEBuilder:
    """Main builder application"""
    
    def __init__(self, projects_dir='projects', port=8000):
        self.projects_dir = os.path.abspath(projects_dir)
        self.port = port
        self.server_url = f"http://localhost:{port}"
        
        # Create projects directory if it doesn't exist
        os.makedirs(self.projects_dir, exist_ok=True)
    
    def start_server(self):
        """Start HTTP server"""
        # Handle both frozen (PyInstaller) and normal Python execution
        if getattr(sys, 'frozen', False):
            # Running as PyInstaller executable
            builder_root = sys._MEIPASS
        else:
            # Running as normal Python script
            builder_root = os.path.dirname(os.path.abspath(__file__))
        
        BuilderHTTPHandler.builder_root = builder_root
        
        server = HTTPServer(('localhost', self.port), BuilderHTTPHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        
        return server
    
    def launch_ui(self):
        """Launch the builder UI in PyWebView"""
        server = self.start_server()
        
        # Get screen dimensions to center the window
        try:
            # Get monitor dimensions using tkinter
            root = tk.Tk()
            root.withdraw()  # Hide the window
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            root.destroy()
            
            # Calculate window size: 85% of screen, capped at 1400x860
            window_width = min(int(screen_width * 0.85), 1400)
            window_height = min(int(screen_height * 0.85), 860)
            x_position = (screen_width - window_width) // 2
            y_position = (screen_height - window_height) // 2

            print(f"Monitor resolution: {screen_width}x{screen_height}")
            print(f"Window position: ({x_position}, {y_position})")
        except Exception as e:
            print(f"Warning: Could not get screen dimensions: {e}")
            window_width = 1280
            window_height = 800
            x_position = 100
            y_position = 100

        # Create window with frameless style and custom controls
        window = webview.create_window(
            title='HTML to EXE Builder',
            url=self.server_url,
            width=window_width,
            height=window_height,
            x=x_position,
            y=y_position,
            resizable=True,
            min_size=(1024, 600),
            frameless=True,
            background_color='#0f172a'
        )
        
        # Store window instance for API access
        BuilderHTTPHandler.window_instance = window
        
        try:
            webview.start(debug=False)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            server.shutdown()
    
    def create_project(self, name, template='blank', author='', version='1.0.0', description=''):
        """Create a new project"""
        project_path = os.path.join(self.projects_dir, name)
        
        if os.path.exists(project_path):
            return {'error': f'Project "{name}" already exists'}
        
        os.makedirs(project_path)
        
        # Create project metadata
        project_meta = {
            'name': name,
            'author': author,
            'version': version,
            'description': description,
            'template': template,
            'created': datetime.now().isoformat()
        }
        
        # Write project.json
        with open(os.path.join(project_path, 'project.json'), 'w') as f:
            json.dump(project_meta, f, indent=2)
        
        # Create template files
        if template == 'blank':
            self.create_blank_template(project_path)
        elif template == 'modern':
            self.create_modern_template(project_path)
        elif template == 'dashboard':
            self.create_dashboard_template(project_path)
        elif template == 'calculator':
            self.create_calculator_template(project_path)
        
        return {'success': True, 'path': project_path}
    
    def scan_folder(self, folder_path):
        """Scan folder for HTML/CSS/JS files and return structure with analysis"""
        try:
            folder_path = os.path.abspath(folder_path)
            
            # Check if folder exists
            if not os.path.isdir(folder_path):
                return {'error': 'Invalid folder path'}
            
            # Find main HTML file
            html_files = []
            css_files = []
            js_files = []
            asset_files = []
            total_files = 0
            
            for root, dirs, files in os.walk(folder_path):
                # Skip node_modules and other common ignored directories
                dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '.vscode', '__pycache__', 'dist', 'build']]
                
                for file in files:
                    total_files += 1
                    if file.endswith('.html'):
                        html_files.append(os.path.relpath(os.path.join(root, file), folder_path))
                    elif file.endswith(('.css', '.scss', '.sass')):
                        css_files.append(os.path.relpath(os.path.join(root, file), folder_path))
                    elif file.endswith('.js'):
                        js_files.append(os.path.relpath(os.path.join(root, file), folder_path))
                    elif file.endswith(('png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico')):
                        asset_files.append(os.path.relpath(os.path.join(root, file), folder_path))
            
            # Find entry point (index.html or first HTML file)
            entry_file = None
            if 'index.html' in html_files:
                entry_file = 'index.html'
            elif html_files:
                entry_file = html_files[0]
            
            # Extract folder name for project name
            folder_name = os.path.basename(folder_path)
            
            # Analyze project for framework and version info
            analyzer = ProjectAnalyzer(folder_path)
            analysis = analyzer.analyze()
            
            return {
                'success': True,
                'folderPath': folder_path,
                'folderName': folder_name,
                'entryFile': entry_file,
                'htmlFiles': html_files,
                'cssFiles': css_files,
                'jsFiles': js_files,
                'assetFiles': asset_files[:10],  # Limit to 10 for preview
                'totalFiles': total_files,
                'summary': {
                    'htmlCount': len(html_files),
                    'cssCount': len(css_files),
                    'jsCount': len(js_files),
                    'assetCount': len(asset_files)
                },
                'analysis': analysis  # Add analysis results
            }
        except Exception as e:
            return {'error': f'Error scanning folder: {str(e)}'}
    
    def create_project(self, name, template='blank', author='', version='1.0.0', description=''):
        """Create a new project"""
        html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My App</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <h1>Welcome to My App</h1>
    <p>Start building your application here.</p>
    <script src="script.js"></script>
</body>
</html>'''
        
        css = '''body {
    font-family: Arial, sans-serif;
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
    background: #f5f5f5;
}

h1 {
    color: #333;
}

p {
    color: #666;
    line-height: 1.6;
}'''
        
        js = '''console.log("App loaded!");'''
        
        with open(os.path.join(path, 'index.html'), 'w') as f:
            f.write(html)
        with open(os.path.join(path, 'style.css'), 'w') as f:
            f.write(css)
        with open(os.path.join(path, 'script.js'), 'w') as f:
            f.write(js)
    
    def create_modern_template(self, path):
        """Create modern template with beautiful UI"""
        # Similar to sample_project - create files for modern design
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Modern App</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <header><h1>🎨 Modern Application</h1></header>
        <main>
            <section class="card">
                <h2>Beautiful Design</h2>
                <p>A modern, responsive application built with HTML5 and CSS3.</p>
            </section>
        </main>
    </div>
    <script src="script.js"></script>
</body>
</html>'''
        
        with open(os.path.join(path, 'index.html'), 'w') as f:
            f.write(html)
        
        self.create_blank_template(path)  # Add basic CSS/JS
    
    def create_dashboard_template(self, path):
        """Create dashboard template"""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Dashboard</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="dashboard">
        <h1>📊 Dashboard</h1>
        <div class="widgets">
            <div class="widget"><h3>Widget 1</h3><p>Data here</p></div>
            <div class="widget"><h3>Widget 2</h3><p>Data here</p></div>
        </div>
    </div>
    <script src="script.js"></script>
</body>
</html>'''
        
        with open(os.path.join(path, 'index.html'), 'w') as f:
            f.write(html)
        
        self.create_blank_template(path)
    
    def create_calculator_template(self, path):
        """Create calculator template"""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>Calculator</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="calculator">
        <div class="display" id="display">0</div>
        <div class="buttons">
            <button onclick="clear_display()">C</button>
            <button onclick="append_operator('/')">/</button>
            <button onclick="append_operator('*')">*</button>
            <button onclick="delete_last()">←</button>
            
            <button onclick="append_number('7')">7</button>
            <button onclick="append_number('8')">8</button>
            <button onclick="append_number('9')">9</button>
            <button onclick="append_operator('-')">-</button>
            
            <button onclick="append_number('4')">4</button>
            <button onclick="append_number('5')">5</button>
            <button onclick="append_number('6')">6</button>
            <button onclick="append_operator('+')">+</button>
            
            <button onclick="append_number('1')">1</button>
            <button onclick="append_number('2')">2</button>
            <button onclick="append_number('3')">3</button>
            <button onclick="calculate()" class="equals">=</button>
            
            <button onclick="append_number('0')" class="zero">0</button>
            <button onclick="append_number('.')">.</button>
        </div>
    </div>
    <script src="script.js"></script>
</body>
</html>'''
        
        with open(os.path.join(path, 'index.html'), 'w') as f:
            f.write(html)
        
        self.create_blank_template(path)


def main():
    parser = argparse.ArgumentParser(description='HTML to EXE Builder')
    parser.add_argument('--port', type=int, default=8000, help='Server port')
    parser.add_argument('--projects', default='projects', help='Projects directory')
    
    args = parser.parse_args()
    
    builder = HTMLToEXEBuilder(projects_dir=args.projects, port=args.port)
    
    user_home = os.path.expanduser('~')
    projects_cache_dir = os.path.join(user_home, 'Documents', 'HTML2EXE')
    downloads_dir = os.path.join(user_home, 'Downloads')
    
    print(f"🚀 HTML to EXE Builder")
    print(f"Starting at http://localhost:{args.port}")
    print(f"\n📂 Storage Locations:")
    print(f"  • Projects cache: {projects_cache_dir}")
    print(f"  • Download folder: {downloads_dir}")
    print(f"\n{'='*60}\n")
    
    try:
        builder.launch_ui()
    except KeyboardInterrupt:
        print("\nShutdown...")
        sys.exit(0)


if __name__ == '__main__':
    main()
