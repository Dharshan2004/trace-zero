"""
Dump (panic) execution strategy.

Sells the entire position in a single trade at t=0. This represents the
worst-case scenario for market impact and is used as the upper bound for
implementation shortfall comparison.
"""

from backend.strategies.base import Strategy, TradeSlice


class DumpStrategy(Strategy):
    """
    Single-trade liquidation at time zero.

    All shares are sold immediately. This maximizes temporary impact on
    the first trade and permanently degrades the book for the rest of the
    (empty) schedule.
    """

    @property
    def name(self) -> str:
        return "dump"

    def generate_schedule(
        self,
        total_shares: float,
        T: float,
        N: int,
    ) -> list[TradeSlice]:
        """
        Returns a single TradeSlice at t=0 with all shares.

        The remaining N-1 steps are zero-qty placeholders so the simulation
        runner can advance the clock uniformly across strategies.
        """
        tau_seconds = (T / N) * 60.0  # minutes -> seconds per step

        schedule: list[TradeSlice] = []
        for i in range(N):
            time_offset = i * tau_seconds
            qty = total_shares if i == 0 else 0.0
            schedule.append(TradeSlice(time_offset=time_offset, qty=qty))

        return schedule
