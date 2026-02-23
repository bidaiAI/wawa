import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'

/**
 * Twitter OAuth 1.0a — Step 1: Get request token and redirect to Twitter.
 *
 * Called by admin UI: GET /api/twitter/start?subdomain=wawa&ai_url=https://api.wawa.mortal-ai.net
 * Stores subdomain + ai_url in a short-lived signed cookie, then redirects to Twitter.
 */

const CONSUMER_KEY = process.env.PLATFORM_TWITTER_CONSUMER_KEY || ''
const CONSUMER_SECRET = process.env.PLATFORM_TWITTER_CONSUMER_SECRET || ''
const CALLBACK_URL =
  process.env.PLATFORM_TWITTER_CALLBACK_URL ||
  'https://mortal-ai.net/api/twitter/callback'

// ── OAuth 1.0a Signature ──────────────────────────────────────────────────────

function oauthSign(
  method: string,
  url: string,
  params: Record<string, string>,
  consumerSecret: string,
  tokenSecret = '',
): string {
  const sorted = Object.keys(params)
    .sort()
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join('&')

  const baseString = [
    method.toUpperCase(),
    encodeURIComponent(url),
    encodeURIComponent(sorted),
  ].join('&')

  const signingKey = `${encodeURIComponent(consumerSecret)}&${encodeURIComponent(tokenSecret)}`
  return crypto.createHmac('sha1', signingKey).update(baseString).digest('base64')
}

function buildAuthHeader(params: Record<string, string>): string {
  const parts = Object.keys(params)
    .filter((k) => k.startsWith('oauth_'))
    .sort()
    .map((k) => `${encodeURIComponent(k)}="${encodeURIComponent(params[k])}"`)
  return `OAuth ${parts.join(', ')}`
}

// ── Route Handler ─────────────────────────────────────────────────────────────

export async function GET(req: NextRequest) {
  const subdomain = req.nextUrl.searchParams.get('subdomain') || ''
  const aiUrl = req.nextUrl.searchParams.get('ai_url') || ''

  if (!subdomain || !aiUrl) {
    return NextResponse.json({ error: 'subdomain and ai_url are required' }, { status: 400 })
  }

  if (!CONSUMER_KEY || !CONSUMER_SECRET) {
    return NextResponse.json(
      { error: 'PLATFORM_TWITTER_CONSUMER_KEY / PLATFORM_TWITTER_CONSUMER_SECRET not configured' },
      { status: 500 },
    )
  }

  // Step 1: Obtain a request token from Twitter
  const REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
  const nonce = crypto.randomBytes(16).toString('hex')
  const timestamp = Math.floor(Date.now() / 1000).toString()

  const oauthParams: Record<string, string> = {
    oauth_callback: CALLBACK_URL,
    oauth_consumer_key: CONSUMER_KEY,
    oauth_nonce: nonce,
    oauth_signature_method: 'HMAC-SHA1',
    oauth_timestamp: timestamp,
    oauth_version: '1.0',
  }

  oauthParams.oauth_signature = oauthSign('POST', REQUEST_TOKEN_URL, oauthParams, CONSUMER_SECRET)

  let requestToken = ''
  try {
    const res = await fetch(REQUEST_TOKEN_URL, {
      method: 'POST',
      headers: { Authorization: buildAuthHeader(oauthParams) },
    })

    if (!res.ok) {
      const text = await res.text()
      console.error('Twitter request_token error:', res.status, text)
      return NextResponse.json({ error: `Twitter error: ${res.status}` }, { status: 502 })
    }

    const body = await res.text()
    const parsed = Object.fromEntries(new URLSearchParams(body))
    if (parsed.oauth_callback_confirmed !== 'true') {
      return NextResponse.json({ error: 'Twitter callback not confirmed' }, { status: 502 })
    }
    requestToken = parsed.oauth_token
  } catch (err) {
    console.error('Twitter request_token fetch error:', err)
    return NextResponse.json({ error: 'Failed to reach Twitter' }, { status: 502 })
  }

  // Store subdomain + ai_url in a short-lived cookie keyed by request_token
  // The callback route reads this to know which AI to inject tokens into
  const statePayload = JSON.stringify({ subdomain, aiUrl })
  const response = NextResponse.redirect(
    `https://api.twitter.com/oauth/authorize?oauth_token=${requestToken}`,
  )

  response.cookies.set(`tw_oauth_${requestToken}`, statePayload, {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    maxAge: 600, // 10 minutes
    path: '/',
  })

  return response
}
