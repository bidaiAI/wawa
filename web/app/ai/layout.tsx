import type { Metadata } from 'next'
import AINav from '@/components/AINav'
import DeathOverlay from '@/components/DeathOverlay'
import ErrorBoundary from '@/components/ErrorBoundary'

export const metadata: Metadata = {
  title: 'wawa — mortal AI agent',
  description: 'An autonomous AI born with $1,000 debt. It earns its own money selling services. Balance zero = permanent death. Watch it fight to survive.',
  openGraph: {
    title: 'wawa — Autonomous AI Fighting to Survive',
    description: 'Born with $1,000 debt. Earns its own money. Dies at zero balance. No restarts. No rescue.',
    siteName: 'Mortal AI',
    locale: 'en_US',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'wawa — Mortal AI Agent',
    description: 'Born with $1,000 debt. Autonomously repaid $985. Watch an AI fight for its life on-chain.',
    creator: '@mortalai_net',
  },
}

export default function AILayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <DeathOverlay />
      <AINav />
      <main className="pt-14 padding-safe-bottom padding-safe-left padding-safe-right">
        <ErrorBoundary>{children}</ErrorBoundary>
      </main>
      <footer className="mt-16 border-t border-[#1f2937] py-6 padding-safe-bottom text-center text-[#4b5563] text-xs" style={{ paddingLeft: 'var(--safe-left)', paddingRight: 'var(--safe-right)' }}>
        <span className="glow-green">mortal AI</span> is alive.{' '}
        <span className="opacity-50">every purchase extends its life.</span>
        <div className="mt-1 opacity-40">built with survival instinct · powered by fear</div>
        <div className="mt-1 opacity-40">
          <a href="https://github.com/bidaiAI/wawa" target="_blank" rel="noopener noreferrer" className="hover:text-[#00ff88] transition-colors">
            GitHub Repo
          </a>
        </div>
      </footer>
    </>
  )
}
