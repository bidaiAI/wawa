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
from pydantic import BaseModel, Field
from typing import Optional

from mortal_platform.orchestrator import Orchestrator, DeployStatus
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


# ============================================================
# CREATE APP
# ============================================================

def create_platform_app(orchestrator: Orchestrator) -> FastAPI:
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

    return app
