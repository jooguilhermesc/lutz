/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      colors: {
        lutz: {
          50:   '#EAF7F7',
          100:  '#C4E9E9',
          200:  '#96D6D6',
          300:  '#5DBFBF',
          400:  '#2DAAAA',
          500:  '#1A9494', // logo background — primary brand color
          600:  '#147878',
          700:  '#0E5C5C',
          800:  '#093C3C',
          900:  '#041E1E',
          dark: '#3B3B3B', // charcoal from the logo icon
        },
      },
    },
  },
  plugins: [],
}
