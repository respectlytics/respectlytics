/**
 * The Overview's Last week card (conversion/insight_cards.py): what changed in the app last week,
 * one line per finding with the view that shows it, as the Monday email says it.
 *
 * Always last week, Monday to Sunday in UTC, whatever range the page shows, so it reads the same
 * as the email. A week with nothing notable says so with the week's totals; an app with no week
 * to read yet shows no card. Each finding's link opens its view on that week.
 */
(function () {
    'use strict';

    // One meaning, one icon: the kind of finding
    const ICONS = {
        volume: 'bars',
        drop_off: 'drop',
        gap: 'swap',
        time: 'clock',
        started: 'spark',
        stopped: 'alert',
        silent: 'alert',
        experiment: 'flask'
    };
    // What the link opens, named by what the person sees there
    const LINKS = {
        volume: 'See events',
        started: 'See events',
        stopped: 'See events',
        silent: 'See events',
        drop_off: 'See drop-offs',
        gap: 'See segments',
        time: 'See timing',
        experiment: 'See the test'
    };

    const esc = (text) => (window.EventGroups ? EventGroups.esc(text) : String(text));
    const icon = (name) => (window.icon ? window.icon(name, 'h-4 w-4') : '');

    function weekLabel(week) {
        // "13 to 19 October", or "27 October to 2 November" across months, in UTC as the week is
        const day = (iso) => new Date(`${iso}T00:00:00Z`);
        const start = day(week.start);
        const end = day(week.end);
        const month = (d) => d.toLocaleDateString('en-GB', { month: 'long', timeZone: 'UTC' });
        const first = start.getUTCMonth() === end.getUTCMonth()
            ? `${start.getUTCDate()}`
            : `${start.getUTCDate()} ${month(start)}`;
        return `${first} to ${end.getUTCDate()} ${month(end)}`;
    }

    function render(card, data) {
        const list = card.querySelector('#insightsList');
        card.querySelector('#insightsWeek').textContent = weekLabel(data.week);
        if (data.insights.length) {
            list.innerHTML = data.insights.map(item => `
                <li class="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                    <span class="mt-0.5 flex h-7 w-7 flex-none items-center justify-center rounded-lg bg-white/[0.06] text-slate-300" aria-hidden="true">${icon(ICONS[item.kind] || 'info')}</span>
                    <div class="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                        <p class="min-w-0 text-sm text-slate-200 [&_code]:rounded [&_code]:bg-[#0f172a] [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-sm [&_code]:text-slate-100">${item.html}</p>
                        <a href="${esc(item.view)}" class="flex-none whitespace-nowrap text-sm font-medium text-brand-300 hover:text-brand-200 underline-offset-2 hover:underline">${LINKS[item.kind] || 'See it'}</a>
                    </div>
                </li>`).join('');
        } else {
            const n = (x) => Number(x).toLocaleString();
            list.innerHTML = `<li class="text-sm text-slate-400">Nothing changed enough to report: ${n(data.sessions)} sessions and ${n(data.events)} events.</li>`;
        }
        card.hidden = false;
    }

    async function load() {
        const card = document.getElementById('insightsCard');
        if (!card) return;
        try {
            const response = await fetch(card.dataset.url, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin'
            });
            if (!response.ok) return;
            const data = await response.json();
            if (!data.insights.length && !data.events) return;  // no week to read yet
            render(card, data);
        } catch (e) {
            // The card is extra: without it the Overview is complete
        }
    }

    document.addEventListener('DOMContentLoaded', load);
})();
