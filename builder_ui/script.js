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

// ============ Toast Notification System ============
function showToast(message, type = 'info') {
    const icons = {
        success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
        error:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
        warning: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        info:    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
    };
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span>${message}</span>`;
    container.appendChild(toast);

    const remove = () => {
        toast.classList.add('removing');
        toast.addEventListener('animationend', () => toast.remove(), { once: true });
    };
    toast.addEventListener('click', remove);
    setTimeout(remove, type === 'error' ? 6000 : 3500);
}

// ============ Custom Confirm Dialog ============
function showConfirm(message, onConfirm, onCancel, title = 'Confirm') {
    const modal = document.getElementById('confirmModal');
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmMessage').textContent = message;
    modal.style.display = 'flex';

    const okBtn = document.getElementById('confirmOkBtn');
    const cancelBtn = document.getElementById('confirmCancelBtn');

    const close = () => { modal.style.display = 'none'; };
    const handleOk = () => { close(); if (onConfirm) onConfirm(); };
    const handleCancel = () => { close(); if (onCancel) onCancel(); };

    // Remove previous listeners by replacing nodes
    const newOk = okBtn.cloneNode(true);
    const newCancel = cancelBtn.cloneNode(true);
    okBtn.parentNode.replaceChild(newOk, okBtn);
    cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);
    newOk.addEventListener('click', handleOk);
    newCancel.addEventListener('click', handleCancel);
    modal.addEventListener('click', (e) => { if (e.target === modal) handleCancel(); }, { once: true });
}

// ============ Open Output Folder ============
let lastBuildOutputPath = '';
let lastPythonOutputPath = '';

function openOutputFolder(type) {
    const path = type === 'python' ? lastPythonOutputPath : lastBuildOutputPath;
    if (!path) { showToast('No output folder path available', 'warning'); return; }

    fetch('/api/open-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folderPath: path })
    })
    .then(r => r.json())
    .then(data => { if (!data.success) showToast('Could not open folder: ' + (data.error || ''), 'error'); })
    .catch(() => showToast('Could not open folder', 'error'));
}

// ============ Build Steps Animation ============
const BUILD_STEPS = [
    'Validating project structure...',
    'Copying project files...',
    'Initializing PyInstaller...',
    'Compiling executable...',
    'Packaging resources...',
    'Finalizing build...'
];

let buildStepInterval = null;
let currentBuildStep = 0;

function startBuildStepsAnimation(stepsContainerId, progressFillId) {
    const container = document.getElementById(stepsContainerId);
    if (!container) return;
    currentBuildStep = 0;
    container.innerHTML = BUILD_STEPS.map((s, i) =>
        `<div class="build-step" id="${stepsContainerId}-step-${i}"><span class="build-step-dot"></span>${s}</div>`
    ).join('');

    buildStepInterval = setInterval(() => {
        if (currentBuildStep < BUILD_STEPS.length) {
            if (currentBuildStep > 0) {
                const prev = document.getElementById(`${stepsContainerId}-step-${currentBuildStep - 1}`);
                if (prev) { prev.classList.remove('active'); prev.classList.add('done'); }
            }
            const curr = document.getElementById(`${stepsContainerId}-step-${currentBuildStep}`);
            if (curr) curr.classList.add('active');
            const fill = document.getElementById(progressFillId);
            if (fill) fill.style.width = Math.round(((currentBuildStep + 1) / BUILD_STEPS.length) * 85) + '%';
            currentBuildStep++;
        }
    }, 1800);
}

function stopBuildStepsAnimation(stepsContainerId, progressFillId, success) {
    clearInterval(buildStepInterval);
    buildStepInterval = null;
    // Mark remaining steps
    for (let i = 0; i < BUILD_STEPS.length; i++) {
        const el = document.getElementById(`${stepsContainerId}-step-${i}`);
        if (el) { el.classList.remove('active'); if (success) el.classList.add('done'); }
    }
    const fill = document.getElementById(progressFillId);
    if (fill) fill.style.width = '100%';
}

// ============ Icon Preview ============
function setupIconPreview(inputId, previewId) {
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    if (!input || !preview) return;
    input.addEventListener('change', function() {
        if (this.files && this.files[0]) {
            const reader = new FileReader();
            reader.onload = (e) => {
                preview.src = e.target.result;
                preview.style.display = 'block';
            };
            reader.readAsDataURL(this.files[0]);
        } else {
            preview.style.display = 'none';
        }
    });
}

// ============ End Helpers ============


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

    // Load built count
    const storedBuilt = localStorage.getItem('htmlToExeBuiltCount');
    if (storedBuilt) {
        builtCount = parseInt(storedBuilt, 10) || 0;
    }
    
    // Set up navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function() {
            const page = this.getAttribute('data-page');
            goToPage(page);
        });
    });

    // Setup icon previews
    setupIconPreview('buildIcon', 'buildIconPreview');
    setupIconPreview('pythonExeIcon', 'pythonIconPreview');

    // Fetch real Python version for dashboard
    fetch('/api/system-info')
        .then(r => r.json())
        .then(data => {
            const el = document.getElementById('pythonVersion');
            if (el && data.python_version) el.textContent = data.python_version;
        })
        .catch(() => {});
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
                updateStats();
                renderProjectsGrid('all', '');
            } else {
                projects = [];
                updateStats();
                projectsList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></div>
                        <h3>No projects yet</h3>
                        <p>Create your first project to get started</p>
                        <button class="btn-primary" onclick="goToPage('create')">Create Project</button>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error loading projects:', error);
            projects = [];
            updateStats();
            projectsList.innerHTML = `
                <div class="empty-state error">
                    <div class="empty-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></div>
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
                    <h3>Project Analysis</h3>
                    
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
        closeProjectAnalysis();
        goToPage('build');
        // Pre-select project in build dropdown
        setTimeout(() => {
            const select = document.getElementById('buildProject');
            if (select) {
                select.value = projectId;
                select.dispatchEvent(new Event('change'));
            }
        }, 150);
    }
}

function showProjectMenu(projectId) {
    // Remove any existing dropdown
    const existing = document.querySelector('.project-menu-dropdown');
    if (existing) { existing.remove(); return; }

    const menuBtn = document.querySelector(`[onclick*="showProjectMenu('${projectId}')"]`);
    if (!menuBtn) return;

    const dropdown = document.createElement('div');
    dropdown.className = 'project-menu-dropdown';
    dropdown.innerHTML = `
        <button onclick="editProjectFromMenu('${projectId}')"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>Build</button>
        <button onclick="viewProjectDetails('${projectId}')"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>Details</button>
        <button class="danger" onclick="deleteProjectFromMenu('${projectId}')"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>Delete</button>
    `;
    menuBtn.parentElement.appendChild(dropdown);

    // Close on outside click
    setTimeout(() => {
        document.addEventListener('click', function handler(e) {
            if (!dropdown.contains(e.target)) {
                dropdown.remove();
                document.removeEventListener('click', handler);
            }
        });
    }, 10);
}

function editProjectFromMenu(projectId) {
    document.querySelector('.project-menu-dropdown')?.remove();
    goToPage('build');
    setTimeout(() => {
        const select = document.getElementById('buildProject');
        if (select) {
            select.value = projectId;
            select.dispatchEvent(new Event('change'));
        }
    }, 150);
}

function viewProjectDetails(projectId) {
    document.querySelector('.project-menu-dropdown')?.remove();
    const project = projects.find(p => p.id === projectId);
    if (project) showProjectAnalysis(project);
}

function deleteProjectFromMenu(projectId) {
    document.querySelector('.project-menu-dropdown')?.remove();
    const project = projects.find(p => p.id === projectId);
    if (!project) return;
    showConfirm(
        `Delete "${project.name}"? This will remove the project and its files from disk.`,
        () => {
            fetch('/api/delete-project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ projectId: projectId })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showToast(`Project "${project.name}" deleted`, 'success');
                    loadProjects();
                    updateStats();
                } else {
                    showToast('Delete failed: ' + (data.error || 'Unknown error'), 'error');
                }
            })
            .catch(() => showToast('Failed to delete project', 'error'));
        },
        null,
        'Delete Project'
    );
}

function filterProjects(filter) {
    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    renderProjectsGrid(filter, document.getElementById('projectSearch')?.value || '');
}

function searchProjects(query) {
    const activeFilter = document.querySelector('.filter-btn.active');
    const filter = activeFilter ? activeFilter.textContent.toLowerCase().trim() : 'all';
    renderProjectsGrid(filter, query);
}

function renderProjectsGrid(filter, searchQuery) {
    const projectsList = document.getElementById('projectsList');
    const now = new Date();
    const sevenDaysAgo = new Date(now - 7 * 24 * 60 * 60 * 1000);
    const q = (searchQuery || '').toLowerCase();

    let filtered = projects.filter(p => {
        if (filter === 'recent') return new Date(p.created) >= sevenDaysAgo;
        if (filter === 'built') return p.built === true;
        return true;
    });

    if (q) {
        filtered = filtered.filter(p =>
            p.name.toLowerCase().includes(q) ||
            (p.description || '').toLowerCase().includes(q) ||
            (p.analysis?.projectType || '').toLowerCase().includes(q)
        );
    }

    if (filtered.length === 0) {
        projectsList.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-4 0v2"/><line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/></svg></div>
                <h3>${q ? 'No matching projects' : 'No projects yet'}</h3>
                <p>${q ? `No results for "${q}"` : 'Create your first project to get started'}</p>
                ${!q ? '<button class="btn-primary" onclick="goToPage(\'create\')">Create Project</button>' : ''}
            </div>
        `;
        return;
    }

    projectsList.innerHTML = filtered.map(project => `
        <div class="project-card" onclick="selectProject('${project.id}')">
            <div class="project-card-header">
                <div class="project-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-4 0v2"/></svg></div>
                <button class="project-menu" onclick="event.stopPropagation(); showProjectMenu('${project.id}')">&#8942;</button>
            </div>
            <h3>${project.name}${project.built ? '<span class="project-built-badge">✓ Built</span>' : ''}</h3>
            <p>${project.description || 'No description'}</p>
            <div class="project-tag">${project.analysis?.projectType || 'Unknown'}</div>
            <div class="project-stats">
                <span>v${project.version}</span>
                <span>${new Date(project.created).toLocaleDateString()}</span>
            </div>
        </div>
    `).join('');
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
        showToast('Please enter a project name', 'warning');
        return;
    }
    
    // Validate project name
    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
        showToast('Project name must contain only alphanumeric characters, hyphens, and underscores', 'warning');
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
    
    showToast(`Project "${name}" created successfully!`, 'success');
    goToPage('projects');
    updateStats();
}

function createExistingProject() {
    const name = document.getElementById('existingProjectName').value.trim();
    const author = document.getElementById('existingProjectAuthor').value.trim();
    const version = document.getElementById('existingProjectVersion').value;
    const description = document.getElementById('existingProjectDescription').value.trim();

    if (!existingImportedFolder) {
        showToast('Please import a project folder first', 'warning');
        return;
    }

    if (!name) {
        showToast('Please enter a project name', 'warning');
        return;
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
        showToast('Project name must contain only alphanumeric characters, hyphens, and underscores', 'warning');
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

            showToast(`Project "${name}" created successfully!`, 'success');
            
            // Reload projects
            loadProjects();
            updateStats();
            goToPage('projects');
        } else {
            showToast(`Error: ${data.error || 'Failed to create project'}`, 'error');
        }
    })
    .catch(error => {
        console.error('Error creating project:', error);
        showToast(`Error: ${error.message}`, 'error');
    })
    .finally(() => {
        // Restore button state
        button.textContent = originalText;
        button.disabled = false;
    });
}

function saveProjects() {
    localStorage.setItem('htmlToExeProjects', JSON.stringify(projects));
    localStorage.setItem('htmlToExeBuiltCount', String(builtCount));
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
        showToast('Please select a project to test', 'warning');
        return;
    }
    const project = projects.find(p => p.id === projectId);
    showToast(`Test mode is not yet available for "${project.name}"`, 'info');
}

function buildProject() {
    const projectId = document.getElementById('buildProject').value;
    if (!projectId) {
        showToast('Please select a project to build', 'warning');
        return;
    }
    
    const project = projects.find(p => p.id === projectId);
    const exeName = document.getElementById('buildName').value || project.name;
    const iconInput = document.getElementById('buildIcon');
    
    // Show loading overlay
    const loadingOverlay = document.getElementById('loadingOverlay');
    document.getElementById('loadingTitle').textContent = `Building ${exeName}...`;
    document.getElementById('loadingMessage').textContent = 'Converting HTML/CSS/JavaScript to EXE. This may take a few minutes.';
    loadingOverlay.style.display = 'flex';
    loadingOverlay.classList.remove('hidden');
    
    // Show progress
    document.getElementById('buildProgressSection').style.display = 'block';
    document.getElementById('buildStatus').textContent = 'Initializing build...';
    document.getElementById('buildLog').textContent = '';
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('openBuildOutputBtn').style.display = 'none';
    startBuildStepsAnimation('buildSteps', 'progressFill');
    
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
    .then(response => {
        // Always parse JSON, regardless of status code
        return response.json().then(data => {
            return { status: response.status, data: data };
        });
    })
    .then(({ status, data }) => {
        stopBuildStepsAnimation('buildSteps', 'progressFill', data.success);
        
        if (data.success) {
            document.getElementById('buildStatus').textContent = '✨ Build complete!';
            document.getElementById('buildLog').textContent += `✅ Build successful!\n\nEXE Location: ${data.exePath}\n\nYou can now run this file!`;
            
            // Show open output button
            const outBtn = document.getElementById('openBuildOutputBtn');
            if (outBtn && data.exePath) {
                lastBuildOutputPath = data.exePath.substring(0, data.exePath.lastIndexOf('\\')) || data.exePath;
                outBtn.style.display = 'inline-flex';
            }

            // Mark as built
            const projectId = document.getElementById('buildProject').value;
            const project = projects.find(p => p.id === projectId);
            if (project) {
                project.built = true;
                builtCount++;
                saveProjects();
                updateStats();
            }
            
            // Hide loading overlay
            const loadingOverlay = document.getElementById('loadingOverlay');
            loadingOverlay.classList.add('hidden');
            setTimeout(() => {
                loadingOverlay.style.display = 'none';
                showToast(`Build complete! "${data.exeName}" saved to Downloads`, 'success');
            }, 300);
        } else {
            document.getElementById('buildStatus').textContent = '❌ Build failed!';
            document.getElementById('buildLog').textContent += `\n❌ Error: ${data.error}`;
            
            // Hide loading overlay
            const loadingOverlay = document.getElementById('loadingOverlay');
            loadingOverlay.classList.add('hidden');
            setTimeout(() => {
                loadingOverlay.style.display = 'none';
                showToast(`Build failed: ${data.error}`, 'error');
            }, 300);
        }
    })
    .catch(error => {
        stopBuildStepsAnimation('buildSteps', 'progressFill', false);
        console.error('Error building project:', error);
        document.getElementById('buildStatus').textContent = '❌ Build failed!';
        document.getElementById('buildLog').textContent += `\n❌ Error: ${error.message}`;
        
        // Hide loading overlay
        const loadingOverlay = document.getElementById('loadingOverlay');
        loadingOverlay.classList.add('hidden');
        setTimeout(() => {
            loadingOverlay.style.display = 'none';
            showToast(`Build error: ${error.message}`, 'error');
        }, 300);
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
                showToast(`Build complete! dist/${exeName}.exe is ready`, 'success');
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
    showToast('Settings saved successfully!', 'success');
}

function resetSettings() {
    showConfirm('Reset all settings to default values?', () => {
        document.getElementById('serverPort').value = '8000';
        document.getElementById('windowWidth').value = '1024';
        document.getElementById('windowHeight').value = '768';
        document.getElementById('windowResizable').checked = true;
        document.getElementById('autoMinify').checked = true;
        document.getElementById('includeSourceMaps').checked = false;
        saveSettings();
        showToast('Settings reset to defaults', 'info');
    }, null, 'Reset Settings');
}

function openProjectsFolder() {
    const user = 'Documents/HTML2EXE';
    fetch('/api/open-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folderPath: 'Documents\\HTML2EXE', relative: true })
    })
    .then(r => r.json())
    .then(data => {
        if (!data.success) showToast('Could not open folder: ' + (data.error || ''), 'error');
    })
    .catch(() => showToast('Could not open projects folder', 'error'));
}

function cleanCache() {
    showConfirm('Clear all cached data? This will remove temporary files and refresh the app.', () => {
        try {
            localStorage.clear();
            sessionStorage.clear();
            if (window.indexedDB) {
                indexedDB.databases().then(dbs => {
                    dbs.forEach(db => indexedDB.deleteDatabase(db.name));
                });
            }
            showToast('Cache cleared. Refreshing...', 'success');
            setTimeout(() => location.reload(), 1200);
        } catch (e) {
            showToast('Error clearing cache: ' + e.message, 'error');
        }
    }, null, 'Clear Cache');
}

function browsePythonProject() {
    // Show loading state
    const pythonPathInput = document.getElementById('pythonProjectPath');
    pythonPathInput.value = 'Opening folder browser...';
    
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
            // Set the selected path
            pythonPathInput.value = data.folderPath;
            
            // Show project info
            document.getElementById('pythonProjectInfo').style.display = 'block';
            document.getElementById('pythonFileName').textContent = data.folderPath.split('\\').pop() || 'Python Project';
            document.getElementById('pythonFileInfo').textContent = 'Python project folder selected';
        } else if (data.cancelled) {
            pythonPathInput.value = '';
            document.getElementById('pythonProjectInfo').style.display = 'none';
        } else {
            showToast(data.error || 'Failed to open folder browser', 'error');
            pythonPathInput.value = '';
            document.getElementById('pythonProjectInfo').style.display = 'none';
        }
    })
    .catch(error => {
        console.error('Error opening folder browser:', error);
        showToast('Error opening folder browser: ' + error.message, 'error');
        pythonPathInput.value = '';
        document.getElementById('pythonProjectInfo').style.display = 'none';
    });
}

function convertPythonToExe() {
    const pythonPath = document.getElementById('pythonProjectPath').value;
    
    if (!pythonPath) {
        showToast('Please select a Python project first', 'warning');
        return;
    }
    
    const exeName = document.getElementById('pythonExeName').value || 'MyApp';
    const hideConsole = document.getElementById('pythonHideConsole').checked;
    const singleFile = document.getElementById('pythonSingleFile').checked;
    const optimize = document.getElementById('pythonOptimize').checked;
    const iconFile = document.getElementById('pythonExeIcon').files[0];
    
    // Show loading overlay
    const loadingOverlay = document.getElementById('loadingOverlay');
    document.getElementById('loadingTitle').textContent = `Converting ${exeName}...`;
    document.getElementById('loadingMessage').textContent = 'Converting Python project to EXE. This may take several minutes depending on your project size.';
    loadingOverlay.style.display = 'flex';
    loadingOverlay.classList.remove('hidden');
    
    // Show progress section
    document.getElementById('pythonConvertProgress').style.display = 'block';
    document.getElementById('openPythonOutputBtn').style.display = 'none';
    startBuildStepsAnimation('pythonBuildSteps', 'pythonProgressFill');
    
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
    updatePythonConvertStatus('Analyzing Python project...');
    
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
    .then(response => {
        // Always parse JSON, regardless of status code
        return response.json().then(data => {
            return { status: response.status, data: data };
        });
    })
    .then(({ status, data }) => {
        // Check if conversion was successful
        if (data.success) {
            updatePythonConvertStatus('✓ Python to EXE conversion completed!');
            addPythonConvertLog(`✅ Build successful!`);
            addPythonConvertLog(`EXE Location: ${data.exePath}`);
            addPythonConvertLog(`File Size: ${data.size}`);
            
            stopBuildStepsAnimation('pythonBuildSteps', 'pythonProgressFill', true);

            // Show open output button
            const outBtn = document.getElementById('openPythonOutputBtn');
            if (outBtn && data.exePath) {
                lastPythonOutputPath = data.exePath.substring(0, data.exePath.lastIndexOf('\\')) || data.exePath;
                outBtn.style.display = 'inline-flex';
            }
            
            // Hide loading overlay
            const loadingOverlay = document.getElementById('loadingOverlay');
            loadingOverlay.classList.add('hidden');
            setTimeout(() => {
                loadingOverlay.style.display = 'none';
                showToast(`Conversion complete! "${data.exeName}" (${data.size}) saved to Downloads`, 'success');
                
                // Reset form
                document.getElementById('pythonProjectPath').value = '';
                document.getElementById('pythonExeName').value = 'MyApp';
                document.getElementById('pythonHideConsole').checked = true;
                document.getElementById('pythonSingleFile').checked = true;
                document.getElementById('pythonOptimize').checked = false;
                document.getElementById('pythonExeIcon').value = '';
                const prev = document.getElementById('pythonIconPreview');
                if (prev) prev.style.display = 'none';
            }, 300);
        } else {
            // Conversion failed
            updatePythonConvertStatus('✗ Conversion Failed');
            addPythonConvertLog('Status: Error');
            addPythonConvertLog('Message: ' + (data.error || 'Unknown error'));
            stopBuildStepsAnimation('pythonBuildSteps', 'pythonProgressFill', false);
            
            // Hide loading overlay
            const loadingOverlay = document.getElementById('loadingOverlay');
            loadingOverlay.classList.add('hidden');
            setTimeout(() => {
                loadingOverlay.style.display = 'none';
                showToast('Conversion failed: ' + (data.error || 'Unknown error'), 'error');
                document.getElementById('pythonConvertProgress').style.display = 'none';
            }, 300);
        }
    })
    .catch(error => {
        console.error('Conversion error:', error);
        stopBuildStepsAnimation('pythonBuildSteps', 'pythonProgressFill', false);
        updatePythonConvertStatus('✗ Error: ' + error.message);
        addPythonConvertLog('Error: ' + error.message);
        
        // Hide loading overlay
        const loadingOverlay = document.getElementById('loadingOverlay');
        loadingOverlay.classList.add('hidden');
        setTimeout(() => {
            loadingOverlay.style.display = 'none';
            showToast('Conversion error: ' + error.message, 'error');
            document.getElementById('pythonConvertProgress').style.display = 'none';
        }, 300);
    });
}

function updatePythonConvertStatus(message) {
    document.getElementById('pythonConvertStatus').textContent = message;
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
                <div class="empty-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r="2.5"/><circle cx="6.5" cy="17.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg></div>
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
                    ${index >= defaultColors.length ? `<button class="color-delete-btn" onclick="deleteColor(${index})"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>` : ''}
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
    showConfirm(`Delete "${colorToDelete.name}"?`, () => {
        customColors = customColors.filter((_, i) => i !== (index - defaultColors.length));
        loadColors();
        saveColors();
    }, null, 'Delete Color');
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
// Removed - search feature no longer available

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
            showToast(data.error || 'Failed to open folder browser', 'error');
            folderPathInput.value = '';
        }
    })
    .catch(error => {
        console.error('Error opening folder browser:', error);
        showToast('Error opening folder browser: ' + error.message, 'error');
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
            showToast(data.error || 'Failed to open folder browser', 'error');
            folderPathInput.value = '';
        }
    })
    .catch(error => {
        console.error('Error opening folder browser:', error);
        showToast('Error opening folder browser: ' + error.message, 'error');
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
            showToast(data.error || 'Failed to scan folder', 'error');
            folderPathInput.value = '';
            scanResult.style.display = 'none';
        }
    })
    .catch(error => {
        console.error('Error scanning folder:', error);
        showToast('Error scanning folder: ' + error.message, 'error');
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
            showToast(data.error || 'Failed to scan folder', 'error');
            folderPathInput.value = '';
            scanResult.style.display = 'none';
        }
    })
    .catch(error => {
        console.error('Error scanning folder:', error);
        showToast('Error scanning folder: ' + error.message, 'error');
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


