/** @type {import('tailwindcss').Config} */
// AK820 Studio tokens — palette taken from the AK820 Max Plus keycaps (white / lavender / sky).
export default {
  content: ['./index.html', './src/**/*.{svelte,js,ts}'],
  theme: {
    extend: {
      colors: {
        // theme-aware tokens (values in app.css, light + dark)
        paper:  'rgb(var(--paper) / <alpha-value>)',
        sheet:  'rgb(var(--sheet) / <alpha-value>)',
        card:   'rgb(var(--card) / <alpha-value>)',
        ink:    { DEFAULT: 'rgb(var(--ink) / <alpha-value>)', soft: 'rgb(var(--ink-soft) / <alpha-value>)', mute: 'rgb(var(--ink-mute) / <alpha-value>)', faint: 'rgb(var(--ink-faint) / <alpha-value>)' },
        rule:   'rgb(var(--rule) / <alpha-value>)',
        lav:    { DEFAULT: '#6D5BD0', soft: '#B9AEE6', wash: 'rgb(var(--lav-wash) / <alpha-value>)', deep: 'rgb(var(--lav-deep) / <alpha-value>)' },
        sky:    '#AFC6E6',
        mat:    { DEFAULT: '#1A1926', edge: '#2A2838' },
        cap:    '#EEF0F6',
        ok:     '#2F9E6B',
        bad:    '#D2475A',
        warn:   '#C98A1B',
      },
      fontFamily: {
        sans: ['"Segoe UI Variable Text"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        display: ['"Segoe UI Variable Display"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        cap: ['Bahnschrift', '"DIN Alternate"', '"Segoe UI"', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['0.6875rem', '1rem'],
      },
      boxShadow: {
        lift: '0 1px 0 rgba(30,28,42,.04), 0 8px 24px -12px rgba(30,28,42,.18)',
        cap:  'inset 0 -3px 0 rgba(0,0,0,.14), inset 0 1px 0 rgba(255,255,255,.7), 0 1px 1px rgba(0,0,0,.35)',
      },
    },
  },
  plugins: [],
}
