from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol

from polymarket_terminal.adapters import preview_fees_or_cost, read_text
from polymarket_terminal.models import OrderBookSummary, SubmittedOrder
from polymarket_terminal.pricing import parse_decimal

DEFAULT_SLIPPAGE_TICKS = 5


class QuickTradeSide(StrEnum):
    BUY_YES = "Buy Yes"
    BUY_NO = "Buy No"
    SELL_YES = "Sell Yes"
    SELL_NO = "Sell No"


class QuickOrderKind(StrEnum):
    MARKET = "Market"
    LIMIT = "Limit"


SIDE_TO_INTENT: dict[QuickTradeSide, str] = {
    QuickTradeSide.BUY_YES: "ORDER_INTENT_BUY_LONG",
    QuickTradeSide.SELL_YES: "ORDER_INTENT_SELL_LONG",
    QuickTradeSide.BUY_NO: "ORDER_INTENT_BUY_SHORT",
    QuickTradeSide.SELL_NO: "ORDER_INTENT_SELL_SHORT",
}


class OrdersProtocol(Protocol):
    async def preview(self, payload: dict[str, Any]) -> object: ...

    async def create(self, payload: dict[str, Any]) -> object: ...


class TradingClientProtocol(Protocol):
    @property
    def orders(self) -> OrdersProtocol: ...

    async def reconcile_after_unknown_order_state(self) -> None: ...

    async def refresh_after_order_change(self) -> None: ...


@dataclass(frozen=True, slots=True)
class QuickTradeDraft:
    market_slug: str
    side: QuickTradeSide
    dollar_amount: Decimal
    current_price: Decimal
    slippage_ticks: int = DEFAULT_SLIPPAGE_TICKS
    order_kind: QuickOrderKind = QuickOrderKind.MARKET


@dataclass(frozen=True, slots=True)
class QuickTradePreview:
    draft: QuickTradeDraft
    payload: MappingProxyType[str, Any]
    fees_or_cost: str


@dataclass(slots=True)
class QuickTradeFlow:
    client: TradingClientProtocol
    preview: QuickTradePreview | None = None
    submitting: bool = False
    reconciliation_requested: bool = False

    def invalidate_preview(self) -> None:
        self.preview = None

    def build_payload(self, draft: QuickTradeDraft) -> dict[str, Any]:
        if not draft.market_slug:
            raise ValueError("Market slug is required")
        if draft.side not in SIDE_TO_INTENT:
            raise ValueError("Trade side is required")
        if not draft.dollar_amount.is_finite() or draft.dollar_amount <= Decimal("0"):
            raise ValueError("Dollar amount must be greater than 0")
        if (
            not draft.current_price.is_finite()
            or not Decimal("0") < draft.current_price < Decimal("1")
        ):
            raise ValueError("Current price must be greater than 0 and less than 1")
        if draft.slippage_ticks < 0:
            raise ValueError("Slippage ticks must be zero or greater")
        base_payload: dict[str, Any] = {
            "marketSlug": draft.market_slug,
            "intent": SIDE_TO_INTENT[draft.side],
            "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_MANUAL",
        }
        if draft.order_kind == QuickOrderKind.LIMIT:
            quantity = (draft.dollar_amount / draft.current_price).to_integral_value(
                rounding=ROUND_FLOOR
            )
            if quantity <= 0:
                raise ValueError("Dollar amount is too small for this limit price")
            return {
                **base_payload,
                "type": "ORDER_TYPE_LIMIT",
                "price": {"value": str(draft.current_price), "currency": "USD"},
                "quantity": int(quantity),
                "tif": "TIME_IN_FORCE_GOOD_TILL_CANCEL",
            }
        return {
            **base_payload,
            "type": "ORDER_TYPE_MARKET",
            "cashOrderQty": {"value": str(draft.dollar_amount), "currency": "USD"},
            "synchronousExecution": True,
            "slippageTolerance": {
                "currentPrice": {"value": str(draft.current_price), "currency": "USD"},
                "ticks": draft.slippage_ticks,
            },
        }

    async def preview_order(self, draft: QuickTradeDraft) -> QuickTradePreview:
        payload = self.build_payload(draft)
        raw_preview = await self.client.orders.preview({"request": deepcopy(payload)})
        self.preview = QuickTradePreview(
            draft=draft,
            payload=MappingProxyType(deepcopy(payload)),
            fees_or_cost=preview_fees_or_cost(raw_preview),
        )
        return self.preview

    async def submit_previewed_order(self, preview: QuickTradePreview) -> SubmittedOrder:
        if self.preview is not preview:
            raise ValueError("Preview is stale; preview the order again")
        if self.submitting:
            raise RuntimeError("Order submission already in progress")
        self.submitting = True
        try:
            raw = await self.client.orders.create(dict(preview.payload))
        except TimeoutError:
            self.reconciliation_requested = True
            await self.client.reconcile_after_unknown_order_state()
            raise RuntimeError("Order state unknown") from None
        finally:
            self.submitting = False
        await self.client.refresh_after_order_change()
        return SubmittedOrder(
            order_id=read_text(raw, "id", "orderId", "order_id"),
            status=read_text(raw, "status", "state"),
        )


def parse_trade_amount(value: str) -> Decimal | None:
    amount = parse_decimal(value)
    if amount is None or amount <= Decimal("0"):
        return None
    return amount


def current_price_for_side(side: QuickTradeSide, order_book: OrderBookSummary) -> Decimal | None:
    if side in {QuickTradeSide.BUY_YES, QuickTradeSide.BUY_NO}:
        return order_book.best_ask
    return order_book.best_bid
