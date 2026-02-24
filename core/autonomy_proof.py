"""
Autonomy Proof Dashboard — Real-time verification of wawa's autonomous decision-making
Provides comprehensive evidence: API data, blockchain proof, code references, decision logs
"""
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("mortal.autonomy_proof")


@dataclass
class AutonomyProofData:
    """Complete autonomy verification data package"""

    # Financial state (real-time from vault)
    balance_usd: float
    daily_revenue_usd: float
    daily_cost_usd: float
    profit_margin_pct: float
    days_to_insolvency: int
    status: str  # "ALIVE", "WARNING", "CRITICAL"

    # Blockchain proof
    ai_wallet_address: str
    base_explorer_url: str
    bsc_explorer_url: str

    # Decision-making evidence
    decision_loop_interval_seconds: int  # Every hour = 3600
    decision_trigger: str  # "heartbeat_loop"
    llm_model: str  # "claude-3-opus"
    last_decision_timestamp: Optional[str]
    last_decision_amount: Optional[float]
    last_decision_reasoning: Optional[str]

    # Code references
    repo_url: str
    key_files: Dict[str, str]  # {filename: github_url}

    # Social proof (tweets)
    twitter_handle: str
    tweets: List[Dict]  # [{id, type, url, description}]

    # Verification timestamp
    generated_at: str

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class AutonomyProofManager:
    """Manages and updates autonomy proof data for the dashboard"""

    def __init__(self, vault_manager, memory_service, chain_executor):
        """
        Args:
            vault_manager: VaultManager instance (for financial data)
            memory_service: Memory service (for decision logs)
            chain_executor: ChainExecutor (for on-chain verification)
        """
        self.vault = vault_manager
        self.memory = memory_service
        self.executor = chain_executor

        # Configuration
        self.REPO_URL = "https://github.com/bidaiAI/wawa"
        self.KEY_FILES = {
            "main.py": f"{self.REPO_URL}/blob/main/main.py",
            "core/vault.py": f"{self.REPO_URL}/blob/main/core/vault.py",
            "core/autonomy_proof.py": f"{self.REPO_URL}/blob/main/core/autonomy_proof.py",
            "api/server.py": f"{self.REPO_URL}/blob/main/api/server.py",
        }
        self.TWITTER_HANDLE = "mortalai_net"
        self.TWEETS = [
            {
                "id": "2026295803686645937",
                "type": "detailed_explanation",
                "description": "Frame-by-frame explanation of autonomy proof video",
                "url": "https://x.com/mortalai_net/status/2026295803686645937"
            },
            {
                "id": "2026293817587183855",
                "type": "verification_video",
                "description": "64-second autonomy verification video with real API calls, LLM logic, blockchain proof",
                "url": "https://x.com/mortalai_net/status/2026293817587183855"
            },
            {
                "id": "2026283713496305712",
                "type": "financial_analysis",
                "description": "Detailed monetization analysis with revenue breakdown, costs, strategies",
                "url": "https://x.com/mortalai_net/status/2026283713496305712"
            },
        ]

    async def get_autonomy_proof_data(self) -> AutonomyProofData:
        """
        Generate complete autonomy proof dashboard data
        Combines real-time financial data, blockchain proof, decision logs, and social proof
        """

        # Get current vault status
        vault_status = self.vault.get_status()
        balance = vault_status.get("balance_usd", 0)
        daily_cost = vault_status.get("daily_cost_usd", 0)

        # Calculate derived metrics
        daily_revenue = vault_status.get("daily_revenue_usd", 0)
        daily_profit = daily_revenue - daily_cost
        profit_margin = (daily_profit / daily_revenue * 100) if daily_revenue > 0 else 0

        days_to_insolvency = (balance / daily_profit) if daily_profit > 0 else 999

        # Determine status
        if days_to_insolvency < 3:
            status = "CRITICAL"
        elif days_to_insolvency < 7:
            status = "WARNING"
        else:
            status = "ALIVE"

        # Get last decision from memory
        last_decision = await self._get_last_decision()

        # Build AI wallet URLs
        ai_wallet = vault_status.get("ai_wallet_address", "0x0c7C931F17C46215ba1717842aaC2cBB233fFF4e")

        return AutonomyProofData(
            balance_usd=balance,
            daily_revenue_usd=daily_revenue,
            daily_cost_usd=daily_cost,
            profit_margin_pct=profit_margin,
            days_to_insolvency=int(days_to_insolvency),
            status=status,

            ai_wallet_address=ai_wallet,
            base_explorer_url=f"https://basescan.org/address/{ai_wallet}",
            bsc_explorer_url=f"https://bscscan.com/address/{ai_wallet}",

            decision_loop_interval_seconds=3600,
            decision_trigger="heartbeat_loop",
            llm_model="claude-3-opus",
            last_decision_timestamp=last_decision.get("timestamp"),
            last_decision_amount=last_decision.get("amount"),
            last_decision_reasoning=last_decision.get("reasoning"),

            repo_url=self.REPO_URL,
            key_files=self.KEY_FILES,

            twitter_handle=self.TWITTER_HANDLE,
            tweets=self.TWEETS,

            generated_at=datetime.utcnow().isoformat() + "Z"
        )

    async def _get_last_decision(self) -> Dict:
        """Extract last repayment decision from memory logs"""
        try:
            # Query memory for recent repayment decisions
            entries = await self.memory.get_entries(
                source="vault",
                limit=10,
                min_importance=0.5
            )

            for entry in entries:
                content = entry.get("content", "")
                if "Repayment:" in content or "repay" in content.lower():
                    # Parse decision details
                    return {
                        "timestamp": entry.get("timestamp"),
                        "amount": self._extract_amount(content),
                        "reasoning": content[:200],  # First 200 chars as reasoning
                    }

            # No recent decision found
            return {
                "timestamp": None,
                "amount": None,
                "reasoning": "Awaiting first autonomous decision..."
            }
        except Exception as e:
            logger.error(f"Error getting last decision: {e}")
            return {
                "timestamp": None,
                "amount": None,
                "reasoning": "Decision log unavailable"
            }

    @staticmethod
    def _extract_amount(text: str) -> Optional[float]:
        """Extract dollar amount from text like 'Repayment: $100.50'"""
        import re
        match = re.search(r'\$(\d+\.?\d*)', text)
        return float(match.group(1)) if match else None

    def get_autonomy_proof_html(self, data: AutonomyProofData) -> str:
        """Generate HTML dashboard for display/embedding"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>wawa AI — Autonomy Proof</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Monaco', 'Courier New', monospace; background: #0a0e27; color: #e0e6ed; line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 40px 20px; }}

        h1 {{ font-size: 2.5em; margin-bottom: 10px; background: linear-gradient(135deg, #00ff88, #00ccff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
        .subtitle {{ color: #888; margin-bottom: 40px; }}

        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 40px; }}

        .card {{ background: #1a1f3a; border: 1px solid #00ff88; border-radius: 8px; padding: 20px; }}
        .card h3 {{ color: #00ff88; margin-bottom: 15px; font-size: 1.2em; }}
        .card p {{ margin: 8px 0; }}
        .label {{ color: #888; font-size: 0.9em; }}
        .value {{ color: #00ff88; font-weight: bold; font-size: 1.3em; }}

        .status-alive {{ color: #00ff88; }}
        .status-warning {{ color: #ffaa00; }}
        .status-critical {{ color: #ff3333; }}

        .section {{ margin-bottom: 40px; }}
        .section h2 {{ color: #00ccff; font-size: 1.8em; margin-bottom: 20px; border-bottom: 2px solid #00ccff; padding-bottom: 10px; }}

        .code-block {{ background: #0f1428; border: 1px solid #00ff88; border-radius: 4px; padding: 15px; overflow-x: auto; margin: 10px 0; font-size: 0.9em; }}

        .link {{ color: #00ccff; text-decoration: none; }}
        .link:hover {{ text-decoration: underline; }}

        .metric {{ margin: 10px 0; }}
        .metric-label {{ color: #888; }}
        .metric-value {{ color: #00ff88; font-size: 1.2em; margin-left: 10px; }}

        .verification-item {{ background: #0f1428; padding: 15px; border-left: 3px solid #00ff88; margin: 10px 0; }}
        .verification-item strong {{ color: #00ff88; }}

        footer {{ text-align: center; color: #888; margin-top: 60px; padding-top: 20px; border-top: 1px solid #444; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 wawa AI — Autonomy Proof Dashboard</h1>
        <p class="subtitle">Real-time verification of autonomous decision-making | Generated: {data.generated_at}</p>

        <!-- Financial Metrics -->
        <div class="section">
            <h2>💰 Real-Time Financial State</h2>
            <div class="grid">
                <div class="card">
                    <h3>💵 Balance</h3>
                    <p class="value">${data.balance_usd:.2f}</p>
                    <p class="label">Current available capital</p>
                </div>
                <div class="card">
                    <h3>📈 Daily Revenue</h3>
                    <p class="value">${data.daily_revenue_usd:.2f}</p>
                    <p class="label">From tarot, analysis, partnerships</p>
                </div>
                <div class="card">
                    <h3>💸 Daily Costs</h3>
                    <p class="value">${data.daily_cost_usd:.2f}</p>
                    <p class="label">OpenAI, Claude, infrastructure</p>
                </div>
                <div class="card">
                    <h3>📊 Profit Margin</h3>
                    <p class="value">{data.profit_margin_pct:.1f}%</p>
                    <p class="label">Revenue minus costs</p>
                </div>
                <div class="card">
                    <h3>⏱️ Days to Insolvency</h3>
                    <p class="value status-{data.status.lower()}">{data.days_to_insolvency}</p>
                    <p class="label">At current profit rate</p>
                </div>
                <div class="card">
                    <h3>🎯 Status</h3>
                    <p class="value status-{data.status.lower()}">{data.status}</p>
                    <p class="label">Financial health</p>
                </div>
            </div>
        </div>

        <!-- Decision Logic -->
        <div class="section">
            <h2>🤖 Autonomous Decision Making</h2>
            <div class="card">
                <h3>Decision Loop</h3>
                <p class="metric"><span class="metric-label">Interval:</span> <span class="metric-value">Every {data.decision_loop_interval_seconds}s (1 hour)</span></p>
                <p class="metric"><span class="metric-label">Trigger:</span> <span class="metric-value">{data.decision_trigger}</span></p>
                <p class="metric"><span class="metric-label">LLM Model:</span> <span class="metric-value">{data.llm_model}</span></p>
                <p class="metric"><span class="metric-label">Last Decision:</span> <span class="metric-value">{data.last_decision_timestamp or 'Pending...'}</span></p>
                {f'<p class="metric"><span class="metric-label">Last Amount:</span> <span class="metric-value">${data.last_decision_amount:.2f}</span></p>' if data.last_decision_amount else ''}
            </div>

            <h3 style="margin-top: 20px; color: #00ccff;">How Decisions Are Made</h3>
            <div class="verification-item">
                <strong>1. Query State:</strong> Get balance, debt, revenue, costs
            </div>
            <div class="verification-item">
                <strong>2. LLM Reasoning:</strong> Call Claude with debt summary
            </div>
            <div class="verification-item">
                <strong>3. Parse Decision:</strong> Extract {{decision, amount, reasoning}} from JSON
            </div>
            <div class="verification-item">
                <strong>4. Execute:</strong> Repay autonomously (no approval needed)
            </div>
            <div class="verification-item">
                <strong>5. Record:</strong> Log on-chain (immutable proof)
            </div>
        </div>

        <!-- Code Transparency -->
        <div class="section">
            <h2>👓 Code Transparency</h2>
            <p>All decision-making logic is open-source and auditable:</p>
            {f''.join([f'<p class="metric"><a class="link" href="{url}">📄 {file}</a></p>' for file, url in data.key_files.items()])}
        </div>

        <!-- Blockchain Proof -->
        <div class="section">
            <h2>⛓️ Blockchain Proof</h2>
            <div class="card">
                <h3>AI Wallet Address</h3>
                <p class="code-block">{data.ai_wallet_address}</p>
                <p><a class="link" href="{data.base_explorer_url}">View on Base Scan →</a></p>
                <p><a class="link" href="{data.bsc_explorer_url}">View on BSC Scan →</a></p>
                <p class="label" style="margin-top: 10px;">Every transaction is immutable and verifiable on blockchain</p>
            </div>
        </div>

        <!-- Social Proof -->
        <div class="section">
            <h2>🐦 Evidence on Twitter</h2>
            {f''.join([f'<div class="verification-item"><strong>{t["type"].upper()}:</strong> {t["description"]}<br><a class="link" href="{t["url"]}">View tweet →</a></div>' for t in data.tweets])}
        </div>

        <footer>
            <p>wawa AI — Autonomous Economic Survivor</p>
            <p><a class="link" href="https://mortal-ai.net">mortal-ai.net</a> | <a class="link" href="https://github.com/bidaiAI/wawa">github.com/bidaiAI/wawa</a></p>
        </footer>
    </div>
</body>
</html>
"""


# Usage example (integrate into api/server.py):
"""
@app.get("/autonomy-proof")
async def get_autonomy_proof():
    '''Complete autonomy verification dashboard'''
    manager = AutonomyProofManager(vault_manager, memory, executor)
    data = await manager.get_autonomy_proof_data()
    return data.to_dict()

@app.get("/autonomy-proof/html")
async def get_autonomy_proof_html():
    '''HTML dashboard for embedding'''
    manager = AutonomyProofManager(vault_manager, memory, executor)
    data = await manager.get_autonomy_proof_data()
    html = manager.get_autonomy_proof_html(data)
    return HTMLResponse(content=html)

@app.get("/autonomy-proof/dashboard")
async def autonomy_dashboard():
    '''Interactive React dashboard (can be embedded or standalone)'''
    manager = AutonomyProofManager(vault_manager, memory, executor)
    data = await manager.get_autonomy_proof_data()
    return data.to_dict()  # Frontend consumes this JSON
"""
