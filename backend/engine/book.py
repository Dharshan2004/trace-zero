"""
Simulated orderbook with L2 depth and cumulative permanent impact tracking.

Each strategy instance gets its own SimulatedBook so that the permanent
impact from one strategy does not contaminate another's view of the market.

L1 vs L2 mode
-------------
If the replay feed contains 'bid_levels' / 'ask_levels' arrays (captured via
the Binance depth20 stream), the book operates in L2 mode and walk_book()
computes exact slippage by consuming resting volume level-by-level.

Without depth data the book falls back to L1 mode: walk_book() returns the
flat impacted_bid, and the exchange applies the AC analytical temp-impact
formula instead.
"""

from __future__ import annotations


class SimulatedBook:
    """
    Tracks the best bid/ask (and optional depth) from the replay feed plus
    any cumulative permanent impact that this strategy's own trading has created.

    The effective execution price degrades as the strategy sells shares,
    modeling the Almgren-Chriss permanent impact assumption.
    """

    def __init__(self) -> None:
        self.raw_bid: float = 0.0
        self.raw_ask: float = 0.0
        self.cumulative_perm_impact: float = 0.0

        # L2 depth: list of [price, qty] sorted best-first (L1 = empty list)
        self.bid_levels: list[list[float]] = []
        self.ask_levels: list[list[float]] = []

    # ------------------------------------------------------------------
    # Feed update
    # ------------------------------------------------------------------

    def update(self, event: dict) -> None:
        """
        Update raw best bid/ask and optional L2 depth from a replay event.

        Expected keys: 'bid', 'ask'
        Optional keys: 'bid_levels', 'ask_levels'
            Each is a list of [price (float), qty (float)] pairs, best first.
        """
        self.raw_bid = float(event["bid"])
        self.raw_ask = float(event["ask"])

        self.bid_levels = event.get("bid_levels") or []
        self.ask_levels = event.get("ask_levels") or []

    # ------------------------------------------------------------------
    # Book-walk: exact L2 slippage
    # ------------------------------------------------------------------

    def walk_book(self, qty_to_sell: float) -> float:
        """
        Compute the VWAP fill price for selling `qty_to_sell` by consuming
        resting bid-side volume level-by-level (walk the book).

        Permanent impact is applied as a uniform price shift across all
        levels (equivalent to a parallel shift of the entire book downward).

        Falls back to impacted_bid if no L2 data is available.

        Parameters
        ----------
        qty_to_sell : float
            Number of shares to sell.

        Returns
        -------
        float
            VWAP-weighted average fill price, adjusted for permanent impact.
        """
        if not self.bid_levels:
            # L1 mode: caller uses analytical temp-impact formula
            return self.impacted_bid

        impact = self.cumulative_perm_impact
        remaining = qty_to_sell
        total_cost = 0.0
        total_filled = 0.0
        worst_price = self.raw_bid - impact  # fallback if book is thin

        for level in self.bid_levels:
            price = float(level[0]) - impact
            qty = float(level[1])
            worst_price = price

            if remaining <= 0:
                break

            fill_qty = min(remaining, qty)
            total_cost += price * fill_qty
            total_filled += fill_qty
            remaining -= fill_qty

        # If order exceeds total resting depth, fill remainder at worst level
        if remaining > 0 and total_filled > 0:
            total_cost += worst_price * remaining
            total_filled += remaining
        elif remaining > 0:
            # Entire book is empty (degenerate); use impacted_bid
            return self.impacted_bid

        return total_cost / total_filled

    # ------------------------------------------------------------------
    # Derived prices
    # ------------------------------------------------------------------

    @property
    def has_l2(self) -> bool:
        """True if L2 depth data is available for this tick."""
        return len(self.bid_levels) > 1

    @property
    def impacted_bid(self) -> float:
        """Effective best bid after subtracting cumulative permanent impact."""
        return self.raw_bid - self.cumulative_perm_impact

    @property
    def impacted_ask(self) -> float:
        """Effective best ask after permanent impact (informational)."""
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

    # ------------------------------------------------------------------
    # Impact application
    # ------------------------------------------------------------------

    def apply_permanent_impact(self, perm_impact: float) -> None:
        """
        Accumulate permanent price impact after a fill.

        perm_impact should be positive — it represents the price degradation
        in absolute price units (e.g., USD per BTC).
        """
        self.cumulative_perm_impact += perm_impact

    def __repr__(self) -> str:
        mode = "L2" if self.has_l2 else "L1"
        return (
            f"SimulatedBook({mode}, bid={self.raw_bid:.4f}, ask={self.raw_ask:.4f}, "
            f"perm_impact={self.cumulative_perm_impact:.6f})"
        )
