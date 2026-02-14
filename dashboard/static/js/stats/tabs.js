/**
 * Stats Dashboard - Tab Management Module
 * 
 * Handles tab switching, lazy loading of tab data, and keyboard navigation.
 * Dependencies: realtime.js (for sidebar mobile)
 */

// Namespace setup
window.StatsApp = window.StatsApp || {};

// ===== Tab Constants =====
StatsApp.TABS = ['overview', 'conversion', 'behavior', 'segments'];

// ===== Tab State =====
StatsApp.tabDataCache = {};  // Cache loaded data per tab
StatsApp.currentTab = 'overview';

/**
 * Switch to a different dashboard tab
 * @param {string} tabName - The tab to switch to
 * @param {boolean} updateHash - Whether to update the URL hash
 */
function switchTab(tabName, updateHash = true) {
    const { TABS, tabDataCache } = StatsApp;
    
    if (!TABS.includes(tabName)) {
        console.warn(`Invalid tab: ${tabName}`);
        return;
    }
    
    // Update current tab
    StatsApp.currentTab = tabName;
    
    // 1. Update URL hash (for bookmarking/sharing)
    if (updateHash) {
        history.replaceState(null, null, `#${tabName}`);
    }
    
    // 2. Update tab button states (both old dashboard-tab and new header-tab)
    document.querySelectorAll('.dashboard-tab, .header-tab').forEach(btn => {
        const isActive = btn.dataset.tab === tabName;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive);
        btn.setAttribute('tabindex', isActive ? '0' : '-1');
    });
    
    // 3. Update sidebar nav items
    document.querySelectorAll('.sidebar-nav-item[data-tab]').forEach(item => {
        const isActive = item.dataset.tab === tabName;
        item.classList.toggle('active', isActive);
    });
    
    // 4. Update tab content visibility
    document.querySelectorAll('.tab-content').forEach(content => {
        const isActive = content.id === `tab-${tabName}`;
        content.classList.toggle('active', isActive);
    });
    
    // 5. Hide global loading overlay when switching away from overview tab
    // (Other tabs manage their own loading states)
    if (tabName !== 'overview') {
        const loadingOverlay = document.getElementById('loadingOverlay');
        if (loadingOverlay) {
            loadingOverlay.style.display = 'none';
        }
    }
    
    // 6. Load tab data if not cached (for non-overview tabs)
    // Also reload tabs previously cached as empty (prevents tabs getting stuck
    // in an empty state when prerequisites later change).
    if (tabName !== 'overview' && (!tabDataCache[tabName] || tabDataCache[tabName].empty)) {
        loadTabData(tabName);
    }
    
    // 6. Re-center globe when switching back to overview tab
    if (tabName === 'overview' && window.globeInstance) {
        // Use setTimeout to ensure the tab is fully visible before resizing
        setTimeout(() => {
            const globeViz = document.getElementById('globeViz');
            if (globeViz && window.globeInstance) {
                window.globeInstance.width(globeViz.clientWidth);
                window.globeInstance.height(700);
            }
        }, 50);
    }
    
    // 7. Close mobile sidebar after switching tabs
    if (window.innerWidth <= 1024 && typeof closeSidebar === 'function') {
        closeSidebar();
    }
    
    // 8. Announce to screen readers
    const tabContent = document.getElementById(`tab-${tabName}`);
    if (tabContent) {
        tabContent.setAttribute('aria-live', 'polite');
    }
}

/**
 * Load data for a specific tab (lazy loading)
 * @param {string} tabName - The tab to load data for
 */
async function loadTabData(tabName) {
    const { tabDataCache } = StatsApp;
    
    const loadingEl = document.getElementById(`${tabName}-loading`);
    const contentEl = document.getElementById(`${tabName}-content`);
    const errorEl = document.getElementById(`${tabName}-error`);
    const emptyEl = document.getElementById(`${tabName}-empty`);
    
    // Special handling for tabs that manage their own progressive loading
    // These tabs use individual section skeletons + processing banners
    const managesOwnLoading = ['conversion', 'behavior', 'segments'].includes(tabName);
    
    // Show loading state (unless tab handles it internally)
    // Use classList only - Tailwind's hidden class uses !important
    if (loadingEl && !managesOwnLoading) loadingEl.classList.remove('hidden');
    if (contentEl && !managesOwnLoading) contentEl.classList.add('hidden');
    if (errorEl) errorEl.classList.add('hidden');
    if (emptyEl) emptyEl.classList.add('hidden');
    
    try {
        // Call tab-specific loading function
        if (tabName === 'conversion') {
            await loadConversionTabData();
        } else if (tabName === 'behavior') {
            await loadBehaviorTabData();
        } else if (tabName === 'segments') {
            await loadSegmentsTabData();
        } else {
            // Placeholder for other tabs
            await new Promise(resolve => setTimeout(resolve, 500));
        }
        
        // Cache that we've loaded this tab
        tabDataCache[tabName] = { loaded: true, timestamp: Date.now() };
        
        // Show content (tabs that manage their own loading handle visibility internally)
        // Use classList only - Tailwind's hidden class uses !important
        if (!managesOwnLoading) {
            if (loadingEl) loadingEl.classList.add('hidden');
            if (contentEl) contentEl.classList.remove('hidden');
        }
        
    } catch (error) {
        console.error(`[TABS] Error loading ${tabName} data:`, error.message, error.stack);
        
        // Hide loading (tabs that manage their own loading handle visibility internally)
        // Use classList only - Tailwind's hidden class uses !important
        if (!managesOwnLoading && loadingEl) loadingEl.classList.add('hidden');
        
        // Handle "empty" state (no data, but not an error)
        // Use classList only - Tailwind's hidden class uses !important
        if (error.message === 'empty') {
            if (contentEl) {
                contentEl.classList.add('hidden');
            }
            if (emptyEl) {
                emptyEl.classList.remove('hidden');
            }
            // Still cache so we don't keep retrying
            tabDataCache[tabName] = { loaded: true, empty: true, timestamp: Date.now() };
        } else {
            // Show error state for real errors
            // Use classList only - Tailwind's hidden class uses !important
            if (contentEl) {
                contentEl.classList.add('hidden');
            }
            if (errorEl) {
                errorEl.classList.remove('hidden');
                const errorMsg = document.getElementById(`${tabName}-error-msg`);
                if (errorMsg) errorMsg.textContent = error.message;
            }
        }
    }
}

/**
 * Initialize tab system - called on page load
 */
function initializeTabs() {
    const { TABS } = StatsApp;
    
    // Handle tab button clicks (both old dashboard-tab and new header-tab)
    document.querySelectorAll('.dashboard-tab, .header-tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            switchTab(e.currentTarget.dataset.tab);
        });
    });
    
    // Handle keyboard navigation (arrow keys) - works with header-tabs now
    const tabContainer = document.querySelector('.header-tabs') || document.querySelector('.dashboard-tabs');
    if (tabContainer) {
        tabContainer.addEventListener('keydown', (e) => {
            const currentIndex = TABS.indexOf(StatsApp.currentTab);
            let newIndex = currentIndex;
            
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                newIndex = (currentIndex + 1) % TABS.length;
                e.preventDefault();
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                newIndex = (currentIndex - 1 + TABS.length) % TABS.length;
                e.preventDefault();
            } else if (e.key === 'Home') {
                newIndex = 0;
                e.preventDefault();
            } else if (e.key === 'End') {
                newIndex = TABS.length - 1;
                e.preventDefault();
            }
            
            if (newIndex !== currentIndex) {
                switchTab(TABS[newIndex]);
                // Focus the new tab button
                document.querySelector(`[data-tab="${TABS[newIndex]}"]`).focus();
            }
        });
    }
    
    // Check for hash on page load
    const hash = window.location.hash.slice(1);
    if (hash && TABS.includes(hash)) {
        switchTab(hash, false);
    }
    
    // Listen for hash changes (browser back/forward)
    window.addEventListener('hashchange', () => {
        const hash = window.location.hash.slice(1);
        if (hash && TABS.includes(hash) && hash !== StatsApp.currentTab) {
            switchTab(hash, false);
        }
    });
}

// Make functions globally available
window.switchTab = switchTab;
window.loadTabData = loadTabData;
window.initializeTabs = initializeTabs;
