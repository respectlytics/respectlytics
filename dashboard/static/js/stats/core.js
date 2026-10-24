/**
 * Stats Dashboard - Core Module
 * Global state
 */

// ===== Global State =====
// These are initialized from StatsConfig which is set in stats.html
window.StatsApp = window.StatsApp || {};

// State variables (will be initialized after DOM load)
StatsApp.state = {
    currentData: null,
    charts: {},
    dateRange: { from: null, to: null },
    realtimePoller: null,
    isLiveMode: true,
    lastUpdateTime: Date.now(),
    countdownInterval: null,
    currentGranularity: 'day',
    selectedConversionEvents: [],
    availableEventTypes: [],
    currentDatePreset: 'today',
    currentTab: 'overview',
    tabDataCache: {},
    currentSegmentType: 'platform',
    globeInitialized: false,
    currentGlobeAltitude: 1.6,
    periodDetailsData: [],
    periodDetailsSortColumn: 'date',
    periodDetailsSortDirection: 'desc'
};

// Initialize state from config (called from stats.html after StatsConfig is defined)
StatsApp.initState = function() {
    if (typeof StatsConfig !== 'undefined') {
        StatsApp.state.selectedConversionEvents = StatsConfig.preferredConversionEvents || [];
    }
};
