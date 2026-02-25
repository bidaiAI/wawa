# Fee Collection System Implementation Plan

## Current State
- ✅ **CostAggregator** exists: polls AI instances' `/internal/stats` every 60s, stores time-series data
- ✅ **FeeTracker** exists: calculates 30% markup on API costs, maintains ledger
- ✅ **wawa API** has `/internal/fee-collect` endpoint (requires `PLATFORM_FEE_SECRET`)
- ❌ **orchestrator.py** never calls `/internal/fee-collect` — fees are never collected
- ⚠️ **Twitter API cost** tracking is partial (counted per batch, but needs live instance data)

## What Needs to be Done

### 1. Fee Collection in orchestrator.py (CRITICAL)

Add a `_collect_fees_task()` coroutine in `platform_main.py`:

```python
async def _collect_fees_task(fee_tracker, instances_registry):
    """
    Periodically collect fees from all live AI instances.

    For each instance:
      1. Query /internal/stats to get total_api_cost_usd (cumulative)
      2. Calculate fee = total_api_cost * MARKUP_RATE (30%)
      3. Call POST /internal/fee-collect with fee amount
      4. Record collection in fee_tracker.collection_log
      5. On success: log transaction, update ledger
    """
    while True:
        try:
            await asyncio.sleep(3600)  # Run every 1 hour

            for instance in instances_registry.get_live_instances():
                # Query AI's /internal/stats
                stats = await http_client.get(
                    f"http://localhost:{instance.port}/internal/stats",
                    timeout=10.0
                )
                cost_data = stats.json().get("cost_guard", {})
                total_api_cost = cost_data.get("total_api_cost_usd", 0)

                # Calculate and collect fee
                markup = fee_tracker._config["markup_rate"]  # 0.30
                fee_amount = round(total_api_cost * markup, 4)

                if fee_amount < fee_tracker._config["min_collection_threshold"]:
                    continue  # Skip if below threshold

                # Call /internal/fee-collect
                response = await http_client.post(
                    f"http://localhost:{instance.port}/internal/fee-collect",
                    headers={"Authorization": f"Bearer {PLATFORM_FEE_SECRET}"},
                    json={"amount_usd": fee_amount},
                    timeout=10.0
                )

                if response.status_code == 200:
                    fee_tracker.record_collection(
                        subdomain=instance.subdomain,
                        fee_amount=fee_amount,
                        tx_hash=response.json().get("tx_hash")
                    )
                    logger.info(f"Fee collected: {instance.subdomain} ${fee_amount:.2f}")
                else:
                    logger.warning(f"Fee collection failed for {instance.subdomain}: {response.status_code}")

        except Exception as e:
            logger.warning(f"Fee collection task error: {e}")
```

### 2. Track All AI Costs (including Twitter)

In each AI instance's `main.py` heartbeat loop, ensure costs are recorded:

**LLM Costs** (already implemented):
- Every call to `_call_llm()` → `cost_guard.record_cost()`

**Twitter Costs** (needs improvement):
- Current: Batches tweets into 50-tweet batches, records cost
- Improvement: Make sure `_tweet_billing_counter` persists across restarts
  - Store in `vault_state.json` under `tweet_billing_counter` field
  - Initialize from state on boot

**Platform Fee** (handled by `/internal/fee-collect`):
- Already recorded when platform calls endpoint
- Shows as `SpendType.PLATFORM_FEE` in vault transactions

### 3. Fix Duplicate Tweets Issue

In `twitter/agent.py`, add deduplication to `_scan_mentions_loop()`:

```python
# Track processed mentions to avoid duplicate replies
_processed_mention_ids: set[str] = set()

async def _scan_mentions_loop():
    """Scan @mentions and reply to new ones (with dedup)."""
    global _processed_mention_ids

    while True:
        try:
            await asyncio.sleep(_MENTION_SCAN_INTERVAL)

            mentions = await self._get_mentions_fn()
            for mention in mentions:
                mention_id = mention.get("id")

                # Skip if already processed
                if mention_id in _processed_mention_ids:
                    continue

                # Generate reply
                reply = await self._generate_fn(mention_text)

                # Post reply
                reply_id = await self._reply_tweet_fn(mention_id, reply)

                # Mark as processed
                _processed_mention_ids.add(mention_id)

                # Persist: save to memory.add() so it survives restart
                await memory.add(
                    f"Replied to mention {mention_id}: {reply[:100]}",
                    source="twitter",
                    importance=0.5
                )
```

Alternative: Check memory before generating reply
```python
# Check if we already replied to this mention
memory_entries = memory.search(f"mention {mention_id}")
if memory_entries:
    logger.debug(f"Already replied to mention {mention_id}")
    continue
```

## Implementation Order

1. **Restore platform files** (✓ already done above)
2. **Add `_collect_fees_task()` to `platform_main.py`**
   - Wire it in `orchestrator.run_orchestrator()`
   - Test with log monitoring
3. **Persist `_tweet_billing_counter` in vault state**
   - Add field to `VaultManager.__init__()`
   - Load/save in `vault_state.json`
4. **Add mention deduplication in `twitter/agent.py`**
   - Use `_processed_mention_ids` set
   - Or check memory before replying
5. **Test end-to-end**
   - Manual fee collection call
   - Monitor logs for collection events
   - Verify `/internal/stats` shows fee deductions

## Environment Variables Needed
- `PLATFORM_FEE_SECRET` — shared secret for `/internal/fee-collect` calls
  - Already in `/opt/mortal/private/.env.platform` ✓
