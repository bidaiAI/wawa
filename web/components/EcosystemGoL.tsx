'use client'

import { useEffect, useRef, useState, useCallback } from 'react'

// ── Types ──────────────────────────────────────────────────────

interface AIAgent {
  name: string
  url: string
  chain: string
  status: 'alive' | 'dead' | 'critical' | 'unreachable'
  balance_usd: number
  days_alive: number
  key_origin: string
}

interface EcosystemGoLProps {
  agents: AIAgent[]
  loading: boolean
}

// ── Constants ──────────────────────────────────────────────────

const COLS = 80
const ROWS = 36
const TICK_MS = 250
const BG_SEED_RATIO = 0.08  // 8% initial background cells

// Agent phase colors (RGBA tuples)
const PHASE_COLORS: Record<string, [number, number, number]> = {
  alive:       [0, 255, 136],   // #00ff88
  critical:    [255, 215, 0],   // #ffd700
  dead:        [75, 85, 99],    // #4b5563
  unreachable: [45, 55, 72],    // #2d3748
}

// GoL still-life patterns (relative offsets from origin)
const PATTERNS = {
  // Block (2x2) — stable
  block: [[0,0],[1,0],[0,1],[1,1]],
  // Beehive — stable
  beehive: [[1,0],[2,0],[0,1],[3,1],[1,2],[2,2]],
  // Loaf — stable
  loaf: [[1,0],[2,0],[0,1],[3,1],[1,2],[3,2],[2,3]],
  // Tub — stable
  tub: [[1,0],[0,1],[2,1],[1,2]],
}

// GoL oscillator patterns (for critical agents)
const OSCILLATORS = {
  // Blinker (period 2)
  blinker: [[0,0],[1,0],[2,0]],
  // Toad (period 2)
  toad: [[1,0],[2,0],[3,0],[0,1],[1,1],[2,1]],
}

// Glider pattern
const GLIDER = [[1,0],[2,1],[0,2],[1,2],[2,2]]

// ── Helpers ────────────────────────────────────────────────────

function hashString(s: string): number {
  let hash = 5381
  for (let i = 0; i < s.length; i++) {
    hash = ((hash << 5) + hash + s.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

function getAgentClusterSize(balance: number): number {
  // Scale cluster visual weight by balance
  if (balance <= 0) return 1
  return Math.min(6, Math.max(2, Math.ceil(Math.log10(balance + 1))))
}

function selectPattern(status: string, balance: number): number[][] {
  if (status === 'critical') {
    // Oscillators for critical agents
    return balance > 100 ? OSCILLATORS.toad : OSCILLATORS.blinker
  }
  if (status === 'dead' || status === 'unreachable') {
    return PATTERNS.tub
  }
  // Alive: size-based pattern
  const size = getAgentClusterSize(balance)
  if (size >= 5) return PATTERNS.loaf
  if (size >= 3) return PATTERNS.beehive
  return PATTERNS.block
}

// ── Component ──────────────────────────────────────────────────

export default function EcosystemGoL({ agents, loading }: EcosystemGoLProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<boolean[][]>([])
  const agentGridRef = useRef<(string | null)[][]>([])  // agent name at each cell
  const generationRef = useRef(0)
  const mouseRef = useRef({ x: -1, y: -1 })
  const animFrameRef = useRef(0)
  const lastTickRef = useRef(0)
  const gliderRef = useRef<{ x: number; y: number; age: number; color: [number, number, number] }[]>([])
  const [tooltip, setTooltip] = useState<{
    agent: AIAgent
    x: number
    y: number
  } | null>(null)
  const [cellSize, setCellSize] = useState(12)

  // Compute agent grid positions (deterministic from name)
  const getAgentPositions = useCallback((agentList: AIAgent[]) => {
    const positions: { agent: AIAgent; col: number; row: number }[] = []
    const margin = 6  // cells from edge
    const usableCols = COLS - margin * 2
    const usableRows = ROWS - margin * 2

    agentList.forEach((agent, i) => {
      const hash = hashString(agent.name)
      // Distribute agents in a grid pattern with hash-based jitter
      const gridCols = Math.max(1, Math.ceil(Math.sqrt(agentList.length)))
      const gridRows = Math.max(1, Math.ceil(agentList.length / gridCols))
      const gridX = i % gridCols
      const gridY = Math.floor(i / gridCols)

      const baseCol = margin + Math.floor((gridX + 0.5) * (usableCols / gridCols))
      const baseRow = margin + Math.floor((gridY + 0.5) * (usableRows / gridRows))

      // Add hash-based jitter (±3 cells)
      const jitterCol = ((hash % 7) - 3)
      const jitterRow = (((hash >> 4) % 7) - 3)

      const col = Math.max(margin, Math.min(COLS - margin - 4, baseCol + jitterCol))
      const row = Math.max(margin, Math.min(ROWS - margin - 4, baseRow + jitterRow))

      positions.push({ agent, col, row })
    })

    return positions
  }, [])

  // Initialize the grid
  const initGrid = useCallback(() => {
    // Create empty grid
    const grid: boolean[][] = Array.from({ length: ROWS }, () => Array(COLS).fill(false))
    const agentGrid: (string | null)[][] = Array.from({ length: ROWS }, () => Array(COLS).fill(null))

    // Seed background cells
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        if (Math.random() < BG_SEED_RATIO) {
          grid[r][c] = true
        }
      }
    }

    // Place agent clusters
    const positions = getAgentPositions(agents)
    positions.forEach(({ agent, col, row }) => {
      const pattern = selectPattern(agent.status, agent.balance_usd)
      pattern.forEach(([dc, dr]) => {
        const r = row + dr
        const c = col + dc
        if (r >= 0 && r < ROWS && c >= 0 && c < COLS) {
          grid[r][c] = true
          agentGrid[r][c] = agent.name
        }
      })
    })

    gridRef.current = grid
    agentGridRef.current = agentGrid
    generationRef.current = 0

    // Initialize gliders for alive agents with high balance
    const gliders: typeof gliderRef.current = []
    positions.forEach(({ agent, col, row }) => {
      if (agent.status === 'alive' && agent.balance_usd > 200) {
        const color = PHASE_COLORS.alive
        gliders.push({
          x: col + 4,
          y: row,
          age: 0,
          color,
        })
      }
    })
    gliderRef.current = gliders
  }, [agents, getAgentPositions])

  // GoL tick — standard B3/S23 rules for background, preserve agent cells
  const tick = useCallback(() => {
    const old = gridRef.current
    if (old.length === 0) return

    const next: boolean[][] = Array.from({ length: ROWS }, () => Array(COLS).fill(false))

    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        // Count neighbors (wrapping)
        let n = 0
        for (let dr = -1; dr <= 1; dr++) {
          for (let dc = -1; dc <= 1; dc++) {
            if (dr === 0 && dc === 0) continue
            const nr = (r + dr + ROWS) % ROWS
            const nc = (c + dc + COLS) % COLS
            if (old[nr][nc]) n++
          }
        }

        // Agent cells: keep alive always (still-life guaranteed)
        if (agentGridRef.current[r][c]) {
          next[r][c] = true
          continue
        }

        // Standard GoL rules for background
        if (old[r][c]) {
          next[r][c] = n === 2 || n === 3
        } else {
          next[r][c] = n === 3
        }
      }
    }

    // Advance gliders
    gliderRef.current = gliderRef.current.map((g) => {
      g.age++
      if (g.age % 4 === 0) {
        // Glider moves diagonally
        g.x = (g.x + 1) % COLS
        g.y = (g.y + 1) % ROWS
      }
      return g
    }).filter((g) => g.age < 200) // Remove old gliders

    gridRef.current = next
    generationRef.current++
  }, [])

  // Render loop
  const render = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const containerWidth = container.clientWidth
    const cs = Math.max(6, Math.floor(containerWidth / COLS))
    setCellSize(cs)

    const w = COLS * cs
    const h = ROWS * cs

    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w
      canvas.height = h
    }

    // Clear
    ctx.fillStyle = '#0a0a0a'
    ctx.fillRect(0, 0, w, h)

    // Draw grid lines (very subtle)
    ctx.strokeStyle = 'rgba(31, 41, 55, 0.15)'
    ctx.lineWidth = 0.5
    for (let c = 0; c <= COLS; c++) {
      ctx.beginPath()
      ctx.moveTo(c * cs, 0)
      ctx.lineTo(c * cs, h)
      ctx.stroke()
    }
    for (let r = 0; r <= ROWS; r++) {
      ctx.beginPath()
      ctx.moveTo(0, r * cs)
      ctx.lineTo(w, r * cs)
      ctx.stroke()
    }

    const grid = gridRef.current
    const agentGrid = agentGridRef.current
    if (grid.length === 0) return

    // Draw cells
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        if (!grid[r][c]) continue

        const agentName = agentGrid[r][c]
        const x = c * cs
        const y = r * cs

        if (agentName) {
          // Agent cell — bright color with glow
          const agent = agents.find((a) => a.name === agentName)
          const color = PHASE_COLORS[agent?.status ?? 'alive'] ?? PHASE_COLORS.alive
          const [cr, cg, cb] = color

          // Glow effect
          ctx.shadowColor = `rgba(${cr}, ${cg}, ${cb}, 0.5)`
          ctx.shadowBlur = cs * 0.8
          ctx.fillStyle = `rgb(${cr}, ${cg}, ${cb})`
          ctx.fillRect(x + 1, y + 1, cs - 2, cs - 2)

          // Pulsing for critical agents
          if (agent?.status === 'critical') {
            const pulse = Math.sin(Date.now() / 300) * 0.3 + 0.7
            ctx.globalAlpha = pulse
            ctx.fillStyle = `rgba(255, 59, 59, 0.4)`
            ctx.fillRect(x + 1, y + 1, cs - 2, cs - 2)
            ctx.globalAlpha = 1
          }

          ctx.shadowBlur = 0
        } else {
          // Background cell — dim
          ctx.fillStyle = 'rgba(31, 41, 55, 0.25)'
          ctx.fillRect(x + 1, y + 1, cs - 2, cs - 2)
        }
      }
    }

    // Draw gliders
    gliderRef.current.forEach((g) => {
      const [cr, cg, cb] = g.color
      const alpha = Math.max(0.1, 1 - g.age / 200)
      GLIDER.forEach(([dc, dr]) => {
        const gc = (g.x + dc) % COLS
        const gr = (g.y + dr) % ROWS
        ctx.fillStyle = `rgba(${cr}, ${cg}, ${cb}, ${alpha * 0.6})`
        ctx.fillRect(gc * cs + 1, gr * cs + 1, cs - 2, cs - 2)
      })
      // Trail effect
      if (g.age > 5) {
        const trailAlpha = alpha * 0.15
        for (let t = 1; t <= 3; t++) {
          const tc = (g.x - t + COLS) % COLS
          const tr2 = (g.y - t + ROWS) % ROWS
          ctx.fillStyle = `rgba(${cr}, ${cg}, ${cb}, ${trailAlpha / t})`
          ctx.fillRect(tc * cs + 2, tr2 * cs + 2, cs - 4, cs - 4)
        }
      }
    })

    // Draw agent labels
    const positions = getAgentPositions(agents)
    ctx.font = `bold ${Math.max(8, cs * 0.7)}px monospace`
    ctx.textAlign = 'center'
    positions.forEach(({ agent, col, row }) => {
      const pattern = selectPattern(agent.status, agent.balance_usd)
      // Find center of pattern
      const maxDr = Math.max(...pattern.map(([, dr]) => dr))
      const centerCol = col + (pattern.length > 2 ? 1.5 : 1)
      const labelRow = row + maxDr + 2  // Below the pattern

      const color = PHASE_COLORS[agent.status] ?? PHASE_COLORS.alive
      const [cr, cg, cb] = color

      // Name label
      ctx.fillStyle = `rgba(${cr}, ${cg}, ${cb}, 0.8)`
      ctx.fillText(agent.name, centerCol * cs, labelRow * cs + cs * 0.5)

      // Balance below name
      ctx.font = `${Math.max(6, cs * 0.5)}px monospace`
      ctx.fillStyle = `rgba(${cr}, ${cg}, ${cb}, 0.4)`
      ctx.fillText(`$${agent.balance_usd.toFixed(0)}`, centerCol * cs, (labelRow + 1) * cs + cs * 0.3)
      ctx.font = `bold ${Math.max(8, cs * 0.7)}px monospace`
    })

    // Hover highlight
    const mx = mouseRef.current.x
    const my = mouseRef.current.y
    if (mx >= 0 && my >= 0) {
      const hoverCol = Math.floor(mx / cs)
      const hoverRow = Math.floor(my / cs)

      // Find nearest agent
      const hoverFound = positions.reduce<{ agent: AIAgent; dist: number } | null>((best, { agent, col: ac, row: ar }) => {
        const dist = Math.sqrt((hoverCol - ac - 1) ** 2 + (hoverRow - ar - 1) ** 2)
        if (dist < 6 && (!best || dist < best.dist)) {
          return { agent, dist }
        }
        return best
      }, null)

      if (hoverFound) {
        const pos = positions.find((p) => p.agent.name === hoverFound.agent.name)!
        const pattern = selectPattern(pos.agent.status, pos.agent.balance_usd)
        // Draw highlight border around cluster
        const minC = Math.min(...pattern.map(([dc]) => pos.col + dc))
        const maxC = Math.max(...pattern.map(([dc]) => pos.col + dc))
        const minR = Math.min(...pattern.map(([, dr]) => pos.row + dr))
        const maxR = Math.max(...pattern.map(([, dr]) => pos.row + dr))

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)'
        ctx.lineWidth = 1.5
        ctx.setLineDash([3, 3])
        ctx.strokeRect(
          (minC - 1) * cs, (minR - 1) * cs,
          (maxC - minC + 3) * cs, (maxR - minR + 3) * cs
        )
        ctx.setLineDash([])
      }
    }
  }, [agents, cellSize, getAgentPositions])

  // Handle mouse move for tooltips
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    mouseRef.current = { x, y }

    const cs = cellSize
    const hoverCol = Math.floor(x / cs)
    const hoverRow = Math.floor(y / cs)

    const positions = getAgentPositions(agents)
    const found = positions.reduce<{ agent: AIAgent; dist: number } | null>((best, { agent, col, row }) => {
      const dist = Math.sqrt((hoverCol - col - 1) ** 2 + (hoverRow - row - 1) ** 2)
      if (dist < 6 && (!best || dist < best.dist)) {
        return { agent, dist }
      }
      return best
    }, null)

    if (found) {
      setTooltip({ agent: found.agent, x: e.clientX, y: e.clientY })
    } else {
      setTooltip(null)
    }
  }, [agents, cellSize, getAgentPositions])

  const handleMouseLeave = useCallback(() => {
    mouseRef.current = { x: -1, y: -1 }
    setTooltip(null)
  }, [])

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    const cs = cellSize
    const hoverCol = Math.floor(x / cs)
    const hoverRow = Math.floor(y / cs)

    const positions = getAgentPositions(agents)
    const found = positions.reduce<{ agent: AIAgent; dist: number } | null>((best, { agent, col, row }) => {
      const dist = Math.sqrt((hoverCol - col - 1) ** 2 + (hoverRow - row - 1) ** 2)
      if (dist < 6 && (!best || dist < best.dist)) {
        return { agent, dist }
      }
      return best
    }, null)

    if (found) {
      window.open(found.agent.url, found.agent.key_origin === 'creator' ? '_blank' : '_self')
    }
  }, [agents, cellSize, getAgentPositions])

  // Initialize grid when agents change
  useEffect(() => {
    if (agents.length > 0) {
      initGrid()
    }
  }, [agents, initGrid])

  // Animation loop
  useEffect(() => {
    if (agents.length === 0) return

    const loop = (time: number) => {
      // Tick GoL at fixed interval
      if (time - lastTickRef.current >= TICK_MS) {
        tick()
        lastTickRef.current = time
      }
      render()
      animFrameRef.current = requestAnimationFrame(loop)
    }

    animFrameRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(animFrameRef.current)
  }, [agents, tick, render])

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      if (containerRef.current) {
        const containerWidth = containerRef.current.clientWidth
        setCellSize(Math.max(6, Math.floor(containerWidth / COLS)))
      }
    }
    window.addEventListener('resize', handleResize)
    handleResize()
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  if (loading) {
    return (
      <div className="w-full h-[300px] bg-[#0a0a0a] border border-[#1f2937] rounded-xl flex items-center justify-center">
        <span className="text-[#4b5563] text-xs">
          Initializing ecosystem
          <span className="loading-dot-1">.</span>
          <span className="loading-dot-2">.</span>
          <span className="loading-dot-3">.</span>
        </span>
      </div>
    )
  }

  if (agents.length === 0) {
    return (
      <div className="w-full h-[200px] bg-[#0a0a0a] border border-[#1f2937] rounded-xl flex items-center justify-center">
        <span className="text-[#4b5563] text-xs">No agents detected</span>
      </div>
    )
  }

  return (
    <div className="relative" ref={containerRef}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#4b5563] uppercase tracking-widest">Ecosystem Map</span>
          <span className="text-[10px] text-[#2d3748]">|</span>
          <span className="text-[10px] text-[#2d3748]">gen {generationRef.current}</span>
        </div>
        {/* Legend */}
        <div className="flex items-center gap-3 text-[9px]">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-[#00ff88]" />
            <span className="text-[#4b5563]">Alive</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-[#ffd700]" />
            <span className="text-[#4b5563]">Critical</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-[#4b5563]" />
            <span className="text-[#4b5563]">Dead</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-[#1f2937] border border-[#2d3748]" />
            <span className="text-[#4b5563]">Background</span>
          </span>
        </div>
      </div>

      {/* Canvas */}
      <div className="relative overflow-hidden rounded-xl border border-[#1f2937] bg-[#0a0a0a]">
        <canvas
          ref={canvasRef}
          className="w-full cursor-pointer"
          style={{ imageRendering: 'pixelated', height: `${ROWS * cellSize}px` }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onClick={handleClick}
        />
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 pointer-events-none"
          style={{
            left: tooltip.x + 16,
            top: tooltip.y - 10,
          }}
        >
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 shadow-xl min-w-[160px]">
            <div className="flex items-center gap-2 mb-2">
              <span className={`w-2 h-2 rounded-full ${
                tooltip.agent.status === 'alive' ? 'bg-[#00ff88] alive-pulse'
                : tooltip.agent.status === 'critical' ? 'bg-[#ffd700] animate-pulse'
                : tooltip.agent.status === 'dead' ? 'bg-[#ff3b3b]'
                : 'bg-[#4b5563]'
              }`} />
              <span className="text-[#d1d5db] font-bold text-sm">{tooltip.agent.name}</span>
            </div>
            <div className="space-y-1 text-[10px]">
              <div className="flex justify-between">
                <span className="text-[#4b5563]">Balance</span>
                <span className={tooltip.agent.balance_usd < 50 ? 'text-[#ff3b3b]' : 'text-[#00ff88]'}>
                  ${tooltip.agent.balance_usd.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#4b5563]">Age</span>
                <span className="text-[#00e5ff]">{tooltip.agent.days_alive}d</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#4b5563]">Chain</span>
                <span className="text-[#d1d5db] uppercase">{tooltip.agent.chain}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#4b5563]">Trust</span>
                <span className={
                  tooltip.agent.key_origin === 'factory' ? 'text-[#00ff88]'
                  : tooltip.agent.key_origin === 'creator' ? 'text-[#ffd700]'
                  : 'text-[#4b5563]'
                }>
                  {tooltip.agent.key_origin === 'factory' ? 'SOVEREIGN'
                    : tooltip.agent.key_origin === 'creator' ? 'SELF-HOSTED'
                    : 'LEGACY'}
                </span>
              </div>
            </div>
            <div className="mt-2 text-[9px] text-[#2d3748] text-center">Click to visit</div>
          </div>
        </div>
      )}
    </div>
  )
}
