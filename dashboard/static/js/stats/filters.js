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
 * Mark the range in use in the bar's range control: a preset, or the calendar button for days
 * chosen by hand (it then names them, updateFilterSummary).
 * @param {string} activePreset - today, 7d, 30d, 90d or custom
 */
function updateDatePresetButtons(activePreset) {
    document.querySelectorAll('#datePresetPills [data-preset]').forEach(btn => {
        btn.setAttribute('aria-pressed', btn.dataset.preset === activePreset ? 'true' : 'false');
    });
}

/**
 * Say the range once, in the bar: the preset is lit, or the calendar button names the days chosen
 * by hand ("Oct 3-Oct 9"). The live line on the Overview shows only on Today, the one range it
 * belongs to.
 */
function updateFilterSummary() {
    const custom = document.getElementById('customRangeLabel');
    if (custom) {
        let text = '';
        if (currentDatePreset === 'custom' && dateRange.from && dateRange.to) {
            const day = (iso) => StatsApp.utils.formatPeriod(iso);
            text = dateRange.from === dateRange.to ? day(dateRange.from) : `${day(dateRange.from)}-${day(dateRange.to)}`;
            if (StatsApp.utils.linkedTimezone && StatsApp.utils.linkedTimezone()) text += ', UTC';
        }
        custom.textContent = text;
        custom.hidden = !text;
    }
    const live = document.getElementById('last30Section');
    if (live) live.hidden = currentDatePreset !== 'today';
}

/**
 * Open or close the conversion events panel under the bar's conversion control
 */
function toggleEventPopover() {
    const popover = document.getElementById('eventStatusPopover');
    if (!popover) return;
    popover.classList.toggle('active');
    const open = popover.classList.contains('active');
    const badge = document.getElementById('eventStatusBadge');
    if (badge) badge.setAttribute('aria-expanded', open ? 'true' : 'false');

    document.removeEventListener('click', closeEventPopoverOnClickOutside);
    if (open) {
        // one panel at a time: the event groups one closes
        const groups = document.getElementById('eventGroupsPanel');
        if (groups && !groups.hidden) document.getElementById('eventGroupsClose').click();
        // Deferred so the opening click does not close it again
        setTimeout(() => document.addEventListener('click', closeEventPopoverOnClickOutside), 0);
        const first = popover.querySelector('input:not([disabled]), button');
        if (first) first.focus();
    } else if (badge && popover.contains(document.activeElement)) {
        badge.focus();
    }
}

function closeEventPopoverOnClickOutside(e) {
    const popover = document.getElementById('eventStatusPopover');
    const badge = document.getElementById('eventStatusBadge');
    if (!popover || !popover.classList.contains('active')) {
        document.removeEventListener('click', closeEventPopoverOnClickOutside);
        return;
    }
    if (!popover.contains(e.target) && !(badge && badge.contains(e.target))) toggleEventPopover();
}

document.addEventListener('keydown', (e) => {
    const popover = document.getElementById('eventStatusPopover');
    if (e.key === 'Escape' && popover && popover.classList.contains('active')) toggleEventPopover();
});

/**
 * The bar's conversion control says which events count: "Converts on: purchase", or
 * "purchase +1" for more than one (a group whose every event is chosen reads as the group).
 */
function updateEventStatusBadge() {
    const prefix = document.getElementById('eventStatusPrefix');
    const label = document.getElementById('eventStatusLabel');
    const badge = document.getElementById('eventStatusBadge');
    if (!label) return;
    const shown = window.EventGroups ? EventGroups.compress(selectedConversionEvents) : selectedConversionEvents;
    if (prefix) prefix.hidden = shown.length === 0;
    label.textContent = shown.length === 0
        ? 'Choose conversions'
        : shown.length === 1 ? shown[0] : `${shown[0]} +${shown.length - 1}`;
    if (badge) {
        badge.title = shown.join(', ');
        badge.setAttribute('aria-label', shown.length
            ? `Converts on ${shown.join(', ')}. Change the conversion events`
            : 'Choose the events that count as conversions');
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
    conversionListDrawn = true;
    
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

    const esc = StatsApp.utils.escapeHtml;
    const row = (eventType, indent) => {
        const isSelected = selectedConversionEvents.includes(eventType);
        const isPending = !knownEventTypes.includes(eventType) && !(window.EventGroups && EventGroups.groupOf(eventType));
        const escaped = esc(eventType);

        const pendingBadge = isPending ? '<span class="ml-auto flex-none text-xs text-amber-300">Not sent yet</span>' : '';

        return `
            <label class="flex items-center gap-3 ${indent ? 'pl-11' : 'px-4'} pr-4 py-2.5 cursor-pointer hover:bg-slate-700/50 transition-colors ${isSelected ? 'bg-indigo-500/10' : ''}">
                <input type="checkbox" value="${escaped}" ${isSelected ? 'checked' : ''}
                       onchange="handleConversionCheckboxChange(this)"
                       class="w-4 h-4 flex-none rounded border-slate-600 text-indigo-600 focus:ring-indigo-500 bg-slate-700">
                <span class="min-w-0 truncate text-sm text-slate-200 ${indent ? 'font-mono' : ''}">${escaped}</span>
                ${pendingBadge}
            </label>
        `;
    };

    // Each group first, chosen whole with one box or event by event below it (event-groups.js)
    const groups = window.EventGroups ? EventGroups.state.groups : [];
    const grouped = new Set(groups.flatMap(g => g.events));
    const groupsHtml = groups.map(group => `
        <div class="border-b border-white/5" role="group" aria-label="${esc(group.name)}, a group of ${group.events.length} events">
            <label class="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-slate-700/50 transition-colors">
                <input type="checkbox" data-conversion-group="${esc(group.name)}"
                       onchange="handleConversionGroupChange(this)"
                       class="w-4 h-4 flex-none rounded border-slate-600 text-indigo-600 focus:ring-indigo-500 bg-slate-700">
                ${EventGroups.name(group.name, { plain: true, mono: true })}
                <span class="ml-auto flex-none text-xs text-slate-400" data-conversion-group-count="${esc(group.name)}"></span>
            </label>
            ${group.events.map(e => row(e, true)).join('')}
        </div>
    `).join('');

    eventList.innerHTML = groupsHtml + allEvents.filter(e => !grouped.has(e)).map(e => row(e, false)).join('');
    syncConversionGroups();
    updateEventStatusBadge();
}

/**
 * Each group's box in the conversion list: ticked when all its events are chosen, half when some
 * are, with how many beside it.
 */
function syncConversionGroups() {
    if (!window.EventGroups) return;
    document.querySelectorAll('#conversionEventList input[data-conversion-group]').forEach(box => {
        const group = EventGroups.group(box.dataset.conversionGroup);
        if (!group) return;
        const chosen = group.events.filter(e => selectedConversionEvents.includes(e)).length;
        box.checked = chosen === group.events.length;
        box.indeterminate = chosen > 0 && chosen < group.events.length;
        const count = [...document.querySelectorAll('#conversionEventList [data-conversion-group-count]')]
            .find(el => el.dataset.conversionGroupCount === group.name);
        if (count) count.textContent = box.indeterminate ? `${chosen} of ${group.events.length}` : '';
    });
}

/**
 * A group's box: choose or clear all its events at once.
 * @param {HTMLInputElement} box - The group's checkbox
 */
function handleConversionGroupChange(box) {
    const group = EventGroups.group(box.dataset.conversionGroup);
    if (!group) return;
    const events = new Set(group.events);
    selectedConversionEvents = selectedConversionEvents.filter(e => !events.has(e));
    if (box.checked) selectedConversionEvents.push(...group.events);
    box.closest('[role=group]').querySelectorAll('input[value]').forEach(input => {
        input.checked = box.checked;
        input.closest('label').classList.toggle('bg-indigo-500/10', box.checked);
    });
    syncConversionGroups();
    updateEventStatusBadge();
    updateFilterSummary();
    if (StatsApp.tabDataCache) {
        Object.keys(StatsApp.tabDataCache).forEach(key => delete StatsApp.tabDataCache[key]);
    }
}

// The list follows the groups: drawn again once they load and after every change
let conversionListDrawn = false;
if (window.EventGroups) {
    EventGroups.onChange(() => {
        if (conversionListDrawn) populateGlobalConversionDropdown(knownEventTypes);
        updateFilterSummary();
    });
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
    
    syncConversionGroups();
    updateEventStatusBadge();
    updateFilterSummary();
    
    // Clear tab data cache so tabs reload with new conversion events
    if (StatsApp.tabDataCache) {
        Object.keys(StatsApp.tabDataCache).forEach(key => delete StatsApp.tabDataCache[key]);
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
            showToast('An event name has at most 255 characters.', 'error');
        }
        return;
    }
    
    // Validation: no problematic characters that could cause issues
    // Allow alphanumeric, underscores, hyphens, dots, spaces, colons, dollar signs
    const safePattern = /^[a-zA-Z0-9_\-\.\s:$]+$/;
    if (!safePattern.test(eventName)) {
        if (typeof showToast === 'function') {
            showToast('An event name can hold letters, numbers, spaces, underscores, hyphens, dots, colons and dollar signs.', 'warning');
        }
        return;
    }
    
    // Check for duplicates
    if (selectedConversionEvents.includes(eventName)) {
        if (typeof showToast === 'function') {
            showToast('That event is already chosen.', 'warning');
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
        showToast(`Added ${eventName}. It counts once your app sends it.`, 'success');
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
window.addCustomConversionEvent = addCustomConversionEvent;
