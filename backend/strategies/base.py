"""
Abstract base class for all execution strategies.

A strategy converts (total_shares, T, N) into a deterministic schedule of
(time_offset_seconds, qty) pairs. The simulation runner uses this schedule
to decide when to fire orders at the exchange.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TradeSlice:
    """
    A single scheduled trade.

    Attributes
    ----------
    time_offset : float
        Seconds from the simulation start at which this trade should fire.
    qty : float
        Number of shares to sell at this step.
    """
    time_offset: float
    qty: float


class Strategy(ABC):
    """
    Base class for execution strategies.

    Subclasses must implement:
        generate_schedule() — produce a list of TradeSlice
        name               — string identifier
    """

    @abstractmethod
    def generate_schedule(
        self,
        total_shares: float,
        T: float,
        N: int,
    ) -> list[TradeSlice]:
        """
        Return a list of N TradeSlice objects defining when and how much
        to sell.

        Parameters
        ----------
        total_shares : float
            Total shares to liquidate over the horizon.
        T : float
            Liquidation horizon in minutes.
        N : int
            Number of discrete trade steps.

        Returns
        -------
        list[TradeSlice]
            Ordered list of (time_offset_seconds, qty) pairs.
            Sum of all qty values should equal total_shares.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy identifier."""
        ...
