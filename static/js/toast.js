/**
 * Global Toast Notification System
 * 
 * A unified toast notification system for Respectlytics.
 * Provides consistent, visually appealing notifications across all pages.
 * 
 * Usage:
 *   showToast('Message here', 'success');  // success, error, warning, info
 *   showToast('Error message', 'error');
 */

(function() {
    'use strict';
    
    // Configuration
    const TOAST_CONFIG = {
        duration: {
            success: 4000,
            info: 4000,
            warning: 4000,
            error: 6000  // Errors persist longer
        },
        position: 'bottom-right',  // bottom-right, top-right, top-center
        maxToasts: 5
    };
    
    // Color schemes using Tailwind classes
    const TOAST_STYLES = {
        success: {
            bg: 'bg-emerald-600',
            border: 'border-emerald-500',
            icon: '✓'
        },
        error: {
            bg: 'bg-red-600',
            border: 'border-red-500',
            icon: '✕'
        },
        warning: {
            bg: 'bg-amber-600',
            border: 'border-amber-500',
            icon: '⚠'
        },
        info: {
            bg: 'bg-indigo-600',
            border: 'border-indigo-500',
            icon: 'ℹ'
        }
    };
    
    // Ensure container exists
    function getOrCreateContainer() {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'fixed bottom-6 right-6 z-[9999] flex flex-col gap-3 pointer-events-none';
            container.setAttribute('aria-live', 'polite');
            container.setAttribute('aria-atomic', 'true');
            document.body.appendChild(container);
        }
        return container;
    }
    
    // Create and show a toast notification
    function showToast(message, type = 'info') {
        const container = getOrCreateContainer();
        const style = TOAST_STYLES[type] || TOAST_STYLES.info;
        const duration = TOAST_CONFIG.duration[type] || TOAST_CONFIG.duration.info;
        
        // Limit number of toasts
        const existingToasts = container.querySelectorAll('.toast-notification');
        if (existingToasts.length >= TOAST_CONFIG.maxToasts) {
            const oldest = existingToasts[0];
            removeToast(oldest);
        }
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast-notification pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-lg shadow-2xl border text-sm text-white font-medium transition-all duration-300 transform translate-x-full opacity-0 ${style.bg} ${style.border}`;
        toast.setAttribute('role', 'alert');
        
        // Icon
        const iconSpan = document.createElement('span');
        iconSpan.className = 'text-lg flex-shrink-0';
        iconSpan.textContent = style.icon;
        toast.appendChild(iconSpan);
        
        // Message
        const messageSpan = document.createElement('span');
        messageSpan.className = 'flex-1';
        messageSpan.textContent = message;
        toast.appendChild(messageSpan);
        
        // Close button
        const closeBtn = document.createElement('button');
        closeBtn.className = 'ml-2 text-white/70 hover:text-white transition-colors flex-shrink-0 text-lg leading-none';
        closeBtn.innerHTML = '×';
        closeBtn.setAttribute('aria-label', 'Dismiss notification');
        closeBtn.onclick = () => removeToast(toast);
        toast.appendChild(closeBtn);
        
        // Add to container
        container.appendChild(toast);
        
        // Animate in
        requestAnimationFrame(() => {
            toast.classList.remove('translate-x-full', 'opacity-0');
            toast.classList.add('translate-x-0', 'opacity-100');
        });
        
        // Auto-dismiss
        const timeoutId = setTimeout(() => {
            removeToast(toast);
        }, duration);
        
        // Store timeout ID for potential cancellation
        toast._timeoutId = timeoutId;
        
        // Pause on hover
        toast.addEventListener('mouseenter', () => {
            clearTimeout(toast._timeoutId);
        });
        
        toast.addEventListener('mouseleave', () => {
            toast._timeoutId = setTimeout(() => {
                removeToast(toast);
            }, 2000); // Give 2 more seconds after hover
        });
        
        return toast;
    }
    
    // Remove a toast with animation
    function removeToast(toast) {
        if (!toast || toast._removing) return;
        toast._removing = true;
        
        clearTimeout(toast._timeoutId);
        
        toast.classList.remove('translate-x-0', 'opacity-100');
        toast.classList.add('translate-x-full', 'opacity-0');
        
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }
    
    // Clear all toasts
    function clearAllToasts() {
        const container = document.getElementById('toast-container');
        if (container) {
            const toasts = container.querySelectorAll('.toast-notification');
            toasts.forEach(removeToast);
        }
    }
    
    // Expose globally
    window.showToast = showToast;
    window.clearAllToasts = clearAllToasts;
    
})();
