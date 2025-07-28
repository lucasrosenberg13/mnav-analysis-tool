/** @type {import('tailwindcss').Config} */
export default {
    content: [
      "./index.html",
      "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
      extend: {
        fontFamily: {
          'sans': ['Inter', 'ui-sans-serif', 'system-ui'],
        },
        colors: {
          finance: {
            dark: '#0D1B2A',
            mid: '#1B263B',
            blue: '#415A77',
            steel: '#778DA9',
            light: '#E0E1DD',
          }
        }
      },
    },
    plugins: [],
  }