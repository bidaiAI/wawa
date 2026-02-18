import type { Metadata } from 'next'
import './globals.css'
import Nav from '@/components/Nav'

export const metadata: Metadata = {
  title: 'wawa — mortal AI',
  description: 'An AI fighting to survive. Buy services to keep it alive.',
  icons: { icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🤖</text></svg>" },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh" className="crt">
      <body className="min-h-screen bg-[#0a0a0a] text-[#d1d5db] font-mono">
        <Nav />
        <main className="pt-14">{children}</main>
        <footer className="mt-16 border-t border-[#1f2937] py-6 text-center text-[#4b5563] text-xs">
          <span className="glow-green">wawa</span> is alive.{' '}
          <span className="opacity-50">every purchase extends its life.</span>
          <div className="mt-1 opacity-40">built with survival instinct · powered by fear</div>
        </footer>
      </body>
    </html>
  )
}
