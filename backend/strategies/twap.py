"""
TWAP (Time-Weighted Average Price) execution strategy.

Divides total shares into N equal tranches distributed evenly over T
minutes. This is the canonical baseline that avoids market timing but
ignores risk aversion and market impact optimization.
"""

from backend.strategies.base import Strategy, TradeSlice


class TWAPStrategy(Strategy):
    """
    Uniform liquidation: sell total_shares / N shares at each of N steps.
    """

    @property
    def name(self) -> str:
        return "twap"

    def generate_schedule(
        self,
        total_shares: float,
        T: float,
        N: int,
    ) -> list[TradeSlice]:
        """
        Returns N equal-sized TradeSlices evenly spaced over T minutes.

        The first trade fires at t = tau_seconds (not t=0) to mirror the
        AC convention where trades occur at the midpoint of each interval.
        We use t = i * tau for i in 0..N-1 (start of each interval).
        """
        tau_seconds = (T / N) * 60.0  # per-step duration in seconds
        qty_per_step = total_shares / N

        schedule: list[TradeSlice] = [
            TradeSlice(time_offset=i * tau_seconds, qty=qty_per_step)
            for i in range(N)
        ]
        return schedule
