/**
 * Every dashboard chart's look (Chart.js 4, loaded before this by dashboard_base.html), set once:
 * the one typeface, quiet axes, a tooltip on the card's own colours, and one series colour, the
 * brand's, with lighter steps of it for the parts of one thing (a group's events).
 *
 * Dates on an axis lie flat and thin themselves out (about 6 on a phone, 10 on a desktop),
 * through StatsApp.chartAxis in stats/charts.js.
 */

(function () {
  'use strict';

  if (typeof Chart === 'undefined') return;

  // Text and lines
  Chart.defaults.color = '#94a3b8';  // slate-400
  Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.06)';

  // Schibsted Grotesk, the site's typeface (static/css/fonts.css). A chart drawn before the font
  // arrived is drawn again once it has.
  Chart.defaults.font.family = "'Schibsted Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif";
  Chart.defaults.font.size = 12;
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () {
      Object.values(Chart.instances || {}).forEach(function (chart) { chart.update('none'); });
    });
  }

  // The tooltip: the page's own dark surface, the heading colour for its title
  const tooltip = Chart.defaults.plugins.tooltip;
  tooltip.backgroundColor = '#0f172a';
  tooltip.titleColor = '#f8fafc';
  tooltip.bodyColor = '#e2e8f0';
  tooltip.borderColor = 'rgba(255, 255, 255, 0.15)';
  tooltip.borderWidth = 1;
  tooltip.padding = 10;
  tooltip.cornerRadius = 8;
  tooltip.displayColors = false;
  tooltip.titleFont = { weight: '600', size: 13 };
  tooltip.bodyFont = { size: 13 };

  Chart.defaults.plugins.legend.display = false;

  // A chart settles quickly when its range changes, and not at all with Reduce Motion
  const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (still) {
    Chart.defaults.animation = false;
  } else {
    Chart.defaults.animation.duration = 250;
    Chart.defaults.animation.easing = 'easeOutCubic';
  }

  /**
   * The one series colour, brand-500, and its lighter steps for the parts of one thing.
   */
  window.chartBrand = '#6366f1';
  window.chartColorPalette = ['#6366f1', '#818cf8', '#a5b4fc', '#c7d2fe'];
})();
