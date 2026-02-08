// HTML to EXE Builder - API Communication Layer
// This handles communication with the Python backend

class BuilderAPI {
    constructor(baseUrl = 'http://localhost:8000/api') {
        this.baseUrl = baseUrl;
    }
    
    async request(endpoint, options = {}) {
        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            
            if (!response.ok) {
                throw new Error(`API error: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }
    
    // Project endpoints
    async getProjects() {
        return this.request('/projects');
    }
    
    async getProject(projectId) {
        return this.request(`/projects/${projectId}`);
    }
    
    async createProject(projectData) {
        return this.request('/projects', {
            method: 'POST',
            body: JSON.stringify(projectData)
        });
    }
    
    async updateProject(projectId, projectData) {
        return this.request(`/projects/${projectId}`, {
            method: 'PUT',
            body: JSON.stringify(projectData)
        });
    }
    
    async deleteProject(projectId) {
        return this.request(`/projects/${projectId}`, {
            method: 'DELETE'
        });
    }
    
    // Build endpoints
    async buildProject(projectId, buildOptions = {}) {
        return this.request(`/build/${projectId}`, {
            method: 'POST',
            body: JSON.stringify(buildOptions)
        });
    }
    
    async testProject(projectId) {
        return this.request(`/test/${projectId}`, {
            method: 'POST'
        });
    }
    
    async getBuildStatus(buildId) {
        return this.request(`/build-status/${buildId}`);
    }
    
    // File endpoints
    async getProjectFiles(projectId) {
        return this.request(`/projects/${projectId}/files`);
    }
    
    async saveFile(projectId, filePath, content) {
        return this.request(`/projects/${projectId}/files`, {
            method: 'POST',
            body: JSON.stringify({ path: filePath, content })
        });
    }
    
    async deleteFile(projectId, filePath) {
        return this.request(`/projects/${projectId}/files`, {
            method: 'DELETE',
            body: JSON.stringify({ path: filePath })
        });
    }
    
    // Settings endpoints
    async getSettings() {
        return this.request('/settings');
    }
    
    async saveSettings(settings) {
        return this.request('/settings', {
            method: 'PUT',
            body: JSON.stringify(settings)
        });
    }
    
    // System endpoints
    async getSystemInfo() {
        return this.request('/system-info');
    }
    
    async openFolder(path) {
        return this.request('/open-folder', {
            method: 'POST',
            body: JSON.stringify({ path })
        });
    }
}

// Initialize API
const api = new BuilderAPI();

// Handle API Events
class APIEventHandler {
    constructor(api) {
        this.api = api;
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        // Set up WebSocket or polling for real-time updates
        this.pollBuildStatus();
    }
    
    pollBuildStatus() {
        setInterval(async () => {
            try {
                // Poll for any active builds
                const buildElement = document.getElementById('buildProgressSection');
                if (buildElement && buildElement.style.display !== 'none') {
                    // Update progress
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 1000);
    }
}

// Initialize event handler
const apiHandler = new APIEventHandler(api);

// WebSocket support for real-time updates
class BuilderWebSocket {
    constructor(url = 'ws://localhost:8000/ws') {
        this.url = url;
        this.ws = null;
        this.connect();
    }
    
    connect() {
        try {
            this.ws = new WebSocket(this.url);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
            };
            
            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                // Attempt to reconnect
                setTimeout(() => this.connect(), 5000);
            };
        } catch (error) {
            console.error('WebSocket connection failed:', error);
        }
    }
    
    handleMessage(data) {
        switch (data.type) {
            case 'build-progress':
                this.updateBuildProgress(data);
                break;
            case 'build-complete':
                this.handleBuildComplete(data);
                break;
            case 'build-error':
                this.handleBuildError(data);
                break;
        }
    }
    
    updateBuildProgress(data) {
        const progressFill = document.getElementById('progressFill');
        const buildStatus = document.getElementById('buildStatus');
        const buildLog = document.getElementById('buildLog');
        
        if (progressFill) progressFill.style.width = data.progress + '%';
        if (buildStatus) buildStatus.textContent = data.message;
        if (buildLog && data.log) {
            buildLog.textContent += data.log + '\n';
            buildLog.scrollTop = buildLog.scrollHeight;
        }
    }
    
    handleBuildComplete(data) {
        alert(`✓ Build complete!\n\nOutput: ${data.output_path}`);
    }
    
    handleBuildError(data) {
        alert(`✗ Build failed:\n\n${data.error}`);
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
}

// Initialize WebSocket (optional, falls back to polling)
let socket = null;
try {
    socket = new BuilderWebSocket();
} catch (error) {
    console.log('WebSocket not available, using polling instead');
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { BuilderAPI, APIEventHandler, BuilderWebSocket };
}
