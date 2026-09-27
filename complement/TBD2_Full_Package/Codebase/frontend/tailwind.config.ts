import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          base:     '#0a0e1a',
          surface:  '#111827',
          elevated: '#1a2236',
          hover:    '#1e2a42',
        },
        accent: {
          primary:   '#6366f1',
          secondary: '#8b5cf6',
          success:   '#10b981',
          warning:   '#f59e0b',
          danger:    '#ef4444',
          info:      '#3b82f6',
        },
        text: {
          primary:   '#f9fafb',
          secondary: '#9ca3af',
          muted:     '#6b7280',
        },
        border: {
          subtle: '#1f2937',
          default: '#374151',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        'pulse-slow': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in':    'fadeIn 0.2s ease-out',
        'slide-in':   'slideIn 0.25s ease-out',
        'slide-up':   'slideUp 0.2s ease-out',
        'shimmer':    'shimmer 1.5s infinite',
        'spin-slow':  'spin 3s linear infinite',
      },
      keyframes: {
        fadeIn:  { from: { opacity: '0' }, to: { opacity: '1' } },
        slideIn: { from: { transform: 'translateX(100%)' }, to: { transform: 'translateX(0)' } },
        slideUp: { from: { transform: 'translateY(8px)', opacity: '0' }, to: { transform: 'translateY(0)', opacity: '1' } },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      backgroundImage: {
        'gradient-radial':  'radial-gradient(var(--tw-gradient-stops))',
        'gradient-glass':   'linear-gradient(135deg, rgba(99,102,241,0.1) 0%, rgba(139,92,246,0.05) 100%)',
        'gradient-primary': 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
        'gradient-success': 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
        'gradient-danger':  'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
        'shimmer-gradient': 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.04) 50%, transparent 100%)',
      },
      boxShadow: {
        'glow-primary':  '0 0 20px rgba(99,102,241,0.3)',
        'glow-success':  '0 0 20px rgba(16,185,129,0.3)',
        'glow-danger':   '0 0 20px rgba(239,68,68,0.3)',
        'card':          '0 4px 24px rgba(0,0,0,0.4)',
        'card-hover':    '0 8px 40px rgba(0,0,0,0.6)',
      },
    },
  },
  plugins: [],
}

export default config
