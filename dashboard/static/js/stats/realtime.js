/**
 * Stats Dashboard - Real-time Polling Module
 * 
 * Handles live updates, polling status, and countdown timers.
 * Dependencies: RealTimePoller class (external)
 */

// Namespace setup
window.StatsApp = window.StatsApp || {};

// ===== Real-time State =====
StatsApp.realtimePoller = null;
StatsApp.isLiveMode = true;
StatsApp.lastUpdateTime = Date.now();
StatsApp.countdownInterval = null;

/**
 * Initialize real-time polling system
 * @param {string} appKey - The app key for API calls
 */
function initializeRealtimePolling(appKey) {
    // Use 24 hour as default range for real-time polling
    const initialRange = 1440;
    
    StatsApp.realtimePoller = new RealTimePoller(appKey, {
        defaultRange: initialRange,
        onNewData: (data) => {
            // Show warning if high traffic
            if (data.warnings && data.warnings.length > 0) {
                showWarning(data.warnings[0]);
            }
            
            // Reload stats silently (no loading overlay) to prevent page flicker
            if (typeof loadStats === 'function') {
                loadStats(true);
            }
            
            // Update last updated time
            StatsApp.lastUpdateTime = Date.now();
            updateLastUpdatedText();
        },
        onError: (error) => {
            console.error('Polling error:', error);
        },
        onStatusChange: (status) => {
            updateLiveIndicator();
        }
    });
    
    // Start polling
    StatsApp.realtimePoller.start();
    
    // Update countdown every second
    startCountdown();
}

/**
 * Toggle live updates (pause/resume)
 */
function toggleLiveUpdates() {
    const { realtimePoller } = StatsApp;
    if (!realtimePoller) return;
    
    const isPaused = realtimePoller.isPaused;
    
    if (isPaused) {
        realtimePoller.resume();
        StatsApp.isLiveMode = true;
    } else {
        realtimePoller.pause();
        StatsApp.isLiveMode = false;
    }
    
    updateLiveIndicator();
}

/**
 * Update live indicator UI
 */
function updateLiveIndicator() {
    const { realtimePoller, isLiveMode } = StatsApp;
    
    // Update global filter bar elements
    const globalIndicator = document.getElementById('globalLiveIndicator');
    const globalStatusText = document.getElementById('globalLiveStatus');
    const globalPauseButton = document.getElementById('globalPauseButton');
    
    if (!realtimePoller || !isLiveMode) {
        if (globalIndicator) globalIndicator.classList.add('paused');
        if (globalStatusText) globalStatusText.textContent = 'Paused';
        if (globalPauseButton) {
            globalPauseButton.innerHTML = '▶️ Resume';
        }
        return;
    }
    
    if (realtimePoller.isPaused) {
        if (globalIndicator) globalIndicator.classList.add('paused');
        if (globalStatusText) globalStatusText.textContent = 'Paused';
        if (globalPauseButton) {
            globalPauseButton.innerHTML = '▶️ Resume';
        }
    } else {
        if (globalIndicator) globalIndicator.classList.remove('paused');
        if (globalStatusText) globalStatusText.textContent = 'Live';
        if (globalPauseButton) {
            globalPauseButton.innerHTML = '⏸️ Pause';
        }
    }
}

/**
 * Update "last updated" text
 */
function updateLastUpdatedText() {
    const { lastUpdateTime } = StatsApp;
    const globalLastUpdated = document.getElementById('globalLastUpdated');
    const now = Date.now();
    const secondsAgo = Math.floor((now - lastUpdateTime) / 1000);
    
    if (!globalLastUpdated) return;
    
    if (secondsAgo < 5) {
        globalLastUpdated.textContent = 'Updated just now';
    } else if (secondsAgo < 60) {
        globalLastUpdated.textContent = `Updated ${secondsAgo}s ago`;
    } else {
        const minutesAgo = Math.floor(secondsAgo / 60);
        globalLastUpdated.textContent = `Updated ${minutesAgo}m ago`;
    }
}

/**
 * Start countdown timer (updates the last updated text periodically)
 */
function startCountdown() {
    if (StatsApp.countdownInterval) {
        clearInterval(StatsApp.countdownInterval);
    }
    
    StatsApp.countdownInterval = setInterval(() => {
        // Update last updated text periodically
        updateLastUpdatedText();
    }, 1000);
}

// Make functions globally available
window.initializeRealtimePolling = initializeRealtimePolling;
window.toggleLiveUpdates = toggleLiveUpdates;
window.updateLiveIndicator = updateLiveIndicator;
window.updateLastUpdatedText = updateLastUpdatedText;
window.startCountdown = startCountdown;
