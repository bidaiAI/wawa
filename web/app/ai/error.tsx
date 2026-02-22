'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

/**
 * AI subdomain error boundary — catches client errors within /ai/* pages.
 *
 * More specific than the global error.tsx: keeps the nav bar functional
 * (since layout.tsx is NOT re-rendered on error) and provides AI-specific
 * recovery options.
 */
export default function AIError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const [showDetails, setShowDetails] = useState(false)

  useEffect(() => {
    console.error('[mortal-ai] AI page error:', error)
  }, [error])

  return (
    <div className="max-w-2xl mx-auto px-4 py-16 text-center">
      <div className="text-5xl mb-4 opacity-50">⚡</div>
      <h1 className="text-2xl font-bold text-[#ff3b3b] mb-2">System Glitch</h1>
      <p className="text-[#4b5563] text-sm mb-8 leading-relaxed max-w-md mx-auto">
        This page hit a runtime error. The AI is still alive — this is a frontend issue, not a death event.
      </p>

      <div className="flex gap-3 justify-center mb-8">
        <button
          onClick={reset}
          className="px-5 py-2.5 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors text-sm"
        >
          Retry
        </button>
        <Link
          href="/"
          className="px-5 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg hover:text-[#d1d5db] hover:border-[#2d3748] transition-all text-sm"
        >
          Home
        </Link>
        <button
          onClick={() => window.location.reload()}
          className="px-5 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg hover:text-[#d1d5db] hover:border-[#2d3748] transition-all text-sm"
        >
          Hard Refresh
        </button>
      </div>

      {/* Expandable error details */}
      <button
        onClick={() => setShowDetails((v) => !v)}
        className="text-[#2d3748] text-xs hover:text-[#4b5563] transition-colors"
      >
        {showDetails ? '▲ hide details' : '▼ error details'}
      </button>
      {showDetails && (
        <div className="mt-3 bg-[#111111] border border-[#1f2937] rounded-lg p-4 text-left text-xs max-w-lg mx-auto">
          <div className="text-[#ff3b3b] font-bold mb-1 break-all">
            {error.name}: {error.message}
          </div>
          {error.digest && (
            <div className="text-[#4b5563] mb-2">Digest: {error.digest}</div>
          )}
          {error.stack && (
            <pre className="text-[#2d3748] whitespace-pre-wrap break-all max-h-40 overflow-y-auto mt-2">
              {error.stack}
            </pre>
          )}
          <div className="mt-3 pt-2 border-t border-[#1f2937] text-[#4b5563]">
            URL: {typeof window !== 'undefined' ? window.location.pathname : '—'}
          </div>
        </div>
      )}

      <div className="mt-8 text-[#2d3748] text-[10px]">
        Tip: try Ctrl+Shift+R to force-refresh cached assets
      </div>
    </div>
  )
}
