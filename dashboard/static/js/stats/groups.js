/**
 * Event groups on the stats page (analytics/event_groups.py decides them, event-groups.js holds
 * them for every card).
 *
 * The Event groups button in the top bar opens one panel, the one place to see and change them:
 * every group with its events and whether the product made it, Show separately and Group again
 * for a group the product made, Remove for one of the owner's, and Group events to put any events
 * together. A group's name on any card opens the panel at that group. Each change is saved at
 * once (dashboard/groups.py); the panel, the Events by Type card and the open tab are drawn again
 * where they are, and the panel stays open. Without the endpoint (StatsApp.state.eventGroupsUrl)
 * the panel only shows.
 *
 * The Events by type card (stats/charts.js) writes each group's events out under its bar, with
 * their counts and shares in the bar's own colours, so nothing waits for the pointer.
 */
(function () {
    'use strict';

    let summary = null;
    let opener = null;
    let busy = false;
    let readyResolve;
    const ready = new Promise(resolve => { readyResolve = resolve; });

    const $ = (id) => document.getElementById(id);
    const esc = (text) => EventGroups.esc(text);
    const url = () => (window.StatsApp && StatsApp.state && StatsApp.state.eventGroupsUrl) || null;
    // The demo reads its groups and changes none (it has no form or footer to change them with)
    const editable = () => Boolean(url()) && !StatsApp.state.eventGroupsReadOnly && Boolean($('eventGroupForm'));
    const icon = (name, size) => (window.icon ? window.icon(name, size) : '');
    const BUTTON = 'flex-none min-h-8 rounded-lg px-2.5 text-xs font-medium text-slate-200 border border-white/15 hover:bg-white/5 transition-colors disabled:opacity-50';

    function say(text) {
        const status = $('eventGroupStatus');
        if (status) status.textContent = text;
    }

    // ---- The Events by Type card ------------------------------------------------------------

    function render(data) {
        // The card draws each group's events with its bar (charts.js). Called with no answer
        // once the groups have loaded, it draws the last one again, its group names now buttons.
        if (data) {
            summary = data;
            return;
        }
        if (summary && window.createEventsTypeChart) {
            window.createEventsTypeChart(summary.events_by_name || {}, summary.event_groups || []);
        }
    }

    async function refresh() {
        const summaryUrl = StatsApp.state.summaryUrl;
        if (!summaryUrl) return;
        const response = await StatsApp.utils.fetchJSON(summaryUrl);
        if (!response.ok) return;
        const data = await response.json();
        render(data);
        window.createEventsTypeChart(data.events_by_name || {}, data.event_groups || []);
    }

    // ---- The panel ----------------------------------------------------------------------------

    function renderPanel() {
        const list = $('eventGroupList');
        if (!list) return;
        const canChange = editable();
        const { groups, separate } = EventGroups.state;
        const rows = groups.map(group => {
            const kind = group.automatic ? 'Grouped automatically' : 'Your group';
            const action = group.automatic
                ? { act: 'separate', label: 'Show separately' }
                : { act: 'remove', label: 'Remove' };
            const button = canChange
                ? `<button type="button" class="${BUTTON}" data-act="${action.act}" data-name="${esc(group.name)}">${action.label}</button>`
                : '';
            const events = group.events.map(e => `<li class="rounded-md bg-[#0f172a] px-1.5 py-0.5 font-mono text-xs text-slate-200">${esc(e)}</li>`).join('');
            return `<section class="-mx-2 px-2 py-3 rounded-lg transition-colors duration-700 focus:outline-none" data-row="${esc(group.name)}" tabindex="-1" aria-label="${esc(group.name)}">
                <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                        <h3 class="flex items-center gap-1.5 text-sm font-semibold text-slate-50">${icon('layers', 'h-4 w-4 flex-none text-indigo-300')}<span class="truncate font-mono">${esc(group.name)}</span></h3>
                        <p class="mt-0.5 text-xs text-slate-400">${kind} · ${group.events.length} events</p>
                    </div>${button}
                </div>
                <ul class="mt-2 flex flex-wrap gap-1.5">${events}</ul>
            </section>`;
        });
        const apart = separate.map(word => `<section class="-mx-2 px-2 py-3" data-row="${esc(word)}">
                <div class="flex items-center justify-between gap-3">
                    <p class="min-w-0 text-sm text-slate-300"><span class="font-mono text-slate-50">${esc(word)}</span> events are shown separately</p>
                    ${canChange ? `<button type="button" class="${BUTTON}" data-act="group_again" data-name="${esc(word)}">Group again</button>` : ''}
                </div>
            </section>`);
        const all = rows.concat(apart);
        list.innerHTML = all.length
            ? all.join('')
            : '<p class="text-sm text-slate-400">No groups yet. Events named as kinds of one event, such as <span class="font-mono text-slate-200">purchase_light</span> and <span class="font-mono text-slate-200">purchase_pro</span>, group themselves.</p>';

        const count = $('eventGroupsCount');
        if (count) {
            count.textContent = groups.length;
            count.hidden = groups.length === 0;
        }
        const button = $('eventGroupsButton');
        if (button) button.setAttribute('aria-label', groups.length ? `Event groups, ${groups.length}` : 'Event groups');
    }

    function isOpen() {
        const panel = $('eventGroupsPanel');
        return panel && !panel.hidden;
    }

    /**
     * Where the panel floats: under the Event groups button while that is in view, otherwise
     * just under the page's sticky header, its right edge in line with the button's and never
     * outside the window, so a group's name far down the page opens it where the reader is.
     */
    function place(panel) {
        const gap = 8;
        const edge = 16;
        const button = $('eventGroupsButton').getBoundingClientRect();
        const header = document.querySelector('body > header');
        const below = header ? header.getBoundingClientRect().bottom : 0;
        const top = Math.max(button.bottom, below) + gap;
        const width = panel.offsetWidth;
        const left = Math.min(Math.max(button.right - width, edge), window.innerWidth - width - edge);
        panel.style.top = `${top}px`;
        panel.style.left = `${Math.max(left, edge)}px`;
        panel.style.maxHeight = `${window.innerHeight - top - edge}px`;
    }

    function openPanel(groupName, from) {
        const panel = $('eventGroupsPanel');
        if (!panel) return;
        opener = from || $('eventGroupsButton');
        // one popover at a time: the conversion events one closes
        const conversion = $('eventStatusPopover');
        if (conversion && conversion.classList.contains('active') && window.toggleEventPopover) window.toggleEventPopover();
        closeForm(false);
        panel.hidden = false;
        place(panel);
        $('eventGroupsButton').setAttribute('aria-expanded', 'true');
        const row = groupName && [...panel.querySelectorAll('[data-row]')].find(r => r.dataset.row === groupName);
        if (row) {
            row.scrollIntoView({ block: 'nearest' });  // inside the panel's list
            // the group asked for, tinted for a moment so the eye finds it
            row.classList.add('bg-indigo-500/15');
            setTimeout(() => row.classList.remove('bg-indigo-500/15'), 1600);
            row.focus({ preventScroll: true });
        } else {
            $('eventGroupsClose').focus();
        }
        setTimeout(() => document.addEventListener('click', closeOnClickOutside), 0);
    }

    function closePanel(returnFocus = true) {
        const panel = $('eventGroupsPanel');
        if (!panel || panel.hidden) return;
        panel.hidden = true;
        $('eventGroupsButton').setAttribute('aria-expanded', 'false');
        document.removeEventListener('click', closeOnClickOutside);
        if (returnFocus && opener && document.body.contains(opener)) opener.focus();
    }

    function closeOnClickOutside(e) {
        const panel = $('eventGroupsPanel');
        if (panel.contains(e.target) || $('eventGroupsButton').contains(e.target)) return;
        closePanel(false);
    }

    // ---- Group events -------------------------------------------------------------------------

    function openForm() {
        const { events } = EventGroups.state;
        $('eventGroupChoices').innerHTML = events.map((name, i) => {
            const group = EventGroups.groupOf(name);
            const note = group ? `<span class="flex-none text-xs text-slate-400">in ${esc(group.name)}</span>` : '';
            return `<label class="flex items-center gap-2.5 text-sm text-slate-200" for="eventGroupChoice${i}">
                <input type="checkbox" name="event" value="${esc(name)}" id="eventGroupChoice${i}"
                    class="h-4 w-4 flex-none rounded border-white/30 bg-[#0f172a] text-indigo-500 focus:ring-indigo-500">
                <span class="min-w-0 truncate font-mono">${esc(name)}</span>${note}
            </label>`;
        }).join('') || '<p class="text-sm text-slate-400">Your app has not sent any events yet.</p>';
        $('eventGroupError').hidden = true;
        $('eventGroupName').value = '';
        $('eventGroupList').hidden = true;
        $('eventGroupFooter').hidden = true;
        $('eventGroupForm').hidden = false;
        $('eventGroupName').focus();
    }

    function closeForm(focus = true) {
        const form = $('eventGroupForm');
        if (!form || form.hidden) return;
        form.hidden = true;
        $('eventGroupList').hidden = false;
        $('eventGroupFooter').hidden = !editable();
        if (focus) $('eventGroupNew').focus();
    }

    function showError(text) {
        const error = $('eventGroupError');
        error.textContent = text;
        error.hidden = false;
    }

    // ---- After a change -----------------------------------------------------------------------

    function redrawTabs() {
        // Events by Type, and the tabs whose names are read through the groups
        refresh();
        if (StatsApp.tabDataCache) {
            delete StatsApp.tabDataCache.conversion;
            delete StatsApp.tabDataCache.behavior;
        }
        if (['conversion', 'behavior'].includes(StatsApp.currentTab) && window.loadTabData) {
            window.loadTabData(StatsApp.currentTab);
        }
    }

    async function act(body) {
        if (busy) return null;
        busy = true;
        try {
            const answer = await EventGroups.change(body);
            if (!answer.error) say('Saved');
            return answer;
        } finally {
            busy = false;
        }
    }

    function init() {
        const panel = $('eventGroupsPanel');
        if (!panel) {
            readyResolve();
            return;
        }
        EventGroups.opens = openPanel;
        EventGroups.onChange(renderPanel);
        const loading = url() ? EventGroups.load(url()) : Promise.resolve();
        loading.then(() => {
            renderPanel();
            render();
            // a change after this redraws what reads the groups
            EventGroups.onChange(() => { render(); redrawTabs(); });
            readyResolve();
        });

        $('eventGroupsButton').addEventListener('click', () => (isOpen() ? closePanel() : openPanel()));
        window.addEventListener('resize', () => { if (isOpen()) place(panel); });
        $('eventGroupsClose').addEventListener('click', () => closePanel());
        panel.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return;
            e.stopPropagation();
            const form = $('eventGroupForm');
            if (form && !form.hidden) closeForm();
            else closePanel();
        });
        if (!editable()) return;

        $('eventGroupFooter').hidden = false;
        $('eventGroupNew').addEventListener('click', openForm);
        $('eventGroupCancel').addEventListener('click', () => closeForm());
        $('eventGroupForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = $('eventGroupName').value.trim();
            const events = [...document.querySelectorAll('#eventGroupChoices input:checked')].map(i => i.value);
            if (!name) return showError('Give the group a name.');
            if (events.length < 2) return showError('Choose at least two events for the group.');
            const answer = await act({ action: 'create', name, events });
            if (!answer) return;
            if (answer.error) return showError(answer.error);
            closeForm(false);
            const row = [...$('eventGroupList').querySelectorAll('[data-row]')].find(r => r.dataset.row === name);
            if (row) row.focus();
        });
        $('eventGroupList').addEventListener('click', async (e) => {
            const button = e.target.closest('button[data-act]');
            if (!button) return;
            const name = button.dataset.name;
            button.disabled = true;
            const answer = await act({ action: button.dataset.act, name });
            if (!answer || answer.error) {
                button.disabled = false;
                if (answer) {
                    say(answer.error);
                    if (window.showToast) window.showToast(answer.error, 'error');
                }
                return;
            }
            // the row's new control (Group again, Show separately) keeps the focus where it was
            const next = [...$('eventGroupList').querySelectorAll('button[data-name]')].find(b => b.dataset.name === name);
            (next || $('eventGroupsClose')).focus();
        });
    }

    window.StatsApp = window.StatsApp || {};
    StatsApp.groups = { render, refresh, ready, open: openPanel };
    document.addEventListener('DOMContentLoaded', init);
})();
