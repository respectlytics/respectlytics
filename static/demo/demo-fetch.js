/**
 * Demo Fetch Interceptor
 * 
 * Intercepts all fetch() calls to API endpoints and returns
 * static demo data instead of making real network requests.
 * 
 * This allows the demo dashboard to work identically to the
 * production dashboard without requiring authentication or
 * a live backend.
 */

(function() {
    'use strict';
    
    // Store the original fetch function
    const originalFetch = window.fetch;
    
    // Demo data will be loaded and stored here
    let DEMO_DATA = null;
    
    /**
     * Load demo data from JSON file
     */
    async function loadDemoData() {
        if (DEMO_DATA) return DEMO_DATA;
        
        try {
            const response = await originalFetch('/static/demo/demo_data.json');
            DEMO_DATA = await response.json();
            window.DEMO_DATA = DEMO_DATA; // Make available globally for debugging
            console.log('[Demo] Loaded demo data successfully');
            return DEMO_DATA;
        } catch (error) {
            console.error('[Demo] Failed to load demo data:', error);
            return null;
        }
    }
    
    /**
     * Create a mock Response object
     */
    function mockResponse(data, status = 200) {
        return new Response(JSON.stringify(data), {
            status: status,
            headers: { 'Content-Type': 'application/json' }
        });
    }
    
    /**
     * Generate dynamic date labels based on current date
     */
    function generateDateLabels(count, granularity = 'day') {
        const labels = [];
        const today = new Date();
        
        for (let i = count - 1; i >= 0; i--) {
            const date = new Date(today);
            if (granularity === 'day') {
                date.setDate(date.getDate() - i);
                labels.push(date.toISOString().split('T')[0]);
            } else if (granularity === 'week') {
                date.setDate(date.getDate() - (i * 7));
                const week = getWeekNumber(date);
                labels.push(`${date.getFullYear()}-W${String(week).padStart(2, '0')}`);
            } else if (granularity === 'month') {
                date.setMonth(date.getMonth() - i);
                labels.push(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`);
            }
        }
        return labels;
    }
    
    function getWeekNumber(date) {
        const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
        const dayNum = d.getUTCDay() || 7;
        d.setUTCDate(d.getUTCDate() + 4 - dayNum);
        const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
        return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    }
    
    /**
     * Add dynamic dates to events_by_day data
     */
    function addDatesToEventsByDay(data) {
        const dates = generateDateLabels(data.length, 'day');
        return data.map((item, i) => ({
            ...item,
            date: dates[i]
        }));
    }
    
    /**
     * Add dynamic period labels to DAU data
     */
    function addPeriodsToDAU(data, granularity) {
        const periods = generateDateLabels(data.length, granularity);
        return data.map((item, i) => ({
            ...item,
            period: periods[i]
        }));
    }
    
    /**
     * Parse URL parameters
     */
    function parseParams(url) {
        try {
            const urlObj = new URL(url, window.location.origin);
            return Object.fromEntries(urlObj.searchParams.entries());
        } catch (e) {
            return {};
        }
    }
    
    /**
     * Get segment data based on segment_by parameter
     */
    function getSegmentData(segmentBy, granularity) {
        if (!DEMO_DATA) return null;
        
        switch (segmentBy) {
            case 'platform':
                return DEMO_DATA.segments_platform;
            case 'country':
                return DEMO_DATA.segments_country;
            case 'events_per_session':
                return DEMO_DATA.segments_events_per_session;
            case 'hour':
                return DEMO_DATA.segments_hour;
            default:
                return DEMO_DATA.segments_platform;
        }
    }
    
    /**
     * Override fetch to intercept API calls
     */
    window.fetch = async function(url, options = {}) {
        const urlStr = typeof url === 'string' ? url : url.toString();
        
        // Only intercept API calls
        if (!urlStr.includes('/api/v1/')) {
            return originalFetch(url, options);
        }
        
        // Ensure demo data is loaded
        if (!DEMO_DATA) {
            await loadDemoData();
        }
        
        if (!DEMO_DATA) {
            console.error('[Demo] No demo data available');
            return mockResponse({ error: 'Demo data not loaded' }, 500);
        }
        
        const params = parseParams(urlStr);
        const granularity = params.granularity || 'day';
        
        console.log('[Demo] Intercepted:', urlStr);
        
        // Route to appropriate mock data
        if (urlStr.includes('/events/summary/')) {
            const data = { ...DEMO_DATA.summary };
            data.events_by_day = addDatesToEventsByDay(data.events_by_day);
            return mockResponse(data);
        }
        
        if (urlStr.includes('/events/event-types/')) {
            return mockResponse(DEMO_DATA.event_types);
        }
        
        if (urlStr.includes('/events/recent-activity/')) {
            // Update timestamps to be recent
            const data = { ...DEMO_DATA.recent_activity };
            const now = new Date();
            data.server_time = now.toISOString();
            data.last_event_timestamp = new Date(now - 60000).toISOString();
            data.event_preview = data.event_preview.map((e, i) => ({
                ...e,
                timestamp: new Date(now - (i * 45000)).toISOString()
            }));
            return mockResponse(data);
        }
        
        if (urlStr.includes('/events/geo-summary/')) {
            return mockResponse(DEMO_DATA.geo_summary);
        }
        
        if (urlStr.includes('/events/count/')) {
            return mockResponse({
                total_events: DEMO_DATA.summary.total_events,
                date_range: { from: null, to: null }
            });
        }
        
        if (urlStr.includes('/analytics/dau/')) {
            let dauData;
            if (granularity === 'week') {
                dauData = { ...DEMO_DATA.dau_weekly };
            } else if (granularity === 'month') {
                dauData = { ...DEMO_DATA.dau_monthly };
            } else {
                dauData = { ...DEMO_DATA.dau };
            }
            dauData.active_sessions = addPeriodsToDAU(dauData.active_sessions, granularity);
            dauData.granularity = granularity;
            return mockResponse(dauData);
        }
        
        if (urlStr.includes('/analytics/globe-stats/')) {
            return mockResponse(DEMO_DATA.globe_stats);
        }
        
        if (urlStr.includes('/analytics/time-to-conversion/')) {
            return mockResponse(DEMO_DATA.time_to_conversion);
        }
        
        if (urlStr.includes('/analytics/conversion-paths/')) {
            return mockResponse(DEMO_DATA.conversion_paths);
        }
        
        if (urlStr.includes('/analytics/drop-off/')) {
            return mockResponse(DEMO_DATA.drop_off);
        }
        
        if (urlStr.includes('/analytics/event-correlation/')) {
            return mockResponse(DEMO_DATA.event_correlation);
        }
        
        if (urlStr.includes('/analytics/segments/')) {
            const segmentBy = params.segment_by || 'platform';
            const segmentData = getSegmentData(segmentBy, granularity);
            return mockResponse(segmentData);
        }
        
        if (urlStr.includes('/events/funnel/')) {
            // Build funnel from selected events
            const steps = params.steps ? params.steps.split(',') : ['app_opened', 'onboarding_completed', 'purchase_completed'];
            const funnel = steps.map(step => ({
                step: step,
                count: DEMO_DATA.events.counts[step] || 0
            }));
            return mockResponse({
                app_name: DEMO_DATA.app.name,
                funnel: funnel,
                total_sessions_analyzed: DEMO_DATA.dau.summary.total_sessions
            });
        }
        
        // For conversion preferences save - just return success
        if (urlStr.includes('/conversion-preferences/') || urlStr.includes('/save-conversion/')) {
            return mockResponse({ success: true, message: 'Demo mode - preferences not saved' });
        }
        
        // Default: pass through to original fetch (will fail, but that's expected for unknown endpoints)
        console.warn('[Demo] Unknown API endpoint:', urlStr);
        return mockResponse({ error: 'Unknown endpoint in demo mode' }, 404);
    };
    
    // Load demo data immediately
    loadDemoData();
    
    // Disable real-time polling in demo mode
    window.addEventListener('DOMContentLoaded', function() {
        // Wait for StatsApp to be defined
        const checkInterval = setInterval(function() {
            if (window.StatsApp) {
                window.StatsApp.isLiveMode = false;
                if (window.StatsApp.realtimePoller) {
                    window.StatsApp.realtimePoller.stop();
                }
                console.log('[Demo] Disabled real-time polling');
                clearInterval(checkInterval);
            }
        }, 100);
        
        // Stop checking after 5 seconds
        setTimeout(function() {
            clearInterval(checkInterval);
        }, 5000);
    });
    
    console.log('[Demo] Fetch interceptor initialized');
})();
