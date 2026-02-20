import { NextRequest, NextResponse } from 'next/server'

/**
 * Subdomain-based routing middleware.
 *
 * mortal-ai.net / www.mortal-ai.net  ->  /platform/...  (platform pages)
 * *.mortal-ai.net (e.g. wawa)        ->  /ai/...        (AI instance pages)
 * localhost                           ->  based on NEXT_PUBLIC_MODE env var
 */
export function middleware(request: NextRequest) {
  const hostname = request.headers.get('host') || ''
  const pathname = request.nextUrl.pathname

  // Skip internal routes, static files, and API routes
  if (
    pathname.startsWith('/platform') ||
    pathname.startsWith('/ai') ||
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon') ||
    pathname.startsWith('/api')
  ) {
    return NextResponse.next()
  }

  // Determine context from subdomain
  const parts = hostname.split('.')
  let isAIInstance = false

  // Multi-part domain: check if first part is a subdomain (not www)
  // e.g. "wawa.mortal-ai.net" -> parts = ["wawa", "mortal-ai", "net"]
  if (parts.length >= 3 && parts[0] !== 'www') {
    isAIInstance = true
  }

  // Vercel preview deployments: *.vercel.app
  if (hostname.includes('vercel.app')) {
    // Default to platform mode on vercel.app (main deployment)
    const sub = parts[0]
    if (sub && !sub.includes('wawa') && !hostname.startsWith('wawa')) {
      isAIInstance = false
    } else {
      isAIInstance = true
    }
  }

  // Localhost: use NEXT_PUBLIC_MODE env var (default: "ai" for backward compat)
  if (hostname.includes('localhost') || hostname.includes('127.0.0.1')) {
    const mode = process.env.NEXT_PUBLIC_MODE || 'ai'
    isAIInstance = mode !== 'platform'
  }

  // Rewrite to internal path prefix
  const prefix = isAIInstance ? '/ai' : '/platform'
  const url = request.nextUrl.clone()
  url.pathname = `${prefix}${pathname}`
  return NextResponse.rewrite(url)
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - /platform/... (internal platform routes)
     * - /ai/...       (internal AI routes)
     * - /_next/...    (Next.js internals)
     * - /favicon.ico
     * - /api/...      (API routes if any)
     */
    '/((?!_next/static|_next/image|favicon\\.ico|platform|ai|api).*)',
  ],
}
