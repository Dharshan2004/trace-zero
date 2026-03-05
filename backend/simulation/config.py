"""
Simulation configuration dataclass.

This is the primary input contract for the simulation runner and the
/api/simulation/run REST endpoint.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SimulationConfig:
    """
    Parameters controlling a single simulation run.

    Attributes
    ----------
    symbol : str
        Market symbol (informational, used for labeling).
    total_shares : float
        Total shares (or BTC, contracts, etc.) to liquidate.
    liquidation_time : float
        Total liquidation horizon in minutes.
    num_trades : int
        Number of discrete trade steps across the horizon.
    risk_aversion : float
        Almgren-Chriss lambda — trader's risk aversion coefficient.
        Larger values produce front-loaded (safer) schedules.
    gamma_override : Optional[float]
        If provided, override calibrated permanent impact coefficient.
    eta_override : Optional[float]
        If provided, override calibrated temporary impact coefficient.
    data_file : Optional[str]
        Absolute or relative path to a JSONL file for replay.
        If None or the file does not exist, synthetic data is generated.
    """
    symbol: str = "BTCUSDT"
    total_shares: float = 1.0
    liquidation_time: float = 60.0
    num_trades: int = 20
    risk_aversion: float = 1e-6
    gamma_override: Optional[float] = None
    eta_override: Optional[float] = None
    data_file: Optional[str] = None
