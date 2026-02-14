/**
 * Stats Dashboard - Charts Module
 *
 * Contains all Chart.js chart creation functions.
 * Dependencies: Chart.js, ChartDataLabels plugin
 */

// Namespace setup
window.StatsApp = window.StatsApp || {};

// Chart instances storage
StatsApp.charts = {};

/**
 * Create Events Over Time chart
 * @param {Array} eventsByPeriod - Array of {date, count, unique_buckets} objects
 */
function createEventsOverTimeChart(eventsByPeriod) {
    const { charts } = StatsApp;
    const { currentDatePreset } = StatsApp.state || { currentDatePreset: 'today' };

    // Destroy existing chart
    if (charts.eventsChart) charts.eventsChart.destroy();

    const container = document.getElementById('eventsChart').parentElement;
    const canvas = document.getElementById('eventsChart');

    // Check for empty data
    if (!eventsByPeriod || eventsByPeriod.length === 0 || eventsByPeriod.every(d => d.count === 0)) {
        canvas.style.display = 'none';
        let emptyMsg = container.querySelector('.empty-state-msg');
        if (!emptyMsg) {
            emptyMsg = document.createElement('div');
            emptyMsg.className = 'empty-state-msg flex flex-col items-center justify-center py-12 text-slate-400';
            emptyMsg.innerHTML = '<div class="text-4xl mb-2">📊</div><div class="text-sm">No events recorded yet</div><div class="text-xs mt-1">Events will appear here as they come in</div>';
            container.appendChild(emptyMsg);
        }
        return;
    }

    // Check if only 1 data point (today view) - show single-day summary instead
    if (eventsByPeriod.length === 1 && currentDatePreset === 'today') {
        canvas.style.display = 'none';
        let singleDayMsg = container.querySelector('.single-day-msg');
        if (!singleDayMsg) {
            singleDayMsg = document.createElement('div');
            singleDayMsg.className = 'single-day-msg flex flex-col items-center justify-center py-8 text-slate-400';
            container.appendChild(singleDayMsg);
        }
        const data = eventsByPeriod[0];
        const sessionsHtml = data.unique_buckets !== undefined
            ? `<div class="mt-2 text-sm"><span class="font-semibold text-emerald-400">${(data.unique_buckets || 0).toLocaleString()}</span> active sessions</div>`
            : '';
        const noteText = 'Select a longer date range to see trends over time';
        singleDayMsg.innerHTML = `
            <div class="text-3xl font-bold text-indigo-400 mb-1">${(data.count || 0).toLocaleString()}</div>
            <div class="text-sm text-slate-400">events today</div>
            ${sessionsHtml}
            <div class="mt-4 text-xs text-slate-500">${noteText}</div>
        `;
        return;
    }

    // Show canvas, hide any messages
    canvas.style.display = 'block';
    const emptyMsg = container.querySelector('.empty-state-msg');
    if (emptyMsg) emptyMsg.remove();
    const singleDayMsg = container.querySelector('.single-day-msg');
    if (singleDayMsg) singleDayMsg.remove();

    const ctx = canvas.getContext('2d');

    // Create subtle gradient for fill
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(99, 102, 241, 0.12)');
    gradient.addColorStop(1, 'rgba(99, 102, 241, 0)');

    // Build datasets - always include events, optionally include unique buckets
    const datasets = [{
        label: 'Events',
        data: eventsByPeriod.map(d => d.count),
        borderColor: '#4F46E5',
        backgroundColor: gradient,
        borderWidth: 2.5,
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: '#4F46E5',
        pointHoverBorderColor: '#fff',
        pointHoverBorderWidth: 2,
        yAxisID: 'y'
    }];

    // Add unique buckets line if data is available
    if (eventsByPeriod.length > 0 && eventsByPeriod[0].unique_buckets !== undefined) {
        const gradient2 = ctx.createLinearGradient(0, 0, 0, 300);
        gradient2.addColorStop(0, 'rgba(16, 185, 129, 0.08)');
        gradient2.addColorStop(1, 'rgba(16, 185, 129, 0)');

        datasets.push({
            label: 'Active Sessions',
            data: eventsByPeriod.map(d => d.unique_buckets),
            borderColor: '#10B981',
            backgroundColor: gradient2,
            borderWidth: 2.5,
            tension: 0.35,
            fill: true,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: '#10B981',
            pointHoverBorderColor: '#fff',
            pointHoverBorderWidth: 2,
            yAxisID: 'y1'
        });
    }

    charts.eventsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: eventsByPeriod.map(d => d.date),
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: datasets.length > 1,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 20,
                        font: { size: 13, weight: '500' }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleFont: { size: 14, weight: '600' },
                    bodyFont: { size: 13 },
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: (context) => {
                            const label = context.dataset.label || '';
                            const value = context.parsed.y || 0;
                            return ` ${label}: ${(value || 0).toLocaleString()}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#94a3b8', font: { size: 13 } }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    beginAtZero: true,
                    ticks: { precision: 0, color: '#94a3b8', font: { size: 13 } },
                    grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
                    title: { display: true, text: 'Events', color: '#94a3b8', font: { size: 14, weight: '600' } }
                },
                y1: {
                    type: 'linear',
                    display: datasets.length > 1,
                    position: 'right',
                    beginAtZero: true,
                    ticks: { precision: 0, color: '#94a3b8', font: { size: 13 } },
                    title: { display: true, text: 'Active Sessions', color: '#94a3b8', font: { size: 14, weight: '600' } },
                    grid: { drawOnChartArea: false }
                }
            }
        }
    });
}

/**
 * Create Daily Sessions & Avg Duration chart (dual-axis)
 * @param {Array} dauData - Array of {date, unique_sessions, avg_session_length_seconds} objects
 */
function createDAUChart(dauData) {
    const { charts } = StatsApp;
    const { currentDatePreset } = StatsApp.state || { currentDatePreset: 'today' };

    if (charts.dauChart) charts.dauChart.destroy();

    const canvas = document.getElementById('dauChart');
    if (!canvas) return;

    const container = canvas.parentElement;

    // Helper to get session count from either field name
    const getSessionCount = (d) => d.unique_buckets || d.unique_sessions || 0;

    // Helper to format duration for tooltip
    const formatDuration = (seconds) => {
        if (!seconds || seconds <= 0) return '-';
        if (seconds < 60) return `${Math.round(seconds)}s`;
        const minutes = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`;
    };

    // Check for empty data
    if (!dauData || dauData.length === 0 || dauData.every(d => getSessionCount(d) === 0)) {
        canvas.style.display = 'none';
        let emptyMsg = container.querySelector('.empty-state-msg');
        if (!emptyMsg) {
            emptyMsg = document.createElement('div');
            emptyMsg.className = 'empty-state-msg flex flex-col items-center justify-center py-12 text-slate-400';
            emptyMsg.innerHTML = '<div class="text-4xl mb-2">👥</div><div class="text-sm">No active sessions yet</div><div class="text-xs mt-1">Session activity will appear here</div>';
            container.appendChild(emptyMsg);
        }
        return;
    }

    // Check if only 1 data point (today view) - show single-day summary
    if (dauData.length === 1 && currentDatePreset === 'today') {
        canvas.style.display = 'none';
        let singleDayMsg = container.querySelector('.single-day-msg');
        if (!singleDayMsg) {
            singleDayMsg = document.createElement('div');
            singleDayMsg.className = 'single-day-msg flex flex-col items-center justify-center py-8 text-slate-400';
            container.appendChild(singleDayMsg);
        }
        const data = dauData[0];
        const durationHtml = data.avg_session_length_seconds
            ? `<div class="mt-2 text-sm"><span class="font-semibold text-purple-400">${formatDuration(data.avg_session_length_seconds)}</span> avg duration</div>`
            : '';
        const noteText = 'Select a longer date range to see trends over time';
        singleDayMsg.innerHTML = `
            <div class="text-3xl font-bold text-emerald-400 mb-1">${getSessionCount(data).toLocaleString()}</div>
            <div class="text-sm text-slate-400">active sessions today</div>
            ${durationHtml}
            <div class="mt-4 text-xs text-slate-500">${noteText}</div>
        `;
        return;
    }

    // Show canvas, hide any messages
    canvas.style.display = 'block';
    const emptyMsg = container.querySelector('.empty-state-msg');
    if (emptyMsg) emptyMsg.remove();
    const singleDayMsg = container.querySelector('.single-day-msg');
    if (singleDayMsg) singleDayMsg.remove();

    // Create gradient for sessions fill
    const context = canvas.getContext('2d');
    const gradient = context.createLinearGradient(0, 0, 0, 250);
    gradient.addColorStop(0, 'rgba(16, 185, 129, 0.15)');
    gradient.addColorStop(1, 'rgba(16, 185, 129, 0)');

    // Check if we have session length data
    const hasSessionLength = dauData.some(d => d.avg_session_length_seconds && d.avg_session_length_seconds > 0);

    // Minimum sessions required for reliable avg duration (avoid outlier spikes)
    const MIN_SESSIONS_FOR_DURATION = 10;

    // Build datasets
    const datasets = [{
        label: 'Sessions',
        data: dauData.map(d => getSessionCount(d)),
        borderColor: '#10B981',
        backgroundColor: gradient,
        borderWidth: 2.5,
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: '#10B981',
        pointHoverBorderColor: '#fff',
        pointHoverBorderWidth: 2,
        yAxisID: 'y'
    }];

    // Add avg session length line if data available
    if (hasSessionLength) {
        datasets.push({
            label: 'Avg Session Length',
            // Null out values with insufficient sample size to avoid misleading spikes
            data: dauData.map(d => {
                const sampleSize = d.sessions_with_duration || getSessionCount(d);
                if (sampleSize < MIN_SESSIONS_FOR_DURATION) return null;
                return d.avg_session_length_seconds || null;
            }),
            borderColor: '#A855F7',
            backgroundColor: 'rgba(168, 85, 247, 0.1)',
            borderWidth: 2,
            borderDash: [5, 5],
            tension: 0.35,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBackgroundColor: '#A855F7',
            pointHoverBorderColor: '#fff',
            pointHoverBorderWidth: 2,
            yAxisID: 'y1'
        });
    }

    charts.dauChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: dauData.map(d => d.date || d.period),
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    display: hasSessionLength,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        pointStyle: 'circle',
                        padding: 16,
                        font: { size: 12, weight: '500' }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleFont: { size: 13, weight: '600' },
                    bodyFont: { size: 12 },
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: (context) => {
                            if (context.datasetIndex === 0) {
                                return ` ${(context.parsed.y || 0).toLocaleString()} sessions`;
                            } else {
                                return ` ${formatDuration(context.parsed.y)} avg duration`;
                            }
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#94a3b8', font: { size: 13 } }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    beginAtZero: true,
                    ticks: { precision: 0, color: '#94a3b8', font: { size: 12 } },
                    grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
                    title: { display: true, text: 'Sessions', color: '#10B981', font: { size: 12, weight: '600' } }
                },
                y1: {
                    type: 'linear',
                    display: hasSessionLength,
                    position: 'right',
                    beginAtZero: true,
                    ticks: {
                        precision: 0,
                        color: '#94a3b8',
                        font: { size: 12 },
                        callback: (value) => formatDuration(value)
                    },
                    title: { display: true, text: 'Avg Duration', color: '#A855F7', font: { size: 12, weight: '600' } },
                    grid: { drawOnChartArea: false }
                }
            }
        }
    });
}

/**
 * Create Events Type distribution chart (horizontal bar)
 */
function createEventsTypeChart(eventsByName) {
    const { charts } = StatsApp;

    if (charts.eventsTypeChart) charts.eventsTypeChart.destroy();

    const canvas = document.getElementById('eventsTypeChart');
    const container = canvas.parentElement;
    const entries = Object.entries(eventsByName || {}).sort((a, b) => b[1] - a[1]).slice(0, 10);

    // Check for empty data
    if (!eventsByName || entries.length === 0 || entries.every(e => e[1] === 0)) {
        canvas.style.display = 'none';
        let emptyMsg = container.querySelector('.empty-state-msg');
        if (!emptyMsg) {
            emptyMsg = document.createElement('div');
            emptyMsg.className = 'empty-state-msg flex flex-col items-center justify-center py-16 text-slate-400';
            emptyMsg.innerHTML = '<div class="text-4xl mb-2">🎯</div><div class="text-sm">No event types recorded</div><div class="text-xs mt-1">Event distribution will appear here</div>';
            container.appendChild(emptyMsg);
        }
        return;
    }

    // Show canvas, hide empty message
    canvas.style.display = 'block';
    const emptyMsg = container.querySelector('.empty-state-msg');
    if (emptyMsg) emptyMsg.remove();

    const ctx = canvas.getContext('2d');

    // Cohesive color palette
    const cohesivePalette = [
        '#4F46E5', '#6366F1', '#818CF8', '#7C3AED', '#8B5CF6',
        '#A78BFA', '#14B8A6', '#2DD4BF', '#5EEAD4', '#99F6E4'
    ];

    const total = entries.reduce((sum, e) => sum + e[1], 0);

    charts.eventsTypeChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: entries.map(e => e[0]),
            datasets: [{
                data: entries.map(e => e[1]),
                backgroundColor: cohesivePalette,
                borderWidth: 0,
                borderRadius: 4,
                barThickness: 24
            }]
        },
        plugins: [ChartDataLabels],
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { right: 60 } },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleFont: { size: 13, weight: '600' },
                    bodyFont: { size: 12 },
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: (context) => ` ${(context.parsed.x || 0).toLocaleString()} events (${((context.parsed.x / total) * 100).toFixed(1)}%)`
                    }
                },
                datalabels: {
                    color: '#f8fafc',
                    font: { weight: '700', size: 13 },
                    anchor: 'end',
                    align: 'right',
                    offset: 4,
                    formatter: (value) => ((value / total) * 100).toFixed(0) + '%'
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
                    ticks: {
                        color: '#94a3b8',
                        font: { size: 13 },
                        callback: function(value) {
                            return value >= 1000 ? (value / 1000).toFixed(0) + 'K' : value;
                        }
                    }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#f8fafc', font: { size: 13, weight: '500' }, padding: 8 }
                }
            }
        }
    });
}

/**
 * Create Countries chart (vertical bar)
 */
function createCountriesChart(topCountries) {
    const { charts } = StatsApp;

    if (charts.countriesChart) charts.countriesChart.destroy();

    const canvas = document.getElementById('countriesChart');
    const container = canvas.parentElement;
    const top10 = (topCountries || []).slice(0, 10);

    // Check for empty data
    if (!topCountries || top10.length === 0 || top10.every(c => c.count === 0)) {
        canvas.style.display = 'none';
        let emptyMsg = container.querySelector('.empty-state-msg');
        if (!emptyMsg) {
            emptyMsg = document.createElement('div');
            emptyMsg.className = 'empty-state-msg flex flex-col items-center justify-center py-16 text-slate-400';
            emptyMsg.innerHTML = '<div class="text-4xl mb-2">🌍</div><div class="text-sm">No geographic data yet</div><div class="text-xs mt-1">Country data will appear as events come in</div>';
            container.appendChild(emptyMsg);
        }
        return;
    }

    // Show canvas, hide empty message
    canvas.style.display = 'block';
    const emptyMsg = container.querySelector('.empty-state-msg');
    if (emptyMsg) emptyMsg.remove();

    const ctx = canvas.getContext('2d');

    // Create gradient for bars
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, '#4F46E5');
    gradient.addColorStop(1, '#6366F1');

    // Helper function to get country flag emoji
    const getCountryFlag = (countryCode) => {
        if (!countryCode || countryCode.length !== 2) return '🌍';
        const codePoints = countryCode.toUpperCase().split('').map(char => 127397 + char.charCodeAt());
        return String.fromCodePoint(...codePoints);
    };

    // Helper function to get country name using Intl.DisplayNames API
    const getCountryName = (countryCode) => {
        if (!countryCode) return 'Unknown';
        try {
            const displayNames = new Intl.DisplayNames(['en'], { type: 'region' });
            return displayNames.of(countryCode.toUpperCase()) || countryCode;
        } catch (e) {
            return countryCode;
        }
    };

    charts.countriesChart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: top10.map(c => c.country),
            datasets: [{
                label: 'Events',
                data: top10.map(c => c.count),
                backgroundColor: gradient,
                borderRadius: 4,
                borderSkipped: false
            }]
        },
        plugins: [ChartDataLabels],
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleFont: { size: 13, weight: '600' },
                    bodyFont: { size: 12 },
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        title: (context) => {
                            const countryCode = context[0].label;
                            const flag = getCountryFlag(countryCode);
                            const name = getCountryName(countryCode);
                            return `${flag} ${name}`;
                        },
                        label: (context) => ` ${(context.parsed.y || 0).toLocaleString()} events`
                    }
                },
                datalabels: {
                    color: '#FFFFFF',
                    font: { weight: '700', size: 13 },
                    anchor: 'center',
                    align: 'center',
                    formatter: (value) => (value || 0) >= 1000 ? ((value || 0) / 1000).toFixed(1) + 'K' : (value || 0).toLocaleString()
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        color: '#f8fafc',
                        font: { size: 11 },
                        callback: function(value, index) {
                            const countryCode = this.getLabelForValue(value);
                            const flag = getCountryFlag(countryCode);
                            const name = getCountryName(countryCode);
                            // Truncate long country names to fit chart
                            const displayName = name.length > 12 ? name.substring(0, 10) + '…' : name;
                            return `${flag} ${displayName}`;
                        }
                    },
                    title: { display: true, text: 'Country', font: { size: 14, weight: '600' }, color: '#94a3b8' }
                },
                y: {
                    beginAtZero: true,
                    ticks: { precision: 0, color: '#94a3b8', font: { size: 13 } },
                    grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
                    title: { display: true, text: 'Event Count', font: { size: 14, weight: '600' }, color: '#94a3b8' }
                }
            }
        }
    });
}

// Make functions globally available
window.createEventsOverTimeChart = createEventsOverTimeChart;
window.createDAUChart = createDAUChart;
window.createEventsTypeChart = createEventsTypeChart;
window.createCountriesChart = createCountriesChart;
