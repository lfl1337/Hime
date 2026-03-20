/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        accent: '#7C6FCD',
      },
      fontFamily: {
        sans: [
          'system-ui',
          'Hiragino Sans',
          'Yu Gothic',
          'Meiryo',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Consolas',
          'monospace',
        ],
      },
    },
  },
  plugins: [],
}
