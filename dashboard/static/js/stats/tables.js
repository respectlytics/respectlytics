/**
 * The Overview's By day (or week, or month) table: each period's events and sessions with the
 * change from the period before, written as an arrow and the percentage in colour, so the change
 * never rests on colour alone. The latest 7 periods first, and every one behind Show all; each
 * column sorts from its header button.
 */

window.StatsApp = window.StatsApp || {};

StatsApp.periodDetailsData = [];
StatsApp.periodDetailsSortColumn = 'date';
StatsApp.periodDetailsSortDirection = 'desc';
StatsApp.periodDetailsAll = false;

const PERIOD_ROWS = 7;

/**
 * @param {Array} eventsByPeriod - [{date, count, unique_sessions}], oldest first
 */
function createDailyTable(eventsByPeriod) {
    const container = document.getElementById('dailyTable');
    if (!container) return;
    if (!eventsByPeriod || eventsByPeriod.length === 0 || eventsByPeriod.every(d => !d.count)) {
        StatsApp.periodDetailsData = [];
        container.innerHTML = '<p class="py-6 text-sm text-slate-400">No events in this range yet.</p>';
        const more = document.getElementById('dailyTableMore');
        if (more) more.hidden = true;
        return;
    }
    StatsApp.periodDetailsData = [...eventsByPeriod];
    renderPeriodDetailsTable();
}

function changeFrom(now, before) {
    if (before === undefined || before === null) return null;
    if (before > 0) return ((now - before) / before) * 100;
    return now > 0 ? Infinity : 0;
}

function formatChange(pct) {
    if (pct === null) return '';
    if (pct === Infinity) return '<span class="text-slate-400">from 0</span>';
    if (Math.abs(pct) < 0.05) return '<span class="text-slate-400">0%</span>';
    const up = pct > 0;
    return `<span class="${up ? 'text-emerald-300' : 'text-rose-300'}"><span aria-hidden="true">${up ? '▲' : '▼'}</span><span class="sr-only">${up ? 'Up' : 'Down'}</span> ${Math.abs(pct).toFixed(1)}%</span>`;
}

function renderPeriodDetailsTable() {
    const container = document.getElementById('dailyTable');
    const data = StatsApp.periodDetailsData;
    if (!container || !data || !data.length) return;
    const column = StatsApp.periodDetailsSortColumn;
    const direction = StatsApp.periodDetailsSortDirection;

    const rows = data.map((item, i) => ({
        ...item,
        sessions: item.unique_sessions || 0,
        eventsChange: i === 0 ? null : changeFrom(item.count || 0, data[i - 1].count || 0),
        sessionsChange: i === 0 ? null : changeFrom(item.unique_sessions || 0, data[i - 1].unique_sessions || 0)
    }));
    const value = (row) => {
        switch (column) {
            case 'events': return row.count || 0;
            case 'sessions': return row.sessions;
            case 'eventsChange': return row.eventsChange === null ? -Infinity : row.eventsChange;
            case 'sessionsChange': return row.sessionsChange === null ? -Infinity : row.sessionsChange;
            default: return row.date;
        }
    };
    rows.sort((a, b) => {
        const x = value(a);
        const y = value(b);
        if (typeof x === 'string') return direction === 'asc' ? x.localeCompare(y) : y.localeCompare(x);
        return direction === 'asc' ? x - y : y - x;
    });
    const shown = StatsApp.periodDetailsAll ? rows : rows.slice(0, PERIOD_ROWS);

    const arrow = (key) => {
        const sorted = column === key;
        const down = !sorted || direction === 'desc';
        return `<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="${down ? 'M5 8l5 5 5-5H5z' : 'M5 12l5-5 5 5H5z'}"/></svg>`;
    };
    const head = (key, label, align) => {
        const sorted = column === key;
        const sort = sorted ? (direction === 'asc' ? 'ascending' : 'descending') : 'none';
        return `<th scope="col" class="${align}" aria-sort="${sort}">
            <button type="button" class="sort-button" onclick="sortPeriodDetails('${key}')"${sorted ? ' data-sorted' : ''}>${label}${arrow(key)}</button>
        </th>`;
    };
    const first = { day: 'Day', week: 'Week', month: 'Month' }[StatsApp.state.currentGranularity] || 'Day';

    container.innerHTML = `
        <table class="stats-table">
            <thead><tr>
                ${head('date', first, 'text-left')}
                ${head('events', 'Events', 'text-right')}
                ${head('eventsChange', 'Change', 'text-right')}
                ${head('sessions', 'Sessions', 'text-right')}
                ${head('sessionsChange', 'Change', 'text-right')}
            </tr></thead>
            <tbody>${shown.map(row => `
                <tr>
                    <td class="text-slate-100">${StatsApp.utils.formatPeriod(row.date, { long: true })}</td>
                    <td class="text-right text-slate-50">${(row.count || 0).toLocaleString()}</td>
                    <td class="text-right">${formatChange(row.eventsChange)}</td>
                    <td class="text-right text-slate-50">${row.sessions.toLocaleString()}</td>
                    <td class="text-right">${formatChange(row.sessionsChange)}</td>
                </tr>`).join('')}
            </tbody>
        </table>`;

    // Every row scrolls inside the card, its header in view, rather than lengthening the page
    container.classList.toggle('scroll-box', Boolean(StatsApp.periodDetailsAll));
    const more = document.getElementById('dailyTableMore');
    if (more) {
        more.hidden = rows.length <= PERIOD_ROWS;
        const unit = { day: 'days', week: 'weeks', month: 'months' }[StatsApp.state.currentGranularity] || 'days';
        more.textContent = StatsApp.periodDetailsAll ? 'Show fewer' : `Show all ${rows.length} ${unit}`;
        more.setAttribute('aria-expanded', StatsApp.periodDetailsAll ? 'true' : 'false');
    }
}

function sortPeriodDetails(column) {
    if (StatsApp.periodDetailsSortColumn === column) {
        StatsApp.periodDetailsSortDirection = StatsApp.periodDetailsSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        StatsApp.periodDetailsSortColumn = column;
        StatsApp.periodDetailsSortDirection = 'desc';
    }
    renderPeriodDetailsTable();
    // the header that was pressed keeps the focus after the table is drawn again
    const button = document.querySelector(`#dailyTable button[onclick="sortPeriodDetails('${column}')"]`);
    if (button) button.focus();
}

function togglePeriodDetails() {
    StatsApp.periodDetailsAll = !StatsApp.periodDetailsAll;
    renderPeriodDetailsTable();
}

window.createDailyTable = createDailyTable;
window.renderPeriodDetailsTable = renderPeriodDetailsTable;
window.sortPeriodDetails = sortPeriodDetails;
window.togglePeriodDetails = togglePeriodDetails;
