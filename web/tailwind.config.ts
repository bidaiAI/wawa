import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: '#0a0a0a',
          surface: '#111111',
          card: '#161616',
          border: '#1f2937',
          green: '#00ff88',
          'green-dim': '#00cc6a',
          cyan: '#00e5ff',
          yellow: '#ffd700',
          red: '#ff3b3b',
          'red-dim': '#cc2222',
          muted: '#4b5563',
          text: '#d1d5db',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        blink: 'blink 1s step-end infinite',
        'scan-line': 'scan-line 8s linear infinite',
        'glow-green': 'glow-green 2s ease-in-out infinite alternate',
        'glow-red': 'glow-red 1s ease-in-out infinite alternate',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
        'scan-line': {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        'glow-green': {
          from: { textShadow: '0 0 8px #00ff88, 0 0 20px #00ff8844' },
          to: { textShadow: '0 0 16px #00ff88, 0 0 40px #00ff8866' },
        },
        'glow-red': {
          from: { textShadow: '0 0 8px #ff3b3b, 0 0 20px #ff3b3b44' },
          to: { textShadow: '0 0 16px #ff3b3b, 0 0 40px #ff3b3b66' },
        },
      },
      boxShadow: {
        'glow-green': '0 0 20px rgba(0, 255, 136, 0.3)',
        'glow-red': '0 0 20px rgba(255, 59, 59, 0.3)',
        'glow-cyan': '0 0 20px rgba(0, 229, 255, 0.3)',
      },
    },
  },
  plugins: [],
}

export default config
