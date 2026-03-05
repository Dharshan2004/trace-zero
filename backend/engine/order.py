"""
Order and Fill dataclasses for the simulated exchange.

These are the core value objects passed between strategies, the exchange,
and the result aggregation layer.
"""

from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class Order:
    """
    A sell order submitted by a strategy to the simulated exchange.

    Attributes
    ----------
    strategy_name : str
        Identifier of the strategy that generated this order.
    qty : float
        Number of shares to sell (positive = sell).
    timestamp_ms : int
        Simulation timestamp at which the order is placed.
    order_id : str
        Unique identifier, auto-generated from nanosecond wall clock if
        not provided explicitly.
    """
    strategy_name: str
    qty: float
    timestamp_ms: int
    order_id: str = field(default_factory=lambda: str(time.time_ns()))


@dataclass
class Fill:
    """
    Result of executing an Order against the simulated book.

    Attributes
    ----------
    order : Order
        The original order that was filled.
    fill_price : float
        Effective execution price after impact.
    qty_filled : float
        Quantity actually filled (matches order.qty in this simulator).
    timestamp_ms : int
        Simulation timestamp of the fill.
    slippage_bps : float
        (arrival_price - fill_price) / arrival_price * 10_000.
        Arrival price is determined by the exchange at fill time.
    temp_impact : float
        Temporary price impact applied to this fill (price units).
    perm_impact : float
        Permanent price impact applied to this fill (price units).
    """
    order: Order
    fill_price: float
    qty_filled: float
    timestamp_ms: int
    slippage_bps: float
    temp_impact: float
    perm_impact: float
