"""
Almgren-Chriss optimal execution strategy.

Uses the AC model's closed-form trade list to generate a front-loaded
schedule that minimizes the mean-variance utility of execution cost.
"""

import numpy as np

from backend.models.almgren_chriss import AlmgrenChriss
from backend.strategies.base import Strategy, TradeSlice


class ACOptimalStrategy(Strategy):
    """
    AC optimal schedule derived from AlmgrenChriss.get_trade_list().

    The AC schedule is typically front-loaded (more selling early) to
    reduce variance at the cost of slightly higher expected shortfall,
    trading off against the risk aversion parameter lambda.
    """

    def __init__(self, ac_model: AlmgrenChriss) -> None:
        self._ac = ac_model

    @property
    def name(self) -> str:
        return "ac"

    def generate_schedule(
        self,
        total_shares: float,
        T: float,
        N: int,
    ) -> list[TradeSlice]:
        """
        Generate the AC optimal trade schedule.

        The AC model is already calibrated with (T, N, shares) matching
        the simulation config. We call get_trade_list() and map each trade
        to a time offset.

        Parameters
        ----------
        total_shares : float
            Must match ac_model.config.shares (passed for API consistency).
        T : float
            Liquidation horizon in minutes (should match ac_model.config.T).
        N : int
            Number of trades (should match ac_model.config.N).

        Returns
        -------
        list[TradeSlice]
            N trade slices following the AC optimal trajectory.
        """
        trade_list: np.ndarray = self._ac.get_trade_list()

        # Ensure length matches N (model should already guarantee this)
        if len(trade_list) != N:
            # Fallback: rescale to N steps
            indices = np.linspace(0, len(trade_list) - 1, N)
            trade_list = np.interp(indices, np.arange(len(trade_list)), trade_list)

        # Normalize to total_shares in case of floating-point drift
        total = trade_list.sum()
        if total > 0:
            trade_list = trade_list * (total_shares / total)

        tau_seconds = (T / N) * 60.0

        schedule: list[TradeSlice] = [
            TradeSlice(
                time_offset=i * tau_seconds,
                qty=float(trade_list[i]),
            )
            for i in range(N)
        ]
        return schedule
