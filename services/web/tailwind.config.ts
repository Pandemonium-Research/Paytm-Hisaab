import type { Config } from 'tailwindcss'
import { tailwindTheme } from './src/design/tokens'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: tailwindTheme
  },
  plugins: []
} satisfies Config
