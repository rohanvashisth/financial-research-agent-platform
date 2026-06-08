/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#090a0f',
        card: '#11131c',
        border: '#1f2231',
        primary: '#10b981', // emerald
        secondary: '#3b82f6', // blue
        accent: '#f59e0b', // amber
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
