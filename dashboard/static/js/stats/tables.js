/**
 * Stats Dashboard - Tables Module
 * 
 * Contains functions for creating data tables (period details, geo tables).
 */

// Namespace setup
window.StatsApp = window.StatsApp || {};

// Table sorting state
StatsApp.periodDetailsData = [];
StatsApp.periodDetailsGranularity = 'day';
StatsApp.periodDetailsSortColumn = 'date';
StatsApp.periodDetailsSortDirection = 'desc';

/**
 * Create Daily/Period table
 * @param {Array} eventsByPeriod - Array of {date, count, unique_buckets} objects
 * @param {string} granularity - 'day', 'week', 'month', 'quarter', 'year'
 */
function createDailyTable(eventsByPeriod, granularity = 'day') {
    const container = document.getElementById('dailyTable');
    
    // Check for empty data
    if (!eventsByPeriod || eventsByPeriod.length === 0 || eventsByPeriod.every(d => d.count === 0)) {
        container.innerHTML = `
            <div class="flex flex-col items-center justify-center py-12 text-slate-400">
                <div class="text-4xl mb-2">📅</div>
                <div class="text-sm">No data available for this period</div>
                <div class="text-xs mt-1">Statistics will appear as events are recorded</div>
            </div>
        `;
        return;
    }
    
    // Store data for sorting
    StatsApp.periodDetailsData = [...eventsByPeriod];
    StatsApp.periodDetailsGranularity = granularity;
    StatsApp.periodDetailsSortColumn = 'date';
    StatsApp.periodDetailsSortDirection = 'desc';
    
    renderPeriodDetailsTable();
}

/**
 * Render the period details table with current sort settings
 */
function renderPeriodDetailsTable() {
    const container = document.getElementById('dailyTable');
    const data = StatsApp.periodDetailsData;
    const granularity = StatsApp.periodDetailsGranularity;
    const sortColumn = StatsApp.periodDetailsSortColumn;
    const sortDir = StatsApp.periodDetailsSortDirection;
    
    if (!data || !container) return;
    
    const hasUniqueBuckets = data.length > 0 && data[0].unique_buckets !== undefined;
    
    // Pre-compute change percentages for each row
    const dataWithChanges = data.map((item, index) => {
        if (index === 0) {
            return { ...item, eventsChangePct: null, sessionsChangePct: null };
        }
        const prev = data[index - 1];
        const eventsChangePct = prev.count > 0 ? ((item.count - prev.count) / prev.count * 100) : (item.count > 0 ? Infinity : 0);
        const sessionsChangePct = hasUniqueBuckets && prev.unique_buckets > 0 
            ? ((item.unique_buckets - prev.unique_buckets) / prev.unique_buckets * 100) 
            : (hasUniqueBuckets && item.unique_buckets > 0 ? Infinity : 0);
        return { ...item, eventsChangePct, sessionsChangePct };
    });
    
    // Sort the data
    const sortedData = [...dataWithChanges].sort((a, b) => {
        let valA, valB;
        switch(sortColumn) {
            case 'date': valA = a.date; valB = b.date; break;
            case 'events': valA = a.count; valB = b.count; break;
            case 'sessions': valA = a.unique_buckets || 0; valB = b.unique_buckets || 0; break;
            case 'eventsChange': 
                valA = a.eventsChangePct === null ? -Infinity : a.eventsChangePct;
                valB = b.eventsChangePct === null ? -Infinity : b.eventsChangePct;
                break;
            case 'sessionsChange': 
                valA = a.sessionsChangePct === null ? -Infinity : a.sessionsChangePct;
                valB = b.sessionsChangePct === null ? -Infinity : b.sessionsChangePct;
                break;
            default: valA = a.date; valB = b.date;
        }
        if (typeof valA === 'string') {
            return sortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        return sortDir === 'asc' ? valA - valB : valB - valA;
    });
    
    // Determine period label
    let periodLabel = 'Date';
    switch(granularity) {
        case 'week': periodLabel = 'Week'; break;
        case 'month': periodLabel = 'Month'; break;
        case 'quarter': periodLabel = 'Quarter'; break;
        case 'year': periodLabel = 'Year'; break;
    }
    
    // Helper for sort icon
    function sortIcon(column) {
        const isActive = sortColumn === column;
        const icon = (isActive && sortDir === 'asc') 
            ? '<svg class="sort-icon w-4 h-4 ml-1 inline-block align-middle" fill="currentColor" viewBox="0 0 20 20"><path d="M5 12l5-5 5 5H5z"/></svg>'
            : '<svg class="sort-icon w-4 h-4 ml-1 inline-block align-middle" fill="currentColor" viewBox="0 0 20 20"><path d="M5 8l5 5 5-5H5z"/></svg>';
        return icon;
    }
    
    // Format change percentage for display (matching Retention/Segments badge style)
    function formatChange(pct) {
        if (pct === null) return '<span class="inline-block px-2 py-1 rounded-lg text-sm font-medium bg-slate-700 text-slate-400">—</span>';
        if (pct === Infinity) return '<span class="inline-block px-2 py-1 rounded-lg text-sm font-semibold bg-emerald-500/15 text-emerald-400">+∞</span>';
        if (pct === -Infinity) return '<span class="inline-block px-2 py-1 rounded-lg text-sm font-semibold bg-rose-500/15 text-rose-400">-∞</span>';
        if (pct > 0) {
            return `<span class="inline-flex items-center gap-0.5 px-2 py-1 rounded-lg text-sm font-semibold bg-emerald-500/15 text-emerald-400"><svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z" clip-rule="evenodd"/></svg>${pct.toFixed(1)}%</span>`;
        } else if (pct < 0) {
            return `<span class="inline-flex items-center gap-0.5 px-2 py-1 rounded-lg text-sm font-semibold bg-rose-500/15 text-rose-400"><svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M14.707 10.293a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 12.586V5a1 1 0 012 0v7.586l2.293-2.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>${Math.abs(pct).toFixed(1)}%</span>`;
        }
        return '<span class="inline-block px-2 py-1 rounded-lg text-sm font-medium bg-slate-700 text-slate-400">0%</span>';
    }
    
    let html = `
        <table class="w-full text-sm">
            <thead class="sticky top-0 bg-[#1e293b] z-10 shadow-sm shadow-black/20">
                <tr class="border-b border-white/10">
                    <th class="text-left px-4 py-2 font-semibold text-slate-50 sortable-header ${sortColumn === 'date' ? 'sort-active' : ''}" onclick="sortPeriodDetails('date')">
                        <div class="flex items-center gap-2">
                            ${periodLabel}${sortIcon('date')}
                        </div>
                    </th>
                    <th class="text-right px-4 py-2 font-semibold text-slate-50 sortable-header ${sortColumn === 'events' ? 'sort-active' : ''}" onclick="sortPeriodDetails('events')">
                        <div class="flex items-center justify-end gap-2">
                            Events${sortIcon('events')}
                            <span class="info-tooltip tooltip-right" data-tip="Total number of events tracked in this period. Higher numbers indicate more session activity.">?</span>
                        </div>
                    </th>
                    <th class="text-right px-4 py-2 font-semibold text-slate-50 sortable-header ${sortColumn === 'eventsChange' ? 'sort-active' : ''}" onclick="sortPeriodDetails('eventsChange')">
                        <div class="flex items-center justify-end gap-2">
                            +/-&\#37;${sortIcon('eventsChange')}
                            <span class="info-tooltip tooltip-right" data-tip="Percentage change in events compared to the previous period. Green (↑) means growth, red (↓) means decline.">?</span>
                        </div>
                    </th>
                    ${hasUniqueBuckets ? `<th class="text-right px-4 py-2 font-semibold text-slate-50 sortable-header ${sortColumn === 'sessions' ? 'sort-active' : ''}" onclick="sortPeriodDetails('sessions')">
                        <div class="flex items-center justify-end gap-2">
                            Sessions${sortIcon('sessions')}
                            <span class="info-tooltip tooltip-right" data-tip="Number of unique sessions that triggered events in this period. Each session is a 2-hour activity window.">?</span>
                        </div>
                    </th>` : ''}
                    ${hasUniqueBuckets ? `<th class="text-right px-4 py-2 font-semibold text-slate-50 sortable-header ${sortColumn === 'sessionsChange' ? 'sort-active' : ''}" onclick="sortPeriodDetails('sessionsChange')">
                        <div class="flex items-center justify-end gap-2">
                            +/-&\#37;${sortIcon('sessionsChange')}
                            <span class="info-tooltip tooltip-right" data-tip="Percentage change in unique sessions compared to the previous period. Shows session activity growth or decline.">?</span>
                        </div>
                    </th>` : ''}
                </tr>
            </thead>
            <tbody>
    `;
    
    sortedData.forEach((item, idx) => {
        const rowBg = idx % 2 === 0 ? 'bg-[#1e293b]' : 'bg-slate-800/30';
        html += `
            <tr class="${rowBg} hover:bg-slate-700/30 transition-colors border-b border-white/5">
                <td class="px-4 py-2 font-medium text-slate-50">${item.date}</td>
                <td class="px-4 py-2 text-right text-slate-50 font-semibold">${(item.count || 0).toLocaleString()}</td>
                <td class="px-4 py-2 text-right">${formatChange(item.eventsChangePct)}</td>
                ${hasUniqueBuckets ? `<td class="px-4 py-2 text-right text-slate-50 font-medium">${(item.unique_buckets || 0).toLocaleString()}</td>` : ''}
                ${hasUniqueBuckets ? `<td class="px-4 py-2 text-right">${formatChange(item.sessionsChangePct)}</td>` : ''}
            </tr>
        `;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

/**
 * Sort period details table
 * @param {string} column - Column to sort by
 */
function sortPeriodDetails(column) {
    if (StatsApp.periodDetailsSortColumn === column) {
        StatsApp.periodDetailsSortDirection = StatsApp.periodDetailsSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        StatsApp.periodDetailsSortColumn = column;
        StatsApp.periodDetailsSortDirection = 'desc';
    }
    renderPeriodDetailsTable();
}

// Make functions globally available
window.createDailyTable = createDailyTable;
window.renderPeriodDetailsTable = renderPeriodDetailsTable;
window.sortPeriodDetails = sortPeriodDetails;
