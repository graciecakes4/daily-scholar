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
        // editorial paper palette — see /nav-mockups/option-b-editorial-sidebar.html
        paper: {
          DEFAULT: '#F2EBDD',
          2: '#FBF6EB',
          3: '#ECE2CC',
        },
        ink: {
          DEFAULT: '#1B1610',
          2: '#3A332A',
        },
        muted: {
          DEFAULT: '#7E7060',
        },
        rule: {
          DEFAULT: '#DBD0B9',
        },
        gold: {
          DEFAULT: '#B5862B',
          dark: '#8A6519',
        },
        rust: {
          DEFAULT: '#8E3A28',
        },
        moss: {
          DEFAULT: '#4F6B3C',
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
