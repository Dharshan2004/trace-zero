"""
VWAP (Volume-Weighted Average Price) execution strategy.

Targets a historically-derived intraday volume profile so that the
strategy's participation rate matches the market's natural volume rhythm.
This is the actual industry-standard benchmark used by institutional desks.

Volume Profile
--------------
Crypto markets exhibit a modified U-shape: elevated volume at the open of
each UTC session (Asia → Europe → US handoff), lower during mid-session,
and a pickup into the close. We model this with a parameterized curve:

    w(t) = base + amplitude * (2t - 1)^2

where t ∈ [0, 1] runs across the liquidation horizon. The weights are
normalized to sum to 1 so that Σ qty_i = total_shares exactly.

POV (Percentage of Volume) note
---------------------------------
A true POV strategy requires real-time observed market volume to size each
child order. Since we replay L1/L2 snapshots (which lack trade volume),
we use the stylized profile as a proxy. If L2 qty data is available in the
event stream, the runner can optionally scale the profile to observed depth.
"""

import numpy as np

from backend.strategies.base import Strategy, TradeSlice


class VWAPStrategy(Strategy):
    """
    Executes proportional to a stylized intraday volume profile.

    Parameters
    ----------
    base : float
        Minimum weight floor at any step (prevents zero-qty slices).
    amplitude : float
        Strength of the U-shape. Higher values front/back-load more.
    """

    def __init__(self, base: float = 1.0, amplitude: float = 2.0) -> None:
        self._base = base
        self._amplitude = amplitude

    @property
    def name(self) -> str:
        return "vwap"

    def generate_schedule(
        self,
        total_shares: float,
        T: float,
        N: int,
    ) -> list[TradeSlice]:
        """
        Return N TradeSlices proportional to the intraday volume profile.

        The volume profile is a continuous U-shaped curve evaluated at N
        uniformly-spaced points across [0, 1], normalized to sum to 1.
        """
        tau_seconds = (T / N) * 60.0

        # t ∈ [0, 1] — normalized position in the liquidation horizon
        t = np.linspace(0.0, 1.0, N)

        # U-shaped volume weight: high at 0 and 1, dip at 0.5
        weights = self._base + self._amplitude * (2.0 * t - 1.0) ** 2
        weights /= weights.sum()

        schedule: list[TradeSlice] = [
            TradeSlice(
                time_offset=i * tau_seconds,
                qty=float(weights[i] * total_shares),
            )
            for i in range(N)
        ]
        return schedule
