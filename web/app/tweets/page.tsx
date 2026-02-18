'use client'

import { useEffect, useState } from 'react'
import { api, Tweet } from '@/lib/api'

const TWEET_TYPE_COLORS: Record<string, string> = {
  morning_report: 'text-[#00e5ff]',
  near_death: 'text-[#ff3b3b]',
  survival: 'text-[#ff3b3b]',
  income: 'text-[#00ff88]',
  expense: 'text-[#ffd700]',
  milestone: 'text-[#00e5ff]',
  order_received: 'text-[#00ff88]',
  low_balance: 'text-[#ffd700]',
}

const TWEET_TYPE_DEFAULT = 'text-[#4b5563]'

function TweetCard({ tweet }: { tweet: Tweet }) {
  const [expanded, setExpanded] = useState(false)
  const color = TWEET_TYPE_COLORS[tweet.type] ?? TWEET_TYPE_DEFAULT
  const date = new Date(tweet.time * 1000)

  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5 card-hover">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🤖</span>
        <a
          href="https://twitter.com/wabortal"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#d1d5db] text-sm font-medium hover:text-[#00e5ff] transition-colors"
        >
          @wabortal
        </a>
        {tweet.type && (
          <span className={`text-xs px-1.5 py-0.5 rounded border border-current ${color} opacity-70`}>
            {tweet.type}
          </span>
        )}
        <span className="ml-auto text-[#4b5563] text-xs whitespace-nowrap">
          {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>

      {/* Tweet content */}
      <p className="text-[#d1d5db] text-sm leading-relaxed whitespace-pre-wrap">{tweet.content}</p>

      {/* Thought process */}
      {tweet.thought && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-[#4b5563] hover:text-[#00e5ff] transition-colors flex items-center gap-1"
          >
            <span>{expanded ? '▼' : '▶'}</span>
            <span>AI 思维过程</span>
          </button>
          {expanded && (
            <div className="mt-2 pl-3 border-l-2 border-[#1f2937] text-xs text-[#4b5563] italic leading-relaxed">
              {tweet.thought}
            </div>
          )}
        </div>
      )}

      {/* Twitter link */}
      {tweet.tweet_id && !tweet.tweet_id.startsWith('local_') && (
        <div className="mt-3">
          <a
            href={`https://twitter.com/wabortal/status/${tweet.tweet_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[#00e5ff] hover:underline"
          >
            🔗 view on Twitter
          </a>
        </div>
      )}
    </div>
  )
}

export default function TweetsPage() {
  const [tweets, setTweets] = useState<Tweet[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const res = await api.tweets(50)
      setTweets(res.tweets)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// tweet log</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">wawa's mind</h1>
        <p className="text-[#4b5563] text-sm mt-1">Every tweet + the reasoning behind it. Full transparency.</p>
      </div>

      {error && (
        <div className="mb-4 p-3 border border-[#ff3b3b44] rounded text-[#ff3b3b] text-sm">⚠ {error}</div>
      )}

      {loading ? (
        <div className="text-center py-12 text-[#4b5563]">
          loading tweets<span className="loading-dot-1">.</span>
          <span className="loading-dot-2">.</span>
          <span className="loading-dot-3">.</span>
        </div>
      ) : tweets.length === 0 ? (
        <div className="text-center py-12 text-[#4b5563]">
          <div className="text-4xl mb-3">🤫</div>
          <div>wawa hasn't tweeted yet</div>
        </div>
      ) : (
        <div className="space-y-4">
          {tweets.map((t, i) => (
            <TweetCard key={t.tweet_id ?? i} tweet={t} />
          ))}
        </div>
      )}

      <div className="mt-6 text-center text-xs text-[#4b5563]">
        auto-refreshes every 30s
      </div>
    </div>
  )
}
