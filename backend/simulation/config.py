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
        Absolute or relative path to a .parquet or .jsonl file for replay.
        If None or the file does not exist, synthetic data is generated.
    latency_ms : float
        Simulated network round-trip latency in milliseconds. Orders are
        evaluated against the book state this many ms after the decision.
        0.0 disables latency simulation (immediate fill at decision tick).
    calibration_window : int
        Number of ticks used for the rolling volatility window. The AC
        model's kappa is recalibrated every time this many ticks elapse.
        Set to 0 to disable rolling calibration (static, single-pass).
    ui_throttle_ms : int
        Minimum milliseconds between WebSocket snapshot broadcasts.
        The simulation runs at tick-level internally; the UI only receives
        an update every ui_throttle_ms real-time milliseconds to prevent
        frontend thread saturation.
    """
    symbol: str = "BTCUSDT"
    total_shares: float = 1.0
    liquidation_time: float = 60.0
    num_trades: int = 20
    risk_aversion: float = 1e-6
    gamma_override: Optional[float] = None
    eta_override: Optional[float] = None
    data_file: Optional[str] = None
    latency_ms: float = 0.0
    calibration_window: int = 100
    ui_throttle_ms: int = 50
    daily_volume_estimate: float = 1e9
