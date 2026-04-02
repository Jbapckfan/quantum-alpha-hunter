/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        display: ['"Space Grotesk"', '"DM Sans"', 'system-ui', 'sans-serif'],
      },
      colors: {
        surface: {
          950: '#06080d',
          900: '#0b0f18',
          800: '#131928',
          700: '#1d2640',
          600: '#2a3555',
          500: '#3d4a6b',
        },
        accent: {
          emerald: '#00e68a',
          cyan: '#00d4ff',
          amber: '#ffb020',
          rose: '#ff4466',
          violet: '#a78bfa',
        },
        signal: {
          buy: '#00e68a',
          sell: '#ff4466',
          hold: '#ffb020',
          neutral: '#6b7fa3',
        },
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
    },
  },
  plugins: [],
}
