'use client'

import React from 'react'

interface State {
  hasError: boolean
  errorMsg: string
}

/**
 * Global error boundary to catch React render errors caused by browser extensions
 * (e.g. Google Translate DOM mutations) and show a friendly reload prompt instead
 * of a full page crash.
 */
export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  State
> {
  constructor(props: { children: React.ReactNode; fallback?: React.ReactNode }) {
    super(props)
    this.state = { hasError: false, errorMsg: '' }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMsg: error?.message?.slice(0, 120) ?? '' }
  }

  componentDidCatch(error: Error) {
    // Silently log — don't bubble up to Next.js global error handler
    console.warn('[mortal] React render error (likely Google Translate):', error.message)
  }

  handleReload = () => {
    this.setState({ hasError: false, errorMsg: '' })
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback

      return (
        <div
          className="min-h-[60vh] flex flex-col items-center justify-center gap-4 px-4 text-center"
          translate="no"
        >
          <div className="text-5xl" translate="no">⚠</div>
          <div className="text-[#ffd700] font-bold text-lg" translate="no">
            Page render error
          </div>
          <p className="text-[#4b5563] text-sm max-w-xs" translate="no">
            A browser extension (e.g. Google Translate) may have caused a DOM conflict.
            Reload to fix.
          </p>
          {this.state.errorMsg && (
            <div
              className="text-[#2d3748] text-[10px] font-mono max-w-xs break-all"
              translate="no"
            >
              {this.state.errorMsg}
            </div>
          )}
          <button
            onClick={this.handleReload}
            className="mt-2 px-6 py-2.5 bg-[#00e5ff] text-[#0a0a0a] font-bold rounded-lg text-sm hover:bg-[#00b8cc] transition-colors"
            translate="no"
          >
            Reload Page
          </button>
          <p className="text-[#2d3748] text-[10px]" translate="no">
            Tip: disable Google Translate on this site to prevent these errors
          </p>
        </div>
      )
    }

    return this.props.children
  }
}
