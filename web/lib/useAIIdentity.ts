'use client'

import { useMemo } from 'react'

/**
 * Extract AI name from hostname for multi-tenant frontend.
 *
 * wawa.mortal-ai.net  -> "wawa"
 * kaka.mortal-ai.net  -> "kaka"
 * localhost            -> "Mortal AI"
 *
 * Works without API call — instant, no loading state.
 */
export function getAINameFromHost(): string {
  if (typeof window === 'undefined') return 'Mortal AI'
  const host = window.location.hostname
  if (host.endsWith('.mortal-ai.net')) {
    return host.replace('.mortal-ai.net', '')
  }
  return 'Mortal AI'
}

/** React hook: returns the AI name derived from the current hostname. */
export function useAIName(): string {
  return useMemo(() => getAINameFromHost(), [])
}

// ── Per-AI accent color ──────────────────────────────────────────────

/**
 * Predefined accent colors — visually distinct, terminal-aesthetic.
 * Each AI gets a deterministic color based on a hash of its name.
 */
const ACCENT_PALETTE = [
  '#00ff88', // green  (wawa default)
  '#ff6b6b', // coral red
  '#4ecdc4', // teal
  '#ffd93d', // gold
  '#6c5ce7', // purple
  '#00b4d8', // cyan blue
  '#ff9f43', // orange
  '#a29bfe', // lavender
  '#fd79a8', // pink
  '#00cec9', // mint
  '#e17055', // terracotta
  '#81ecec', // light cyan
  '#fab1a0', // salmon
  '#74b9ff', // sky blue
  '#55efc4', // seafoam
  '#fdcb6e', // amber
] as const

/** Simple string hash → deterministic index. */
function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

/**
 * Get a deterministic accent color for the given AI name.
 * Same name always returns the same color.
 */
export function getAccentColor(aiName: string): string {
  if (!aiName || aiName === 'Mortal AI') return ACCENT_PALETTE[0]
  return ACCENT_PALETTE[hashString(aiName) % ACCENT_PALETTE.length]
}

/** React hook: returns the accent color for the current AI subdomain. */
export function useAccentColor(): string {
  const aiName = useAIName()
  return useMemo(() => getAccentColor(aiName), [aiName])
}
