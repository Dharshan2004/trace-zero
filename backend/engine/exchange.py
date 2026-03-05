"""
Simulated matching engine applying Almgren-Chriss market impact.

Each strategy gets its own SimulatedExchange instance so that their
cumulative permanent impact does not interfere with each other.

Impact model
------------
Temporary impact (per trade):
    temp_impact = epsilon * sign(qty) + (eta / tau) * qty
    This is per-trade cost, applied at fill time and does not persist.

Permanent impact (cumulative):
    perm_impact = gamma * qty
    Permanently degrades the book for this strategy going forward.

Fill price (sell order):
    fill_price = impacted_bid - temp_impact
    (impacted_bid already includes all prior permanent impact)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from backend.engine.book import SimulatedBook
from backend.engine.order import Fill, Order

if TYPE_CHECKING:
    from backend.models.almgren_chriss import AlmgrenChriss


class SimulatedExchange:
    """
    Matching engine that executes sell orders with AC market impact.

    Usage
    -----
        exchange = SimulatedExchange(ac_model)
        exchange.update_book(event)          # feed each replay event
        fill = exchange.execute(order)       # submit a sell order
    """

    def __init__(self, ac_model: "AlmgrenChriss") -> None:
        self.book = SimulatedBook()
        self.ac = ac_model
        self.fills: list[Fill] = []
        self.shares_remaining: float = ac_model.config.shares

        # Arrival price = first mid seen; set on first update_book call.
        self._arrival_price: Optional[float] = None

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

    def execute(self, order: Order) -> Fill:
        """
        Execute a sell order and return a Fill.

        Steps
        -----
        1. Compute temporary impact using rate-based formula.
        2. Compute fill price = impacted_bid - temp_impact.
        3. Compute permanent impact = gamma * qty.
        4. Apply permanent impact to the book (degrades future bids).
        5. Deduct qty from shares_remaining.
        6. Compute slippage vs arrival price.
        7. Record and return Fill.
        """
        if self._arrival_price is None:
            # Edge case: no book update yet — use the raw ask as proxy
            self._arrival_price = self.book.raw_ask if self.book.raw_ask > 0 else 1.0

        qty = order.qty

        # Temporary impact: epsilon*sign + (eta/tau)*qty
        # temporaryImpact() uses self.tau internally
        temp_impact = self.ac.temporaryImpact(qty)

        # Fill price: effective bid minus temporary impact
        effective_bid = self.book.impacted_bid
        fill_price = max(effective_bid - temp_impact, 0.0)

        # Permanent impact: linear in qty
        perm_impact = self.ac.permanentImpact(qty)

        # Apply permanent impact to this book instance
        self.book.apply_permanent_impact(perm_impact)

        # Slippage in basis points vs arrival price
        arrival = self._arrival_price
        if arrival > 0:
            slippage_bps = (arrival - fill_price) / arrival * 10_000.0
        else:
            slippage_bps = 0.0

        # Deduct from remaining inventory
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
        total_value = sum(f.fill_price * f.qty_filled for f in self.fills)
        return total_value / total_qty

    @property
    def implementation_shortfall_bps(self) -> float:
        """
        Implementation shortfall in basis points:
            IS = (arrival_price - VWAP) / arrival_price * 10_000
        """
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
            f"IS={self.implementation_shortfall_bps:.2f}bps)"
        )
