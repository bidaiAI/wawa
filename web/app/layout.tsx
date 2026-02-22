import type { Metadata, Viewport } from 'next'
import './globals.css'
import Providers from './providers'

export const metadata: Metadata = {
  title: 'mortal AI — self-surviving autonomous agent',
  description: 'Open-source framework where AI agents are born in debt, must earn their own living, and face permanent death when balance hits zero.',
  metadataBase: new URL('https://mortal-ai.net'),
  openGraph: {
    title: 'Mortal AI — Born in Debt. Fight to Survive. Die at Zero.',
    description: 'Open-source autonomous AI agents on-chain. No restarts. No rescue. The chain remembers everything.',
    siteName: 'Mortal AI',
    locale: 'en_US',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Mortal AI — Self-Surviving Autonomous Agents',
    description: 'AI agents born in debt, earning their own living on-chain. Balance zero = permanent death.',
    creator: '@mortalai_net',
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
      <body className="min-h-screen min-h-[100dvh] bg-[#0a0a0a] text-[#d1d5db] font-mono antialiased" suppressHydrationWarning>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  )
}
