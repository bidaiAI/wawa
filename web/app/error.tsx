'use client'

import { useEffect, useState } from 'react'

/**
 * Global error boundary — catches any unhandled client-side exception.
 *
 * Without this file, Next.js shows a blank white "Application error" page
 * with zero diagnostic info. This provides a themed fallback + retry button.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const [showDetails, setShowDetails] = useState(false)

  useEffect(() => {
    console.error('[mortal-ai] Unhandled client error:', error)
  }, [error])

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#d1d5db] font-mono flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center">
        <div className="text-4xl mb-4 opacity-60">⚠</div>
        <h1 className="text-xl font-bold text-[#ff3b3b] mb-2">Something broke</h1>
        <p className="text-[#4b5563] text-sm mb-6 leading-relaxed">
          A client-side error occurred. This is usually temporary — try refreshing.
        </p>

        <div className="flex gap-3 justify-center mb-6">
          <button
            onClick={reset}
            className="px-5 py-2.5 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors text-sm"
          >
            Try Again
          </button>
          <a
            href="/"
            className="px-5 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg hover:text-[#d1d5db] hover:border-[#2d3748] transition-all text-sm"
          >
            Go Home
          </a>
        </div>

        {/* Error details toggle */}
        <button
          onClick={() => setShowDetails((v) => !v)}
          className="text-[#2d3748] text-xs hover:text-[#4b5563] transition-colors"
        >
          {showDetails ? '▲ hide details' : '▼ show error details'}
        </button>
        {showDetails && (
          <div className="mt-3 bg-[#111111] border border-[#1f2937] rounded-lg p-4 text-left text-xs">
            <div className="text-[#ff3b3b] font-bold mb-1">{error.name}: {error.message}</div>
            {error.digest && (
              <div className="text-[#4b5563] mb-2">Digest: {error.digest}</div>
            )}
            {error.stack && (
              <pre className="text-[#2d3748] whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                {error.stack}
              </pre>
            )}
          </div>
        )}

        <div className="mt-6 text-[#2d3748] text-[10px]">
          mortal AI — errors are part of survival
        </div>
      </div>
    </div>
  )
}
