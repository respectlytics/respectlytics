/**
 * The Overview's charts and ranked lists (partials/stats/_tab_overview.html).
 *
 * Over time is three small charts of one series each (events, sessions, average session), in the
 * brand's colour, with dates written "Oct 3" through StatsApp.utils.formatPeriod, lying flat and
 * thinned out to about 6 on a phone and 10 on a desktop. Ranked data (events by type, countries)
 * is a list of bars with each name written out in full and its figure beside it, so nothing is
 * cut off and nothing waits for the pointer. Dependencies: Chart.js (chart-theme.js sets its look).
 */

window.StatsApp = window.StatsApp || {};
StatsApp.charts = {};

const BRAND = '#6366f1';                 // brand-500, the one series colour
const TINTS = ['#6366f1', '#818cf8', '#a5b4fc', '#c7d2fe'];  // a group's events, lighter in turn

/** The x axis of a chart over time: dates flat, as many as fit. */
StatsApp.chartAxis = function(labels) {
    return {
        grid: { display: false },
        border: { display: false },
        ticks: {
            color: '#94a3b8',
            maxRotation: 0,
            autoSkip: true,
            autoSkipPadding: 12,
            maxTicksLimit: window.innerWidth < 640 ? 6 : 10,
            callback: (value, index) => StatsApp.utils.formatPeriod(labels[index])
        }
    };
};

/**
 * One series over time on a canvas, in the brand's colour. Points that are null (an average
 * from too few sessions) leave a gap rather than a spike.
 */
function lineChart(id, labels, values, { format = (v) => (v || 0).toLocaleString(), tick = null, stepSize = undefined } = {}) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    if (StatsApp.charts[id]) StatsApp.charts[id].destroy();
    const ctx = canvas.getContext('2d');
    const fill = ctx.createLinearGradient(0, 0, 0, 240);
    fill.addColorStop(0, 'rgba(99, 102, 241, 0.22)');
    fill.addColorStop(1, 'rgba(99, 102, 241, 0)');
    const few = labels.length <= 8;
    StatsApp.charts[id] = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                data: values,
                borderColor: BRAND,
                backgroundColor: fill,
                borderWidth: 2,
                tension: 0.3,
                fill: true,
                spanGaps: false,
                pointRadius: few ? 3 : 0,
                pointBackgroundColor: BRAND,
                pointHoverRadius: 4,
                pointHoverBackgroundColor: BRAND,
                pointHoverBorderColor: '#f8fafc',
                pointHoverBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            layout: { padding: { top: 4 } },
            plugins: {
                tooltip: {
                    callbacks: {
                        title: (items) => StatsApp.utils.formatPeriod(labels[items[0].dataIndex], { long: true }),
                        label: (context) => context.parsed.y === null ? 'Too few sessions' : format(context.parsed.y)
                    }
                }
            },
            scales: {
                x: StatsApp.chartAxis(labels),
                y: {
                    beginAtZero: true,
                    border: { display: false },
                    grid: { color: 'rgba(255, 255, 255, 0.06)' },
                    ticks: {
                        color: '#94a3b8',
                        precision: 0,
                        maxTicksLimit: 5,
                        stepSize,
                        callback: tick || ((value) => (value >= 1000 ? `${+(value / 1000).toFixed(1)}K` : value))
                    }
                }
            }
        }
    });
}

/** "4m 1s", "45s"; "-" for none. */
function shortDuration(seconds) {
    if (!seconds || seconds <= 0) return '-';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`;
}

/**
 * The Over time card: events, sessions and the average session per period. One period (Today)
 * has no trend to draw, so the card says so once and offers a longer range.
 * @param {Array} points - [{date, count, unique_sessions, avg_session_length_seconds, sessions_with_duration}], oldest first
 */
function renderOverTime(points) {
    const charts = document.getElementById('overTimeCharts');
    const note = document.getElementById('overTimeNote');
    if (!charts || !note) return;
    const data = points || [];
    const hasEvents = data.some(p => (p.count || 0) > 0);
    // Today is one day, whichever days its hours fall on in UTC
    const oneDay = (StatsApp.state && StatsApp.state.currentDatePreset === 'today') || data.length < 2;
    if (!hasEvents || oneDay) {
        charts.hidden = true;
        note.hidden = false;
        note.querySelector('[data-note-text]').textContent = !hasEvents
            ? 'No events in this range yet.'
            : 'A trend needs more than one day.';
        note.querySelector('[data-note-action]').hidden = !hasEvents;
        return;
    }
    charts.hidden = false;
    note.hidden = true;
    const labels = data.map(p => p.date);
    lineChart('eventsChart', labels, data.map(p => p.count || 0), {
        format: (v) => `${v.toLocaleString()} events`
    });
    lineChart('dauChart', labels, data.map(p => p.unique_sessions || 0), {
        format: (v) => `${v.toLocaleString()} sessions`
    });
    // An average from fewer than 10 sessions is left out rather than drawn as a spike
    const durations = data.map(p => {
        const sample = p.sessions_with_duration !== undefined ? p.sessions_with_duration : (p.unique_sessions || 0);
        return sample >= 10 && p.avg_session_length_seconds ? p.avg_session_length_seconds : null;
    });
    const durationEmpty = document.getElementById('durationEmpty');
    const durationBox = document.getElementById('durationChart')?.parentElement;
    const anyDuration = durations.some(v => v !== null);
    if (durationEmpty) durationEmpty.hidden = anyDuration;
    if (durationBox) durationBox.hidden = !anyDuration;
    if (anyDuration) {
        // ticks on whole minutes (or seconds for short sessions), at most four of them
        const longest = Math.max(...durations.filter(v => v !== null), 1);
        const stepSize = [15, 30, 60, 120, 300, 600, 900, 1800, 3600].find(step => longest / step <= 4) || 3600;
        lineChart('durationChart', labels, durations, {
            format: (v) => `${shortDuration(v)} on average`,
            tick: (value) => (value ? shortDuration(value) : '0'),
            stepSize
        });
    }
}

/**
 * One row of a ranked list: the name in full, its figure at the right, and a bar under it whose
 * parts are the row's share of the largest row (a group's events in lighter steps).
 * @param {{name: string, value: string, parts: Array<{pct: number, color?: string}>, extra?: string, quiet?: boolean}} row
 *        name and value are HTML the caller has escaped
 */
StatsApp.barRow = function(row) {
    const fills = row.parts.map(p => `<span class="bar-fill${row.quiet ? ' is-quiet' : ''}" style="width:${Math.max(0, Math.min(100, p.pct)).toFixed(2)}%${p.color && !row.quiet ? `;background:${p.color}` : ''}"></span>`).join('');
    return `<li class="py-2.5 first:pt-0 last:pb-0">
        <div class="flex items-baseline justify-between gap-4">
            <span class="min-w-0 break-words text-sm text-slate-100">${row.name}</span>
            <span class="flex-none text-sm text-slate-50">${row.value}</span>
        </div>
        <span class="bar-track mt-1.5" aria-hidden="true">${fills}</span>
        ${row.extra || ''}
    </li>`;
};

/**
 * Events by type: one bar per group (analytics/event_groups.py), split into its events in
 * lighter steps of the brand's colour and written out under it, and one per event in no group;
 * the ten largest, each with its share of every event in the range.
 */
function createEventsTypeChart(eventsByName, eventGroups) {
    const list = document.getElementById('eventsTypeList');
    if (!list) return;
    const esc = StatsApp.utils.escapeHtml;
    const groups = eventGroups || [];
    const inGroup = new Set(groups.flatMap(g => g.events.map(e => e.event_name)));
    const all = [
        ...groups.map(g => ({ label: g.name, total: g.total, group: true,
                              parts: g.events.map(e => [e.event_name, e.count]) })),
        ...Object.entries(eventsByName || {}).filter(([name]) => !inGroup.has(name))
            .map(([name, count]) => ({ label: name, total: count, group: false, parts: [[name, count]] }))
    ].sort((a, b) => b.total - a.total);
    const rows = all.slice(0, 10);
    const total = all.reduce((sum, r) => sum + r.total, 0);

    if (!rows.length || total === 0) {
        StatsApp.state.eventTypeRows = [];
        list.innerHTML = '<li class="py-6 text-sm text-slate-400">No events in this range yet.</li>';
        return;
    }
    rows.forEach(row => { row.colors = row.parts.map((_, k) => TINTS[Math.min(k, TINTS.length - 1)]); });
    StatsApp.state.eventTypeRows = rows;
    const largest = rows[0].total || 1;
    const share = (n, of) => `${Math.round((n / of) * 100)}%`;

    list.innerHTML = rows.map(row => {
        const name = row.group && window.EventGroups ? EventGroups.name(row.label) : esc(row.label);
        const extra = row.group && row.parts.length > 1
            ? `<ul class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-300">${row.parts.map(([event, count], k) => `
                <li class="flex min-w-0 max-w-full items-center gap-1.5">
                    <span class="h-2 w-2 flex-none rounded-sm" style="background:${row.colors[k]}" aria-hidden="true"></span>
                    <span class="break-all font-mono">${esc(event)}</span>
                    <span class="flex-none whitespace-nowrap text-slate-400">${count.toLocaleString()} · ${share(count, row.total || 1)}</span>
                </li>`).join('')}</ul>`
            : '';
        return StatsApp.barRow({
            name,
            value: `${row.total.toLocaleString()} <span class="ml-1 text-slate-400">${share(row.total, total)}</span>`,
            parts: row.parts.map(([, count], k) => ({ pct: (count / largest) * 100, color: row.colors[k] })),
            extra
        });
    }).join('');
}

/**
 * The Countries card's list: each country with its flag, its sessions and, where conversion
 * events are chosen, the share of its sessions that converted; the five with most sessions,
 * and every one behind Show all.
 * @param {Array} countries - [{country, count, sessions, conversions, conversion_rate}], rate in percent
 */
function renderCountriesList(countries) {
    const list = document.getElementById('countriesList');
    const more = document.getElementById('countriesMore');
    const rateHead = document.getElementById('countriesRateHead');
    if (!list) return;
    const esc = StatsApp.utils.escapeHtml;
    // the page's chosen conversions (stats.html, filters.js)
    const withRate = (typeof selectedConversionEvents !== 'undefined' ? selectedConversionEvents : []).length > 0;
    const rows = [...(countries || [])]
        .filter(c => c && c.country && ((c.sessions || 0) > 0 || (c.count || 0) > 0))
        .sort((a, b) => (b.sessions || 0) - (a.sessions || 0) || (b.count || 0) - (a.count || 0));
    if (rateHead) rateHead.hidden = !withRate;
    if (!rows.length) {
        list.innerHTML = `<tr><td colspan="3" class="py-6 text-slate-400">No sessions with a country in this range yet.</td></tr>`;
        if (more) more.hidden = true;
        return;
    }
    const open = list.dataset.all === '1';
    const shown = open ? rows : rows.slice(0, 5);
    list.innerHTML = shown.map(c => `
        <tr>
            <td class="whitespace-normal">
                <span class="flex items-center gap-2"><span class="flex-none text-base leading-none" aria-hidden="true">${StatsApp.utils.getCountryFlag(c.country)}</span><span class="min-w-0 text-slate-100">${esc(StatsApp.utils.getCountryName(c.country))}</span></span>
            </td>
            <td class="text-right">${(c.sessions || 0).toLocaleString()}</td>
            ${withRate ? `<td class="text-right">${(c.conversion_rate || 0).toFixed(1)}%</td>` : ''}
        </tr>`).join('');
    if (more) {
        more.hidden = rows.length <= 5;
        more.textContent = open ? 'Show fewer' : `Show all ${rows.length} countries`;
        more.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
}

function toggleCountriesList() {
    const list = document.getElementById('countriesList');
    if (!list) return;
    list.dataset.all = list.dataset.all === '1' ? '' : '1';
    renderCountriesList(StatsApp.state.countries || []);
}

window.renderOverTime = renderOverTime;
window.createEventsTypeChart = createEventsTypeChart;
window.renderCountriesList = renderCountriesList;
window.toggleCountriesList = toggleCountriesList;
