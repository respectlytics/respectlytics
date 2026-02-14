/**
 * Stats Dashboard - Core Module
 * Global state management and app switcher functionality
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

// ===== App Switcher Functions =====

/**
 * Toggle the app switcher dropdown open/closed
 */
function toggleAppSwitcher() {
    const switcher = document.getElementById('appSwitcher');
    if (switcher) {
        const isOpen = switcher.classList.toggle('open');
        const button = switcher.querySelector('.app-switcher-button');
        if (button) {
            button.setAttribute('aria-expanded', isOpen);
        }
    }
}

/**
 * Close the app switcher dropdown
 */
function closeAppSwitcher() {
    const switcher = document.getElementById('appSwitcher');
    if (switcher && switcher.classList.contains('open')) {
        switcher.classList.remove('open');
        const button = switcher.querySelector('.app-switcher-button');
        if (button) {
            button.setAttribute('aria-expanded', 'false');
        }
    }
}

/**
 * Switch to a different app's dashboard
 * @param {string} appSlug - The slug of the app to switch to
 */
function switchApp(appSlug) {
    if (appSlug) {
        window.location.href = `/dashboard/stats/${appSlug}/`;
    }
}

// Close app switcher when clicking outside
document.addEventListener('click', function(event) {
    const switcher = document.getElementById('appSwitcher');
    if (switcher && !switcher.contains(event.target)) {
        closeAppSwitcher();
    }
});

// Close app switcher on escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeAppSwitcher();
    }
});

// ===== UI Helper Functions =====

/**
 * Show warning banner
 * @param {string} warning - Warning message to display
 */
function showWarning(warning) {
    const banner = document.getElementById('warningBanner');
    const warningText = document.getElementById('warningText');
    if (banner && warningText) {
        warningText.textContent = warning;
        banner.classList.add('visible');
    }
}

/**
 * Toggle collapsible section
 * @param {string} sectionId - The ID of the section to toggle
 */
function toggleCollapsible(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.classList.toggle('collapsed');
        localStorage.setItem(`stats-${sectionId}-collapsed`, section.classList.contains('collapsed'));
    }
}

/**
 * Restore collapsible states from localStorage
 */
function restoreCollapsibleStates() {
    document.querySelectorAll('.collapsible-section').forEach(section => {
        const isCollapsed = localStorage.getItem(`stats-${section.id}-collapsed`) === 'true';
        if (isCollapsed) {
            section.classList.add('collapsed');
        }
    });
}

// Make functions globally available
window.toggleAppSwitcher = toggleAppSwitcher;
window.closeAppSwitcher = closeAppSwitcher;
window.switchApp = switchApp;
window.showWarning = showWarning;
window.toggleCollapsible = toggleCollapsible;
window.restoreCollapsibleStates = restoreCollapsibleStates;
