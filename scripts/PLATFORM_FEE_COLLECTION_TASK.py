"""
Platform Fee Collection Task Implementation

This module implements the `_collect_fees_task()` coroutine that should be
integrated into mortal_platform/platform_main.py.

The task:
1. Runs every 1 hour (configurable)
2. Queries each live AI instance's /internal/stats to get total_api_cost_usd
3. Calculates fee = total_api_cost * 30% markup
4. Calls /internal/fee-collect on each instance to collect the fee
5. Logs all transactions for audit trail

Author: Platform Team
Reviewed: P8 Fee System Implementation
"""

import asyncio
import logging
import time
from typing import Optional
import aiohttp
import json

logger = logging.getLogger("mortal.platform.fee_collector")

# Configuration
FEE_COLLECTION_INTERVAL = 3600  # 1 hour
MARKUP_RATE = 0.30  # 30% markup on API costs
MIN_COLLECTION_THRESHOLD = 0.01  # Only collect if >= $0.01
REQUEST_TIMEOUT = 10.0


async def _collect_fees_task(
    fee_tracker,  # FeeTracker instance
    instances_path: str,  # Path to platform_instances.json
    http_client: Optional[aiohttp.ClientSession] = None,
):
    """
    Periodically collect fees from all live AI instances.

    Called from platform_main.py as a background task.
    Should be wrapped in asyncio.create_task() at startup.

    Args:
        fee_tracker: FeeTracker instance from platform
        instances_path: Path to platform_instances.json containing instance registry
        http_client: aiohttp ClientSession (optional, creates one if None)

    Implementation notes:
    - Non-blocking: log failures but continue to next instance
    - Rate-limited: each instance can only collect max 10 calls/min
    - Safety: respects survival minimum balance on AI side ($1)
    - Audit: all collections logged to fee_tracker.collection_log
    """

    if http_client is None:
        http_client = aiohttp.ClientSession()

    # Get PLATFORM_FEE_SECRET from environment
    import os
    fee_secret = os.getenv("PLATFORM_FEE_SECRET", "")
    if not fee_secret or len(fee_secret) < 16:
        logger.error("FEE COLLECTION DISABLED: PLATFORM_FEE_SECRET not set or too short")
        return

    while True:
        try:
            await asyncio.sleep(FEE_COLLECTION_INTERVAL)

            logger.info("Fee collection cycle started")

            # Load live instances from JSON file
            try:
                with open(instances_path, 'r') as f:
                    instances_data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load instances from {instances_path}: {e}")
                continue

            # Convert to list of instance objects
            live_instances = []
            for vault_addr, inst_data in instances_data.items():
                if isinstance(inst_data, dict) and inst_data.get("status") == "live":
                    # Create simple object with port and subdomain
                    class Instance:
                        def __init__(self, data):
                            self.port = data.get("port", 8000)
                            self.subdomain = data.get("subdomain", "unknown")

                    live_instances.append(Instance(inst_data))

            if not live_instances:
                logger.debug("No live instances found for fee collection")
                continue

            collected_total = 0.0
            collection_count = 0

            for instance in live_instances:
                try:
                    # Step 1: Query /internal/stats to get total_api_cost_usd
                    stats_url = f"http://localhost:{instance.port}/internal/stats"
                    logger.debug(f"Fetching stats from {instance.subdomain} at {stats_url}")

                    try:
                        stats_response = await asyncio.wait_for(
                            http_client.get(stats_url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)),
                            timeout=REQUEST_TIMEOUT
                        )
                        if stats_response.status != 200:
                            logger.warning(
                                f"Failed to fetch stats from {instance.subdomain}: "
                                f"HTTP {stats_response.status}"
                            )
                            continue

                        stats_data = await stats_response.json()
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout fetching stats from {instance.subdomain}")
                        continue
                    except Exception as e:
                        logger.warning(f"Error fetching stats from {instance.subdomain}: {e}")
                        continue

                    # Extract cost data
                    cost_guard_data = stats_data.get("cost_guard", {})
                    total_api_cost = cost_guard_data.get("total_api_cost_usd", 0)

                    # Step 2: Calculate fee (30% markup)
                    fee_amount = round(total_api_cost * MARKUP_RATE, 4)

                    if fee_amount < MIN_COLLECTION_THRESHOLD:
                        logger.debug(
                            f"Skipping {instance.subdomain}: fee amount ${fee_amount:.4f} "
                            f"below threshold ${MIN_COLLECTION_THRESHOLD}"
                        )
                        continue

                    # Step 3: Call /internal/fee-collect endpoint
                    fee_collect_url = f"http://localhost:{instance.port}/internal/fee-collect"

                    fee_collect_payload = {
                        "amount_usd": fee_amount,
                        "reason": f"API usage fee (markup {int(MARKUP_RATE*100)}%)"
                    }

                    logger.debug(
                        f"Collecting ${fee_amount:.4f} from {instance.subdomain} "
                        f"(base cost: ${total_api_cost:.4f})"
                    )

                    try:
                        fee_response = await asyncio.wait_for(
                            http_client.post(
                                fee_collect_url,
                                headers={"Authorization": f"Bearer {fee_secret}"},
                                json=fee_collect_payload,
                                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                            ),
                            timeout=REQUEST_TIMEOUT
                        )

                        if fee_response.status == 200:
                            response_data = await fee_response.json()

                            if response_data.get("collected"):
                                tx_hash = response_data.get("tx_hash")
                                logger.info(
                                    f"✓ Fee collected: {instance.subdomain} ${fee_amount:.4f} "
                                    f"(tx: {tx_hash[:16] if tx_hash else 'N/A'})"
                                )

                                # Step 4: Record in fee_tracker
                                fee_tracker.record_collection(
                                    subdomain=instance.subdomain,
                                    fee_amount=fee_amount,
                                    tx_hash=tx_hash,
                                    base_cost=total_api_cost
                                )

                                collected_total += fee_amount
                                collection_count += 1
                            else:
                                reason = response_data.get("reason", "Unknown")
                                logger.warning(
                                    f"Fee collection failed for {instance.subdomain}: {reason}"
                                )
                        else:
                            response_text = await fee_response.text()
                            logger.warning(
                                f"Fee collection request failed for {instance.subdomain}: "
                                f"HTTP {fee_response.status} - {response_text[:100]}"
                            )

                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout calling /internal/fee-collect on {instance.subdomain}")
                    except Exception as e:
                        logger.warning(f"Error collecting fee from {instance.subdomain}: {e}")

                except Exception as e:
                    logger.error(f"Unexpected error processing {instance.subdomain}: {e}")

            # Summary
            if collection_count > 0:
                logger.info(
                    f"Fee collection cycle complete: "
                    f"${collected_total:.4f} collected from {collection_count} instance(s)"
                )
            else:
                logger.debug("Fee collection cycle complete: no fees collected")

        except Exception as e:
            logger.error(f"Fee collection task error (will retry in {FEE_COLLECTION_INTERVAL}s): {e}")
            # Continue despite error; next cycle will retry


# Integration Example
# ==================
# Add this to platform_main.py in the lifespan or startup sequence:
#
# from mortal_platform.fee_collector import _collect_fees_task
#
# async def startup():
#     global fee_collection_task
#     fee_collection_task = asyncio.create_task(
#         _collect_fees_task(fee_tracker, instances_registry)
#     )
#
# Or if platform_main.py already has an asyncio event loop:
#     asyncio.create_task(_collect_fees_task(fee_tracker, instances_registry))
