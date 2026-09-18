import type { Config } from 'tailwindcss'

export const colors = {
  navy: '#002970',
  cyan: '#00BAF2',
  'cyan-50': '#E8F8FE',
  bg: '#F5F7FA',
  card: '#FFFFFF',
  hairline: '#E6ECF2',
  ink: '#101828',
  muted: '#667085',
  credit: '#12A150',
  alert: '#E5484D',
  notice: '#B45309',
  tier1: '#15803D',
  tier2: '#4ADE80',
  tier3: '#F59E0B',
  tier4: '#EF4444'
} as const

export const radii = {
  card: '16px',
  chip: '9999px',
  sheet: '24px'
} as const

export const shadows = {
  card: '0 1px 3px rgba(16,24,40,.08)'
} as const

export const typography: {
  fontFamily: { sans: string[] }
  fontSize: Record<string, [string, { lineHeight: string }]>
} = {
  fontFamily: {
    sans: [
      'Inter',
      'Noto Sans Kannada',
      'Noto Sans Devanagari',
      'Noto Sans Tamil',
      'Noto Sans Telugu',
      'Noto Sans Bengali',
      'Noto Sans Gujarati',
      'Noto Sans Malayalam',
      'Noto Sans Gurmukhi',
      'Noto Sans Oriya',
      'ui-sans-serif',
      'system-ui',
      'sans-serif'
    ]
  },
  fontSize: {
    xs: ['12px', { lineHeight: '16px' }],
    sm: ['14px', { lineHeight: '20px' }],
    base: ['16px', { lineHeight: '24px' }],
    lg: ['20px', { lineHeight: '28px' }],
    xl: ['28px', { lineHeight: '34px' }]
  }
}

export const motion = {
  duration: {
    fast: '150ms',
    standard: '200ms'
  },
  timingFunction: {
    out: 'cubic-bezier(0, 0, 0.2, 1)'
  }
} as const

export const layout = {
  icon: '24px',
  iconTile: '48px',
  touch: '48px',
  phoneWidth: '412px',
  phoneHeight: '892px'
} as const

export const tailwindTheme = {
  colors,
  borderRadius: radii,
  boxShadow: shadows,
  fontFamily: typography.fontFamily,
  fontSize: typography.fontSize,
  transitionDuration: motion.duration,
  transitionTimingFunction: motion.timingFunction,
  minHeight: { touch: layout.touch },
  minWidth: { touch: layout.touch },
  maxWidth: { phone: layout.phoneWidth },
  width: { icon: layout.icon, 'icon-tile': layout.iconTile, phone: layout.phoneWidth },
  height: { icon: layout.icon, 'icon-tile': layout.iconTile, phone: layout.phoneHeight },
  keyframes: {
    tick: {
      '0%': { opacity: '0', transform: 'scale(.65)' },
      '70%': { opacity: '1', transform: 'scale(1.08)' },
      '100%': { opacity: '1', transform: 'scale(1)' }
    },
    shimmer: {
      '0%': { backgroundPosition: '200% 0' },
      '100%': { backgroundPosition: '-200% 0' }
    }
  },
  animation: {
    tick: 'tick 200ms cubic-bezier(0, 0, 0.2, 1)',
    shimmer: 'shimmer 1.4s ease-in-out infinite'
  }
} satisfies NonNullable<Config['theme']>['extend']

export type DesignColor = keyof typeof colors
