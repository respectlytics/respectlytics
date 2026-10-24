/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './users/templates/**/*.html',
    './dashboard/templates/**/*.html',
    './website/templates/**/*.html',
    './billing/templates/**/*.html',
    './analytics/templates/**/*.html',
    './tools/templates/**/*.html',
    // Every other app's templates (respectlytics.com's setup pages among them).
    './[a-z]*/templates/**/*.html',
    './static/js/**/*.js',
    // Each app's own scripts write class names into the page too.
    './analytics/static/**/*.js',
    './dashboard/static/**/*.js',
    './tools/static/**/*.js',
    './website/static/**/*.js',
    // respectlytics.com's own apps (teams/, properties/, alerts/)
    './teams/static/**/*.js',
    './properties/static/**/*.js',
    './alerts/static/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        // The faintest text tone: notes, breadcrumbs, captions. slate-500 reads
        // at under 4.5:1 on the dark surfaces; this passes on every one of them.
        slate: {
          450: '#8492a8',
        },
        brand: {
          50: '#EEF2FF',
          100: '#E0E7FF',
          200: '#C7D2FE',
          300: '#A5B4FC',
          400: '#818CF8',
          500: '#6366F1',
          600: '#4F46E5',
          700: '#4338CA',
          800: '#3730A3',
          900: '#312E81',
          950: '#1e1b4b',
        },
        success: {
          50: '#ECFDF5',
          100: '#D1FAE5',
          500: '#10B981',
          600: '#059669',
        },
        warning: {
          50: '#FFFBEB',
          100: '#FEF3C7',
          500: '#F59E0B',
          600: '#D97706',
        },
        error: {
          50: '#FEF2F2',
          100: '#FEE2E2',
          500: '#EF4444',
          600: '#DC2626',
        },
      },
      // Schibsted Grotesk everywhere (static/css/fonts.css); system fonts are only the fallback.
      fontFamily: {
        sans: ['"Schibsted Grotesk"', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        display: ['"Schibsted Grotesk"', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        body: ['"Schibsted Grotesk"', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', 'Courier New', 'monospace'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}

