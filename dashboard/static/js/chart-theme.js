/**
 * Respectlytics Dark Theme - Chart.js Global Configuration
 * 
 * Part of: UI/Design System Backlog - Task UI-003
 * Documentation: .github/design-system/
 * 
 * This file configures Chart.js defaults for consistent dark theme
 * across all charts in the dashboard. Load AFTER Chart.js CDN.
 * 
 * Usage:
 * <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
 * <script src="{% static 'js/chart-theme.js' %}"></script>
 */

(function() {
  'use strict';
  
  if (typeof Chart === 'undefined') {
    return; // Chart.js not loaded yet - will be applied when it loads
  }
  
  // ============================================
  // GLOBAL COLOR SETTINGS
  // ============================================
  
  Chart.defaults.color = '#94a3b8';  // Slate 400 - Default text color
  Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.05)';  // Subtle borders
  
  // ============================================
  // FONT CONFIGURATION
  // ============================================
  
  Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', 'Roboto', sans-serif";
  Chart.defaults.font.size = 12;
  
  // ============================================
  // TOOLTIP CONFIGURATION
  // ============================================
  
  Chart.defaults.plugins.tooltip.backgroundColor = '#1e293b';  // Slate 800 - Matches surface color
  Chart.defaults.plugins.tooltip.titleColor = '#f8fafc';  // Slate 50 - Primary text
  Chart.defaults.plugins.tooltip.bodyColor = '#94a3b8';  // Slate 400 - Secondary text
  Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 255, 255, 0.1)';  // Subtle border
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 12;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.displayColors = true;
  Chart.defaults.plugins.tooltip.boxPadding = 6;
  
  // ============================================
  // LEGEND CONFIGURATION
  // ============================================
  
  Chart.defaults.plugins.legend.labels.color = '#94a3b8';  // Slate 400
  Chart.defaults.plugins.legend.labels.padding = 16;
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.legend.labels.boxHeight = 12;
  Chart.defaults.plugins.legend.labels.useBorderRadius = true;
  Chart.defaults.plugins.legend.labels.borderRadius = 2;
  
  // ============================================
  // DATASET COLOR PALETTE
  // ============================================
  
  /**
   * Global color palette optimized for dark backgrounds
   * Use these colors for multi-dataset charts
   */
  window.chartColorPalette = [
    '#8b5cf6',  // Purple 500 - Primary
    '#06b6d4',  // Cyan 500 - Secondary
    '#f59e0b',  // Amber 500 - Accent
    '#10b981',  // Emerald 500 - Success
    '#ef4444',  // Red 500 - Error
    '#ec4899',  // Pink 500 - Highlight
    '#6366f1',  // Indigo 500 - Brand
    '#14b8a6'   // Teal 500 - Info
  ];
  
  /**
   * Helper function to get color from palette with alpha
   * @param {number} index - Color index (0-7)
   * @param {number} alpha - Opacity (0-1)
   * @returns {string} RGBA color string
   */
  window.getChartColor = function(index, alpha = 1) {
    const colors = window.chartColorPalette;
    const color = colors[index % colors.length];
    
    if (alpha === 1) return color;
    
    // Convert hex to rgba
    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);
    
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  };
  
  /**
   * Helper function to generate gradient backgrounds
   * Useful for area charts on dark backgrounds
   * @param {CanvasRenderingContext2D} ctx - Chart canvas context
   * @param {string} color - Base color (hex)
   * @param {number} height - Chart height
   * @returns {CanvasGradient} Gradient object
   */
  window.createChartGradient = function(ctx, color, height) {
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    
    // Parse hex color
    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);
    
    gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.3)`);
    gradient.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, 0.1)`);
    gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.0)`);
    
    return gradient;
  };
  
})();
