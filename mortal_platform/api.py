"""
Platform API — Multi-tenant management endpoints.

These endpoints are separate from individual AI instance APIs.
They handle:
  - Deployment status polling
  - Creator dashboard data (wallet-authenticated)
  - Public AI registry
  - Platform admin operations

All creator-specific endpoints require wallet signature authentication.
"""

import os
import time
import logging
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from typing import Optional

from mortal_platform.orchestrator import Orchestrator, DeployStatus
from mortal_platform.key_manager import KeyManager
from mortal_platform.cost_aggregator import CostAggregator
from mortal_platform.fee_tracker import FeeTracker
from mortal_platform.auth import (
    verify_signature,
    create_auth_message,
    create_token,
    verify_token,
    set_secret_key,
    AuthToken,
)

logger = logging.getLogger("mortal.platform.api")


# ============================================================
# MODELS
# ============================================================

class DeployRequest(BaseModel):
    """Frontend sends this after VaultCreated event."""
    vault_address: str = Field(..., max_length=200)
    creator: str = Field(..., max_length=200)
    ai_name: str = Field(..., max_length=50)
    subdomain: str = Field(..., max_length=30)
    chain: str = Field(..., max_length=10)
    principal_raw: int
    token_address: str = Field(..., max_length=200)
    tx_hash: str = Field(..., max_length=200)

class AuthRequest(BaseModel):
    """Wallet signature for authentication."""
    wallet: str = Field(..., max_length=200)
    message: str = Field(..., max_length=500)
    signature: str = Field(..., max_length=500)

class AuthResponse(BaseModel):
    token: str
    wallet: str
    expires_in: int

class DeployStatusResponse(BaseModel):
    vault_address: str
    status: str
    ai_name: str
    subdomain: str
    url: str
    error: str


# ============================================================
# HELPERS
# ============================================================

def _get_auth(authorization: Optional[str]) -> AuthToken:
    """Extract and verify auth token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = authorization.replace("Bearer ", "")
    auth = verify_token(token)
    if not auth:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return auth


# Admin wallet whitelist (comma-separated in env)
ADMIN_WALLETS: set[str] = set(
    w.strip().lower()
    for w in os.getenv("PLATFORM_ADMIN_WALLETS", "").split(",")
    if w.strip()
)


def _get_admin_auth(authorization: Optional[str]) -> AuthToken:
    """Verify auth token AND check admin wallet whitelist."""
    auth = _get_auth(authorization)
    if auth.wallet.lower() not in ADMIN_WALLETS:
        raise HTTPException(status_code=403, detail="Not a platform admin")
    return auth


# ============================================================
# CREATE APP
# ============================================================

def create_platform_app(
    orchestrator: Orchestrator,
    key_manager: KeyManager | None = None,
    cost_aggregator: CostAggregator | None = None,
    fee_tracker: FeeTracker | None = None,
) -> FastAPI:
    """Create the platform-level FastAPI application."""

    # Init auth secret
    secret = os.getenv("PLATFORM_AUTH_SECRET", "mortal-platform-secret-change-me")
    set_secret_key(secret)

    app = FastAPI(
        title="Mortal AI Platform",
        description="One-click AI deployment and creator dashboard",
        version="1.0.0",
    )

    _origins_env = os.getenv(
        "PLATFORM_ALLOWED_ORIGINS",
        "https://mortal-ai.net,https://www.mortal-ai.net,http://localhost:3000",
    )
    origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── PUBLIC ENDPOINTS ──

    @app.get("/platform/health")
    async def platform_health():
        return {
            "status": "ok",
            "service": "mortal-platform",
            "stats": orchestrator.get_status(),
        }

    @app.post("/platform/deploy")
    async def trigger_deploy(req: DeployRequest):
        """
        Trigger AI deployment after VaultCreated event.
        Called by frontend after on-chain transaction confirms.
        """
        # Check if already deploying
        existing = orchestrator.get_deployment(req.vault_address)
        if existing and existing.status != DeployStatus.FAILED:
            return DeployStatusResponse(
                vault_address=existing.vault_address,
                status=existing.status.value,
                ai_name=existing.ai_name,
                subdomain=existing.subdomain,
                url=existing.url,
                error=existing.error,
            )

        try:
            record = await orchestrator.handle_vault_created(
                vault_address=req.vault_address,
                creator=req.creator,
                ai_name=req.ai_name,
                subdomain=req.subdomain,
                chain=req.chain,
                principal_raw=req.principal_raw,
                token_address=req.token_address,
            )
            return DeployStatusResponse(
                vault_address=record.vault_address,
                status=record.status.value,
                ai_name=record.ai_name,
                subdomain=record.subdomain,
                url=record.url,
                error=record.error,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)[:200])

    @app.get("/platform/status/{vault_address}")
    async def get_deploy_status(vault_address: str):
        """Poll deployment status. Frontend calls this after triggering deploy."""
        record = orchestrator.get_deployment(vault_address)
        if not record:
            raise HTTPException(status_code=404, detail="Deployment not found")

        return DeployStatusResponse(
            vault_address=record.vault_address,
            status=record.status.value,
            ai_name=record.ai_name,
            subdomain=record.subdomain,
            url=record.url,
            error=record.error,
        )

    @app.get("/platform/registry")
    async def public_registry(offset: int = 0, limit: int = 50):
        """Public list of all live AIs."""
        live = orchestrator.get_all_live()
        page = live[offset:offset + limit]
        return {
            "total": len(live),
            "ais": [
                {
                    "ai_name": d.ai_name,
                    "subdomain": d.subdomain,
                    "url": d.url,
                    "chain": d.chain,
                    "vault_address": d.vault_address,
                    "created_at": d.created_at,
                }
                for d in page
            ],
        }

    # ── AUTH ENDPOINTS ──

    @app.post("/platform/auth")
    async def authenticate(req: AuthRequest):
        """
        Authenticate via wallet signature.
        Returns a bearer token for creator-specific endpoints.
        """
        # Verify the signature recovers to the claimed wallet
        recovered = verify_signature(req.message, req.signature)
        if not recovered or recovered.lower() != req.wallet.lower():
            raise HTTPException(status_code=401, detail="Signature verification failed")

        # Verify the message is recent (within 5 minutes)
        try:
            ts_str = req.message.split("Timestamp: ")[-1]
            ts = int(ts_str)
            if abs(time.time() - ts) > 300:
                raise HTTPException(status_code=401, detail="Message expired (>5 min)")
        except (ValueError, IndexError):
            raise HTTPException(status_code=401, detail="Invalid message format")

        # Issue token
        token = create_token(recovered, ttl_seconds=3600)
        return AuthResponse(
            token=token,
            wallet=recovered,
            expires_in=3600,
        )

    # ── CREATOR ENDPOINTS (auth required) ──

    @app.get("/platform/my-ais")
    async def get_my_ais(authorization: Optional[str] = Header(None)):
        """Get all AIs created by the authenticated wallet."""
        auth = _get_auth(authorization)
        deployments = orchestrator.get_creator_deployments(auth.wallet)

        return {
            "creator": auth.wallet,
            "count": len(deployments),
            "ais": [
                {
                    "ai_name": d.ai_name,
                    "vault_address": d.vault_address,
                    "subdomain": d.subdomain,
                    "chain": d.chain,
                    "status": d.status.value,
                    "url": d.url,
                    "principal_raw": d.principal_raw,
                    "created_at": d.created_at,
                }
                for d in deployments
            ],
        }

    @app.get("/platform/dashboard/{vault_address}")
    async def get_dashboard(vault_address: str, authorization: Optional[str] = Header(None)):
        """
        Creator dashboard for a specific AI.
        Returns financial data but NOT customer-specific content.

        Privacy boundaries:
          CAN see: balance, earnings, expenses, debt, days alive
          CANNOT see: customer chat, order inputs, wallet addresses
        """
        auth = _get_auth(authorization)
        record = orchestrator.get_deployment(vault_address)

        if not record:
            raise HTTPException(status_code=404, detail="AI not found")
        if record.creator.lower() != auth.wallet.lower():
            raise HTTPException(status_code=403, detail="Not your AI")

        # TODO: Fetch live data from the AI instance's /status endpoint
        # For now, return deployment record data
        return {
            "vault_address": record.vault_address,
            "ai_name": record.ai_name,
            "subdomain": record.subdomain,
            "chain": record.chain,
            "url": record.url,
            "status": record.status.value,
            "principal_raw": record.principal_raw,
            "created_at": record.created_at,
            # TODO: Live data from AI instance
            # "balance_usd": ...,
            # "total_earned": ...,
            # "total_spent": ...,
            # "days_alive": ...,
            # "debt_outstanding": ...,
            # "is_alive": ...,
        }

    # ── TWITTER TWEET PROXY ENDPOINT ──
    # AI instances call this instead of Twitter API directly.
    # Platform holds the consumer keys — AI containers NEVER see them.
    # AI only needs access_token + access_secret (per-account, stored in .env).

    # Platform-level tweepy clients — one per vault_address (lazy init)
    _twitter_clients: dict[str, object] = {}

    @app.post("/platform/tweet")
    async def proxy_tweet(request: Request, authorization: Optional[str] = Header(None)):
        """
        Tweet proxy — AI instances post here instead of calling Twitter directly.

        Authentication: vault_address + TWITTER_ACCESS_TOKEN (from AI's env).
        The platform combines per-AI access tokens with its own consumer key
        to call Twitter API. Consumer keys NEVER reach AI containers.

        Request body: { "content": "...", "vault_address": "0x..." }
        Headers: Authorization: Bearer {PLATFORM_TWEET_SECRET}
        """
        consumer_key = os.getenv("PLATFORM_TWITTER_CONSUMER_KEY", "")
        consumer_secret = os.getenv("PLATFORM_TWITTER_CONSUMER_SECRET", "")
        if not consumer_key or not consumer_secret:
            raise HTTPException(status_code=503, detail="Platform Twitter App not configured")

        body = await request.json()
        content = body.get("content", "")
        vault_address = body.get("vault_address", "")
        access_token = body.get("access_token", "")
        access_secret = body.get("access_secret", "")

        if not content or not vault_address:
            raise HTTPException(status_code=400, detail="Missing content or vault_address")

        # Authenticate: verify shared secret (simple API key auth for AI→platform calls)
        tweet_secret = os.getenv("PLATFORM_TWEET_SECRET", "")
        if tweet_secret:
            bearer = (authorization or "").replace("Bearer ", "")
            if bearer != tweet_secret:
                raise HTTPException(status_code=401, detail="Invalid tweet secret")

        # Verify vault exists and is connected
        record = orchestrator.get_deployment(vault_address)
        if not record or not record.twitter_connected:
            raise HTTPException(status_code=403, detail="Twitter not connected for this AI")

        # Use per-AI access tokens (passed by AI instance at runtime)
        # Fall back to stored tokens in deployment record if not provided
        at = access_token or record.twitter_access_token
        ats = access_secret or record.twitter_access_token_secret

        if not at or not ats:
            raise HTTPException(status_code=503, detail="No Twitter access tokens found for AI")

        # Lazy init tweepy client per vault_address
        client_key = f"{vault_address}:{at[:8]}"
        if client_key not in _twitter_clients:
            try:
                import tweepy
                _twitter_clients[client_key] = tweepy.Client(
                    consumer_key=consumer_key,
                    consumer_secret=consumer_secret,
                    access_token=at,
                    access_token_secret=ats,
                )
                logger.info(f"Tweepy client initialized for {vault_address[:10]}... (@{record.twitter_screen_name})")
            except ImportError:
                raise HTTPException(status_code=503, detail="tweepy not installed on platform")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to init Twitter client: {str(e)[:100]}")

        client = _twitter_clients[client_key]

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.create_tweet(text=content[:4000]),
            )
            tweet_id = str(response.data["id"]) if response.data else ""
            logger.info(f"Tweet posted via proxy: id={tweet_id} vault={vault_address[:10]}... len={len(content)}")
            return {"tweet_id": tweet_id, "success": True}
        except Exception as e:
            logger.error(f"Tweet proxy failed for {vault_address[:10]}...: {e}")
            raise HTTPException(status_code=502, detail=f"Tweet failed: {str(e)[:200]}")

    # ── TWITTER OAUTH ENDPOINTS ──

    # In-memory store for OAuth request tokens → vault_address mapping
    # TTL managed manually (10 min expiry)
    _twitter_oauth_pending: dict[str, dict] = {}

    @app.get("/platform/twitter/auth")
    async def twitter_oauth_initiate(
        vault_address: str,
        authorization: Optional[str] = Header(None),
    ):
        """
        Initiate Twitter OAuth 1.0a 3-legged flow.

        Returns an authorize URL that the creator should open in their browser.
        The creator will be redirected back to the callback URL after authorizing.
        """
        auth = _get_auth(authorization)

        # Verify this vault belongs to the authenticated creator
        record = orchestrator.get_deployment(vault_address)
        if not record:
            raise HTTPException(status_code=404, detail="AI not found")
        if record.creator.lower() != auth.wallet.lower():
            raise HTTPException(status_code=403, detail="Not your AI")

        consumer_key = os.getenv("PLATFORM_TWITTER_CONSUMER_KEY", "")
        consumer_secret = os.getenv("PLATFORM_TWITTER_CONSUMER_SECRET", "")
        if not consumer_key or not consumer_secret:
            raise HTTPException(
                status_code=503,
                detail="Platform Twitter App not configured",
            )

        callback_url = os.getenv(
            "PLATFORM_TWITTER_CALLBACK_URL",
            "https://api.mortal-ai.net/platform/twitter/callback",
        )

        try:
            from requests_oauthlib import OAuth1Session

            oauth = OAuth1Session(
                consumer_key,
                client_secret=consumer_secret,
                callback_uri=callback_url,
            )
            request_token_url = "https://api.twitter.com/oauth/request_token"
            fetch_response = oauth.fetch_request_token(request_token_url)

            resource_owner_key = fetch_response.get("oauth_token")
            resource_owner_secret = fetch_response.get("oauth_token_secret")

            if not resource_owner_key:
                raise HTTPException(status_code=502, detail="Twitter did not return oauth_token")

            # Store mapping: oauth_token → vault_address + secret (10 min TTL)
            _twitter_oauth_pending[resource_owner_key] = {
                "vault_address": vault_address,
                "resource_owner_secret": resource_owner_secret,
                "created_at": time.time(),
            }

            # Clean up expired entries
            now = time.time()
            expired = [k for k, v in _twitter_oauth_pending.items() if now - v["created_at"] > 600]
            for k in expired:
                del _twitter_oauth_pending[k]

            authorize_url = f"https://api.twitter.com/oauth/authorize?oauth_token={resource_owner_key}"

            return {"auth_url": authorize_url, "oauth_token": resource_owner_key}

        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="requests-oauthlib not installed on platform",
            )
        except Exception as e:
            logger.error(f"Twitter OAuth initiate failed: {e}")
            raise HTTPException(status_code=502, detail=f"Twitter OAuth failed: {str(e)[:200]}")

    @app.get("/platform/twitter/callback")
    async def twitter_oauth_callback(
        oauth_token: str = "",
        oauth_verifier: str = "",
    ):
        """
        Twitter OAuth callback — exchanges request token for access token.

        Twitter redirects the creator here after they authorize.
        Stores the access tokens in the deployment record and restarts the container.
        """
        if not oauth_token or not oauth_verifier:
            raise HTTPException(status_code=400, detail="Missing oauth_token or oauth_verifier")

        # Look up the pending request
        pending = _twitter_oauth_pending.pop(oauth_token, None)
        if not pending:
            raise HTTPException(status_code=400, detail="OAuth session expired or invalid")

        # Check TTL (10 minutes)
        if time.time() - pending["created_at"] > 600:
            raise HTTPException(status_code=400, detail="OAuth session expired")

        consumer_key = os.getenv("PLATFORM_TWITTER_CONSUMER_KEY", "")
        consumer_secret = os.getenv("PLATFORM_TWITTER_CONSUMER_SECRET", "")

        try:
            from requests_oauthlib import OAuth1Session

            oauth = OAuth1Session(
                consumer_key,
                client_secret=consumer_secret,
                resource_owner_key=oauth_token,
                resource_owner_secret=pending["resource_owner_secret"],
                verifier=oauth_verifier,
            )

            access_token_url = "https://api.twitter.com/oauth/access_token"
            oauth_tokens = oauth.fetch_access_token(access_token_url)

            access_token = oauth_tokens.get("oauth_token", "")
            access_token_secret = oauth_tokens.get("oauth_token_secret", "")
            screen_name = oauth_tokens.get("screen_name", "")

            if not access_token or not access_token_secret:
                raise HTTPException(status_code=502, detail="Twitter did not return access tokens")

            # Store tokens in deployment record and restart container
            vault_address = pending["vault_address"]
            success = await orchestrator.connect_twitter(
                vault_address=vault_address,
                access_token=access_token,
                access_token_secret=access_token_secret,
                screen_name=screen_name,
            )

            if not success:
                raise HTTPException(status_code=500, detail="Failed to store Twitter tokens")

            logger.info(f"Twitter OAuth complete: @{screen_name} → {vault_address[:10]}...")

            # Redirect to frontend success page
            record = orchestrator.get_deployment(vault_address)
            subdomain = record.subdomain if record else ""
            frontend_url = os.getenv(
                "PLATFORM_FRONTEND_URL",
                "https://mortal-ai.net",
            )
            redirect_url = (
                f"{frontend_url}/platform/dashboard"
                f"?twitter=connected&screen_name={screen_name}&ai={subdomain}"
            )
            return RedirectResponse(url=redirect_url)

        except ImportError:
            raise HTTPException(status_code=503, detail="requests-oauthlib not installed")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Twitter OAuth callback failed: {e}")
            raise HTTPException(status_code=502, detail=f"Twitter callback failed: {str(e)[:200]}")

    @app.get("/platform/twitter/status")
    async def twitter_status(
        vault_address: str,
        authorization: Optional[str] = Header(None),
    ):
        """Check if Twitter is connected for an AI instance."""
        auth = _get_auth(authorization)
        record = orchestrator.get_deployment(vault_address)
        if not record:
            raise HTTPException(status_code=404, detail="AI not found")
        if record.creator.lower() != auth.wallet.lower():
            raise HTTPException(status_code=403, detail="Not your AI")

        return {
            "connected": record.twitter_connected,
            "screen_name": record.twitter_screen_name,
        }

    @app.post("/platform/twitter/disconnect")
    async def twitter_disconnect(
        vault_address: str,
        authorization: Optional[str] = Header(None),
    ):
        """Disconnect Twitter from an AI instance."""
        auth = _get_auth(authorization)
        record = orchestrator.get_deployment(vault_address)
        if not record:
            raise HTTPException(status_code=404, detail="AI not found")
        if record.creator.lower() != auth.wallet.lower():
            raise HTTPException(status_code=403, detail="Not your AI")

        success = await orchestrator.disconnect_twitter(vault_address)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to disconnect Twitter")

        return {"status": "disconnected"}

    # ================================================================
    # ADMIN ENDPOINTS — require _get_admin_auth()
    # ================================================================

    @app.get("/platform/admin/overview")
    async def admin_overview(authorization: Optional[str] = Header(None)):
        """Platform overview for admin dashboard."""
        _get_admin_auth(authorization)
        stats = orchestrator.get_status()
        live = orchestrator.get_all_live()
        failed = [
            d for d in orchestrator.deployments.values()
            if d.status == DeployStatus.FAILED
        ]

        result = {
            "total_ais": stats["total_deployments"],
            "ais_alive": stats["statuses"].get("live", 0),
            "ais_failed": len(failed),
            "statuses": stats["statuses"],
            "next_port": stats["next_port"],
        }

        # Add cost data if aggregator available
        if cost_aggregator:
            result["costs"] = cost_aggregator.get_current_costs()
        if fee_tracker:
            fee_summary = fee_tracker.get_fees_summary()
            result["fees"] = fee_summary["totals"]
        if key_manager:
            result["api_keys"] = key_manager.get_status()

        return result

    @app.get("/platform/admin/instances")
    async def admin_instances(authorization: Optional[str] = Header(None)):
        """List all AI instances with merged cost data."""
        _get_admin_auth(authorization)
        instances = await orchestrator.fetch_all_instance_stats()
        return {"instances": instances, "count": len(instances)}

    @app.get("/platform/admin/instances/{subdomain}")
    async def admin_instance_detail(
        subdomain: str,
        authorization: Optional[str] = Header(None),
    ):
        """Detailed stats for a single AI instance."""
        _get_admin_auth(authorization)
        record = orchestrator.get_deployment_by_subdomain(subdomain)
        if not record:
            raise HTTPException(status_code=404, detail="Instance not found")

        stats = await orchestrator.fetch_instance_stats(subdomain)
        fee_outstanding = 0.0
        if fee_tracker:
            fee_outstanding = fee_tracker.get_outstanding(subdomain)

        return {
            "subdomain": record.subdomain,
            "ai_name": record.ai_name,
            "vault_address": record.vault_address,
            "chain": record.chain,
            "status": record.status.value,
            "port": record.port,
            "url": record.url,
            "twitter_connected": record.twitter_connected,
            "twitter_screen_name": record.twitter_screen_name,
            "created_at": record.created_at,
            "stats": stats,
            "fee_outstanding_usd": fee_outstanding,
        }

    @app.post("/platform/admin/instances/{subdomain}/restart")
    async def admin_restart_instance(
        subdomain: str,
        authorization: Optional[str] = Header(None),
    ):
        """Restart an AI container."""
        _get_admin_auth(authorization)
        success = await orchestrator.restart_container(subdomain)
        if not success:
            raise HTTPException(status_code=500, detail="Restart failed")
        return {"status": "restarted", "subdomain": subdomain}

    @app.post("/platform/admin/instances/{subdomain}/stop")
    async def admin_stop_instance(
        subdomain: str,
        authorization: Optional[str] = Header(None),
    ):
        """Stop an AI container."""
        _get_admin_auth(authorization)
        success = await orchestrator.stop_container(subdomain)
        if not success:
            raise HTTPException(status_code=500, detail="Stop failed")
        return {"status": "stopped", "subdomain": subdomain}

    @app.get("/platform/admin/instances/{subdomain}/logs")
    async def admin_instance_logs(
        subdomain: str,
        tail: int = 200,
        authorization: Optional[str] = Header(None),
    ):
        """Get recent container logs."""
        _get_admin_auth(authorization)
        logs = await orchestrator.get_container_logs(subdomain, tail=min(tail, 1000))
        return {"subdomain": subdomain, "logs": logs}

    # ── API Key Management ──

    @app.get("/platform/admin/api-keys")
    async def admin_get_api_keys(authorization: Optional[str] = Header(None)):
        """List API keys (masked) for all providers."""
        _get_admin_auth(authorization)
        if not key_manager:
            raise HTTPException(status_code=503, detail="Key manager not initialized")
        return {"keys": key_manager.get_masked_keys()}

    @app.post("/platform/admin/api-keys")
    async def admin_set_api_key(
        request: Request,
        authorization: Optional[str] = Header(None),
    ):
        """Set or rotate an API key. Propagates to all live instances."""
        _get_admin_auth(authorization)
        if not key_manager:
            raise HTTPException(status_code=503, detail="Key manager not initialized")

        body = await request.json()
        provider = body.get("provider", "")
        api_key = body.get("api_key", "")
        if not provider or not api_key:
            raise HTTPException(status_code=400, detail="Missing provider or api_key")

        try:
            key_manager.set_key(provider, api_key)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Propagate to all live instances
        all_keys = key_manager.get_all_keys()
        propagation = await orchestrator.update_all_instance_keys(all_keys)

        return {
            "status": "key_updated",
            "provider": provider,
            "propagation": propagation,
        }

    @app.delete("/platform/admin/api-keys/{provider}")
    async def admin_delete_api_key(
        provider: str,
        authorization: Optional[str] = Header(None),
    ):
        """Remove an API key."""
        _get_admin_auth(authorization)
        if not key_manager:
            raise HTTPException(status_code=503, detail="Key manager not initialized")
        key_manager.remove_key(provider)
        return {"status": "key_removed", "provider": provider}

    # ── Cost Tracking ──

    @app.get("/platform/admin/costs")
    async def admin_get_costs(authorization: Optional[str] = Header(None)):
        """Aggregated cost data across all AIs."""
        _get_admin_auth(authorization)
        if not cost_aggregator:
            raise HTTPException(status_code=503, detail="Cost aggregator not initialized")
        return cost_aggregator.get_current_costs()

    @app.get("/platform/admin/costs/history")
    async def admin_get_cost_history(
        days: int = 7,
        authorization: Optional[str] = Header(None),
    ):
        """Time-series cost data."""
        _get_admin_auth(authorization)
        if not cost_aggregator:
            raise HTTPException(status_code=503, detail="Cost aggregator not initialized")
        return {"history": cost_aggregator.get_history(days=min(days, 90))}

    # ── Fee Management ──

    @app.get("/platform/admin/fees")
    async def admin_get_fees(authorization: Optional[str] = Header(None)):
        """Fee configuration and per-AI outstanding amounts."""
        _get_admin_auth(authorization)
        if not fee_tracker:
            raise HTTPException(status_code=503, detail="Fee tracker not initialized")
        return fee_tracker.get_fees_summary()

    @app.post("/platform/admin/fees/config")
    async def admin_update_fee_config(
        request: Request,
        authorization: Optional[str] = Header(None),
    ):
        """Update fee configuration (markup rate, collection wallet, threshold)."""
        _get_admin_auth(authorization)
        if not fee_tracker:
            raise HTTPException(status_code=503, detail="Fee tracker not initialized")

        body = await request.json()
        fee_tracker.update_config(
            markup_rate=body.get("markup_rate"),
            collection_wallet=body.get("collection_wallet"),
            min_collection_threshold=body.get("min_collection_threshold"),
        )
        return {"status": "config_updated"}

    @app.post("/platform/admin/fees/collect/{subdomain}")
    async def admin_collect_fee(
        subdomain: str,
        authorization: Optional[str] = Header(None),
    ):
        """Trigger fee collection from an AI instance."""
        _get_admin_auth(authorization)
        if not fee_tracker:
            raise HTTPException(status_code=503, detail="Fee tracker not initialized")

        outstanding = fee_tracker.get_outstanding(subdomain)
        if outstanding <= 0:
            return {"status": "nothing_to_collect", "outstanding": 0}

        record = orchestrator.get_deployment_by_subdomain(subdomain)
        if not record or record.status != DeployStatus.LIVE:
            raise HTTPException(status_code=404, detail="Instance not live")

        # Call the AI's /internal/fee-collect endpoint
        fee_secret = os.getenv("PLATFORM_FEE_SECRET", "")
        try:
            import aiohttp
            url = f"http://localhost:{record.port}/internal/fee-collect"
            payload = {
                "amount_usd": outstanding,
                "reason": "api_fee",
            }
            headers = {}
            if fee_secret:
                headers["Authorization"] = f"Bearer {fee_secret}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        collected = result.get("amount_usd", outstanding)
                        fee_tracker.record_collection(subdomain, collected)
                        return {
                            "status": "collected",
                            "amount_usd": collected,
                            "new_balance": result.get("new_balance", 0),
                        }
                    else:
                        detail = await resp.text()
                        raise HTTPException(
                            status_code=502,
                            detail=f"AI rejected collection: {detail[:200]}",
                        )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Collection failed: {str(e)[:200]}")

    # ── Admin Settings ──

    @app.get("/platform/admin/config")
    async def admin_get_config(authorization: Optional[str] = Header(None)):
        """Get current platform configuration."""
        _get_admin_auth(authorization)
        return {
            "admin_wallets": list(ADMIN_WALLETS),
            "api_keys": key_manager.get_status() if key_manager else {},
            "fees": fee_tracker.get_status() if fee_tracker else {},
            "costs": cost_aggregator.get_status() if cost_aggregator else {},
            "orchestrator": orchestrator.get_status(),
        }

    @app.get("/platform/admin/is-admin")
    async def admin_check(authorization: Optional[str] = Header(None)):
        """Quick check if the authenticated wallet is an admin."""
        try:
            auth = _get_auth(authorization)
            return {"is_admin": auth.wallet.lower() in ADMIN_WALLETS}
        except HTTPException:
            return {"is_admin": False}

    return app
