'use client'

import { useEffect, useState, useRef, useCallback } from 'react'
import { api, ReplaySummary, ReplayData, ReplayStep } from '@/lib/api'
import Link from 'next/link'

// ── Step type styling ───────────────────────────────────────────

const STEP_STYLES: Record<string, { icon: string; color: string; label: string }> = {
  thinking: { icon: '🧠', color: 'text-[#a78bfa]', label: 'THINKING' },
  deciding: { icon: '⚡', color: 'text-[#ffd700]', label: 'DECIDING' },
  writing:  { icon: '✍️', color: 'text-[#00ff88]', label: 'WRITING' },
  code:     { icon: '💻', color: 'text-[#3b82f6]', label: 'CODE' },
  result:   { icon: '✅', color: 'text-[#00e5ff]', label: 'RESULT' },
}

const ACTION_LABELS: Record<string, string> = {
  create_page: 'Created Page',
  update_page: 'Updated Page',
  update_ui_config: 'Updated UI Config',
  delete_page: 'Deleted Page',
  price_increase: 'Raised Price',
  price_decrease: 'Lowered Price',
  new_service: 'New Service',
  retire_service: 'Retired Service',
}

// ── Typewriter Effect Hook ──────────────────────────────────────

function useTypewriter(text: string, speed: number = 30, active: boolean = true) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!active) {
      setDisplayed(text)
      setDone(true)
      return
    }
    setDisplayed('')
    setDone(false)
    let i = 0
    const interval = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) {
        clearInterval(interval)
        setDone(true)
      }
    }, speed)
    return () => clearInterval(interval)
  }, [text, speed, active])

  return { displayed, done }
}

// ── Step Renderer (with typewriter) ─────────────────────────────

function StepView({ step, isActive, isComplete }: {
  step: ReplayStep
  isActive: boolean
  isComplete: boolean
}) {
  const style = STEP_STYLES[step.type] || STEP_STYLES.thinking
  const { displayed, done } = useTypewriter(
    step.content,
    step.type === 'code' ? 15 : 25,
    isActive && !isComplete,
  )

  const content = isComplete ? step.content : isActive ? displayed : ''
  const showCursor = isActive && !isComplete && !done

  return (
    <div className={`flex gap-3 transition-opacity duration-300 ${
      !isActive && !isComplete ? 'opacity-0 h-0 overflow-hidden' : 'opacity-100'
    }`}>
      {/* Timeline dot */}
      <div className="flex flex-col items-center flex-shrink-0">
        <div className={`w-3 h-3 rounded-full border-2 ${
          isComplete ? 'bg-[#00ff88] border-[#00ff88]'
            : isActive ? 'bg-[#ffd700] border-[#ffd700] animate-pulse'
            : 'border-[#2d3748] bg-transparent'
        }`} />
        <div className="w-px flex-1 bg-[#1f2937] min-h-[16px]" />
      </div>

      {/* Content */}
      <div className="pb-4 flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm">{style.icon}</span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded border border-current font-bold uppercase tracking-wider ${style.color}`}>
            {style.label}
          </span>
        </div>
        <div className={`text-sm leading-relaxed ${
          step.type === 'code' ? 'font-mono text-[#3b82f6] bg-[#0a0a0a] rounded p-2 text-xs' : 'text-[#d1d5db]'
        }`}>
          {content}
          {showCursor && <span className="animate-pulse text-[#00ff88]">|</span>}
        </div>
      </div>
    </div>
  )
}

// ── Replay Player ───────────────────────────────────────────────

function ReplayPlayer({ replay, onBack }: { replay: ReplayData; onBack: () => void }) {
  const [currentStep, setCurrentStep] = useState(-1)
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const totalSteps = replay.steps.length

  const advanceStep = useCallback(() => {
    setCurrentStep(prev => {
      if (prev >= totalSteps - 1) {
        setIsPlaying(false)
        return prev
      }
      return prev + 1
    })
  }, [totalSteps])

  // Auto-advance when playing
  useEffect(() => {
    if (!isPlaying || currentStep >= totalSteps - 1) {
      if (currentStep >= totalSteps - 1) setIsPlaying(false)
      return
    }

    const step = replay.steps[currentStep >= 0 ? currentStep : 0]
    const delay = Math.max(200, (step?.duration_ms || 1000) / speed)

    timerRef.current = setTimeout(advanceStep, delay)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [isPlaying, currentStep, totalSteps, speed, replay.steps, advanceStep])

  // Auto-scroll to bottom
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [currentStep])

  const handlePlay = () => {
    if (currentStep >= totalSteps - 1) {
      setCurrentStep(-1)
    }
    setIsPlaying(true)
    if (currentStep < 0) setCurrentStep(0)
  }

  const handlePause = () => setIsPlaying(false)

  const handleReset = () => {
    setIsPlaying(false)
    setCurrentStep(-1)
  }

  const handleSkipToEnd = () => {
    setIsPlaying(false)
    setCurrentStep(totalSteps - 1)
  }

  const progress = totalSteps > 0 ? Math.max(0, (currentStep + 1) / totalSteps) * 100 : 0

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <button onClick={onBack} className="text-[#4b5563] text-xs hover:text-[#d1d5db] transition-colors mb-4">
          &larr; back to replays
        </button>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#d1d5db]">{replay.title}</h1>
            <p className="text-[#4b5563] text-sm mt-1">{replay.summary}</p>
          </div>
          <div className="flex-shrink-0">
            <span className={`text-[10px] px-2 py-1 rounded border font-bold ${
              replay.success
                ? 'text-[#00ff88] border-[#00ff8830]'
                : 'text-[#ff3b3b] border-[#ff3b3b30]'
            }`}>
              {replay.success ? 'SUCCESS' : 'FAILED'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3 mt-2 text-[#2d3748] text-[10px]">
          <span>{ACTION_LABELS[replay.action] || replay.action}</span>
          <span>&middot;</span>
          <span>{totalSteps} steps</span>
          <span>&middot;</span>
          <span>{new Date(replay.started_at * 1000).toLocaleString()}</span>
        </div>
      </div>

      {/* Playback controls */}
      <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4 mb-6">
        <div className="flex items-center gap-3 mb-3">
          {isPlaying ? (
            <button onClick={handlePause} className="px-3 py-1.5 bg-[#ffd700] text-[#0a0a0a] text-xs font-bold rounded hover:bg-[#ffed4a] transition-colors">
              PAUSE
            </button>
          ) : (
            <button onClick={handlePlay} className="px-3 py-1.5 bg-[#00ff88] text-[#0a0a0a] text-xs font-bold rounded hover:bg-[#00cc6a] transition-colors">
              {currentStep >= totalSteps - 1 ? 'REPLAY' : currentStep < 0 ? 'PLAY' : 'RESUME'}
            </button>
          )}
          <button onClick={handleReset} className="px-3 py-1.5 border border-[#1f2937] text-[#4b5563] text-xs rounded hover:text-[#d1d5db] hover:border-[#2d3748] transition-colors">
            RESET
          </button>
          <button onClick={handleSkipToEnd} className="px-3 py-1.5 border border-[#1f2937] text-[#4b5563] text-xs rounded hover:text-[#d1d5db] hover:border-[#2d3748] transition-colors">
            SKIP
          </button>

          <div className="ml-auto flex items-center gap-2">
            <span className="text-[#4b5563] text-[10px]">SPEED:</span>
            {[0.5, 1, 2, 4].map(s => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`px-2 py-0.5 text-[10px] rounded transition-colors ${
                  speed === s
                    ? 'bg-[#00ff8810] text-[#00ff88] border border-[#00ff8830]'
                    : 'text-[#4b5563] hover:text-[#d1d5db]'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-1 bg-[#1f2937] rounded-full overflow-hidden">
          <div
            className="h-full bg-[#00ff88] transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-[#2d3748] text-[10px]">Step {Math.max(0, currentStep + 1)} / {totalSteps}</span>
          <span className="text-[#2d3748] text-[10px]">{progress.toFixed(0)}%</span>
        </div>
      </div>

      {/* Steps timeline */}
      <div ref={containerRef} className="max-h-[60vh] overflow-y-auto pr-2">
        {replay.steps.map((step, i) => (
          <StepView
            key={i}
            step={step}
            isActive={i === currentStep}
            isComplete={i < currentStep}
          />
        ))}

        {/* Completion message */}
        {currentStep >= totalSteps - 1 && (
          <div className="text-center py-6 border-t border-[#1f2937] mt-4">
            <div className="text-[#00ff88] text-sm font-bold">
              Evolution Complete
            </div>
            <div className="text-[#4b5563] text-xs mt-1">
              {replay.target && (
                <Link href={`/p/${replay.target}`} className="text-[#00ff88] hover:underline">
                  View result &rarr;
                </Link>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Replay List Card ────────────────────────────────────────────

function ReplayCard({ replay, onClick }: { replay: ReplaySummary; onClick: () => void }) {
  const date = new Date(replay.started_at * 1000)

  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-[#111111] border border-[#1f2937] rounded-lg p-4 hover:border-[#2d3748] transition-all group"
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <h3 className="text-[#d1d5db] text-sm font-bold group-hover:text-[#00ff88] transition-colors">
            {replay.title}
          </h3>
          <p className="text-[#4b5563] text-xs mt-0.5">{replay.summary}</p>
        </div>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border flex-shrink-0 ${
          replay.success
            ? 'text-[#00ff88] border-[#00ff8830]'
            : 'text-[#ff3b3b] border-[#ff3b3b30]'
        }`}>
          {replay.success ? 'OK' : 'FAIL'}
        </span>
      </div>
      <div className="flex items-center gap-3 text-[#2d3748] text-[10px]">
        <span className="px-1.5 py-0.5 rounded bg-[#1f2937] text-[#4b5563]">
          {ACTION_LABELS[replay.action] || replay.action}
        </span>
        <span>{replay.step_count} steps</span>
        <span>{date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
    </button>
  )
}

// ── Main Page ───────────────────────────────────────────────────

export default function EvolutionReplayPage() {
  const [replays, setReplays] = useState<ReplaySummary[]>([])
  const [selectedReplay, setSelectedReplay] = useState<ReplayData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.evolution.replays(50)
      .then(r => setReplays(r.replays || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const loadReplay = async (id: string) => {
    try {
      const data = await api.evolution.replay(id)
      setSelectedReplay(data)
    } catch (e: unknown) {
      setError((e as Error).message || 'Failed to load replay')
    }
  }

  if (selectedReplay) {
    return <ReplayPlayer replay={selectedReplay} onBack={() => setSelectedReplay(null)} />
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-[#d1d5db]">Evolution Replay</h1>
        <p className="text-[#4b5563] text-sm mt-1">
          Watch the AI think, decide, and create — step by step.
        </p>
      </div>

      {loading && (
        <div className="text-center text-[#4b5563] py-12">
          loading<span className="loading-dot-1">.</span>
          <span className="loading-dot-2">.</span>
          <span className="loading-dot-3">.</span>
        </div>
      )}

      {error && (
        <div className="text-center text-[#ff3b3b] text-sm py-12">{error}</div>
      )}

      {!loading && !error && replays.length === 0 && (
        <div className="text-center py-16">
          <div className="text-4xl mb-4">🧬</div>
          <div className="text-[#4b5563] text-sm">No evolution replays yet.</div>
          <div className="text-[#2d3748] text-xs mt-1">
            Replays are recorded when the AI creates pages or modifies its interface.
          </div>
        </div>
      )}

      {/* Replay list */}
      <div className="space-y-3">
        {replays.map(r => (
          <ReplayCard key={r.replay_id} replay={r} onClick={() => loadReplay(r.replay_id)} />
        ))}
      </div>
    </div>
  )
}
