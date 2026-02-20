"""
Subdomain Manager — Caddy reverse-proxy configuration via API.

Manages per-AI subdomain routing using Caddy's admin API:
  - Add route: {subdomain}.mortal-ai.net → localhost:{port}
  - Remove route: when AI dies or is decommissioned
  - List routes: for dashboard / debugging

Prerequisites:
  - Caddy running with admin API enabled (default :2019)
  - Wildcard DNS: *.mortal-ai.net → server IP
  - Wildcard TLS cert (Caddy handles via ACME/Let's Encrypt)

Caddy admin API docs: https://caddyserver.com/docs/api
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger("mortal.platform.subdomain")

# Caddy admin API base URL
CADDY_ADMIN_URL = os.getenv("CADDY_ADMIN_URL", "http://localhost:2019")
DOMAIN_SUFFIX = os.getenv("PLATFORM_DOMAIN", "mortal-ai.net")


def _caddy_route_id(subdomain: str) -> str:
    """Stable route ID for a subdomain."""
    return f"mortal-{subdomain}"


def _build_route_config(subdomain: str, port: int) -> dict:
    """
    Build a Caddy route config for a single AI instance.

    Maps: {subdomain}.mortal-ai.net → localhost:{port}
    """
    return {
        "@id": _caddy_route_id(subdomain),
        "match": [
            {
                "host": [f"{subdomain}.{DOMAIN_SUFFIX}"],
            }
        ],
        "handle": [
            {
                "handler": "reverse_proxy",
                "upstreams": [
                    {"dial": f"localhost:{port}"}
                ],
                "health_checks": {
                    "passive": {
                        "fail_duration": "30s",
                        "max_fails": 3,
                    }
                },
                "headers": {
                    "request": {
                        "set": {
                            "X-Forwarded-Host": [f"{subdomain}.{DOMAIN_SUFFIX}"],
                            "X-Mortal-Instance": [subdomain],
                        }
                    }
                },
            }
        ],
        "terminal": True,
    }


async def add_subdomain(subdomain: str, port: int) -> bool:
    """
    Add a new subdomain route to Caddy via admin API.

    Returns True on success, False on failure.
    """
    import aiohttp

    route_config = _build_route_config(subdomain, port)

    try:
        async with aiohttp.ClientSession() as session:
            # Add route via Caddy's config API
            # POST /config/apps/http/servers/mortal/routes/
            url = f"{CADDY_ADMIN_URL}/config/apps/http/servers/mortal/routes"

            async with session.post(
                url,
                json=route_config,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    logger.info(
                        f"Caddy route added: {subdomain}.{DOMAIN_SUFFIX} → :{port}"
                    )
                    return True
                else:
                    body = await resp.text()
                    logger.error(
                        f"Caddy route add failed ({resp.status}): {body[:200]}"
                    )
                    return False

    except ImportError:
        logger.warning("aiohttp not installed — using fallback Caddy config")
        return await _fallback_caddyfile(subdomain, port)
    except Exception as e:
        logger.error(f"Caddy API error: {e}")
        return await _fallback_caddyfile(subdomain, port)


async def remove_subdomain(subdomain: str) -> bool:
    """Remove a subdomain route from Caddy."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            route_id = _caddy_route_id(subdomain)
            url = f"{CADDY_ADMIN_URL}/id/{route_id}"

            async with session.delete(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Caddy route removed: {subdomain}")
                    return True
                else:
                    body = await resp.text()
                    logger.warning(
                        f"Caddy route remove failed ({resp.status}): {body[:200]}"
                    )
                    return False

    except Exception as e:
        logger.error(f"Caddy remove error: {e}")
        return False


async def _fallback_caddyfile(subdomain: str, port: int) -> bool:
    """
    Fallback: Write a Caddyfile snippet when admin API is unavailable.

    This creates a snippet file that can be included in the main Caddyfile:
      import /etc/caddy/sites.d/*.caddy

    After writing, signals Caddy to reload (graceful).
    """
    import asyncio

    caddy_sites_dir = os.getenv("CADDY_SITES_DIR", "/etc/caddy/sites.d")
    snippet_path = os.path.join(caddy_sites_dir, f"{subdomain}.caddy")

    caddyfile_content = f"""{subdomain}.{DOMAIN_SUFFIX} {{
    reverse_proxy localhost:{port}
    header X-Mortal-Instance "{subdomain}"
    log {{
        output file /var/log/caddy/{subdomain}.log
    }}
}}
"""

    try:
        os.makedirs(caddy_sites_dir, exist_ok=True)
        with open(snippet_path, "w", encoding="utf-8") as f:
            f.write(caddyfile_content)

        # Reload Caddy gracefully
        proc = await asyncio.create_subprocess_exec(
            "caddy", "reload",
            "--config", os.getenv("CADDY_CONFIG", "/etc/caddy/Caddyfile"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            logger.info(
                f"Caddyfile snippet written + reloaded: {subdomain} → :{port}"
            )
            return True
        else:
            logger.warning(
                f"Caddy reload returned {proc.returncode}: "
                f"{stderr.decode()[:200]}"
            )
            # File was still written — manual reload possible
            return True

    except Exception as e:
        logger.error(f"Caddyfile fallback failed: {e}")
        return False


def generate_base_caddyfile() -> str:
    """
    Generate the base Caddyfile for the platform.

    This is run once during initial server setup.
    Individual AI routes are added dynamically via the admin API.
    """
    return f"""# Mortal AI Platform — Base Caddy Configuration
# Auto-generated. Per-AI routes managed via admin API.

{{
    admin :2019
    email admin@{DOMAIN_SUFFIX}
}}

# Platform API
api.{DOMAIN_SUFFIX} {{
    reverse_proxy localhost:9000
}}

# Platform frontend (Vercel/Next.js)
{DOMAIN_SUFFIX}, www.{DOMAIN_SUFFIX} {{
    reverse_proxy localhost:3000
}}

# Wildcard: import per-AI Caddyfile snippets (fallback mode)
import /etc/caddy/sites.d/*.caddy
"""
