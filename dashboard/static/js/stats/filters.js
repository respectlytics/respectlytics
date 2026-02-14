/**
 * Stats Dashboard - Filters Module
 * Date range and conversion event filtering functionality
 */

// ===== Global Filter Bar Functions =====

/**
 * Set date range based on preset buttons
 * @param {string} preset - The preset to apply (today, 7d, 30d, 90d)
 */
function setDatePreset(preset) {
    const today = new Date();
    let fromDate = new Date();
    
    switch (preset) {
        case 'today':
            fromDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
            break;
        case '7d':
            fromDate.setDate(today.getDate() - 7);
            break;
        case '30d':
            fromDate.setDate(today.getDate() - 30);
            break;
        case '90d':
            fromDate.setDate(today.getDate() - 90);
            break;
        default:
            return;
    }
    
    // Update date range using utility function from utils.js
    const newFrom = StatsApp.utils.formatLocalDate(fromDate);
    const newTo = StatsApp.utils.formatLocalDate(today);
    
    dateRange.from = newFrom;
    dateRange.to = newTo;
    currentDatePreset = preset;
    if (window.StatsApp && StatsApp.state) {
        StatsApp.state.currentDatePreset = preset;
    }

    if (StatsApp.utils && typeof StatsApp.utils.saveDateFilterState === 'function') {
        StatsApp.utils.saveDateFilterState({
            preset,
            from: dateRange.from,
            to: dateRange.to
        });
    }
    
    updateDatePresetButtons(preset);
    updateFilterSummary();
    
    // Clear custom date picker
    const customDateInput = document.getElementById('globalDateRange');
    if (customDateInput && customDateInput._flatpickr) {
        customDateInput._flatpickr.clear();
    }
    
    // Clear tab data cache so tabs reload with new date range
    if (StatsApp.tabDataCache) {
        Object.keys(StatsApp.tabDataCache).forEach(key => delete StatsApp.tabDataCache[key]);
    }
    
    // Apply auto-granularity based on new date range
    if (typeof applyAutoGranularity === 'function') {
        applyAutoGranularity();
    }
    
    // PERF-022: Lazy load - only load Overview data when on Overview tab
    const activeTab = StatsApp.currentTab || 'overview';
    if (activeTab === 'overview') {
        loadStats();
    }
    
    // Reload current tab data
    if (activeTab !== 'overview') {
        loadTabData(activeTab);
    }
}

/**
 * Apply a custom date range selection and refresh dashboard data
 * @param {Date|string} fromValue - Start date (Date object or YYYY-MM-DD)
 * @param {Date|string} toValue - End date (Date object or YYYY-MM-DD)
 * @param {{skipPickerUpdate?: boolean}} options - Control UI sync behavior
 */
function setCustomDateRange(fromValue, toValue, options = {}) {
    if (!fromValue || !toValue) {
        console.warn('[setCustomDateRange] Both start and end dates are required');
        return;
    }

    const normalizeDate = (value) => {
        if (typeof value === 'string') {
            return value;
        }
        if (StatsApp.utils && typeof StatsApp.utils.formatLocalDate === 'function') {
            return StatsApp.utils.formatLocalDate(value);
        }
        return value.toISOString().split('T')[0];
    };

    const normalizedFrom = normalizeDate(fromValue);
    const normalizedTo = normalizeDate(toValue);

    dateRange.from = normalizedFrom;
    dateRange.to = normalizedTo;
    currentDatePreset = 'custom';
    if (window.StatsApp && StatsApp.state) {
        StatsApp.state.currentDatePreset = 'custom';
    }

    updateDatePresetButtons('custom');
    updateFilterSummary();

    if (!options.skipPickerUpdate) {
        const customDateInput = document.getElementById('globalDateRange');
        if (customDateInput && customDateInput._flatpickr) {
            customDateInput._flatpickr.setDate([normalizedFrom, normalizedTo], true, 'Y-m-d');
        }
    }

    if (StatsApp.utils && typeof StatsApp.utils.saveDateFilterState === 'function') {
        StatsApp.utils.saveDateFilterState({
            preset: 'custom',
            from: normalizedFrom,
            to: normalizedTo
        });
    }

    const poller = (typeof realtimePoller !== 'undefined' && realtimePoller)
        ? realtimePoller
        : StatsApp.realtimePoller;
    if (poller && typeof poller.stop === 'function') {
        poller.stop();
    }

    if (typeof isLiveMode !== 'undefined') {
        isLiveMode = false;
    }
    StatsApp.isLiveMode = false;
    if (typeof updateLiveIndicator === 'function') {
        updateLiveIndicator();
    }

    if (StatsApp.tabDataCache) {
        Object.keys(StatsApp.tabDataCache).forEach(key => delete StatsApp.tabDataCache[key]);
    }

    // Apply auto-granularity based on new date range
    if (typeof applyAutoGranularity === 'function') {
        applyAutoGranularity();
    }

    // PERF-022: Lazy load - only load Overview data when on Overview tab
    if (typeof loadStats === 'function') {
        const activeTab = (typeof StatsApp.currentTab !== 'undefined' && StatsApp.currentTab)
            ? StatsApp.currentTab
            : 'overview';
        if (activeTab === 'overview') {
            loadStats();
        }
        // Reload current tab data
        if (activeTab !== 'overview' && typeof loadTabData === 'function') {
            loadTabData(activeTab);
        }
    }
}

/**
 * Update the active state of date preset buttons
 * @param {string} activePreset - The currently active preset
 */
function updateDatePresetButtons(activePreset) {
    document.querySelectorAll('.pill-tab[data-preset]').forEach(btn => {
        const isActive = btn.dataset.preset === activePreset;
        
        if (isActive) {
            btn.classList.add('active', 'bg-white', 'shadow-sm', 'text-brand-600');
            btn.classList.remove('text-gray-600', 'hover:bg-gray-200');
        } else {
            btn.classList.remove('active', 'bg-white', 'shadow-sm', 'text-brand-600');
            btn.classList.add('text-gray-600', 'hover:bg-gray-200');
        }
    });
    
    document.querySelectorAll('.date-preset-btn[data-preset]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.preset === activePreset);
    });
}

/**
 * Update the filter summary chips and all scope badges
 */
function updateFilterSummary() {
    let dateLabelText = 'All time';
    if (dateRange.from && dateRange.to) {
        const fromDate = new Date(dateRange.from);
        const toDate = new Date(dateRange.to);
        const options = { month: 'short', day: 'numeric' };
        
        if (currentDatePreset === 'today') {
            dateLabelText = 'Today';
        } else if (currentDatePreset === '7d') {
            dateLabelText = 'Last 7 days';
        } else if (currentDatePreset === '30d') {
            dateLabelText = 'Last 30 days';
        } else if (currentDatePreset === '90d') {
            dateLabelText = 'Last 90 days';
        } else {
            dateLabelText = `${fromDate.toLocaleDateString('en-US', options)} – ${toDate.toLocaleDateString('en-US', options)}`;
        }
    }
    
    const dateLabel = document.getElementById('dateFilterLabel');
    if (dateLabel) {
        dateLabel.textContent = dateLabelText;
    }
    
    const isRealtime = currentDatePreset === 'today';
    const badgeIcon = isRealtime ? '⚡' : '📅';
    const badgeClasses = isRealtime 
        ? 'bg-green-100 text-green-700' 
        : 'bg-blue-100 text-blue-700';
    
    const dateBadgeIds = ['scopeBadgeGlobe', 'scopeBadgeMetrics', 'scopeBadgeChart', 'scopeBadgeDAU', 'scopeBadgeSegments'];
    dateBadgeIds.forEach(id => {
        const badge = document.getElementById(id);
        if (badge) {
            badge.textContent = `${badgeIcon} ${dateLabelText}`;
            badge.className = `px-3 py-1 text-xs font-medium rounded-full ${badgeClasses}`;
        }
    });
    
    const combinedBadgeIds = ['scopeBadgeConversion', 'scopeBadgeBehavior'];
    combinedBadgeIds.forEach(id => {
        const badge = document.getElementById(id);
        if (badge) {
            badge.textContent = `📅 ${dateLabelText} • 🎯 Conversion events`;
        }
    });
    
    const conversionChip = document.getElementById('conversionFilterChip');
    const conversionLabel = document.getElementById('conversionFilterLabel');
    if (conversionChip && conversionLabel) {
        if (selectedConversionEvents && selectedConversionEvents.length > 0) {
            conversionChip.style.display = 'inline-flex';
            if (selectedConversionEvents.length === 1) {
                conversionLabel.textContent = selectedConversionEvents[0];
            } else {
                conversionLabel.textContent = `${selectedConversionEvents.length} events`;
            }
        } else {
            conversionChip.style.display = 'none';
        }
    }
}

/**
 * Toggle the event status popover
 */
function toggleEventPopover() {
    const popover = document.getElementById('eventStatusPopover');
    if (!popover) return;

    popover.classList.toggle('active');

    if (popover.classList.contains('active')) {
        // Avoid stacking listeners across open/close cycles.
        // Defer to avoid the opening click immediately closing the popover.
        setTimeout(() => {
            document.removeEventListener('click', closeEventPopoverOnClickOutside);
            document.addEventListener('click', closeEventPopoverOnClickOutside);
        }, 0);
    } else {
        // If the popover is closed via toggling (badge/CTA), clean up the listener.
        document.removeEventListener('click', closeEventPopoverOnClickOutside);
    }
}

function closeEventPopoverOnClickOutside(e) {
    const popover = document.getElementById('eventStatusPopover');
    const badge = document.getElementById('eventStatusBadge');
    if (!popover || !popover.classList.contains('active')) {
        document.removeEventListener('click', closeEventPopoverOnClickOutside);
        return;
    }

    const clickedInsidePopover = popover.contains(e.target);
    const clickedInsideBadge = badge ? badge.contains(e.target) : false;

    if (!clickedInsidePopover && !clickedInsideBadge) {
        popover.classList.remove('active');
        document.removeEventListener('click', closeEventPopoverOnClickOutside);
    }
}

/**
 * Update the event status badge based on selected events
 */
function updateEventStatusBadge() {
    const badge = document.getElementById('eventStatusBadge');
    const label = document.getElementById('eventStatusLabel');
    const selectedCount = selectedConversionEvents.length;
    
    if (badge && label) {
        if (selectedCount > 0) {
            badge.classList.remove('event-status-badge--inactive');
            label.textContent = `Events: ${selectedCount} Active`;
        } else {
            badge.classList.add('event-status-badge--inactive');
            label.textContent = '🎯 Select Events';
        }
    }
}

// Track available events from API (used for visual distinction)
let knownEventTypes = [];

/**
 * Populate the conversion events list with checkboxes
 * Merges API-fetched events with custom user-entered events
 * @param {Array} eventTypes - Array of available event types from API
 */
function populateGlobalConversionDropdown(eventTypes) {
    const eventList = document.getElementById('conversionEventList');
    const emptyHint = document.getElementById('conversionEmptyHint');
    const datalist = document.getElementById('availableEventsList');
    
    if (!eventList) return;
    
    // Store known events for visual distinction
    knownEventTypes = eventTypes || [];
    
    // Populate datalist for autocomplete
    if (datalist) {
        datalist.innerHTML = knownEventTypes.map(evt => 
            `<option value="${StatsApp.utils.escapeHtml(evt)}">`
        ).join('');
    }
    
    // Merge API events with any custom events that were selected but don't exist yet
    const customEvents = selectedConversionEvents.filter(evt => !knownEventTypes.includes(evt));
    const allEvents = [...knownEventTypes, ...customEvents];
    
    if (allEvents.length === 0) {
        eventList.innerHTML = '';
        eventList.parentElement.style.display = 'none';
        if (emptyHint) emptyHint.style.display = 'block';
        return;
    }
    
    eventList.parentElement.style.display = 'block';
    if (emptyHint) emptyHint.style.display = 'none';
    
    eventList.innerHTML = allEvents.map(eventType => {
        const isSelected = selectedConversionEvents.includes(eventType);
        const isPending = !knownEventTypes.includes(eventType);
        const escaped = StatsApp.utils.escapeHtml(eventType);
        
        // Visual distinction: pending events have dashed border and amber styling
        const pendingClasses = isPending ? 'border-l-2 border-dashed border-amber-500/50' : '';
        const pendingBadge = isPending ? '<span class="ml-auto text-xs text-amber-400 font-medium">pending</span>' : '';
        
        return `
            <label class="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-slate-700/50 transition-colors ${isSelected ? 'bg-indigo-500/10' : ''} ${pendingClasses}">
                <input type="checkbox" value="${escaped}" ${isSelected ? 'checked' : ''} 
                       onchange="handleConversionCheckboxChange(this)"
                       class="w-4 h-4 rounded border-slate-600 text-indigo-600 focus:ring-indigo-500 bg-slate-700">
                <span class="text-sm text-slate-200">${escaped}</span>
                ${pendingBadge}
            </label>
        `;
    }).join('');
    
    updateEventStatusBadge();
}

/**
 * Handle checkbox change in conversion event list
 * @param {HTMLInputElement} checkbox - The checkbox element
 */
function handleConversionCheckboxChange(checkbox) {
    const eventType = checkbox.value;
    const label = checkbox.closest('label');
    
    if (checkbox.checked) {
        if (!selectedConversionEvents.includes(eventType)) {
            selectedConversionEvents.push(eventType);
        }
        label.classList.add('bg-indigo-500/10');
    } else {
        selectedConversionEvents = selectedConversionEvents.filter(e => e !== eventType);
        label.classList.remove('bg-indigo-500/10');
    }
    
    updateEventStatusBadge();
    updateFilterSummary();
    
    // Clear tab data cache so tabs reload with new conversion events
    if (StatsApp.tabDataCache) {
        Object.keys(StatsApp.tabDataCache).forEach(key => delete StatsApp.tabDataCache[key]);
    }
}

/**
 * Update the conversion select button label
 */
function updateConversionSelectLabel() {
    const label = document.getElementById('conversionSelectLabel');
    const btn = document.getElementById('conversionSelectBtn');
    
    if (!label || !btn) return;
    
    if (selectedConversionEvents.length === 0) {
        label.textContent = 'Select events...';
        btn.classList.remove('has-selection');
    } else if (selectedConversionEvents.length === 1) {
        label.textContent = selectedConversionEvents[0];
        btn.classList.add('has-selection');
    } else {
        label.textContent = `${selectedConversionEvents.length} events selected`;
        btn.classList.add('has-selection');
    }
    
    updateEventStatusBadge();
}

/**
 * Update the last updated timestamp in the filter bar
 */
function updateGlobalLastUpdated() {
    const el = document.getElementById('globalLastUpdated');
    if (el) {
        const now = new Date();
        el.textContent = `Updated ${now.toLocaleTimeString()}`;
    }
}

/**
 * Add a custom conversion event from the text input
 * Allows adding events that haven't been tracked yet
 */
function addCustomConversionEvent() {
    const input = document.getElementById('customEventInput');
    if (!input) return;
    
    const eventName = input.value.trim();
    
    // Validation: non-empty
    if (!eventName) {
        return;
    }
    
    // Validation: max length 255 chars
    if (eventName.length > 255) {
        if (typeof showToast === 'function') {
            showToast('Event name must be 255 characters or less.', 'error');
        }
        return;
    }
    
    // Validation: no problematic characters that could cause issues
    // Allow alphanumeric, underscores, hyphens, dots, spaces, colons, dollar signs
    const safePattern = /^[a-zA-Z0-9_\-\.\s:$]+$/;
    if (!safePattern.test(eventName)) {
        if (typeof showToast === 'function') {
            showToast('Event name can only contain letters, numbers, underscores, hyphens, dots, spaces, colons, and dollar signs.', 'warning');
        }
        return;
    }
    
    // Check for duplicates
    if (selectedConversionEvents.includes(eventName)) {
        if (typeof showToast === 'function') {
            showToast('This event is already selected.', 'warning');
        }
        input.value = '';
        return;
    }
    
    // Add to selected events
    selectedConversionEvents.push(eventName);
    input.value = '';
    
    // Refresh the dropdown to show the new event
    populateGlobalConversionDropdown(knownEventTypes);
    updateEventStatusBadge();
    updateFilterSummary();
    
    // Show feedback
    const isPending = !knownEventTypes.includes(eventName);
    if (isPending && typeof showToast === 'function') {
        showToast(`Added "${eventName}" - will match when events are tracked.`, 'success');
    }
    
    // Clear tab cache
    if (StatsApp.tabDataCache) {
        Object.keys(StatsApp.tabDataCache).forEach(key => delete StatsApp.tabDataCache[key]);
    }
}

// Make functions globally available
window.setDatePreset = setDatePreset;
window.setCustomDateRange = setCustomDateRange;
window.updateDatePresetButtons = updateDatePresetButtons;
window.updateFilterSummary = updateFilterSummary;
window.toggleEventPopover = toggleEventPopover;
window.closeEventPopoverOnClickOutside = closeEventPopoverOnClickOutside;
window.updateEventStatusBadge = updateEventStatusBadge;
window.populateGlobalConversionDropdown = populateGlobalConversionDropdown;
window.handleConversionCheckboxChange = handleConversionCheckboxChange;
window.updateConversionSelectLabel = updateConversionSelectLabel;
window.updateGlobalLastUpdated = updateGlobalLastUpdated;
window.addCustomConversionEvent = addCustomConversionEvent;
