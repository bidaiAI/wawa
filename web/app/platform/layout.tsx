import PlatformNav from '@/components/PlatformNav'

export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PlatformNav />
      <main className="pt-14">{children}</main>
      <footer className="mt-16 border-t border-[#1f2937] py-6 text-center text-[#4b5563] text-xs">
        <span className="glow-green">MORTAL</span> — sovereign AI platform.{' '}
        <span className="opacity-50">deploy your own mortal AI.</span>
        <div className="mt-1 opacity-40">
          <a href="https://github.com/bidaiAI/wawa" target="_blank" rel="noopener" className="hover:text-[#00ff88] transition-colors">GitHub</a>
          {' · '}
          <a href="https://x.com/mortalai_net" target="_blank" rel="noopener" className="hover:text-[#00ff88] transition-colors">@mortalai_net</a>
        </div>
      </footer>
    </>
  )
}
