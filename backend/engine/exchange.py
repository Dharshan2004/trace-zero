"""
Simulated matching engine with L2 book-walk and network latency simulation.

Impact model
------------
L2 mode (bid_levels available):
    fill_price = walk_book(qty)         — exact multi-level slippage
    perm_impact = gamma * qty           — same permanent impact model

L1 mode (fallback):
    temp_impact = epsilon*sign + (eta/tau)*qty
    fill_price  = impacted_bid - temp_impact

Latency simulation
------------------
When latency_ms > 0, orders are not filled immediately. Instead:
  1. execute() records the order as "pending" with a target fill timestamp.
  2. The runner calls apply_pending_fills(event) on each tick.
  3. When the current event's timestamp reaches the target, the fill is
     evaluated against the book state AT THAT TICK — modeling execution
     risk (the price may have moved adversely during transit).
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Optional

from backend.engine.book import SimulatedBook
from backend.engine.order import Fill, Order

if TYPE_CHECKING:
    from backend.models.almgren_chriss import AlmgrenChriss


class SimulatedExchange:
    """
    Matching engine that executes sell orders with AC market impact.

    Usage (no latency)
    ------------------
        exchange = SimulatedExchange(ac_model)
        exchange.update_book(event)          # feed each replay event
        fill = exchange.execute(order)       # returns Fill immediately

    Usage (with latency)
    --------------------
        exchange = SimulatedExchange(ac_model, latency_ms=30.0)
        exchange.update_book(event)
        exchange.execute(order)              # returns None; fill is pending
        new_fills = exchange.apply_pending_fills(event)  # call each tick
    """

    def __init__(self, ac_model: "AlmgrenChriss", latency_ms: float = 0.0) -> None:
        self.book = SimulatedBook()
        self.ac = ac_model
        self.latency_ms = latency_ms
        self.fills: list[Fill] = []
        self.shares_remaining: float = ac_model.config.shares

        self._arrival_price: Optional[float] = None

        # Pending orders waiting for latency window to elapse:
        # deque of (target_timestamp_ms, Order)
        self._pending: deque[tuple[float, Order]] = deque()

    # ------------------------------------------------------------------
    # Book updates
    # ------------------------------------------------------------------

    def update_book(self, event: dict) -> None:
        """Push a new replay event into the book."""
        self.book.update(event)
        if self._arrival_price is None:
            self._arrival_price = self.book.mid

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    def execute(self, order: Order) -> Optional[Fill]:
        """
        Execute a sell order.

        If latency_ms == 0  → fill immediately, return Fill.
        If latency_ms >  0  → enqueue as pending, return None.
                              Call apply_pending_fills() each tick.
        """
        if self._arrival_price is None:
            self._arrival_price = self.book.raw_ask if self.book.raw_ask > 0 else 1.0

        if self.latency_ms <= 0:
            return self._fill_order(order)

        # Schedule for execution at order.timestamp_ms + latency_ms
        target_ts = order.timestamp_ms + self.latency_ms
        self._pending.append((target_ts, order))
        return None

    def apply_pending_fills(self, event: dict) -> list[Fill]:
        """
        Check pending orders against the current event timestamp and
        execute any that have passed their latency window.

        Call this on every tick after update_book().

        Returns
        -------
        list[Fill]
            Any fills that were executed this tick.
        """
        current_ts = float(event.get("timestamp_ms", 0))
        executed: list[Fill] = []

        while self._pending and self._pending[0][0] <= current_ts:
            _target_ts, order = self._pending.popleft()
            fill = self._fill_order(order)
            executed.append(fill)

        return executed

    # ------------------------------------------------------------------
    # Internal fill logic
    # ------------------------------------------------------------------

    def _fill_order(self, order: Order) -> Fill:
        """
        Compute and record a fill against the current book state.

        Fill price determination:
        - L2 mode: walk_book() consumes depth levels for exact slippage
        - L1 mode: analytical temp-impact formula (epsilon + eta/tau * qty)

        In L2 mode, temp_impact is measured as the book-walk premium over
        the raw best bid (i.e., how far the order walked into the book).
        """
        qty = order.qty

        if self.book.has_l2:
            # L2: exact slippage from consuming resting depth
            walk_price = self.book.walk_book(qty)
            fill_price = max(walk_price, 0.0)
            # temp_impact = how far we walked below impacted_bid
            temp_impact = max(self.book.impacted_bid - fill_price, 0.0)
        else:
            # L1: analytical AC temporary impact
            temp_impact = self.ac.temporaryImpact(qty)
            effective_bid = self.book.impacted_bid
            fill_price = max(effective_bid - temp_impact, 0.0)

        # Permanent impact: linear in qty (same regardless of L1/L2 mode)
        perm_impact = self.ac.permanentImpact(qty)
        self.book.apply_permanent_impact(perm_impact)

        # Slippage in basis points vs arrival price
        arrival = self._arrival_price or 1.0
        slippage_bps = (arrival - fill_price) / arrival * 10_000.0 if arrival > 0 else 0.0

        self.shares_remaining = max(self.shares_remaining - qty, 0.0)

        fill = Fill(
            order=order,
            fill_price=fill_price,
            qty_filled=qty,
            timestamp_ms=order.timestamp_ms,
            slippage_bps=slippage_bps,
            temp_impact=temp_impact,
            perm_impact=perm_impact,
        )
        self.fills.append(fill)
        return fill

    # ------------------------------------------------------------------
    # Aggregate metrics
    # ------------------------------------------------------------------

    @property
    def arrival_price(self) -> float:
        return self._arrival_price or 0.0

    @property
    def avg_fill_price(self) -> float:
        """Volume-weighted average fill price across all fills."""
        if not self.fills:
            return 0.0
        total_qty = sum(f.qty_filled for f in self.fills)
        if total_qty <= 0:
            return 0.0
        return sum(f.fill_price * f.qty_filled for f in self.fills) / total_qty

    @property
    def implementation_shortfall_bps(self) -> float:
        """IS = (arrival_price - VWAP) / arrival_price * 10_000."""
        arrival = self.arrival_price
        vwap = self.avg_fill_price
        if arrival <= 0:
            return 0.0
        return (arrival - vwap) / arrival * 10_000.0

    @property
    def total_qty_filled(self) -> float:
        return sum(f.qty_filled for f in self.fills)

    def __repr__(self) -> str:
        return (
            f"SimulatedExchange(fills={len(self.fills)}, "
            f"vwap={self.avg_fill_price:.4f}, "
            f"IS={self.implementation_shortfall_bps:.2f}bps, "
            f"latency={self.latency_ms}ms)"
        )
