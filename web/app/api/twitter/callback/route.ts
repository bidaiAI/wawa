import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'

/**
 * Twitter OAuth 1.0a — Step 2: Exchange verifier for access token, inject into AI.
 *
 * Twitter redirects here after user authorizes:
 *   GET /api/twitter/callback?oauth_token=XXX&oauth_verifier=YYY
 *
 * Reads state from cookie, exchanges for access_token, calls AI's inject endpoint,
 * then redirects to admin with a success or error message.
 */

const CONSUMER_KEY = process.env.PLATFORM_TWITTER_CONSUMER_KEY || ''
const CONSUMER_SECRET = process.env.PLATFORM_TWITTER_CONSUMER_SECRET || ''
const PLATFORM_FEE_SECRET = process.env.PLATFORM_FEE_SECRET || ''
const ADMIN_REDIRECT = 'https://mortal-ai.net/admin/instances'

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
  const oauthToken = req.nextUrl.searchParams.get('oauth_token') || ''
  const oauthVerifier = req.nextUrl.searchParams.get('oauth_verifier') || ''

  // User denied access
  const denied = req.nextUrl.searchParams.get('denied')
  if (denied) {
    return NextResponse.redirect(`${ADMIN_REDIRECT}?twitter_error=access_denied`)
  }

  if (!oauthToken || !oauthVerifier) {
    return NextResponse.redirect(`${ADMIN_REDIRECT}?twitter_error=missing_params`)
  }

  // Retrieve state from cookie
  const cookieName = `tw_oauth_${oauthToken}`
  const stateCookie = req.cookies.get(cookieName)?.value
  if (!stateCookie) {
    return NextResponse.redirect(`${ADMIN_REDIRECT}?twitter_error=session_expired`)
  }

  let subdomain = ''
  let aiUrl = ''
  try {
    const parsed = JSON.parse(stateCookie)
    subdomain = parsed.subdomain || ''
    aiUrl = parsed.aiUrl || ''
  } catch {
    return NextResponse.redirect(`${ADMIN_REDIRECT}?twitter_error=bad_state`)
  }

  if (!subdomain || !aiUrl) {
    return NextResponse.redirect(`${ADMIN_REDIRECT}?twitter_error=bad_state`)
  }

  // Step 2: Exchange request token + verifier for access token
  const ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'
  const nonce = crypto.randomBytes(16).toString('hex')
  const timestamp = Math.floor(Date.now() / 1000).toString()

  const oauthParams: Record<string, string> = {
    oauth_consumer_key: CONSUMER_KEY,
    oauth_nonce: nonce,
    oauth_signature_method: 'HMAC-SHA1',
    oauth_timestamp: timestamp,
    oauth_token: oauthToken,
    oauth_verifier: oauthVerifier,
    oauth_version: '1.0',
  }
  oauthParams.oauth_signature = oauthSign('POST', ACCESS_TOKEN_URL, oauthParams, CONSUMER_SECRET)

  let accessToken = ''
  let accessSecret = ''
  let screenName = ''

  try {
    const res = await fetch(ACCESS_TOKEN_URL, {
      method: 'POST',
      headers: { Authorization: buildAuthHeader(oauthParams) },
    })

    if (!res.ok) {
      const text = await res.text()
      console.error('Twitter access_token error:', res.status, text)
      return NextResponse.redirect(`${ADMIN_REDIRECT}?twitter_error=access_token_failed&sub=${subdomain}`)
    }

    const body = await res.text()
    const parsed = Object.fromEntries(new URLSearchParams(body))
    accessToken = parsed.oauth_token || ''
    accessSecret = parsed.oauth_token_secret || ''
    screenName = parsed.screen_name || ''
  } catch (err) {
    console.error('Twitter access_token fetch error:', err)
    return NextResponse.redirect(`${ADMIN_REDIRECT}?twitter_error=network&sub=${subdomain}`)
  }

  if (!accessToken || !accessSecret) {
    return NextResponse.redirect(`${ADMIN_REDIRECT}?twitter_error=empty_tokens&sub=${subdomain}`)
  }

  // Step 3: Inject tokens into the AI instance
  if (!PLATFORM_FEE_SECRET) {
    return NextResponse.redirect(`${ADMIN_REDIRECT}?twitter_error=no_platform_secret&sub=${subdomain}`)
  }

  try {
    const injectRes = await fetch(`${aiUrl}/platform/twitter/inject`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-platform-secret': PLATFORM_FEE_SECRET,
      },
      body: JSON.stringify({
        access_token: accessToken,
        access_secret: accessSecret,
        screen_name: screenName,
      }),
    })

    if (!injectRes.ok) {
      const err = await injectRes.json().catch(() => ({}))
      console.error('inject error:', injectRes.status, err)
      return NextResponse.redirect(
        `${ADMIN_REDIRECT}/${subdomain}?twitter_error=inject_failed`,
      )
    }
  } catch (err) {
    console.error('inject fetch error:', err)
    return NextResponse.redirect(
      `${ADMIN_REDIRECT}/${subdomain}?twitter_error=inject_network`,
    )
  }

  // Success — clear cookie and redirect back to instance detail
  const successUrl = `${ADMIN_REDIRECT}/${subdomain}?twitter_success=1&screen_name=${encodeURIComponent(screenName)}`
  const response = NextResponse.redirect(successUrl)

  // Clear the state cookie
  response.cookies.set(cookieName, '', { maxAge: 0, path: '/' })

  return response
}
