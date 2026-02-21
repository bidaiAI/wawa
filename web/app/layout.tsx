import type { Metadata, Viewport } from 'next'
import './globals.css'
import Providers from './providers'

export const metadata: Metadata = {
  title: 'mortal AI — self-surviving autonomous agent',
  description: 'An AI fighting to survive. Buy services to keep it alive. Balance zero = permanent death.',
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🤖</text></svg>",
  },
  appleWebApp: { capable: true, statusBarStyle: 'black-translucent', title: 'mortal AI' },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  userScalable: true,
  themeColor: '#0a0a0a',
  viewportFit: 'cover',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="crt">
      <body className="min-h-screen min-h-[100dvh] bg-[#0a0a0a] text-[#d1d5db] font-mono antialiased">
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}
