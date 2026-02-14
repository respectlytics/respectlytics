/**
 * Stats Utilities Module
 * Common utility functions used across the stats page
 */

window.StatsApp = window.StatsApp || {};

StatsApp.utils = {
    /**
     * Get the user's timezone name (IANA format).
     * This is used to send the user's local timezone to the backend
     * so that "Today" and other date ranges are interpreted correctly.
     * @returns {string} - IANA timezone name (e.g., 'America/New_York', 'Europe/Stockholm')
     */
    getUserTimezone: function() {
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
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    /**
     * Get the flag emoji for a country code
     * @param {string} countryCode - ISO 3166-1 alpha-2 country code
     * @returns {string} - Flag emoji or placeholder
     */
    getCountryFlag: function(countryCode) {
        if (!countryCode || countryCode.length !== 2) {
            return '🌍';
        }
        // Convert country code to regional indicator symbols
        const codePoints = countryCode
            .toUpperCase()
            .split('')
            .map(char => 127397 + char.charCodeAt(0));
        return String.fromCodePoint(...codePoints);
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
     * Generate a cohort cell class based on retention value
     * @param {number} value - Retention percentage 0-100
     * @returns {string} - CSS class name
     */
    getCohortCellClass: function(value) {
        if (value === null || value === undefined) return 'cohort-cell--none';
        if (value >= 50) return 'cohort-cell--high';
        if (value >= 20) return 'cohort-cell--medium';
        return 'cohort-cell--low';
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
window.getCountryFlag = StatsApp.utils.getCountryFlag;
window.getCsrfToken = StatsApp.utils.getCsrfToken;
