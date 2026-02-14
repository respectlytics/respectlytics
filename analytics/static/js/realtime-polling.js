/**
 * Respectlytics Real-Time Polling Module
 * Handles auto-refresh functionality for analytics pages
 */

class RealTimePoller {
    constructor(appKey, options = {}) {
        this.appKey = appKey;
        this.lastPollTimestamp = null;
        this.pollInterval = null;
        this.isPaused = false;
        this.failureCount = 0;
        this.maxFailures = 3;
        
        // Time range configuration (in minutes)
        this.timeRanges = {
            30: { minutes: 30, interval: 300000, label: 'Last 30 minutes' },    // 5 min (reduced from 1 min to lower server load)
            60: { minutes: 60, interval: 300000, label: 'Last hour' },          // 5 min
            360: { minutes: 360, interval: 300000, label: 'Last 6 hours' },     // 5 min
            1440: { minutes: 1440, interval: 600000, label: 'Last 24 hours' },  // 10 min
        };
        
        // Current selection
        this.currentRange = options.defaultRange || 1440;
        
        // Callbacks
        this.onNewData = options.onNewData || (() => {});
        this.onError = options.onError || (() => {});
        this.onStatusChange = options.onStatusChange || (() => {});
        
        // Load saved preferences
        this.loadPreferences();
    }
    
    /**
     * Start polling with the current time range
     */
    start() {
        if (this.isPaused) {
            this.isPaused = false;
        }
        
        // Clear any existing interval
        this.stop();
        
        // Initial poll
        this.poll();
        
        // Set up recurring polls
        const config = this.timeRanges[this.currentRange];
        this.pollInterval = setInterval(() => {
            if (!this.isPaused) {
                this.poll();
            }
        }, config.interval);
        
        this.onStatusChange({
            status: 'active',
            range: this.currentRange,
            interval: config.interval / 1000,
            label: config.label
        });
    }
    
    /**
     * Stop polling
     */
    stop() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }
    
    /**
     * Pause polling (keeps interval running but skips polls)
     */
    pause() {
        this.isPaused = true;
        this.onStatusChange({ status: 'paused' });
    }
    
    /**
     * Resume polling
     */
    resume() {
        this.isPaused = false;
        this.poll(); // Immediate poll on resume
        this.onStatusChange({ status: 'active' });
    }
    
    /**
     * Change time range and restart polling
     */
    setTimeRange(rangeName) {
        if (!this.timeRanges[rangeName]) {
            console.error('Invalid time range:', rangeName);
            return;
        }
        
        this.currentRange = rangeName;
        this.savePreferences();
        this.start(); // Restart with new interval
    }
    
    /**
     * Perform a single poll
     */
    async poll() {
        try {
            const config = this.timeRanges[this.currentRange];
            const url = new URL('/api/v1/events/recent-activity/', window.location.origin);
            url.searchParams.append('time_range', config.minutes);
            
            if (this.lastPollTimestamp) {
                url.searchParams.append('since', this.lastPollTimestamp);
            }
            url.searchParams.append('_', Date.now());
            
            const response = await fetch(url, {
                cache: 'no-store',
                headers: {
                    'X-App-Key': this.appKey,
                    'Cache-Control': 'no-cache'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // Reset failure count on success
            this.failureCount = 0;
            
            // Update last poll timestamp
            this.lastPollTimestamp = data.server_time;
            
            // Notify callback with new data
            this.onNewData(data);
            
            // Handle warnings
            if (data.warnings && data.warnings.length > 0) {
                data.warnings.forEach(warning => {
                    console.warn('Polling warning:', warning.message);
                    if (warning.type === 'high_traffic') {
                        this.onError({
                            type: 'warning',
                            message: warning.message,
                            suggestedRange: this.getRangeName(warning.suggested_time_range)
                        });
                    }
                });
            }
            
        } catch (error) {
            this.failureCount++;
            console.error('Polling error:', error);
            
            if (this.failureCount >= this.maxFailures) {
                this.pause();
                this.onError({
                    type: 'error',
                    message: 'Connection lost. Auto-refresh paused.',
                    canRetry: true
                });
            } else {
                this.onError({
                    type: 'error',
                    message: `Connection issue (attempt ${this.failureCount}/${this.maxFailures})`,
                    canRetry: false
                });
            }
        }
    }
    
    /**
     * Get range name from minutes
     */
    getRangeName(minutes) {
        for (const [name, config] of Object.entries(this.timeRanges)) {
            if (config.minutes === minutes) {
                return name;
            }
        }
        return null;
    }
    
    /**
     * Save preferences to localStorage
     */
    savePreferences() {
        try {
            localStorage.setItem('respectlytics_time_range', this.currentRange);
        } catch (e) {
            console.warn('Could not save preferences:', e);
        }
    }
    
    /**
     * Load preferences from localStorage
     */
    loadPreferences() {
        try {
            const saved = localStorage.getItem('respectlytics_time_range');
            if (saved && this.timeRanges[saved]) {
                this.currentRange = saved;
            }
        } catch (e) {
            console.warn('Could not load preferences:', e);
        }
    }
    
    /**
     * Get current configuration
     */
    getConfig() {
        return {
            range: this.currentRange,
            ...this.timeRanges[this.currentRange]
        };
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RealTimePoller;
}
