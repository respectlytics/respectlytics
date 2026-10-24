/**
 * The signed-in screens' menus and help (partials/app_bar.html, partials/help.html): a button
 * with data-popover opens the element its aria-controls names on a click or a key, and Esc, a
 * click elsewhere or opening another closes it, giving focus back to its button. One at a time.
 *
 * And "Email us" on every page (partials/email_menu.html, the loheden-design skill, Contact): a
 * link to /email/ opens a small menu with Open in Mail and Copy address; the address is fetched
 * only when Copy address is clicked, so it is in no page, and shows beside "Copied" for anyone
 * whose clipboard refuses.
 */
(function () {
    'use strict';

    let open = null;  // the button whose panel is open

    function close(returnFocus) {
        if (!open) return;
        const panel = document.getElementById(open.getAttribute('aria-controls'));
        if (panel) panel.hidden = true;
        open.setAttribute('aria-expanded', 'false');
        if (returnFocus) open.focus();
        open = null;
    }

    document.addEventListener('click', (e) => {
        const button = e.target.closest('button[data-popover][aria-controls]');
        if (button) {
            const same = button === open;
            close(false);
            if (same) return;
            const panel = document.getElementById(button.getAttribute('aria-controls'));
            if (!panel) return;
            panel.hidden = false;
            button.setAttribute('aria-expanded', 'true');
            open = button;
            return;
        }
        if (open) {
            const panel = document.getElementById(open.getAttribute('aria-controls'));
            if (!panel || !panel.contains(e.target)) close(false);
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && open) close(true);
    });

    // ===== Email us =====
    const mailMenu = document.getElementById('email-menu');
    if (!mailMenu) return;
    const copied = mailMenu.querySelector('[data-copied]');
    let trigger = null;

    function hideMail(focusBack) {
        if (!trigger) return;
        mailMenu.hidden = true;
        copied.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        if (focusBack) trigger.focus();
        trigger = null;
    }

    document.addEventListener('click', (e) => {
        const link = e.target.closest('a[href="/email/"]');
        if (link && !mailMenu.contains(link)) {
            e.preventDefault();
            const same = link === trigger;
            hideMail(false);
            if (same) return;
            trigger = link;
            link.setAttribute('aria-expanded', 'true');
            mailMenu.hidden = false;
            // Under the link, or above it when the window ends below; never past its edges
            const r = link.getBoundingClientRect();
            const w = mailMenu.offsetWidth;
            const h = mailMenu.offsetHeight;
            const left = Math.min(Math.max(8, r.left), document.documentElement.clientWidth - w - 8);
            const top = r.bottom + 6 + h > window.innerHeight && r.top - 6 - h > 0 ? r.top - 6 - h : r.bottom + 6;
            mailMenu.style.left = `${left}px`;
            mailMenu.style.top = `${top}px`;
            mailMenu.querySelector('a').focus({ preventScroll: true });
            return;
        }
        if (trigger && !mailMenu.contains(e.target)) hideMail(false);
    });
    document.querySelectorAll('a[href="/email/"]').forEach((link) => {
        if (mailMenu.contains(link)) return;
        link.setAttribute('aria-haspopup', 'menu');
        link.setAttribute('aria-expanded', 'false');
    });
    mailMenu.querySelector('a').addEventListener('click', () => hideMail(false));
    window.addEventListener('scroll', () => hideMail(false), { passive: true });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideMail(true); });

    mailMenu.querySelector('[data-copy-address]').addEventListener('click', async () => {
        const label = copied.querySelector('[data-copied-label]');
        const shown = copied.querySelector('[data-address]');
        try {
            const answer = await fetch(mailMenu.dataset.addressUrl, { headers: { 'X-Requested-With': 'fetch' }, credentials: 'same-origin' });
            const { address } = await answer.json();
            shown.textContent = address;
            label.textContent = '';
            copied.hidden = false;
            await navigator.clipboard.writeText(address);
            label.textContent = 'Copied';
        } catch (err) {
            // The clipboard refused, or the address could not be fetched: it stays shown and
            // selected, so a keyboard copy takes it
            if (shown.textContent) window.getSelection().selectAllChildren(shown);
        }
    });
})();
