from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from polymarket_terminal.credentials import Credentials as Credentials


class ConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    MARKET_DATA_ONLY = "market data only"
    ERROR = "error"


UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class AccountSummary:
    current_balance: Decimal | None = None
    buying_power: Decimal | None = None
    asset_notional: Decimal | None = None
    open_orders_count: int = 0
    total_estimated_pnl: Decimal | None = None
    total_estimated_pnl_percent: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PositionRow:
    market: str = UNAVAILABLE
    market_slug: str = UNAVAILABLE
    outcome: str = UNAVAILABLE
    direction: str = UNAVAILABLE
    net_contracts: Decimal | None = None
    cost_basis: Decimal | None = None
    current_value: Decimal | None = None
    estimated_pnl: Decimal | None = None
    estimated_pnl_percent: Decimal | None = None
    realized_pnl: Decimal | None = None
    last_updated: str = UNAVAILABLE


@dataclass(frozen=True, slots=True)
class MarketSummary:
    title: str = UNAVAILABLE
    slug: str = UNAVAILABLE
    active: str = UNAVAILABLE
    outcomes: tuple[str, ...] = ()
    live: bool = False
    event_title: str = UNAVAILABLE


@dataclass(frozen=True, slots=True)
class OrderBookSummary:
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    bid_size: Decimal | None = None
    ask_size: Decimal | None = None
    last_update_time: str = UNAVAILABLE


@dataclass(frozen=True, slots=True)
class OrderDraft:
    market_slug: str
    market_title: str
    outcome: str
    side_label: str
    official_intent: str
    limit_price: Decimal
    quantity: Decimal
    time_in_force: str
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    bbo_time: str = UNAVAILABLE


@dataclass(frozen=True, slots=True)
class OrderPreview:
    draft: OrderDraft
    payload: MappingProxyType[str, Any]
    fees_or_cost: str = UNAVAILABLE


@dataclass(frozen=True, slots=True)
class SubmittedOrder:
    order_id: str
    status: str


@dataclass(frozen=True, slots=True)
class OpenOrderRow:
    order_id: str = UNAVAILABLE
    market: str = UNAVAILABLE
    market_slug: str = UNAVAILABLE
    outcome: str = UNAVAILABLE
    side: str = UNAVAILABLE
    price: Decimal | None = None
    quantity: Decimal | None = None
    filled_quantity: Decimal | None = None
    remaining_quantity: Decimal | None = None
    status: str = UNAVAILABLE
    created_time: str = UNAVAILABLE


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    account: AccountSummary = field(default_factory=AccountSummary)
    positions: tuple[PositionRow, ...] = ()
    open_orders: tuple[OpenOrderRow, ...] = ()
    selected_market: MarketSummary | None = None
    order_book: OrderBookSummary = field(default_factory=OrderBookSummary)
