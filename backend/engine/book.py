"""
Simulated L1 orderbook with cumulative permanent impact tracking.

Each strategy instance gets its own SimulatedBook so that the permanent
impact from one strategy does not contaminate another strategy's view of
the market — they all start from the same raw feed but diverge as trades
are executed.
"""


class SimulatedBook:
    """
    Tracks the best bid/ask from the replay feed plus any cumulative
    permanent impact that this strategy's own trading has created.

    The effective execution price (impacted_bid) degrades as the strategy
    sells shares, modeling the Almgren-Chriss permanent impact assumption.
    """

    def __init__(self) -> None:
        self.raw_bid: float = 0.0
        self.raw_ask: float = 0.0
        self.cumulative_perm_impact: float = 0.0

    def update(self, event: dict) -> None:
        """
        Update raw best bid/ask from a normalized replay event.

        Expected keys: 'bid', 'ask'
        """
        self.raw_bid = float(event["bid"])
        self.raw_ask = float(event["ask"])

    @property
    def impacted_bid(self) -> float:
        """
        Effective best bid after subtracting cumulative permanent impact.

        As the strategy sells, it permanently pushes prices down, so the
        bid it can achieve deteriorates over time.
        """
        return self.raw_bid - self.cumulative_perm_impact

    @property
    def impacted_ask(self) -> float:
        """
        Effective best ask after permanent impact (informational).
        """
        return self.raw_ask - self.cumulative_perm_impact

    @property
    def mid(self) -> float:
        """Raw mid-price (not impact-adjusted)."""
        return (self.raw_bid + self.raw_ask) / 2.0

    @property
    def impacted_mid(self) -> float:
        """Impact-adjusted mid-price."""
        return self.mid - self.cumulative_perm_impact

    @property
    def spread(self) -> float:
        """Raw bid-ask spread."""
        return self.raw_ask - self.raw_bid

    def apply_permanent_impact(self, perm_impact: float) -> None:
        """
        Accumulate permanent price impact after a fill.

        perm_impact should be positive — it represents the price degradation
        in absolute price units (e.g., USD per BTC).
        """
        self.cumulative_perm_impact += perm_impact

    def __repr__(self) -> str:
        return (
            f"SimulatedBook(bid={self.raw_bid:.4f}, ask={self.raw_ask:.4f}, "
            f"perm_impact={self.cumulative_perm_impact:.6f})"
        )
