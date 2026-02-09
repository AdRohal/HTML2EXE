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
                        
                        # Create build directory
                        build_dir = os.path.join(metadata_dir, 'build')
                        os.makedirs(build_dir, exist_ok=True)
                        
                        print(f"\n🔧 Creating build script...")
                        
                        # Create a Python script that serves the HTML project
                        build_script = f'''
import os
import sys
import webview
from pathlib import Path

# Project directory
PROJECT_DIR = r"{project_folder}"

class API:
    def __init__(self):
        pass

if __name__ == "__main__":
    # Create window with project
    window = webview.create_window(
        title="{project_name}",
        url=f"file://" + os.path.join(PROJECT_DIR, "index.html"),
        width=1024,
        height=768,
        resizable=True,
        background_color="#ffffff"
    )
    
    webview.start(debug=False, http_server=False)
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
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        
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
                        
                        print(f"\n🔧 Preparing PyInstaller command...")
                        
                        # Create PyInstaller command
                        cmd = [
                            'pyinstaller',
                            '--onefile' if single_file else '--onedir',
                        ]
                        
                        if hide_console:
                            cmd.append('--windowed')
                        
                        if optimize:
                            cmd.extend(['--optimize', '2'])
                        
                        cmd.extend([
                            '--noupx',
                            '-y',
                            f'--name={exe_name}',
                            f'--distpath={output_dir}',
                            f'--workpath={os.path.join(build_dir, "build")}',
                            f'--specpath={build_dir}',
                        ])
                        
                        # Add icon if available
                        if final_icon_path and os.path.exists(final_icon_path):
                            abs_icon_path = os.path.abspath(final_icon_path)
                            print(f"📌 Icon: {abs_icon_path}")
                            cmd.append(f'--icon={abs_icon_path}')
                        
                        cmd.append(entry_point_path)
                        
                        print(f"\n⚙️  Running PyInstaller...")
                        print(f"Command: {' '.join(cmd)}\n")
                        
                        # Run PyInstaller
                        result = subprocess.run(cmd, capture_output=True, text=True, cwd=python_path)
                        
                        print(f"PyInstaller output:\n{result.stdout}")
                        
                        if result.stderr and result.stderr.strip():
                            print(f"PyInstaller warnings:\n{result.stderr}")
                        
                        if result.returncode != 0:
                            print(f"\n❌ Build failed!")
                            self.send_json({
                                'error': f'PyInstaller build failed: {result.stderr}'
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
                                'message': f'Python to EXE conversion successful!',
                                'exePath': exe_path,
                                'exeName': f'{exe_name}.exe',
                                'size': f'{exe_size:.2f} MB'
                            })
                        else:
                            print(f"❌ EXE was not created at expected location!")
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
        
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', len(response))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response)
    
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
        BuilderHTTPHandler.builder_root = os.path.dirname(os.path.abspath(__file__))
        
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
            
            # Calculate center position
            window_width = 1800
            window_height = 1200
            x_position = (screen_width - window_width) // 2
            y_position = (screen_height - window_height) // 2
            
            print(f"Monitor resolution: {screen_width}x{screen_height}")
            print(f"Window position: ({x_position}, {y_position})")
        except Exception as e:
            print(f"Warning: Could not get screen dimensions: {e}")
            x_position = 100
            y_position = 100
        
        # Create window with frameless style and custom controls
        window = webview.create_window(
            title='HTML to EXE Builder',
            url=self.server_url,
            width=1800,
            height=1200,
            x=x_position,
            y=y_position,
            resizable=True,
            min_size=(1024, 600),
            frameless=True,
            background_color='#E8EBF7'
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
