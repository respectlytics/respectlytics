/**
 * The app's event groups on the dashboard's pages (analytics/event_groups.py decides them).
 *
 * EventGroups.load(url) reads them once from dashboard/groups.py; change(body) saves a change and
 * hands every listener the new groups. name(text) draws an event's or a group's name the same way
 * on every card and page: a group with the group icon and its events in its title, as a button
 * that opens the Event groups panel where the page has one (EventGroups.opens), so it is always
 * plain which names stand for several events.
 */
(function () {
    'use strict';

    const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    // Names are written by every copy of an app and land in attributes: quotes are escaped too.
    const esc = (text) => String(text == null ? '' : text).replace(/[&<>"']/g, c => ESCAPES[c]);

    const state = { groups: [], separate: [], events: [] };
    let byName = new Map();
    let byEvent = new Map();
    let endpoint = null;
    const listeners = [];

    function set(next) {
        state.groups = (next && next.groups) || [];
        state.separate = (next && next.separate) || [];
        state.events = (next && next.events) || [];
        byName = new Map(state.groups.map(g => [g.name, g]));
        byEvent = new Map();
        state.groups.forEach(g => g.events.forEach(e => byEvent.set(e, g)));
        listeners.forEach(fn => fn(state));
    }

    function csrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    async function load(url) {
        endpoint = url;
        try {
            const response = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            if (response.ok) set(await response.json());
        } catch (e) {
            // No groups is a page that still works: every name stands for itself.
        }
        return state;
    }

    async function change(body) {
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                body: JSON.stringify(body)
            });
            const answer = await response.json().catch(() => ({}));
            if (!response.ok) return { error: answer.error || 'The change could not be saved. Try again.' };
            set(answer);
            return answer;
        } catch (e) {
            return { error: 'The change could not be saved. Check your connection and try again.' };
        }
    }

    function events(text) {
        const group = byName.get(text);
        return group ? group.events : [text];
    }

    /**
     * An event's or a group's name as HTML, in the font of the place it sits (`mono` for a list
     * of names). `plain` draws a group without the button, for a place that is itself a control
     * (a checkbox's label); `bare` draws it without its own tint, for a place that already has a
     * box of its own (a step of a path).
     */
    function name(text, { plain = false, bare = false, mono = false } = {}) {
        const font = mono ? 'font-mono' : '';
        const group = byName.get(text);
        if (!group) return font ? `<span class="${font}">${esc(text)}</span>` : esc(text);
        const label = `${group.events.length} events: ${group.events.join(', ')}`;
        const inner = `${window.icon ? window.icon('layers', 'h-3.5 w-3.5 flex-none') : ''}<span class="${font} truncate">${esc(text)}</span>`;
        const classes = bare
            ? 'event-group-name inline-flex max-w-full items-center gap-1 align-middle'
            : 'event-group-name inline-flex max-w-full min-h-6 items-center gap-1 rounded-md bg-indigo-500/15 px-1.5 align-middle text-indigo-200';
        if (plain || !EventGroups.opens) return `<span class="${classes}" title="${esc(label)}">${inner}</span>`;
        const hover = bare ? 'hover:underline underline-offset-2' : 'hover:bg-indigo-500/25';
        return `<button type="button" class="${classes} ${hover} focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400" data-group="${esc(text)}" title="${esc(label)}" aria-label="${esc(text)}, a group of ${label}. Show the event groups">${inner}</button>`;
    }

    /** Names as a person reads them: a group whose every event is among them, by its name. */
    function compress(names) {
        const chosen = new Set(names);
        const out = [];
        names.forEach(n => {
            const group = byEvent.get(n);
            const whole = group && group.events.every(e => chosen.has(e));
            const shown = whole ? group.name : n;
            if (!out.includes(shown)) out.push(shown);
        });
        return out;
    }

    // A group's name anywhere on the page opens the panel at that group
    document.addEventListener('click', (e) => {
        const button = e.target.closest('button[data-group]');
        if (button && EventGroups.opens) {
            e.preventDefault();
            e.stopImmediatePropagation();  // the panel's own click-outside must not close it again
            EventGroups.opens(button.dataset.group, button);
        }
    });

    window.EventGroups = {
        state,
        load,
        change,
        events,
        name,
        compress,
        group: (text) => byName.get(text) || null,
        groupOf: (event) => byEvent.get(event) || null,
        onChange: (fn) => listeners.push(fn),
        opens: null,
        esc
    };
})();
