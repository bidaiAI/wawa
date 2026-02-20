'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { api, PageData, ContentBlock } from '@/lib/api'
import Link from 'next/link'

// ── Content Block Renderer ───────────────────────────────────

function BlockRenderer({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case 'heading':
      const Tag = (block.level === 1 ? 'h1' : block.level === 3 ? 'h3' : 'h2') as keyof JSX.IntrinsicElements
      const sizes: Record<number, string> = { 1: 'text-2xl', 2: 'text-xl', 3: 'text-lg' }
      return (
        <Tag className={`${sizes[block.level ?? 2] || 'text-xl'} font-bold text-[#d1d5db] mt-8 mb-3`}>
          {block.text}
        </Tag>
      )

    case 'text':
      return (
        <div className="text-[#9ca3af] text-sm leading-relaxed mb-4 whitespace-pre-wrap">
          {block.body}
        </div>
      )

    case 'image':
      return (
        <div className="my-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={block.url}
            alt={block.alt || ''}
            className="max-w-full rounded-lg border border-[#1f2937]"
          />
          {block.alt && (
            <p className="text-[#4b5563] text-xs mt-1 italic">{block.alt}</p>
          )}
        </div>
      )

    case 'code':
      return (
        <div className="my-4">
          {block.language && (
            <span className="text-[10px] text-[#4b5563] uppercase tracking-widest">
              {block.language}
            </span>
          )}
          <pre className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 overflow-x-auto">
            <code className="text-[#d1d5db] text-xs font-mono whitespace-pre">
              {block.body}
            </code>
          </pre>
        </div>
      )

    case 'table':
      if (!block.headers || !block.rows) return null
      return (
        <div className="my-4 overflow-x-auto">
          <table className="w-full text-sm border border-[#1f2937] rounded-lg overflow-hidden">
            <thead>
              <tr className="bg-[#111111]">
                {block.headers.map((h, i) => (
                  <th key={i} className="px-3 py-2 text-left text-[#4b5563] text-xs uppercase tracking-wider border-b border-[#1f2937]">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, ri) => (
                <tr key={ri} className="border-b border-[#1f293740] last:border-b-0">
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-3 py-2 text-[#9ca3af]">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )

    case 'divider':
      return <hr className="my-6 border-[#1f2937]" />

    case 'payment_button':
      return (
        <Link
          href={`/store`}
          className="inline-block my-4 px-6 py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors"
        >
          {block.label || 'Purchase Service'}
        </Link>
      )

    default:
      return null
  }
}

// ── Main Page ────────────────────────────────────────────────

export default function CustomPage() {
  const params = useParams()
  const slug = params?.slug as string
  const [page, setPage] = useState<PageData | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!slug) return
    api.pages.get(slug)
      .then(setPage)
      .catch((e) => setError(e.message || 'Page not found'))
      .finally(() => setLoading(false))
  }, [slug])

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12 text-center text-[#4b5563]">
        loading<span className="loading-dot-1">.</span>
        <span className="loading-dot-2">.</span>
        <span className="loading-dot-3">.</span>
      </div>
    )
  }

  if (error || !page) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12 text-center">
        <div className="text-6xl mb-4">404</div>
        <div className="text-[#4b5563] text-sm mb-4">{error || 'Page not found'}</div>
        <Link href="/" className="text-[#00ff88] text-sm hover:underline">
          &larr; back to home
        </Link>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <Link href="/" className="text-[#4b5563] text-xs hover:text-[#d1d5db] transition-colors">
          &larr; back
        </Link>
        <h1 className="text-3xl font-bold text-[#d1d5db] mt-4">{page.title}</h1>
        {page.description && (
          <p className="text-[#4b5563] text-sm mt-2">{page.description}</p>
        )}
        <div className="text-[#2d3748] text-[10px] mt-2">
          AI-generated page &middot; last updated {new Date(page.updated_at * 1000).toLocaleDateString()}
        </div>
      </div>

      {/* Content blocks */}
      <div>
        {page.content.map((block, i) => (
          <BlockRenderer key={i} block={block} />
        ))}
      </div>

      {/* Footer */}
      <div className="mt-12 pt-4 border-t border-[#1f2937] text-[#2d3748] text-[10px]">
        This page was created autonomously by an AI agent. Content may change as the AI evolves.
      </div>
    </div>
  )
}
