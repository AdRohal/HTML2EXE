"""
HTML to EXE Builder - GUI Application
Professional UI for managing projects and building EXEs
"""

import os
import sys
import json
import webview
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import argparse
import subprocess
import shutil
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import filedialog
import secrets

# Force UTF-8 encoding for console output to support emojis and Unicode
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from h2e import dashboard, iconfinder, jobs, python_builder, syscheck, templates  # noqa: E402
from h2e import secrets as envsecrets  # noqa: E402
from h2e import workspace  # noqa: E402
from h2e.analyzer import ProjectAnalyzer, walk_project  # noqa: E402
from h2e.android_builder import AndroidBuilder  # noqa: E402
from h2e.exe_build import build_exe  # noqa: E402
from h2e.security import API_TOKEN, is_safe_project_id, project_dir_for  # noqa: E402


def _pywebview_version():
    """pywebview has no __version__ attribute; ask the package metadata."""
    try:
        from importlib.metadata import version
        return version('pywebview')
    except Exception:
        return 'unknown'


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
    
    def _is_authorized(self):
        """Check Host, Origin and API token for /api/ requests."""
        port = self.server.server_address[1]
        allowed_hosts = {f'localhost:{port}', f'127.0.0.1:{port}'}
        if self.headers.get('Host', '') not in allowed_hosts:
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{h}' for h in allowed_hosts}:
            return False
        supplied = self.headers.get('X-Builder-Token', '')
        return secrets.compare_digest(supplied.encode(), API_TOKEN.encode())

    def _reject(self):
        # Drain a small request body first: answering 403 with unread data makes Windows reset the
        # connection, and the client would see a network error instead of a clean 403.
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if 0 < length <= 1_000_000:
                self.rfile.read(length)
        except (ValueError, OSError):
            pass
        self.close_connection = True
        self.send_error(403, "Forbidden")

    def do_GET(self):
        """Handle GET requests"""
        # Parse URL
        parsed = urlparse(self.path)
        path = parsed.path
        
        # API endpoints
        if path.startswith('/api/'):
            if not self._is_authorized():
                return self._reject()
            self.query = parse_qs(parsed.query)
            self.handle_api_request(path[5:], 'GET')
            return
        
        # Serve builder UI
        if path == '/' or path == '/index.html':
            self.serve_file('builder_ui/index.html')
            return
        
        # Serve static files
        static_files = {
            '/style.css': 'builder_ui/style.css',
            '/app.js': 'builder_ui/app.js',
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
            if not self._is_authorized():
                return self._reject()
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
            if not self._is_authorized():
                return self._reject()
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
            if not self._is_authorized():
                return self._reject()
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            self.handle_api_request(path[5:], 'DELETE', body)
            return
        
        self.send_error(404, "Not Found")
    
    query = {}

    ASYNC_ENDPOINTS = ('build-project', 'convert-python-to-exe', 'build-android')

    def _start_async(self, endpoint, body):
        """Run a long endpoint as a background job and return its id."""
        def run(job):
            responder = _CapturingHandler.__new__(_CapturingHandler)
            responder.captured = None
            responder.query = {}
            responder.handle_api_request(endpoint, 'POST', body)
            data, status = responder.captured or ({'success': False, 'error': 'No result'}, 500)
            if status >= 400 and not data.get('error'):
                data['error'] = f'Failed (HTTP {status})'
            return data
        job = jobs.start_job(endpoint, run)
        self.send_json({'success': True, 'jobId': job.id})

    def handle_api_request(self, endpoint, method, body=None):
        """Handle API requests"""
        if method == 'POST' and endpoint in self.ASYNC_ENDPOINTS and body:
            try:
                wants_async = bool(json.loads(body).get('async'))
            except ValueError:
                wants_async = False
            if wants_async and not isinstance(self, _CapturingHandler):
                return self._start_async(endpoint, body)
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
                                    'sourceFolder': project_meta.get('sourceFolder', ''),
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
                    'pywebview_version': _pywebview_version(),
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
                # Build project to EXE (HTML / frameworks / PHP). See h2e/exe_build.py
                try:
                    data = json.loads(body) if body else {}
                    job = jobs.current_job() or jobs.Job('exe')
                    result = build_exe(data, job)
                    if result.get('success'):
                        dashboard.record_for_project(data.get('projectId'), result)
                        self.send_json(result)
                    else:
                        self.send_json(result, 400)
                except jobs.JobCancelled:
                    raise
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    self.send_json({'success': False, 'error': f'Build error: {str(e)}'}, 500)

            elif endpoint == 'system-check' and method == 'GET':
                self.send_json(syscheck.run_checks(AndroidBuilder.check_prerequisites))

            elif endpoint == 'job-status' and method == 'GET':
                job = jobs.get_job((self.query.get('id') or [''])[0])
                if not job:
                    self.send_json({'error': 'Unknown job'}, 404)
                else:
                    since = int((self.query.get('since') or ['0'])[0] or 0)
                    self.send_json(job.snapshot(since))

            elif endpoint == 'job-cancel' and method == 'POST':
                data = json.loads(body) if body else {}
                job = jobs.get_job(data.get('id', ''))
                if job:
                    job.cancel()
                self.send_json({'success': bool(job)})

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
                        if not is_safe_project_id(project_name):
                            self.send_json({'error': 'Project name cannot contain any of: / : * ? " < > | or a backslash'}, 400)
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
                        
                        # "Create Project" without a source folder: start from a template
                        if not folder_path:
                            if not os.path.isfile(os.path.join(downloads_dir, 'index.html')):
                                templates.write_template(downloads_dir, str(data.get('template') or 'blank'))
                                print(f"  Created '{data.get('template') or 'blank'}' template files")
                            analysis_folder = downloads_dir
                        else:
                            analysis_folder = folder_path

                        # Analyze project for framework and version info
                        analyzer = ProjectAnalyzer(analysis_folder)
                        analysis = analyzer.analyze()
                        
                        # Create project.json metadata in Documents
                        project_meta = {
                            'name': project_name,
                            'author': author,
                            'version': version,
                            'description': description,
                            'sourceFolder': analysis_folder,
                            'downloadFolder': downloads_dir,
                            'created': datetime.now().isoformat(),
                            'analysis': analysis
                        }
                        
                        # Write project metadata
                        metadata_file = os.path.join(metadata_dir, 'project.json')
                        print(f"\n💾 Saving metadata to: {metadata_file}")
                        with open(metadata_file, 'w', encoding='utf-8') as f:
                            json.dump(project_meta, f, indent=2, ensure_ascii=False)
                        
                        print(f"✅ Metadata saved")
                        
                        # Temporary working copy in Downloads (deleted after the build; see h2e/workspace.py)
                        same_folder = bool(folder_path) and os.path.realpath(folder_path) == os.path.realpath(downloads_dir)
                        if folder_path and os.path.isdir(folder_path) and not same_folder:
                            print("\nPreparing the working copy...")
                            copied = workspace.sync_working_copy(folder_path, downloads_dir, log=print)
                            print(f"Copied {copied} items")

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
                if not body:
                    self.send_json({'error': 'No project data provided'}, 400)
                else:
                    try:
                        payload = json.loads(body)
                    except ValueError:
                        self.send_json({'error': 'Request body is not valid JSON'}, 400)
                        return
                    result, status = python_builder.convert(payload)
                    self.send_json(result, status)

            elif endpoint == 'find-icon' and method == 'POST':
                data = json.loads(body) if body else {}
                folder = str(data.get('folderPath', ''))
                found = iconfinder.find_icon(os.path.abspath(folder)) if folder and os.path.isdir(folder) else None
                if found:
                    found.pop('path', None)               # the page needs the picture and the name, not the disk path
                self.send_json({'success': True, 'found': bool(found), **(found or {})})

            elif endpoint == 'dashboard' and method == 'GET':
                self.send_json(dashboard.stats())

            elif endpoint == 'analyze-python' and method == 'POST':
                data = json.loads(body) if body else {}
                try:
                    self.send_json(python_builder.analyze(str(data.get('pythonPath', ''))))
                except FileNotFoundError as exc:
                    self.send_json({'error': str(exc)}, 404)
                except ValueError as exc:
                    self.send_json({'error': str(exc)}, 400)

            elif endpoint == 'env-scan' and method == 'POST':
                data = json.loads(body) if body else {}
                folder = str(data.get('folderPath', ''))
                if not folder or not os.path.isdir(folder):
                    self.send_json({'error': 'Invalid folder path'}, 400)
                else:
                    self.send_json({'success': True, **envsecrets.describe(os.path.abspath(folder))})

            elif endpoint == 'open-url' and method == 'POST':
                # "Install Node.js" style links: open in the default browser, https only
                data = json.loads(body) if body else {}
                url = str(data.get('url', ''))
                if url.startswith('https://') and len(url) < 400:
                    webbrowser.open(url)
                    self.send_json({'success': True})
                else:
                    self.send_json({'success': False, 'error': 'Only https links can be opened'}, 400)

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
                    metadata_dir = project_dir_for(project_id)
                    if metadata_dir is None:
                        self.send_json({'error': 'Invalid project ID'}, 400)
                        return
                    if os.path.exists(metadata_dir):
                        try:
                            with open(os.path.join(metadata_dir, 'project.json'), encoding='utf-8') as fh:
                                meta = json.load(fh)
                            workspace.remove_working_copy(meta.get('downloadFolder', ''), meta.get('sourceFolder', ''))
                        except (OSError, ValueError):
                            pass
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
                    except jobs.JobCancelled:
                        raise
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        self.send_json({'success': False, 'error': str(e)}, 500)
                else:
                    self.send_json({'error': 'No build data provided'}, 400)

            else:
                self.send_json({'error': 'Endpoint not found'}, 404)

        except jobs.JobCancelled:
            raise          # the job runner reports "cancelled", not a 500
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
    def serve_file(self, file_path):
        """Serve a static file"""
        ui_root = os.path.realpath(os.path.join(self.builder_root, 'builder_ui'))
        full_path = os.path.realpath(os.path.join(self.builder_root, file_path))

        # Never serve anything outside builder_ui/ (blocks ../ traversal)
        try:
            inside = os.path.commonpath([ui_root, full_path]) == ui_root
        except ValueError:
            inside = False
        if not inside:
            self.send_error(403, "Forbidden")
            return

        if not os.path.isfile(full_path):
            self.send_error(404, "File Not Found")
            return

        try:
            with open(full_path, 'rb') as f:
                content = f.read()

            if file_path.endswith('index.html'):
                # Give our own page the API token and make every same-origin
                # fetch('/api/...') carry it.
                bootstrap = (
                    '<script>(function(){var t=' + json.dumps(API_TOKEN) + ';'
                    'var f=window.fetch;window.fetch=function(u,o){'
                    'o=o||{};var s=(typeof u==="string")?u:(u&&u.url)||"";'
                    'if(s.indexOf("/api/")!==-1){var h=new Headers(o.headers||{});'
                    'h.set("X-Builder-Token",t);o.headers=h;}'
                    'return f.call(this,u,o);};})();</script>'
                ).encode('utf-8')
                content = content.replace(b'<head>', b'<head>' + bootstrap, 1)
            
            # Set content type
            content_type = self.guess_type(file_path)
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', len(content))
            self.send_header('Cache-Control', 'no-store')
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


class _CapturingHandler(BuilderHTTPHandler):
    """Runs API code inside a background job and captures send_json()."""
    captured = None

    def send_json(self, data, status=200):
        self.captured = (data, status)


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
        
        # Threaded: one slow request (a big folder scan, the native folder dialog) must not freeze
        # the window, the job log polling or the title-bar buttons.
        server = ThreadingHTTPServer(('localhost', self.port), BuilderHTTPHandler)
        server.daemon_threads = True
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
            
            for root, file in walk_project(folder_path):
                if True:
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
