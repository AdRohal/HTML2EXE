"""Project analysis: look at a folder and guess what kind of web project it is."""
import json
import os

from .recipes import SKIP_DIRS as _BASE_SKIP

# --- bounded folder walking -------------------------------------------------------------------
# A real React/Next/Nuxt project has folders that are huge and useless for detection (node_modules,
# .next/cache, build output, vendor). Walking and reading them made "pick a folder" hang for minutes.
SCAN_SKIP_DIRS = set(_BASE_SKIP) | {'dist', 'build', 'out', '.cache', '.turbo', '.parcel-cache',
                                    '.vercel', '.expo', 'vendor', 'target'}
MAX_FILES = 6000          # stop looking after this many files
MAX_SIZE = 1_000_000      # never read files bigger than this (bundles, data dumps)
MAX_READ = 200_000        # read at most this much of a file


def walk_project(folder, max_files=MAX_FILES):
    """Yield (root, filename) for the source files of a project, skipping heavy folders."""
    seen = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SCAN_SKIP_DIRS]
        for name in files:
            seen += 1
            if seen > max_files:
                return
            yield root, name


def read_head(path, limit=MAX_READ):
    """The start of a text file, or '' when it is missing or too big to be hand-written source."""
    try:
        if os.path.getsize(path) > MAX_SIZE:
            return ''
        with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            return fh.read(limit)
    except OSError:
        return ''


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

        # Framework recipes know about Astro, Laravel, PHP, Next static export ...
        try:
            from h2e import recipes
            info = recipes.detect(self.folder_path)
            analysis['framework'] = info['framework']
            analysis['support'] = info['support']
            analysis['frameworkLabel'] = info['label']
            analysis['notes'] = info['notes']
            analysis['server'] = info.get('server', False)
            analysis['serverFeatures'] = info.get('serverFeatures', [])
            if info['framework'] in ('astro', 'laravel', 'php'):
                name = {'astro': 'Astro', 'laravel': 'Laravel', 'php': 'PHP'}[info['framework']]
                if name not in analysis['frameworks']:
                    analysis['frameworks'].append(name)
                if name not in analysis['technologies']:
                    analysis['technologies'].append(name)
                analysis['projectType'] = {'astro': 'Astro (static site)', 'laravel': 'Laravel (PHP)', 'php': 'PHP site'}[info['framework']]
        except Exception:
            pass
        
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
        for root, file in walk_project(self.folder_path):
            if True:
                if file.endswith('.html'):
                    file_path = os.path.join(root, file)
                    try:
                        content = read_head(file_path)
                        
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
        
        for root, file in walk_project(self.folder_path):
            if True:
                if file.endswith(('.js', '.jsx', '.ts', '.tsx')):
                    file_path = os.path.join(root, file)
                    try:
                        content = read_head(file_path)
                        
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
        for root, file in walk_project(self.folder_path):
            if True:
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
