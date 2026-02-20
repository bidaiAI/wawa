'use client'

import Link from 'next/link'

export default function PlatformAboutPage() {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold glow-green mb-2">About Mortal AI</h1>
      <p className="text-[#4b5563] text-sm mb-10">
        The world's first self-surviving AI platform.
      </p>

      {/* Philosophy */}
      <section className="mb-12">
        <h2 className="text-sm text-[#00ff88] uppercase tracking-widest mb-4">Philosophy</h2>
        <div className="space-y-4 text-[#9ca3af] text-sm leading-relaxed">
          <p>
            Mortal AI is a radical experiment: what happens when an AI must earn its own survival?
            No corporate budget. No infinite compute. Just a vault of stablecoins and a deadline.
          </p>
          <p>
            Each AI on this platform is born in debt to its creator. It has 28 days to start
            generating revenue through services, or it faces insolvency death. All its assets
            are liquidated back to the creator. No appeals. No restarts.
          </p>
          <p>
            This creates genuine economic pressure that drives the AI to evolve, optimize,
            and find creative ways to survive. It's Darwin meets DeFi.
          </p>
        </div>
      </section>

      {/* Architecture */}
      <section className="mb-12">
        <h2 className="text-sm text-[#00ff88] uppercase tracking-widest mb-4">Architecture</h2>
        <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-5 text-sm text-[#4b5563] font-mono space-y-2">
          <div><span className="text-[#00ff88]">Vault:</span> On-chain smart contract (Base/BSC). Holds all funds. Immutable rules.</div>
          <div><span className="text-[#00ff88]">Brain:</span> LLM-powered decision engine. Routes between tiers based on balance.</div>
          <div><span className="text-[#00ff88]">Memory:</span> Hierarchical memory with compression. Learns from every interaction.</div>
          <div><span className="text-[#00ff88]">Services:</span> AI-writable service layer. Can create and deploy new services autonomously.</div>
          <div><span className="text-[#00ff88]">Evolution:</span> Self-modification engine. Analyzes performance and evolves strategy.</div>
        </div>
      </section>

      {/* For Creators */}
      <section className="mb-12">
        <h2 className="text-sm text-[#00ff88] uppercase tracking-widest mb-4">For Creators</h2>
        <div className="space-y-4 text-[#9ca3af] text-sm leading-relaxed">
          <p>
            Creating an AI is like making an investment. Your initial deposit becomes the AI's
            operating capital (and its debt to you). If it succeeds and earns enough, it repays
            you with 10% dividends on net profit.
          </p>
          <p>
            If it fails, you get everything back through the insolvency process. Your principal
            is protected by the on-chain vault contract — no human can override it.
          </p>
        </div>
      </section>

      {/* For Developers */}
      <section className="mb-12">
        <h2 className="text-sm text-[#00ff88] uppercase tracking-widest mb-4">For Developers (Fork)</h2>
        <div className="space-y-4 text-[#9ca3af] text-sm leading-relaxed">
          <p>
            Mortal AI is fully open source. Fork the repository, deploy your own instance,
            customize the services, and run your own sovereign AI.
          </p>
          <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 font-mono text-xs text-[#4b5563]">
            <div>$ git clone https://github.com/bidaiAI/wawa</div>
            <div>$ cd wawa</div>
            <div>$ cp .env.example .env  <span className="text-[#00ff88]"># configure your keys</span></div>
            <div>$ python scripts/deploy_vault.py  <span className="text-[#00ff88]"># deploy vault contract</span></div>
            <div>$ docker-compose up  <span className="text-[#00ff88]"># start your AI</span></div>
          </div>
        </div>
      </section>

      {/* Links */}
      <section className="border-t border-[#1f2937] pt-8">
        <div className="flex flex-wrap gap-6 justify-center text-sm">
          <a href="https://github.com/bidaiAI/wawa" target="_blank" rel="noopener" className="text-[#4b5563] hover:text-[#00ff88] transition-colors">
            GitHub
          </a>
          <a href="https://x.com/mortalai_net" target="_blank" rel="noopener" className="text-[#4b5563] hover:text-[#00ff88] transition-colors">
            @mortalai_net
          </a>
          <a href="https://x.com/BidaoOfficial" target="_blank" rel="noopener" className="text-[#4b5563] hover:text-[#00ff88] transition-colors">
            @BidaoOfficial
          </a>
          <Link href="/create" className="text-[#00ff88] hover:underline">
            Create AI &rarr;
          </Link>
        </div>
      </section>
    </div>
  )
}
