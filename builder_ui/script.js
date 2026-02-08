// HTML to EXE Builder - Main Script

let currentPage = 'dashboard';
let selectedTemplate = 'blank';
let projects = [];
let builtCount = 0;
let customColors = [];
let importedFolder = null;  // Store imported folder info
let existingImportedFolder = null; // Store existing project folder info

// Default color palette
const defaultColors = [
    { name: 'ROJO', hex: '#DE1A1A', rgb: 'rgb(222, 26, 26)' },
    { name: 'GHOST WHITE', hex: '#E8EBF7', rgb: 'rgb(232, 235, 247)' },
    { name: 'Primary', hex: '#667eea', rgb: 'rgb(102, 126, 234)' },
    { name: 'Secondary', hex: '#764ba2', rgb: 'rgb(118, 75, 162)' },
    { name: 'Accent', hex: '#f5576c', rgb: 'rgb(245, 87, 108)' },
    { name: 'Success', hex: '#51cf66', rgb: 'rgb(81, 207, 102)' },
    { name: 'Warning', hex: '#ffd700', rgb: 'rgb(255, 215, 0)' },
    { name: 'Danger', hex: '#ff6b6b', rgb: 'rgb(255, 107, 107)' },
    { name: 'Dark', hex: '#1a1a2e', rgb: 'rgb(26, 26, 46)' },
    { name: 'Light', hex: '#f8f9fa', rgb: 'rgb(248, 249, 250)' },
    { name: 'Gray', hex: '#6c757d', rgb: 'rgb(108, 117, 125)' },
    { name: 'Border', hex: '#e0e0e0', rgb: 'rgb(224, 224, 224)' },
];

// ============ Window Control Functions ============
function minimizeWindow() {
    try {
        fetch('/api/minimize-window', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .catch(e => console.log('Minimize:', e));
    } catch (e) {
        console.error('Minimize error:', e);
    }
}

function maximizeWindow() {
    try {
        fetch('/api/maximize-window', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .catch(e => console.log('Maximize:', e));
    } catch (e) {
        console.error('Maximize error:', e);
    }
}

function closeWindow() {
    try {
        fetch('/api/close-window', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(r => r.json())
        .catch(e => console.log('Close:', e));
    } catch (e) {
        console.error('Close error:', e);
    }
}

// ============ End Window Control Functions ============

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
    loadProjects();
    loadSavedColors();
    updateStats();
    
    // Setup color picker event listener
    const colorPicker = document.getElementById('colorPicker');
    if (colorPicker) {
        colorPicker.addEventListener('change', function() {
            const hexDisplay = document.getElementById('colorHexDisplay');
            if (hexDisplay) {
                hexDisplay.textContent = this.value.toUpperCase();
            }
        });
        
        colorPicker.addEventListener('input', function() {
            const hexDisplay = document.getElementById('colorHexDisplay');
            if (hexDisplay) {
                hexDisplay.textContent = this.value.toUpperCase();
            }
        });
    }
});

function initializeApp() {
    // Load projects from local storage
    const stored = localStorage.getItem('htmlToExeProjects');
    if (stored) {
        projects = JSON.parse(stored);
    }
    
    // Set up navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function() {
            const page = this.getAttribute('data-page');
            goToPage(page);
        });
    });
}

function setupEventListeners() {
    // Page navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function() {
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            this.classList.add('active');
        });
    });
}

function goToPage(page) {
    // Hide all pages
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    
    // Show selected page
    const pageElement = document.getElementById(page + '-page');
    if (pageElement) {
        pageElement.classList.add('active');
        currentPage = page;
        const pageTitles = {
            dashboard: 'Dashboard',
            projects: 'My Projects',
            create: 'Create',
            existing: 'Existing Project',
            build: 'Build System',
            colors: 'Colors & Theme',
            settings: 'Settings',
            'python-convert': 'Python to EXE'
        };
        document.getElementById('pageTitle').textContent = pageTitles[page] || (page.charAt(0).toUpperCase() + page.slice(1));
        
        // Load page-specific data
        if (page === 'projects') {
            loadProjects();
        } else if (page === 'build') {
            populateBuildProject();
        } else if (page === 'colors') {
            loadColors();
        }
    }
}

function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('active');
}

// Dashboard
function updateStats() {
    document.getElementById('projectCount').textContent = projects.length;
    document.getElementById('builtCount').textContent = builtCount;
}

// Projects Page
function loadProjects() {
    const projectsList = document.getElementById('projectsList');
    projectsList.innerHTML = '<div class="loading">Loading projects...</div>';
    
    // Fetch projects from API
    fetch('/api/projects')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.projects.length > 0) {
                projects = data.projects;
                
                projectsList.innerHTML = projects.map(project => `
                    <div class="project-card" onclick="selectProject('${project.id}')">
                        <div class="project-card-header">
                            <div class="project-icon">📦</div>
                            <button class="project-menu" onclick="event.stopPropagation(); showProjectMenu('${project.id}')">⋮</button>
                        </div>
                        <h3>${project.name}</h3>
                        <p>${project.description || 'No description'}</p>
                        <div class="project-tag">
                            ${project.analysis.projectType}
                        </div>
                        <div class="project-stats">
                            <span>v${project.version}</span>
                            <span>📅 ${new Date(project.created).toLocaleDateString()}</span>
                        </div>
                    </div>
                `).join('');
            } else {
                projectsList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">📁</div>
                        <h3>No projects yet</h3>
                        <p>Create your first project to get started</p>
                        <button class="btn-primary" onclick="goToPage('create')">Create Project</button>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error loading projects:', error);
            projectsList.innerHTML = `
                <div class="empty-state error">
                    <div class="empty-icon">⚠️</div>
                    <h3>Error loading projects</h3>
                    <p>${error.message}</p>
                </div>
            `;
        });
}

function selectProject(projectId) {
    const project = projects.find(p => p.id === projectId);
    if (project) {
        showProjectAnalysis(project);
    }
}

function showProjectAnalysis(project) {
    // Create a modal to show project analysis
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.onclick = (e) => {
        if (e.target === modal) closeProjectAnalysis();
    };
    
    let frameworksHTML = '';
    if (project.analysis.frameworks && project.analysis.frameworks.length > 0) {
        frameworksHTML = `
            <div class="analysis-item">
                <strong>Frameworks:</strong>
                <div class="tag-list">
                    ${project.analysis.frameworks.map(fw => `<span class="tag tag-framework">${fw}</span>`).join('')}
                </div>
            </div>
        `;
    }
    
    let technologiesHTML = '';
    if (project.analysis.technologies && project.analysis.technologies.length > 0) {
        technologiesHTML = `
            <div class="analysis-item">
                <strong>Technologies:</strong>
                <div class="tag-list">
                    ${project.analysis.technologies.map(tech => `<span class="tag tag-tech">${tech}</span>`).join('')}
                </div>
            </div>
        `;
    }
    
    let versionsHTML = '';
    if (project.analysis.versions && Object.keys(project.analysis.versions).length > 0) {
        let versionsList = '';
        for (const [name, version] of Object.entries(project.analysis.versions)) {
            versionsList += `<div class="version-item"><span class="version-name">${name}:</span> <span class="version-value">${version}</span></div>`;
        }
        versionsHTML = `
            <div class="analysis-item">
                <strong>Versions:</strong>
                <div class="versions-list">${versionsList}</div>
            </div>
        `;
    }
    
    let dependenciesHTML = '';
    if (project.analysis.dependencies && Object.keys(project.analysis.dependencies).length > 0) {
        const depCount = Object.keys(project.analysis.dependencies).length;
        dependenciesHTML = `
            <div class="analysis-item">
                <strong>Dependencies:</strong>
                <small>${depCount} npm dependencies found</small>
            </div>
        `;
    }
    
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>${project.name}</h2>
                <button class="modal-close" onclick="closeProjectAnalysis()">×</button>
            </div>
            
            <div class="modal-body">
                <div class="project-details">
                    <div class="detail-group">
                        <label>Description:</label>
                        <p>${project.description || 'No description'}</p>
                    </div>
                    
                    <div class="detail-group">
                        <label>Author:</label>
                        <p>${project.author || 'Unknown'}</p>
                    </div>
                    
                    <div class="detail-group">
                        <label>Version:</label>
                        <p>${project.version}</p>
                    </div>
                    
                    <div class="detail-group">
                        <label>Path:</label>
                        <p class="path-text">${project.path}</p>
                    </div>
                </div>
                
                <hr style="margin: 20px 0;">
                
                <div class="analysis-section">
                    <h3>📊 Project Analysis</h3>
                    
                    <div class="analysis-item">
                        <strong>Project Type:</strong>
                        <span>${project.analysis.projectType}</span>
                    </div>
                    
                    ${frameworksHTML}
                    ${technologiesHTML}
                    ${versionsHTML}
                    ${dependenciesHTML}
                </div>
            </div>
            
            <div class="modal-footer">
                <button class="btn-secondary" onclick="closeProjectAnalysis()">Close</button>
                <button class="btn-primary" onclick="editProject('${project.id}')">Edit Project</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

function closeProjectAnalysis() {
    const modal = document.querySelector('.modal-overlay');
    if (modal) {
        modal.remove();
    }
}

function editProject(projectId) {
    const project = projects.find(p => p.id === projectId);
    if (project) {
        alert(`Edit: ${project.name}\n\nPath: ${project.path}`);
        closeProjectAnalysis();
        // TODO: Open file explorer or editor at project path
    }
}

function showProjectMenu(projectId) {
    const actions = confirm('Edit or delete this project?');
    if (!actions) {
        const deleteProject = confirm('Are you sure you want to delete this project?');
        if (deleteProject) {
            projects = projects.filter(p => p.id !== projectId);
            saveProjects();
            loadProjects();
        }
    }
}

function filterProjects(filter) {
    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    
    console.log('Filtering projects:', filter);
    // Implement filtering logic
}

// Create Project Page
function selectTemplate(template) {
    selectedTemplate = template;
    document.querySelectorAll('.template-card').forEach(card => card.classList.remove('active'));
    event.target.closest('.template-card').classList.add('active');
}

function createProject() {
    const name = document.getElementById('projectName').value.trim();
    const author = document.getElementById('projectAuthor').value.trim();
    const version = document.getElementById('projectVersion').value;
    const description = document.getElementById('projectDescription').value.trim();
    
    if (!name) {
        alert('Please enter a project name');
        return;
    }
    
    // Validate project name
    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
        alert('Project name must contain only alphanumeric characters, hyphens, and underscores');
        return;
    }
    
    // Create project object
    const project = {
        id: generateId(),
        name: name,
        author: author || 'Unknown',
        version: version,
        description: description,
        template: selectedTemplate,
        created: new Date().toISOString(),
        path: `./${name}`,
        built: false,
        importedFolder: importedFolder || null  // Include imported folder info
    };
    
    // Add to projects list
    projects.push(project);
    saveProjects();
    
    // Clear form
    document.getElementById('projectName').value = '';
    document.getElementById('projectAuthor').value = '';
    document.getElementById('projectVersion').value = '1.0.0';
    document.getElementById('projectDescription').value = '';
    document.getElementById('folderPath').value = '';
    document.getElementById('folderScanResult').style.display = 'none';
    importedFolder = null;  // Reset imported folder
    
    alert(`✓ Project "${name}" created successfully!\n\nYou can now edit the files in the project folder.`);
    goToPage('projects');
    updateStats();
}

function createExistingProject() {
    const name = document.getElementById('existingProjectName').value.trim();
    const author = document.getElementById('existingProjectAuthor').value.trim();
    const version = document.getElementById('existingProjectVersion').value;
    const description = document.getElementById('existingProjectDescription').value.trim();

    if (!existingImportedFolder) {
        alert('Please import a project folder first');
        return;
    }

    if (!name) {
        alert('Please enter a project name');
        return;
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
        alert('Project name must contain only alphanumeric characters, hyphens, and underscores');
        return;
    }

    // Show loading state
    const button = event.target;
    const originalText = button.textContent;
    button.textContent = 'Creating project...';
    button.disabled = true;

    // Call backend API to create project
    fetch('/api/create-project', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: name,
            folderPath: existingImportedFolder.folderPath,
            author: author || 'Unknown',
            version: version,
            description: description
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Clear form
            document.getElementById('existingProjectName').value = '';
            document.getElementById('existingProjectAuthor').value = '';
            document.getElementById('existingProjectVersion').value = '1.0.0';
            document.getElementById('existingProjectDescription').value = '';
            document.getElementById('existingFolderPath').value = '';
            document.getElementById('existingScanResult').style.display = 'none';
            existingImportedFolder = null;

            alert(`✓ Project "${name}" created successfully!\n\nProject saved to:\n${data.downloadFolder}\n\nMetadata saved to:\n${data.metadataFolder}`);
            
            // Reload projects
            loadProjects();
            updateStats();
            goToPage('projects');
        } else {
            alert(`❌ Error: ${data.error || 'Failed to create project'}`);
        }
    })
    .catch(error => {
        console.error('Error creating project:', error);
        alert(`❌ Error: ${error.message}`);
    })
    .finally(() => {
        // Restore button state
        button.textContent = originalText;
        button.disabled = false;
    });
}

function saveProjects() {
    localStorage.setItem('htmlToExeProjects', JSON.stringify(projects));
}

// Build Page
function populateBuildProject() {
    const select = document.getElementById('buildProject');
    select.innerHTML = '<option value="">Choose a project...</option>' + 
        projects.map(p => `<option value="${p.id}">${p.name} (v${p.version})</option>`).join('');
    
    select.addEventListener('change', function() {
        const projectId = this.value;
        if (projectId) {
            const project = projects.find(p => p.id === projectId);
            document.getElementById('buildName').value = project.name.replace(/\s+/g, '');
        }
    });
}

function testProject() {
    const projectId = document.getElementById('buildProject').value;
    if (!projectId) {
        alert('Please select a project to test');
        return;
    }
    
    const project = projects.find(p => p.id === projectId);
    alert(`🧪 Testing project: ${project.name}\n\nThe test window will open in a moment...`);
    // In real app, this would call the Python backend to run the project
}

function buildProject() {
    const projectId = document.getElementById('buildProject').value;
    if (!projectId) {
        alert('Please select a project to build');
        return;
    }
    
    const project = projects.find(p => p.id === projectId);
    const exeName = document.getElementById('buildName').value || project.name;
    const iconInput = document.getElementById('buildIcon');
    
    // Show progress
    document.getElementById('buildProgressSection').style.display = 'block';
    document.getElementById('buildStatus').textContent = 'Initializing build...';
    document.getElementById('buildLog').textContent = '';
    document.getElementById('progressFill').style.width = '0%';
    
    // Prepare build data
    const buildData = {
        projectName: exeName,
        projectId: projectId
    };
    
    // Handle icon file if selected (.ico or .png)
    if (iconInput.files && iconInput.files[0]) {
        const iconFile = iconInput.files[0];
        const reader = new FileReader();
        
        reader.onload = function(e) {
            // Send icon as base64 data URI
            buildData.iconData = e.target.result;
            console.log(`Icon selected: ${iconFile.name} (${iconFile.type})`);
            executeBuild(buildData);
        };
        
        reader.readAsDataURL(iconFile);
    } else {
        // No icon selected, build without icon
        executeBuild(buildData);
    }
}

function executeBuild(buildData) {
    // Call backend API to build project
    fetch('/api/build-project', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(buildData)
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById('progressFill').style.width = '100%';
        
        if (data.success) {
            document.getElementById('buildStatus').textContent = '✨ Build complete!';
            document.getElementById('buildLog').textContent += `✅ Build successful!\n\nEXE Location: ${data.exePath}\n\nYou can now run this file!`;
            
            // Mark as built
            const projectId = document.getElementById('buildProject').value;
            const project = projects.find(p => p.id === projectId);
            if (project) {
                project.built = true;
                builtCount++;
                saveProjects();
                updateStats();
            }
            
            setTimeout(() => {
                alert(`✓ Successfully built!\n\nExecutable: ${data.exeName}\n\nLocation: ${data.exePath}\n\nYou can now distribute this file to others!`);
            }, 500);
        } else {
            document.getElementById('buildStatus').textContent = '❌ Build failed!';
            document.getElementById('buildLog').textContent += `\n❌ Error: ${data.error}`;
            alert(`Build error: ${data.error}`);
        }
    })
    .catch(error => {
        console.error('Error building project:', error);
        document.getElementById('buildStatus').textContent = '❌ Build failed!';
        document.getElementById('buildLog').textContent += `\n❌ Error: ${error.message}`;
        alert(`Build error: ${error.message}`);
    });
}

function simulateBuild(project, exeName) {
    const steps = [
        { text: 'Validating project structure...', progress: 10 },
        { text: 'Copying project files...', progress: 20 },
        { text: 'Initializing PyInstaller...', progress: 30 },
        { text: 'Building executable...', progress: 60 },
        { text: 'Packaging resources...', progress: 80 },
        { text: 'Finalizing build...', progress: 90 },
        { text: '✓ Build complete!', progress: 100 },
    ];
    
    let step = 0;
    const interval = setInterval(() => {
        if (step < steps.length) {
            const current = steps[step];
            document.getElementById('buildStatus').textContent = current.text;
            
            const log = document.getElementById('buildLog');
            log.textContent += `[${new Date().toLocaleTimeString()}] ${current.text}\n`;
            log.scrollTop = log.scrollHeight;
            
            document.getElementById('progressFill').style.width = current.progress + '%';
            step++;
        } else {
            clearInterval(interval);
            
            // Mark as built
            project.built = true;
            builtCount++;
            saveProjects();
            updateStats();
            
            // Show success message
            setTimeout(() => {
                alert(`✓ Successfully built!\n\nExecutable: dist/${exeName}.exe\nSize: ~180MB\n\nYou can now distribute this file to others!`);
            }, 500);
        }
    }, 500);
}

// Settings Page
function saveSettings() {
    const settings = {
        serverPort: document.getElementById('serverPort').value,
        windowWidth: document.getElementById('windowWidth').value,
        windowHeight: document.getElementById('windowHeight').value,
        windowResizable: document.getElementById('windowResizable').checked,
        autoMinify: document.getElementById('autoMinify').checked,
        includeSourceMaps: document.getElementById('includeSourceMaps').checked
    };
    
    localStorage.setItem('htmlToExeSettings', JSON.stringify(settings));
    alert('✓ Settings saved successfully!');
}

function resetSettings() {
    if (confirm('Reset all settings to default values?')) {
        document.getElementById('serverPort').value = '8000';
        document.getElementById('windowWidth').value = '1024';
        document.getElementById('windowHeight').value = '768';
        document.getElementById('windowResizable').checked = true;
        document.getElementById('autoMinify').checked = true;
        document.getElementById('includeSourceMaps').checked = false;
        saveSettings();
    }
}

function openProjectsFolder() {
    alert('Opening projects folder...');
    // In real app, this would call the Python backend to open the folder
}

function cleanCache() {
    if (confirm('Clear all cached data? This will remove temporary files and rebuild cache on next use.')) {
        try {
            // Clear localStorage
            localStorage.clear();
            
            // Clear sessionStorage
            sessionStorage.clear();
            
            // Clear IndexedDB
            if (window.indexedDB) {
                indexedDB.databases().then(dbs => {
                    dbs.forEach(db => {
                        indexedDB.deleteDatabase(db.name);
                    });
                });
            }
            
            alert('✓ Cache cleaned successfully! The application will refresh.');
            
            // Refresh the page to rebuild cache
            setTimeout(() => {
                location.reload();
            }, 500);
        } catch (e) {
            alert('Error cleaning cache: ' + e.message);
            console.error('Cache clean error:', e);
        }
    }
}

function browsePythonProject() {
    // In a real app, this would call the backend to browse for a Python project
    alert('Select your Python project folder (must contain main.py or setup.py)');
}

function convertPythonToExe() {
    const pythonPath = document.getElementById('pythonProjectPath').value;
    
    if (!pythonPath) {
        alert('Please select a Python project first');
        return;
    }
    
    const exeName = document.getElementById('pythonExeName').value || 'MyApp';
    const hideConsole = document.getElementById('pythonHideConsole').checked;
    const singleFile = document.getElementById('pythonSingleFile').checked;
    const optimize = document.getElementById('pythonOptimize').checked;
    const iconFile = document.getElementById('pythonExeIcon').files[0];
    
    // Show progress section
    document.getElementById('pythonConvertProgress').style.display = 'block';
    
    let iconData = null;
    if (iconFile) {
        const reader = new FileReader();
        reader.onload = function(e) {
            iconData = e.target.result;
            executeConversion(pythonPath, exeName, hideConsole, singleFile, optimize, iconData);
        };
        reader.readAsDataURL(iconFile);
    } else {
        executeConversion(pythonPath, exeName, hideConsole, singleFile, optimize, null);
    }
}

function executeConversion(pythonPath, exeName, hideConsole, singleFile, optimize, iconData) {
    updatePythonConvertStatus('Preparing Python project for conversion...');
    
    const conversionData = {
        pythonPath: pythonPath,
        exeName: exeName,
        hideConsole: hideConsole,
        singleFile: singleFile,
        optimize: optimize,
        iconData: iconData
    };
    
    fetch('/api/convert-python-to-exe', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(conversionData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updatePythonConvertStatus('✓ Conversion completed successfully!');
            addPythonConvertLog('EXE created: ' + data.exePath);
            setTimeout(() => {
                alert('✓ Python to EXE conversion completed!\n\nYour executable is ready in:\n' + data.exePath);
                document.getElementById('pythonConvertProgress').style.display = 'none';
                document.getElementById('pythonProjectPath').value = '';
                document.getElementById('pythonExeName').value = 'MyApp';
            }, 1000);
        } else {
            updatePythonConvertStatus('✗ Conversion failed: ' + data.error);
            addPythonConvertLog('Error: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Conversion error:', error);
        updatePythonConvertStatus('✗ Error: ' + error.message);
        addPythonConvertLog('Error: ' + error.message);
    });
}

function updatePythonConvertStatus(message) {
    document.getElementById('pythonConvertStatus').textContent = message;
    const progress = Math.random() * 30 + 70;  // Simulate progress 70-100%
    document.getElementById('pythonProgressFill').style.width = progress + '%';
}

function addPythonConvertLog(message) {
    const logElement = document.getElementById('pythonConvertLog');
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    logEntry.textContent = '[' + new Date().toLocaleTimeString() + '] ' + message;
    logElement.appendChild(logEntry);
    logElement.scrollTop = logElement.scrollHeight;
}

function showHelp() {
    document.getElementById('helpModal').classList.add('active');
}

function closeModal(event) {
    // Close only if clicking on modal background
    if (event && event.target.id !== 'helpModal') return;
    document.getElementById('helpModal').classList.remove('active');
}

// Color Panel Functions
function loadColors() {
    const colorGrid = document.getElementById('colorGrid');
    const allColors = defaultColors.concat(customColors);
    
    if (allColors.length === 0) {
        colorGrid.innerHTML = `
            <div class="empty-colors">
                <div class="empty-icon">🎨</div>
                <h3>No colors</h3>
                <p>Add a custom color to get started</p>
            </div>
        `;
        return;
    }
    
    colorGrid.innerHTML = allColors.map((color, index) => `
        <div class="color-card" title="Click to copy hex code">
            <div class="color-sample" style="background-color: ${color.hex}" onclick="copyToClipboard('${color.hex}')">
                <span style="font-size: 12px; opacity: 0.8;">Click to copy</span>
            </div>
            <div class="color-info">
                <div class="color-name">
                    <span>${color.name}</span>
                    ${index >= defaultColors.length ? `<button class="color-delete-btn" onclick="deleteColor(${index})">✕</button>` : ''}
                </div>
                <div class="color-hex" onclick="copyToClipboard('${color.hex}')">${color.hex}</div>
                <div class="color-rgb">${color.rgb}</div>
            </div>
        </div>
    `).join('');
}

function addCustomColor() {
    const colorPicker = document.getElementById('colorPicker');
    const colorNameInput = document.getElementById('colorNameInput');
    const hexCode = colorPicker.value.toUpperCase();
    const colorName = colorNameInput.value.trim() || 'Custom Color';
    
    // Convert hex to RGB
    const r = parseInt(hexCode.slice(1, 3), 16);
    const g = parseInt(hexCode.slice(3, 5), 16);
    const b = parseInt(hexCode.slice(5, 7), 16);
    const rgb = `rgb(${r}, ${g}, ${b})`;
    
    customColors.push({
        name: colorName,
        hex: hexCode,
        rgb: rgb
    });
    
    // Reset inputs
    colorPicker.value = '#667eea';
    colorNameInput.value = '';
    document.getElementById('colorHexDisplay').textContent = '#667EEA';
    loadColors();
    saveColors();
}

function deleteColor(index) {
    const colorToDelete = defaultColors.concat(customColors)[index];
    if (confirm(`Delete "${colorToDelete.name}"?`)) {
        customColors = customColors.filter((_, i) => i !== (index - defaultColors.length));
        loadColors();
        saveColors();
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        // Show feedback
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #333;
            color: white;
            padding: 15px 20px;
            border-radius: 5px;
            z-index: 1001;
            animation: slideInRight 0.3s ease;
        `;
        notification.textContent = `✓ Copied: ${text}`;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => notification.remove(), 300);
        }, 2000);
    });
}

function saveColors() {
    localStorage.setItem('customColors', JSON.stringify(customColors));
}

function loadSavedColors() {
    const saved = localStorage.getItem('customColors');
    if (saved) {
        customColors = JSON.parse(saved);
    }
}
function generateId() {
    return 'proj_' + Math.random().toString(36).substr(2, 9);
}

// Search functionality
document.getElementById('searchInput')?.addEventListener('input', function(e) {
    const query = e.target.value.toLowerCase();
    const filtered = projects.filter(p => 
        p.name.toLowerCase().includes(query) ||
        p.description.toLowerCase().includes(query)
    );
    
    console.log('Filtered projects:', filtered);
});

// Folder Import Functions
function openFolderBrowser() {
    // Show loading state
    const folderPathInput = document.getElementById('folderPath');
    folderPathInput.value = 'Opening folder browser...';
    
    // Call API to open folder browser dialog
    fetch('/api/browse-folder', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.folderPath) {
            // Scan the selected folder
            scanSelectedFolder(data.folderPath);
        } else if (data.cancelled) {
            folderPathInput.value = '';
        } else {
            alert(data.error || 'Failed to open folder browser');
            folderPathInput.value = '';
        }
    })
    .catch(error => {
        console.error('Error opening folder browser:', error);
        alert('Error opening folder browser: ' + error.message);
        folderPathInput.value = '';
    });
}

function openExistingFolderBrowser() {
    const folderPathInput = document.getElementById('existingFolderPath');
    folderPathInput.value = 'Opening folder browser...';

    fetch('/api/browse-folder', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.folderPath) {
            scanExistingFolder(data.folderPath);
        } else if (data.cancelled) {
            folderPathInput.value = '';
        } else {
            alert(data.error || 'Failed to open folder browser');
            folderPathInput.value = '';
        }
    })
    .catch(error => {
        console.error('Error opening folder browser:', error);
        alert('Error opening folder browser: ' + error.message);
        folderPathInput.value = '';
    });
}

// Fallback: Manual folder path input
function scanSelectedFolder(folderPath) {
    // Show loading state
    const folderPathInput = document.getElementById('folderPath');
    const scanResult = document.getElementById('folderScanResult');
    
    folderPathInput.value = 'Scanning...';
    
    // Call API to scan folder
    fetch('/api/scan-folder', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ folderPath: folderPath })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            importedFolder = data;
            folderPathInput.value = data.folderPath;
            
            // Update project name and description
            const projectNameInput = document.getElementById('projectName');
            if (projectNameInput && projectNameInput.value === '') {
                projectNameInput.value = data.folderName;
            }
            
            // Show scan result
            document.getElementById('foundFileName').textContent = data.entryFile || 'index.html not found';
            document.getElementById('foundFileCount').textContent = 
                `Found ${data.totalFiles} files (${data.summary.htmlCount} HTML, ${data.summary.cssCount} CSS, ${data.summary.jsCount} JS)`;
            
            // Display analysis results if available
            if (data.analysis) {
                displayProjectAnalysis(data.analysis);
            }
            
            scanResult.style.display = 'block';
        } else {
            alert(data.error || 'Failed to scan folder');
            folderPathInput.value = '';
            scanResult.style.display = 'none';
        }
    })
    .catch(error => {
        console.error('Error scanning folder:', error);
        alert('Error scanning folder: ' + error.message);
        folderPathInput.value = '';
        scanResult.style.display = 'none';
    });
}

function scanExistingFolder(folderPath) {
    const folderPathInput = document.getElementById('existingFolderPath');
    const scanResult = document.getElementById('existingScanResult');

    folderPathInput.value = 'Scanning...';

    fetch('/api/scan-folder', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ folderPath: folderPath })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            existingImportedFolder = data;
            folderPathInput.value = data.folderPath;

            const projectNameInput = document.getElementById('existingProjectName');
            if (projectNameInput && projectNameInput.value === '') {
                projectNameInput.value = data.folderName;
            }

            document.getElementById('existingFoundFileName').textContent = data.entryFile || 'index.html not found';
            document.getElementById('existingFoundFileCount').textContent =
                `Found ${data.totalFiles} files (${data.summary.htmlCount} HTML, ${data.summary.cssCount} CSS, ${data.summary.jsCount} JS)`;

            if (data.analysis) {
                displayExistingProjectAnalysis(data.analysis);
            }

            scanResult.style.display = 'block';
        } else {
            alert(data.error || 'Failed to scan folder');
            folderPathInput.value = '';
            scanResult.style.display = 'none';
        }
    })
    .catch(error => {
        console.error('Error scanning folder:', error);
        alert('Error scanning folder: ' + error.message);
        folderPathInput.value = '';
        scanResult.style.display = 'none';
    });
}

// Display project analysis results
function displayProjectAnalysis(analysis) {
    // Display project type
    const projectTypeElement = document.getElementById('projectTypeAnalysis');
    if (projectTypeElement) {
        projectTypeElement.textContent = analysis.projectType || 'Unknown';
    }
    
    // Display frameworks
    if (analysis.frameworks && analysis.frameworks.length > 0) {
        const frameworkSection = document.getElementById('frameworkSection');
        const frameworksList = document.getElementById('frameworksList');
        frameworksList.innerHTML = analysis.frameworks.map(fw => 
            `<span class="tag tag-framework">${fw}</span>`
        ).join('');
        frameworkSection.style.display = 'block';
    }
    
    // Display technologies
    if (analysis.technologies && analysis.technologies.length > 0) {
        const technologiesSection = document.getElementById('technologiesSection');
        const technologiesList = document.getElementById('technologiesList');
        technologiesList.innerHTML = analysis.technologies.map(tech => 
            `<span class="tag tag-tech">${tech}</span>`
        ).join('');
        technologiesSection.style.display = 'block';
    }
    
    // Display versions
    if (analysis.versions && Object.keys(analysis.versions).length > 0) {
        const versionsSection = document.getElementById('versionsSection');
        const versionsList = document.getElementById('versionsList');
        let versionsHTML = '';
        for (const [name, version] of Object.entries(analysis.versions)) {
            versionsHTML += `<div class="version-item"><span class="version-name">${name}:</span> <span class="version-value">${version}</span></div>`;
        }
        versionsList.innerHTML = versionsHTML;
        versionsSection.style.display = 'block';
    }
    
    // Display dependencies count
    if (analysis.dependencies && Object.keys(analysis.dependencies).length > 0) {
        const dependenciesSection = document.getElementById('dependenciesSection');
        const dependenciesCount = document.getElementById('dependenciesCount');
        const depCount = Object.keys(analysis.dependencies).length;
        dependenciesCount.textContent = `Found ${depCount} npm dependencies`;
        dependenciesSection.style.display = 'block';
    }
}

function displayExistingProjectAnalysis(analysis) {
    const projectTypeElement = document.getElementById('existingProjectTypeAnalysis');
    if (projectTypeElement) {
        projectTypeElement.textContent = analysis.projectType || 'Unknown';
    }

    if (analysis.frameworks && analysis.frameworks.length > 0) {
        const frameworkSection = document.getElementById('existingFrameworkSection');
        const frameworksList = document.getElementById('existingFrameworksList');
        frameworksList.innerHTML = analysis.frameworks.map(fw =>
            `<span class="tag tag-framework">${fw}</span>`
        ).join('');
        frameworkSection.style.display = 'block';
    }

    if (analysis.technologies && analysis.technologies.length > 0) {
        const technologiesSection = document.getElementById('existingTechnologiesSection');
        const technologiesList = document.getElementById('existingTechnologiesList');
        technologiesList.innerHTML = analysis.technologies.map(tech =>
            `<span class="tag tag-tech">${tech}</span>`
        ).join('');
        technologiesSection.style.display = 'block';
    }

    if (analysis.versions && Object.keys(analysis.versions).length > 0) {
        const versionsSection = document.getElementById('existingVersionsSection');
        const versionsList = document.getElementById('existingVersionsList');
        let versionsHTML = '';
        for (const [name, version] of Object.entries(analysis.versions)) {
            versionsHTML += `<div class="version-item"><span class="version-name">${name}:</span> <span class="version-value">${version}</span></div>`;
        }
        versionsList.innerHTML = versionsHTML;
        versionsSection.style.display = 'block';
    }

    if (analysis.dependencies && Object.keys(analysis.dependencies).length > 0) {
        const dependenciesSection = document.getElementById('existingDependenciesSection');
        const dependenciesCount = document.getElementById('existingDependenciesCount');
        const depCount = Object.keys(analysis.dependencies).length;
        dependenciesCount.textContent = `Found ${depCount} npm dependencies`;
        dependenciesSection.style.display = 'block';
    }
}


