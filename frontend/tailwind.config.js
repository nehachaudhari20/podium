/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        podium: {
          50: '#f5f3ff',
          100: '#ede9fe',
          200: '#ddd6fe',
          300: '#c4b5fd',
          400: '#a78bfa',
          500: '#7c5cfc',
          600: '#6b46ef',
          700: '#5b35d9',
          800: '#4c2bb0',
          900: '#3f268c',
        },
        ink: {
          50: '#f7f8fa',
          100: '#eef0f4',
          200: '#dde1e8',
          300: '#c3cad5',
          400: '#9aa3b2',
          500: '#6b7385',
          600: '#4a5163',
          700: '#343a48',
          800: '#1f2430',
          900: '#12151c',
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        soft: '0 1px 2px rgba(18, 21, 28, 0.04), 0 1px 3px rgba(18, 21, 28, 0.06)',
        panel: '0 8px 24px rgba(18, 21, 28, 0.08)',
      },
    },
  },
  plugins: [],
}
