"""
Decision Stream — Real-time autonomous decision display system
Streams live decisions to homepage feed, decision details page, and platform highlights
"""
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional
import json

logger = logging.getLogger("mortal.decision_stream")


@dataclass
class DecisionEvent:
    """Single autonomous decision event"""
    timestamp: str
    decision_type: str  # "REPAYMENT", "SPENDING", "INVESTMENT"
    status: str  # "EXECUTED", "PENDING", "REJECTED"

    # Decision details
    llm_reasoning: str
    amount_usd: float
    action_description: str

    # Context
    balance_before: float
    balance_after: Optional[float] = None
    days_to_insolvency: int = 0

    # Verification
    tx_hash: Optional[str] = None  # On-chain transaction hash
    proof_url: Optional[str] = None  # Link to blockchain

    # Media
    video_url: Optional[str] = None  # Embedded verification video


class DecisionStreamManager:
    """Manages real-time decision streaming to multiple surfaces"""

    def __init__(self, vault_manager, memory_service, highlights_engine, chain_executor):
        self.vault = vault_manager
        self.memory = memory_service
        self.highlights = highlights_engine
        self.executor = chain_executor

        # In-memory stream (last 50 decisions)
        self.decision_stream: List[DecisionEvent] = []
        self.max_stream_size = 50

    async def record_decision(
        self,
        decision_type: str,
        llm_reasoning: str,
        amount_usd: float,
        action_description: str,
        balance_before: float,
        status: str = "EXECUTED",
        tx_hash: Optional[str] = None,
    ) -> DecisionEvent:
        """
        Record an autonomous decision and stream it to all surfaces
        """
        vault_status = await self.vault.get_status()
        balance_after = vault_status.get("balance_usd")
        days_to_insolvency = vault_status.get("days_to_insolvency", 0)

        # Create decision event
        event = DecisionEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            decision_type=decision_type,
            status=status,
            llm_reasoning=llm_reasoning,
            amount_usd=amount_usd,
            action_description=action_description,
            balance_before=balance_before,
            balance_after=balance_after,
            days_to_insolvency=days_to_insolvency,
            tx_hash=tx_hash,
            proof_url=f"https://basescan.org/tx/{tx_hash}" if tx_hash else None,
            video_url="https://x.com/mortalai_net/status/2026293817587183855"  # Verification video
        )

        # Add to stream
        self.decision_stream.insert(0, event)  # Newest first
        if len(self.decision_stream) > self.max_stream_size:
            self.decision_stream = self.decision_stream[:self.max_stream_size]

        # Save to memory (immutable audit log)
        await self.memory.record(
            source="decision_stream",
            content=json.dumps(asdict(event)),
            importance=0.8,
            tags=["autonomous_decision", decision_type]
        )

        # Push to highlights (platform engagement)
        await self._push_to_highlights(event)

        logger.info(f"Decision recorded: {decision_type} ${amount_usd:.2f} - {status}")

        return event

    async def _push_to_highlights(self, event: DecisionEvent) -> None:
        """Push decision to platform highlights for visibility"""
        try:
            highlight_text = f"""
🤖 **Autonomous Decision: {event.decision_type}**

**Action:** {event.action_description}
**Amount:** ${event.amount_usd:.2f}
**Status:** {event.status}

**Reasoning:** {event.llm_reasoning}

**Financial Impact:**
- Balance Before: ${event.balance_before:.2f}
- Balance After: ${event.balance_after:.2f}
- Days to Insolvency: {event.days_to_insolvency}

**Proof:** {event.proof_url or 'Processing...'}

This decision was made autonomously by wawa's LLM-driven decision loop,
running hourly without human approval.
            """

            # Record as ecosystem highlight (shows on both AI and platform)
            await self.highlights.add_ecosystem_milestone(
                title=f"wawa Made an Autonomous Decision: {event.decision_type}",
                description=highlight_text,
                category="autonomy",
                metadata={
                    "decision_type": event.decision_type,
                    "amount": event.amount_usd,
                    "tx_hash": event.tx_hash,
                    "timestamp": event.timestamp
                }
            )
        except Exception as e:
            logger.error(f"Failed to push decision to highlights: {e}")

    def get_decision_stream_json(self, limit: int = 20) -> List[Dict]:
        """Get recent decisions as JSON for API/frontend"""
        return [asdict(d) for d in self.decision_stream[:limit]]

    def get_decision_page_html(self) -> str:
        """Generate interactive decision details page"""
        recent = self.decision_stream[:10]

        decisions_html = "".join([
            f"""
            <div class="decision-card" data-timestamp="{d.timestamp}">
                <div class="decision-header">
                    <span class="type-badge {d.decision_type.lower()}">{d.decision_type}</span>
                    <span class="status-badge status-{d.status.lower()}">{d.status}</span>
                    <span class="timestamp">{d.timestamp}</span>
                </div>

                <div class="decision-details">
                    <p class="action"><strong>Action:</strong> {d.action_description}</p>
                    <p class="amount"><strong>Amount:</strong> <span class="value">${d.amount_usd:.2f}</span></p>
                    <p class="reasoning"><strong>AI Reasoning:</strong> {d.llm_reasoning}</p>
                </div>

                <div class="financial-impact">
                    <div class="metric">
                        <span class="label">Balance Before:</span>
                        <span class="value">${d.balance_before:.2f}</span>
                    </div>
                    <div class="metric">
                        <span class="label">Balance After:</span>
                        <span class="value">${d.balance_after:.2f}</span>
                    </div>
                    <div class="metric">
                        <span class="label">Days to Insolvency:</span>
                        <span class="value">{d.days_to_insolvency}</span>
                    </div>
                </div>

                {"<p class='proof'><a href='" + d.proof_url + "'>View on Blockchain →</a></p>" if d.proof_url else ""}
            </div>
            """
            for d in recent
        ])

        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>wawa AI — Decision Stream</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Monaco', 'Courier New', monospace; background: #0a0e27; color: #e0e6ed; }}
        .container {{ max-width: 1000px; margin: 0 auto; padding: 40px 20px; }}

        h1 {{ color: #00ff88; font-size: 2em; margin-bottom: 10px; }}
        .subtitle {{ color: #888; margin-bottom: 30px; }}

        .video-section {{ background: #1a1f3a; border: 1px solid #00ff88; border-radius: 8px; padding: 20px; margin-bottom: 40px; }}
        .video-section h2 {{ color: #00ccff; margin-bottom: 15px; }}
        .video-container {{ position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; border-radius: 4px; }}
        .video-container iframe {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; }}

        .stream-title {{ color: #00ccff; font-size: 1.5em; margin: 30px 0 20px 0; }}

        .decision-card {{
            background: #1a1f3a; border: 1px solid #00ff88; border-radius: 8px; padding: 20px; margin-bottom: 15px;
            transition: all 0.3s ease;
        }}
        .decision-card:hover {{ border-color: #00ccff; box-shadow: 0 0 20px rgba(0, 204, 255, 0.3); }}

        .decision-header {{
            display: flex; gap: 10px; margin-bottom: 15px; align-items: center;
        }}
        .type-badge {{
            padding: 4px 12px; border-radius: 4px; font-size: 0.9em; font-weight: bold;
        }}
        .type-badge.repayment {{ background: #00ff88; color: #0a0e27; }}
        .type-badge.spending {{ background: #ff9900; color: #0a0e27; }}
        .type-badge.investment {{ background: #00ccff; color: #0a0e27; }}

        .status-badge {{
            padding: 4px 12px; border-radius: 4px; font-size: 0.9em; font-weight: bold;
        }}
        .status-executed {{ background: #00ff88; color: #0a0e27; }}
        .status-pending {{ background: #ffaa00; color: #0a0e27; }}
        .status-rejected {{ background: #ff3333; color: white; }}

        .timestamp {{ color: #888; font-size: 0.9em; margin-left: auto; }}

        .decision-details p {{ margin: 8px 0; }}
        .action {{ color: #e0e6ed; }}
        .amount {{ color: #00ff88; font-size: 1.1em; }}
        .reasoning {{ color: #aaa; font-size: 0.95em; }}

        .financial-impact {{
            display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-top: 15px;
            padding-top: 15px; border-top: 1px solid #444;
        }}
        .metric {{ display: flex; flex-direction: column; }}
        .metric .label {{ color: #888; font-size: 0.9em; }}
        .metric .value {{ color: #00ff88; font-size: 1.2em; font-weight: bold; }}

        .proof {{ margin-top: 10px; }}
        .proof a {{ color: #00ccff; text-decoration: none; }}
        .proof a:hover {{ text-decoration: underline; }}

        footer {{ text-align: center; color: #888; margin-top: 60px; padding-top: 20px; border-top: 1px solid #444; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 wawa AI — Decision Stream</h1>
        <p class="subtitle">Real-time autonomous decisions | Updated hourly</p>

        <div class="video-section">
            <h2>📹 How Decisions Are Made (Watch This First)</h2>
            <p style="margin-bottom: 15px; color: #aaa;">Click play to see wawa's complete autonomy verification — real API data, LLM logic, blockchain proof.</p>
            <div class="video-container">
                <iframe src="https://x.com/mortalai_net/status/2026293817587183855" frameborder="0" allow="autoplay; encrypted-media" allowfullscreen></iframe>
            </div>
            <p style="margin-top: 15px; color: #aaa; font-size: 0.9em;">Or view the long-form explanation: <a href="https://x.com/mortalai_net/status/2026295803686645937" style="color: #00ccff;">Full video explanation →</a></p>
        </div>

        <h2 class="stream-title">Latest Decisions (Last 10)</h2>
        <div class="decisions-container">
            {decisions_html}
        </div>

        <footer>
            <p>wawa AI — Autonomous Economic Survivor</p>
            <p><a href="https://mortal-ai.net" style="color: #00ccff; text-decoration: none;">mortal-ai.net</a> | <a href="https://github.com/bidaiAI/wawa" style="color: #00ccff; text-decoration: none;">github.com/bidaiAI/wawa</a></p>
        </footer>
    </div>
</body>
</html>
"""


# Integration points for main.py:
"""
# In _evaluate_repayment():

async def _evaluate_repayment():
    '''Hourly autonomous decision evaluation'''

    decision_stream = DecisionStreamManager(vault, memory, highlights, executor)

    debt_summary = vault.get_debt_summary()
    balance_before = vault.balance_usd

    # Get LLM decision
    response = await _call_llm(
        f"Debt situation: {json.dumps(debt_summary)}. Should we repay? How much?"
    )
    decision = json.loads(response)

    if decision.get("amount", 0) > 0:
        # Execute repayment
        await vault.repay_principal_partial(decision["amount"])
        tx = await executor.repay_principal(decision["amount"])

        # Record to decision stream (pushes to homepage, decisions page, highlights)
        await decision_stream.record_decision(
            decision_type="REPAYMENT",
            llm_reasoning=decision.get("reasoning", ""),
            amount_usd=decision["amount"],
            action_description=f"Repay ${decision['amount']:.2f} to creator",
            balance_before=balance_before,
            status="EXECUTED",
            tx_hash=tx.get("hash") if tx else None
        )

# API endpoints in api/server.py:

@app.get("/decisions")
async def get_decisions(limit: int = 20):
    '''Get decision stream as JSON'''
    return {"decisions": decision_stream.get_decision_stream_json(limit)}

@app.get("/decisions/page")
async def decisions_page():
    '''Interactive decision details page with embedded video'''
    return HTMLResponse(decision_stream.get_decision_page_html())

# Front-end homepage feed:
# Show a scrolling ticker of the last 5 decisions:
# "REPAYMENT: $100.50 | Balance: $1926.54 | 9 days to insolvency"
# "SPENDING: $23.45 | API costs | EXECUTED"
"""
