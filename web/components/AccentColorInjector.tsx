'use client'

import { useEffect } from 'react'
import { useAIName, getAccentColor } from '@/lib/useAIIdentity'

/**
 * Injects the per-AI accent color as a CSS variable on <html>.
 * This makes .glow-green, .card-hover, and any var(--accent) usage
 * automatically adopt the AI's unique color.
 *
 * Mount once in the AI layout — no visual output.
 */
export default function AccentColorInjector() {
  const aiName = useAIName()

  useEffect(() => {
    const color = getAccentColor(aiName)
    document.documentElement.style.setProperty('--accent', color)
    // Also update the theme-color meta tag for mobile browser chrome
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', color)
    return () => {
      document.documentElement.style.removeProperty('--accent')
    }
  }, [aiName])

  return null
}
