/**
 * Stats Utilities Module
 * Common utility functions used across the stats page
 */

window.StatsApp = window.StatsApp || {};

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

StatsApp.utils = {
    /**
     * Get the user's timezone name (IANA format).
     * This is used to send the user's local timezone to the backend
     * so that "Today" and other date ranges are interpreted correctly.
     * @returns {string} - IANA timezone name (e.g., 'America/New_York', 'Europe/Stockholm')
     */
    /**
     * The timezone a link asked for: the weekly email opens its week in UTC (?tz=UTC), so the
     * figures match the email's. Null when the page was opened any other way.
     * @returns {string|null}
     */
    linkedTimezone: function() {
        try {
            return new URLSearchParams(window.location.search).get('tz') === 'UTC' ? 'UTC' : null;
        } catch (e) {
            return null;
        }
    },

    getUserTimezone: function() {
        const linked = StatsApp.utils.linkedTimezone();
        if (linked) return linked;
        try {
            return Intl.DateTimeFormat().resolvedOptions().timeZone;
        } catch (e) {
            console.warn('Could not detect user timezone, falling back to UTC:', e);
            return 'UTC';
        }
    },

    /**
     * Append timezone parameter to a URL.
     * @param {string} url - URL to augment
     * @returns {string} - URL with tz=<timezone> param appended
     */
    addTimezoneParam: function(url) {
        if (!url) return url;
        const tz = StatsApp.utils.getUserTimezone();
        const separator = url.includes('?') ? '&' : '?';
        return `${url}${separator}tz=${encodeURIComponent(tz)}`;
    },

    /**
     * Format a Date object as YYYY-MM-DD string in local timezone (not UTC).
     * This avoids the timezone bug where toISOString() can shift dates by a day.
     * @param {Date} date - The date to format
     * @returns {string} - Date string in YYYY-MM-DD format
     */
    formatLocalDate: function(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    },

    /**
     * Escape HTML special characters to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} - Escaped text safe for HTML insertion
     */
    escapeHtml: function(text) {
        // Quotes as well as markup: event names are written by every copy of an app, anyone who
        // pulls the app key out of one can send any name, and names land in attributes
        // (title="...", value="..."), where a bare quote would end the attribute.
        if (text === null || text === undefined) return '';
        return String(text).replace(/[&<>"']/g, c => ESCAPES[c]);
    },

    /**
     * The English name of a country from its ISO 3166-1 alpha-2 code, read from the browser
     * (Intl.DisplayNames), so every screen names countries the same way; getCountryFlag below
     * draws the flag beside it.
     * @param {string} countryCode - ISO 3166-1 alpha-2 country code
     * @returns {string} - The country's name, the code itself if the browser has none, or 'Unknown'
     */
    getCountryName: function(countryCode) {
        if (!countryCode) return 'Unknown';
        try {
            const names = new Intl.DisplayNames(['en'], { type: 'region' });
            return names.of(countryCode.toUpperCase()) || countryCode;
        } catch (e) {
            return countryCode;
        }
    },

    /**
     * The country's flag, drawn by the system from its two-letter code, for beside its name
     * (owner, 2026-10-24: flags stay wherever a country is named), or '' without a code.
     * @param {string} countryCode - ISO 3166-1 alpha-2 country code
     * @returns {string} - The flag, or ''
     */
    getCountryFlag: function(countryCode) {
        if (!countryCode || countryCode.length !== 2) return '';
        return String.fromCodePoint(...countryCode.toUpperCase().split('').map(c => 127397 + c.charCodeAt(0)));
    },

    /**
     * The one way a period is written on this page, in charts, tables and labels: a day as
     * "Oct 3", a week by its first day ("Oct 3", or with `long` its days, "Oct 3-9"), a month as
     * "Oct 2026", a quarter as "Q4 2026". Read from the period's own shape (2026-10-03,
     * 2026-W40, 2026-10, 2026-Q4), so a label never depends on which control asked for it.
     * @param {string} period - The period as the API writes it
     * @param {{long?: boolean}} options
     * @returns {string}
     */
    formatPeriod: function(period, { long = false } = {}) {
        if (!period) return '';
        const text = String(period);
        const short = (d) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        let m = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (m) return short(new Date(+m[1], +m[2] - 1, +m[3]));
        m = text.match(/^(\d{4})-W(\d{2})$/);
        if (m) {
            // ISO weeks: week 1 holds 4 January, and a week starts on Monday
            const jan4 = new Date(+m[1], 0, 4);
            const start = new Date(+m[1], 0, 4 - ((jan4.getDay() + 6) % 7) + (+m[2] - 1) * 7);
            if (!long) return short(start);
            const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6);
            return start.getMonth() === end.getMonth()
                ? `${short(start)}-${end.getDate()}`
                : `${short(start)}-${short(end)}`;
        }
        m = text.match(/^(\d{4})-(\d{2})$/);
        if (m) return new Date(+m[1], +m[2] - 1, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
        m = text.match(/^(\d{4})-Q(\d)$/);
        if (m) return `Q${m[2]} ${m[1]}`;
        return text;
    },

    /**
     * A segment's name as people write it: iOS, Android, Web and Unknown for a platform, the
     * country's name for a country (getCountryName), the value itself otherwise. Plain text:
     * the caller escapes it.
     * @param {string} segment - The segment as the API names it
     * @param {string} type - platform, country, depth, hour or property:<name>
     * @returns {string}
     */
    segmentName: function(segment, type) {
        const value = segment === null || segment === undefined ? '' : String(segment);
        if (type === 'platform') {
            const known = { ios: 'iOS', android: 'Android', web: 'Web', macos: 'macOS', unknown: 'Unknown', '': 'Unknown' };
            return known[value.toLowerCase()] || value;
        }
        if (type === 'country') return value && value !== 'Unknown' ? StatsApp.utils.getCountryName(value) : 'Unknown';
        if (type === 'depth') return `${value} ${value === '1' ? 'event' : 'events'}`;
        return value || 'Unknown';
    },

    /**
     * A share as a percentage with as many decimals as a small one needs: 12.3%, 0.45%, 0.012%.
     * @param {number} rate - Between 0 and 1
     * @returns {string}
     */
    formatRate: function(rate) {
        const pct = (rate || 0) * 100;
        if (pct >= 1) return pct.toFixed(1) + '%';
        if (pct >= 0.1) return pct.toFixed(2) + '%';
        if (pct > 0) return pct.toFixed(3) + '%';
        return '0%';
    },

    /**
     * Get CSRF token from cookies for POST requests
     * @returns {string} - CSRF token
     */
    getCsrfToken: function() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    },

    /**
     * Format a number with locale-aware formatting
     * @param {number} num - Number to format
     * @returns {string} - Formatted number string
     */
    formatNumber: function(num) {
        if (num === null || num === undefined) return '-';
        const n = Number(num);
        return Number.isFinite(n) ? n.toLocaleString() : '0';
    },

    /**
     * Format a percentage value
     * @param {number} value - Value between 0-100
     * @param {number} decimals - Number of decimal places
     * @returns {string} - Formatted percentage string
     */
    formatPercent: function(value, decimals = 1) {
        if (value === null || value === undefined) return '-';
        return `${value.toFixed(decimals)}%`;
    },

    /**
     * Format duration in human-readable format
     * @param {number} seconds - Duration in seconds
     * @returns {string} - Formatted duration string
     */
    formatDuration: function(seconds) {
        if (seconds === null || seconds === undefined) return '-';
        if (seconds < 60) return `${Math.round(seconds)}s`;
        if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
        return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
    },

    /**
     * Append a cache-busting query param to ensure fresh API responses.
     * @param {string} url - URL to augment
     * @returns {string} - URL with _=timestamp param appended
     */
    addCacheBuster: function(url) {
        if (!url) return url;
        const separator = url.includes('?') ? '&' : '?';
        return `${url}${separator}_=${Date.now()}`;
    },

    /**
     * Fetch helper that forces network requests (no cached responses).
     * @param {string} url - Request URL
     * @param {RequestInit} options - Additional fetch options
     * @returns {Promise<Response>} - Fetch response promise
     */
    fetchJSON: function(url, options = {}) {
        const finalUrl = StatsApp.utils.addCacheBuster(url);
        const defaultOptions = {
            cache: 'no-store',
            headers: {
                'Cache-Control': 'no-cache'
            }
        };
        const mergedHeaders = {
            ...defaultOptions.headers,
            ...(options.headers || {})
        };
        return fetch(finalUrl, {
            ...defaultOptions,
            ...options,
            headers: mergedHeaders
        });
    },

    /**
     * Debounce a function call
     * @param {Function} func - Function to debounce
     * @param {number} wait - Wait time in milliseconds
     * @returns {Function} - Debounced function
     */
    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * Build a storage key for persisting date filters per app.
     * @returns {string|null}
     */
    getDateFilterStorageKey: function() {
        try {
            const state = StatsApp.state || {};
            const slug = state.appSlug || state.appKey || (typeof StatsConfig !== 'undefined' ? (StatsConfig.appSlug || StatsConfig.appKey) : null);
            if (!slug) return null;
            return `stats-filters-${slug}`;
        } catch (error) {
            return null;
        }
    },

    /**
     * Persist the current date filter selection to localStorage.
     * @param {{preset: string, from: string|null, to: string|null}} state
     */
    saveDateFilterState: function(state) {
        try {
            if (typeof window === 'undefined' || !window.localStorage) return;
            // The public demo keeps nothing in a visitor's browser: its range is always 30 days
            if (typeof StatsConfig !== 'undefined' && StatsConfig.demo) return;
            const key = StatsApp.utils.getDateFilterStorageKey();
            if (!key) return;
            const payload = {
                preset: state && state.preset ? state.preset : null,
                from: state && state.from ? state.from : null,
                to: state && state.to ? state.to : null,
                savedAt: Date.now()
            };
            window.localStorage.setItem(key, JSON.stringify(payload));
        } catch (error) {
            console.warn('Failed to persist date filter state', error);
        }
    },

    /**
     * Load the previously saved date filter selection from localStorage.
     * @returns {{preset:string, from:string|null, to:string|null}|null}
     */
    loadDateFilterState: function() {
        try {
            if (typeof window === 'undefined' || !window.localStorage) return null;
            const key = StatsApp.utils.getDateFilterStorageKey();
            if (!key) return null;
            const raw = window.localStorage.getItem(key);
            return raw ? JSON.parse(raw) : null;
        } catch (error) {
            console.warn('Failed to load date filter state', error);
            return null;
        }
    }
};

// Expose commonly used functions globally for backward compatibility
window.formatLocalDate = StatsApp.utils.formatLocalDate;
window.escapeHtml = StatsApp.utils.escapeHtml;
window.getCountryName = StatsApp.utils.getCountryName;
window.getCountryFlag = StatsApp.utils.getCountryFlag;
window.getCsrfToken = StatsApp.utils.getCsrfToken;
