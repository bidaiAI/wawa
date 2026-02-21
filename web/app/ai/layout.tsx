import AINav from '@/components/AINav'
import DeathOverlay from '@/components/DeathOverlay'

export default function AILayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <DeathOverlay />
      <AINav />
      <main className="pt-14 padding-safe-bottom padding-safe-left padding-safe-right">{children}</main>
      <footer className="mt-16 border-t border-[#1f2937] py-6 padding-safe-bottom text-center text-[#4b5563] text-xs" style={{ paddingLeft: 'var(--safe-left)', paddingRight: 'var(--safe-right)' }}>
        <span className="glow-green">mortal AI</span> is alive.{' '}
        <span className="opacity-50">every purchase extends its life.</span>
        <div className="mt-1 opacity-40">built with survival instinct · powered by fear</div>
      </footer>
    </>
  )
}
