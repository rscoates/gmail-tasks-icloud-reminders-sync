const API_BASE = '/api';

// ============ Utilities ============

function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type}`;
    notification.style.display = 'block';
    
    setTimeout(() => {
        notification.style.display = 'none';
    }, 4000);
}

async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
    };
    
    if (body) {
        options.body = JSON.stringify(body);
    }
    
    const response = await fetch(`${API_BASE}${endpoint}`, options);
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'API request failed');
    }
    
    return response.json();
}

function formatDate(dateString) {
    if (!dateString) return '--';
    const date = new Date(dateString);
    return date.toLocaleString();
}

// ============ Status ============

async function loadStatus() {
    try {
        const status = await apiCall('/status');
        
        // Scheduler status
        const schedulerBadge = document.getElementById('scheduler-status');
        if (status.scheduler_running) {
            schedulerBadge.textContent = 'Running';
            schedulerBadge.className = 'badge badge-active';
        } else {
            schedulerBadge.textContent = 'Stopped';
            schedulerBadge.className = 'badge badge-inactive';
        }
        
        // Next sync
        document.getElementById('next-sync').textContent = formatDate(status.next_sync_at);
        
        // Google status
        const googleBadge = document.getElementById('google-status');
        if (status.google_connected) {
            googleBadge.textContent = 'Connected';
            googleBadge.className = 'badge badge-active';
            document.getElementById('google-auth-btn').textContent = 'Reconnect Google';
            loadGoogleTaskLists();
        } else {
            googleBadge.textContent = 'Not Connected';
            googleBadge.className = 'badge badge-inactive';
        }
        
        // iCloud status
        const icloudBadge = document.getElementById('icloud-status');
        if (status.icloud_connected) {
            icloudBadge.textContent = 'Connected';
            icloudBadge.className = 'badge badge-active';
            loadICloudCalendars();
        } else {
            icloudBadge.textContent = 'Not Connected';
            icloudBadge.className = 'badge badge-inactive';
        }
        
        // Last sync
        if (status.last_sync) {
            const container = document.getElementById('last-sync-container');
            container.style.display = 'block';
            
            const info = status.last_sync;
            let statusText = info.status === 'success' ? '✅ Success' : '❌ Failed';
            let details = `${statusText} - ${info.tasks_synced} tasks, ${info.reminders_synced} reminders synced`;
            
            if (info.error_message) {
                details += ` - Error: ${info.error_message}`;
            }
            
            document.getElementById('last-sync-info').textContent = 
                `${formatDate(info.started_at)} - ${details}`;
        }
        
    } catch (error) {
        console.error('Failed to load status:', error);
    }
}

// ============ Settings ============

let currentSettings = null;

async function loadSettings() {
    try {
        currentSettings = await apiCall('/settings');
        
        document.getElementById('sync-interval').value = currentSettings.sync_interval_minutes;
        document.getElementById('sync-direction').value = currentSettings.sync_direction;
        
        // Set task list if available
        if (currentSettings.gmail_task_list_id) {
            const taskListSelect = document.getElementById('google-tasklist');
            if (taskListSelect.querySelector(`option[value="${currentSettings.gmail_task_list_id}"]`)) {
                taskListSelect.value = currentSettings.gmail_task_list_id;
            }
        }
        
        // Set calendar if available
        if (currentSettings.icloud_calendar_name) {
            const calendarSelect = document.getElementById('icloud-calendar');
            if (calendarSelect.querySelector(`option[value="${currentSettings.icloud_calendar_name}"]`)) {
                calendarSelect.value = currentSettings.icloud_calendar_name;
            }
        }
        
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

async function saveSettings(event) {
    event.preventDefault();
    
    const settings = {
        sync_interval_minutes: parseInt(document.getElementById('sync-interval').value),
        sync_direction: document.getElementById('sync-direction').value,
    };
    
    // Add task list if selected
    const taskList = document.getElementById('google-tasklist').value;
    if (taskList) {
        settings.gmail_task_list_id = taskList;
    }
    
    // Add calendar if selected
    const calendar = document.getElementById('icloud-calendar').value;
    if (calendar) {
        settings.icloud_calendar_name = calendar;
    }
    
    try {
        await apiCall('/settings', 'PUT', settings);
        showNotification('Settings saved successfully!', 'success');
        loadStatus();
    } catch (error) {
        showNotification(`Failed to save settings: ${error.message}`, 'error');
    }
}

// ============ Sync Operations ============

async function triggerSync() {
    const btn = document.getElementById('sync-now-btn');
    btn.disabled = true;
    btn.textContent = '🔄 Syncing...';
    
    try {
        const result = await apiCall('/sync/trigger', 'POST');
        showNotification(result.message, result.message.includes('success') ? 'success' : 'error');
        loadStatus();
        loadSyncLogs();
    } catch (error) {
        showNotification(`Sync failed: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔄 Sync Now';
    }
}

async function startScheduler() {
    try {
        await apiCall('/scheduler/start', 'POST');
        showNotification('Scheduler started!', 'success');
        loadStatus();
    } catch (error) {
        showNotification(`Failed to start scheduler: ${error.message}`, 'error');
    }
}

async function stopScheduler() {
    try {
        await apiCall('/scheduler/stop', 'POST');
        showNotification('Scheduler stopped!', 'info');
        loadStatus();
    } catch (error) {
        showNotification(`Failed to stop scheduler: ${error.message}`, 'error');
    }
}

async function loadSyncLogs() {
    const container = document.getElementById('sync-history');
    
    try {
        const logs = await apiCall('/sync/logs?limit=10');
        
        if (logs.length === 0) {
            container.innerHTML = '<p class="loading">No sync history yet</p>';
            return;
        }
        
        container.innerHTML = logs.map(log => `
            <div class="sync-log-item ${log.status}">
                <div class="sync-log-info">
                    <span class="sync-log-time">${formatDate(log.started_at)}</span>
                    <span class="sync-log-details">
                        ${log.status === 'success' ? '✅' : '❌'} 
                        ${log.tasks_synced} tasks, ${log.reminders_synced} reminders
                        (${log.direction.replace('_', ' → ')})
                    </span>
                    ${log.error_message ? `<span class="sync-log-error">${log.error_message}</span>` : ''}
                </div>
            </div>
        `).join('');
        
    } catch (error) {
        container.innerHTML = '<p class="loading">Failed to load sync history</p>';
    }
}

// ============ Google Authentication ============

async function connectGoogle() {
    try {
        const { auth_url } = await apiCall('/auth/google/url');
        window.location.href = auth_url;
    } catch (error) {
        showNotification(`Failed to get auth URL: ${error.message}`, 'error');
    }
}

async function loadGoogleTaskLists() {
    const container = document.getElementById('google-tasklist-container');
    const select = document.getElementById('google-tasklist');
    
    try {
        const taskLists = await apiCall('/google/tasklists');
        
        select.innerHTML = taskLists.map(list => 
            `<option value="${list.id}">${list.title}</option>`
        ).join('');
        
        container.style.display = 'block';
        
        // Restore saved selection
        if (currentSettings && currentSettings.gmail_task_list_id) {
            select.value = currentSettings.gmail_task_list_id;
        }
        
    } catch (error) {
        console.error('Failed to load task lists:', error);
    }
}

async function saveTaskList() {
    const taskList = document.getElementById('google-tasklist').value;
    if (!taskList) return;
    
    try {
        const currentSettings = await apiCall('/settings');
        await apiCall('/settings', 'PUT', {
            ...currentSettings,
            gmail_task_list_id: taskList
        });
        showNotification('Task list saved!', 'success');
    } catch (error) {
        showNotification(`Failed to save task list: ${error.message}`, 'error');
    }
}

// ============ iCloud Authentication ============

async function connectICloud(event) {
    event.preventDefault();
    
    const username = document.getElementById('icloud-username').value;
    const password = document.getElementById('icloud-password').value;
    
    try {
        await apiCall('/auth/icloud', 'POST', {
            username,
            app_password: password
        });
        
        showNotification('iCloud connected successfully!', 'success');
        loadStatus();
        loadICloudCalendars();
        
    } catch (error) {
        showNotification(`Failed to connect iCloud: ${error.message}`, 'error');
    }
}

async function loadICloudCalendars() {
    const container = document.getElementById('icloud-calendar-container');
    const select = document.getElementById('icloud-calendar');
    
    try {
        const calendars = await apiCall('/icloud/calendars');
        
        select.innerHTML = calendars.map(cal => 
            `<option value="${cal.id}">${cal.name}</option>`
        ).join('');
        
        container.style.display = 'block';
        
        // Restore saved selection
        if (currentSettings && currentSettings.icloud_calendar_name) {
            select.value = currentSettings.icloud_calendar_name;
        }
        
    } catch (error) {
        console.error('Failed to load calendars:', error);
    }
}

async function saveCalendar() {
    const calendar = document.getElementById('icloud-calendar').value;
    if (!calendar) return;
    
    try {
        const currentSettings = await apiCall('/settings');
        await apiCall('/settings', 'PUT', {
            ...currentSettings,
            icloud_calendar_name: calendar
        });
        showNotification('Reminder list saved!', 'success');
    } catch (error) {
        showNotification(`Failed to save reminder list: ${error.message}`, 'error');
    }
}

// ============ Handle OAuth Callback ============

function handleOAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    
    if (code) {
        // Clear the URL
        window.history.replaceState({}, document.title, '/');
        showNotification('Google authentication successful!', 'success');
    }
    
    const error = urlParams.get('error');
    if (error) {
        window.history.replaceState({}, document.title, '/');
        showNotification(`Google authentication failed: ${error}`, 'error');
    }
}

// ============ Initialize ============

document.addEventListener('DOMContentLoaded', () => {
    handleOAuthCallback();
    loadStatus();
    loadSettings();
    loadSyncLogs();
    
    // Refresh status every 30 seconds
    setInterval(loadStatus, 30000);
});
