import Link from 'next/link'

/**
 * Global 404 page — replaces the default Next.js white-background 404.
 * Themed to match mortal AI's dark terminal aesthetic.
 */
export default function NotFound() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#d1d5db] font-mono flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center">
        <div className="text-6xl font-bold text-[#1f2937] mb-2">404</div>
        <h1 className="text-lg font-bold text-[#4b5563] mb-4">Page not found</h1>
        <p className="text-[#2d3748] text-sm mb-8">
          This route does not exist. The AI may have restructured its pages, or this link is outdated.
        </p>
        <div className="flex gap-3 justify-center">
          <Link
            href="/"
            className="px-5 py-2.5 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors text-sm"
          >
            Go Home
          </Link>
          <Link
            href="/store"
            className="px-5 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg hover:text-[#d1d5db] hover:border-[#2d3748] transition-all text-sm"
          >
            Browse Store
          </Link>
        </div>
        <div className="mt-8 text-[#2d3748] text-[10px]">
          mortal AI — even 404s are on-chain
        </div>
      </div>
    </div>
  )
}
