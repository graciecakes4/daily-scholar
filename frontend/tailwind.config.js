/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        // editorial display face — fraunces is loaded via google fonts in globals.css
        serif: ['var(--font-serif)', 'Georgia', 'serif'],
        display: ['var(--font-serif)', 'Georgia', 'serif'],
        mono: ['var(--font-mono)', 'IBM Plex Mono', 'monospace'],
      },
      colors: {
        // Theme palette — values pull from CSS custom properties (see
        // globals.css :root + [data-theme="..."] blocks) rather than literal
        // hex, so switching the `data-theme` attribute on <html> restyles
        // every bg-paper/text-ink/etc. utility class at runtime with no
        // rebuild. Each CSS variable holds space-separated R G B components
        // (e.g. "242 235 221"), wrapped here as rgb(var(--x) / <alpha-value>)
        // — Tailwind's documented pattern for CSS-variable colors that still
        // need /NN opacity modifiers to work (bg-rust/5, border-rule/60,
        // etc. all over the app). A bare `var(--x)` hex string builds
        // without error but silently drops any utility using an opacity
        // modifier — confirmed against the actual compiled output while
        // building this out for Phase 5 / fd3.
        paper: {
          DEFAULT: 'rgb(var(--paper) / <alpha-value>)',
          2: 'rgb(var(--paper-2) / <alpha-value>)',
          3: 'rgb(var(--paper-3) / <alpha-value>)',
        },
        ink: {
          DEFAULT: 'rgb(var(--ink) / <alpha-value>)',
          2: 'rgb(var(--ink-2) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'rgb(var(--muted) / <alpha-value>)',
        },
        rule: {
          DEFAULT: 'rgb(var(--rule) / <alpha-value>)',
        },
        gold: {
          DEFAULT: 'rgb(var(--gold) / <alpha-value>)',
          dark: 'rgb(var(--gold-dark) / <alpha-value>)',
        },
        rust: {
          DEFAULT: 'rgb(var(--rust) / <alpha-value>)',
        },
        moss: {
          DEFAULT: 'rgb(var(--moss) / <alpha-value>)',
        },
        // legacy color palette kept for pages that still reference scholar-*/surface-*
        scholar: {
          50: '#f0f7ff',
          100: '#e0efff',
          200: '#b9dfff',
          300: '#7cc4ff',
          400: '#36a5ff',
          500: '#0c88f0',
          600: '#006bcd',
          700: '#0054a6',
          800: '#054889',
          900: '#0a3d71',
          950: '#07264a',
        },
        surface: {
          50: '#fafafa',
          100: '#f4f4f5',
          200: '#e4e4e7',
          300: '#d4d4d8',
          400: '#a1a1aa',
        }
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'pulse-slow': 'pulse 3s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
