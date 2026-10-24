/**
 * The demo's answers (demo/): every call the stats and funnel pages make, to the API and to the
 * event groups, is answered from static/demo/demo_data.json, so the demo runs the dashboard's
 * own pages with no account and no request to the server for data.
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
     * A segments answer as the API gives it: the sample's days (oldest first, sessions and
     * conversions) summed into the granularity asked for, each dated and with its rate, the
     * newest first (conversion/views.py _segments_from).
     */
    function withPeriods(answer, granularity) {
        const size = { week: 7, month: 30 }[granularity] || 1;
        const segments = answer.segments.map(segment => {
            if (!segment.periods) return segment;
            const days = segment.periods;
            const groups = [];
            for (let end = days.length; end > 0; end -= size) {
                const chunk = days.slice(Math.max(0, end - size), end);
                const sessions = chunk.reduce((n, d) => n + d.active_sessions, 0);
                const conversions = chunk.reduce((n, d) => n + d.conversions, 0);
                groups.unshift({ active_sessions: sessions, conversions });
            }
            const dates = generateDateLabels(groups.length, granularity);
            const periods = groups.map((g, i) => ({
                period: dates[i],
                ...g,
                conversion_rate: g.active_sessions ? g.conversions / g.active_sessions : 0
            })).reverse();
            return { ...segment, periods };
        });
        return { ...answer, granularity, segments };
    }

    /** The segments the Segments tab asks for, by its segment_by. */
    function getSegmentData(segmentBy) {
        switch (segmentBy) {
            case 'country':
                return DEMO_DATA.segments_country;
            case 'depth':
            case 'events_per_session':
                return DEMO_DATA.segments_events_per_session;
            case 'hour':
                return DEMO_DATA.segments_hour;
            default:
                // A declared property ("property:paywall")
                if (segmentBy.startsWith('property:')) {
                    return DEMO_DATA.segments_property[segmentBy.slice(9)] || DEMO_DATA.segments_platform;
                }
                return DEMO_DATA.segments_platform;
        }
    }

    /** One answer per kind of call, from the sample data. */
    function answer(urlStr, params) {
        const granularity = params.granularity || 'day';

        if (urlStr.includes('/event-groups/')) {
            return DEMO_DATA.event_groups_state;
        }
        if (urlStr.includes('/insights/')) {
            // The Last week card: the sample's findings, for the week before today
            const today = new Date();
            const monday = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
            monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7) - 7);
            const sunday = new Date(monday);
            sunday.setUTCDate(monday.getUTCDate() + 6);
            const iso = (d) => d.toISOString().split('T')[0];
            return { ...DEMO_DATA.insights, week: { start: iso(monday), end: iso(sunday) } };
        }
        if (urlStr.includes('/properties/')) {
            return DEMO_DATA.properties;
        }
        if (urlStr.includes('/experiments/')) {
            // The sample tests, dated back from today as a live app's would be
            const ago = (days) => new Date(Date.now() - days * 86400000).toISOString();
            const data = { ...DEMO_DATA.experiments };
            data.experiments = data.experiments.map(t => ({
                ...t,
                started_at: ago(t.started_days_ago),
                ended_at: t.ended_days_ago === null ? null : ago(t.ended_days_ago)
            }));
            return data;
        }
        if (urlStr.includes('/events/summary/')) {
            const data = { ...DEMO_DATA.summary };
            data.events_by_day = addDatesToEventsByDay(data.events_by_day);
            return data;
        }
        if (urlStr.includes('/events/event-types/')) {
            return DEMO_DATA.event_types;
        }
        if (urlStr.includes('/events/recent-activity/')) {
            // Recent, as a live app's would be
            const data = { ...DEMO_DATA.recent_activity };
            const now = new Date();
            data.server_time = now.toISOString();
            data.last_event_timestamp = new Date(now - 60000).toISOString();
            data.event_preview = data.event_preview.map((e, i) => ({
                ...e,
                timestamp: new Date(now - (i * 45000)).toISOString()
            }));
            return data;
        }
        if (urlStr.includes('/events/geo-summary/')) {
            return DEMO_DATA.geo_summary;
        }
        if (urlStr.includes('/events/count/')) {
            return { total_events: DEMO_DATA.summary.total_events, date_range: { from: null, to: null } };
        }
        if (urlStr.includes('/events/filter-options/')) {
            return {
                filters: {
                    countries: DEMO_DATA.geo_summary.countries.map(c => c.country),
                    platforms: ['ios', 'android'],
                    event_names: DEMO_DATA.event_types.event_types
                }
            };
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
            // The sample runs oldest to newest; the API answers newest first (conversion/views.py)
            dauData.active_sessions = addPeriodsToDAU(dauData.active_sessions, granularity).reverse();
            dauData.granularity = granularity;
            return dauData;
        }
        if (urlStr.includes('/analytics/globe-stats/')) {
            return DEMO_DATA.globe_stats;
        }
        if (urlStr.includes('/analytics/time-to-conversion/')) {
            return DEMO_DATA.time_to_conversion;
        }
        if (urlStr.includes('/analytics/conversion-paths/')) {
            return DEMO_DATA.conversion_paths;
        }
        if (urlStr.includes('/analytics/drop-off/')) {
            return DEMO_DATA.drop_off;
        }
        if (urlStr.includes('/analytics/event-correlation/')) {
            return DEMO_DATA.event_correlation;
        }
        if (urlStr.includes('/analytics/segments/')) {
            return withPeriods(getSegmentData(params.segment_by || 'platform'), granularity);
        }
        // The funnel page's sample funnel and its timing
        if (urlStr.includes('/events/funnel/')) {
            return DEMO_DATA.funnel;
        }
        if (urlStr.includes('/analytics/step-timing/')) {
            return DEMO_DATA.step_timing;
        }
        return null;
    }

    window.fetch = async function(url, options = {}) {
        const urlStr = typeof url === 'string' ? url : url.toString();
        if (!urlStr.includes('/api/v1/') && !urlStr.includes('/dashboard/api/') && !urlStr.includes('/event-groups/')) {
            return originalFetch(url, options);
        }
        if (!DEMO_DATA) await loadDemoData();
        if (!DEMO_DATA) return mockResponse({ error: 'Demo data not loaded' }, 500);
        const data = answer(urlStr, parseParams(urlStr));
        if (data === null) {
            console.warn('[Demo] No sample answer for', urlStr);
            return mockResponse({ error: 'Not in the demo' }, 404);
        }
        return mockResponse(data);
    };

    loadDemoData();
})();
