"""
Result dataclasses for completed simulation runs.

StrategyResult holds the per-strategy metrics. SimulationResult is the
top-level object returned by the runner and serialized for the API.
"""

from dataclasses import dataclass, field
from typing import Any

from backend.engine.order import Fill
from backend.simulation.config import SimulationConfig


@dataclass
class StrategyResult:
    """
    Aggregated results for a single strategy within a simulation.

    Attributes
    ----------
    name : str
        Strategy identifier ('dump', 'twap', 'ac').
    fills : list[Fill]
        All fills executed by this strategy.
    vwap : float
        Volume-weighted average fill price.
    implementation_shortfall_bps : float
        (arrival_price - VWAP) / arrival_price * 10_000.
    trajectory_variance : float
        Sum of squared trade sizes * sigma2 (risk measure).
    utility : float
        AC utility = E[shortfall] + lambda * Var[shortfall].
    trajectory : list[float]
        Shares remaining after each trade step (length N).
    cost_curve : list[float]
        Cumulative implementation shortfall in bps after each step (length N).
    """
    name: str
    fills: list[Fill]
    vwap: float
    implementation_shortfall_bps: float
    trajectory_variance: float
    utility: float
    trajectory: list[float]
    cost_curve: list[float]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict (fills are summarized, not expanded)."""
        return {
            "name": self.name,
            "vwap": self.vwap,
            "implementation_shortfall_bps": self.implementation_shortfall_bps,
            "trajectory_variance": self.trajectory_variance,
            "utility": self.utility,
            "trajectory": self.trajectory,
            "cost_curve": self.cost_curve,
            "num_fills": len(self.fills),
        }


@dataclass
class SimulationResult:
    """
    Complete output of one simulation run covering all three strategies.

    Attributes
    ----------
    config : SimulationConfig
        The configuration used for this run.
    dump : StrategyResult
        Results for the panic-dump strategy.
    twap : StrategyResult
        Results for TWAP.
    ac : StrategyResult
        Results for AC optimal strategy.
    price_series : list[dict]
        Raw price feed used during simulation:
        [{timestamp_ms, mid, bid, ask}, ...].
    ac_savings_vs_dump_bps : float
        IS(dump) - IS(ac) in basis points — positive means AC saved cost.
    ac_savings_vs_twap_bps : float
        IS(twap) - IS(ac) in basis points.
    """
    config: SimulationConfig
    dump: StrategyResult
    twap: StrategyResult
    ac: StrategyResult
    price_series: list[dict]
    ac_savings_vs_dump_bps: float
    ac_savings_vs_twap_bps: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe nested dict."""
        return {
            "config": {
                "symbol": self.config.symbol,
                "total_shares": self.config.total_shares,
                "liquidation_time": self.config.liquidation_time,
                "num_trades": self.config.num_trades,
                "risk_aversion": self.config.risk_aversion,
            },
            "strategies": {
                "dump": self.dump.to_dict(),
                "twap": self.twap.to_dict(),
                "ac": self.ac.to_dict(),
            },
            "price_series": self.price_series,
            "ac_savings_vs_dump_bps": self.ac_savings_vs_dump_bps,
            "ac_savings_vs_twap_bps": self.ac_savings_vs_twap_bps,
        }
