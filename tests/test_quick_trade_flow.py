import asyncio
from decimal import Decimal

import pytest

from polymarket_terminal.models import OrderBookSummary
from polymarket_terminal.quick_trade_flow import (
    DEFAULT_SLIPPAGE_TICKS,
    QuickOrderKind,
    QuickTradeDraft,
    QuickTradeFlow,
    QuickTradeSide,
    current_price_for_side,
    parse_trade_amount,
    should_cancel_unfilled_limit_order,
)


class FakeOrders:
    def __init__(self) -> None:
        self.preview_calls: list[dict[str, object]] = []
        self.create_calls: list[dict[str, object]] = []
        self.timeout_create = False
        self.create_response: dict[str, object] = {"id": "order-1", "status": "ORDER_STATE_FILLED"}

    async def preview(self, payload: dict[str, object]) -> dict[str, object]:
        self.preview_calls.append(payload)
        return {"cost": {"value": "10.00", "currency": "USD"}}

    async def create(self, payload: dict[str, object]) -> dict[str, object]:
        self.create_calls.append(payload)
        if self.timeout_create:
            raise TimeoutError
        return self.create_response


class FakeClient:
    def __init__(self) -> None:
        self.orders = FakeOrders()
        self.reconciled = 0
        self.refreshed = 0
        self.cancel_calls: list[tuple[str, str]] = []

    async def reconcile_after_unknown_order_state(self) -> None:
        self.reconciled += 1

    async def refresh_after_order_change(self) -> None:
        self.refreshed += 1

    async def cancel_order(self, market_slug: str, order_id: str) -> None:
        self.cancel_calls.append((market_slug, order_id))


def draft(side: QuickTradeSide = QuickTradeSide.BUY_YES) -> QuickTradeDraft:
    return QuickTradeDraft(
        market_slug="market-a",
        side=side,
        dollar_amount=Decimal("10.00"),
        current_price=Decimal("0.55"),
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
    )


@pytest.mark.parametrize(
    ("side", "intent"),
    [
        (QuickTradeSide.BUY_YES, "ORDER_INTENT_BUY_LONG"),
        (QuickTradeSide.SELL_YES, "ORDER_INTENT_SELL_LONG"),
        (QuickTradeSide.BUY_NO, "ORDER_INTENT_BUY_SHORT"),
        (QuickTradeSide.SELL_NO, "ORDER_INTENT_SELL_SHORT"),
    ],
)
def test_market_order_payload_for_all_sides(side: QuickTradeSide, intent: str) -> None:
    payload = QuickTradeFlow(FakeClient()).build_payload(draft(side))
    assert payload["marketSlug"] == "market-a"
    assert payload["intent"] == intent
    assert payload["type"] == "ORDER_TYPE_MARKET"
    assert payload["cashOrderQty"] == {"value": "10.00", "currency": "USD"}
    assert payload["manualOrderIndicator"] == "MANUAL_ORDER_INDICATOR_MANUAL"
    assert payload["synchronousExecution"] is True
    assert payload["slippageTolerance"] == {
        "currentPrice": {"value": "0.55", "currency": "USD"},
        "ticks": 5,
    }


def test_limit_fallback_payload_uses_manual_price_and_integer_quantity() -> None:
    payload = QuickTradeFlow(FakeClient()).build_payload(
        QuickTradeDraft(
            market_slug="market-a",
            side=QuickTradeSide.BUY_YES,
            dollar_amount=Decimal("10.00"),
            current_price=Decimal("0.40"),
            order_kind=QuickOrderKind.LIMIT,
        )
    )
    assert payload["type"] == "ORDER_TYPE_LIMIT"
    assert payload["price"] == {"value": "0.40", "currency": "USD"}
    assert payload["quantity"] == 25
    assert payload["tif"] == "TIME_IN_FORCE_GOOD_TILL_CANCEL"
    assert "cashOrderQty" not in payload


def limit_draft() -> QuickTradeDraft:
    return QuickTradeDraft(
        market_slug="market-a",
        side=QuickTradeSide.BUY_YES,
        dollar_amount=Decimal("10.00"),
        current_price=Decimal("0.40"),
        order_kind=QuickOrderKind.LIMIT,
    )


@pytest.mark.parametrize(
    "bad_draft",
    [
        QuickTradeDraft("", QuickTradeSide.BUY_YES, Decimal("1"), Decimal("0.5")),
        QuickTradeDraft("m", QuickTradeSide.BUY_YES, Decimal("0"), Decimal("0.5")),
        QuickTradeDraft("m", QuickTradeSide.BUY_YES, Decimal("1"), Decimal("0")),
        QuickTradeDraft("m", QuickTradeSide.BUY_YES, Decimal("1"), Decimal("1")),
        QuickTradeDraft("m", QuickTradeSide.BUY_YES, Decimal("1"), Decimal("0.5"), -1),
        QuickTradeDraft(
            "m",
            QuickTradeSide.BUY_YES,
            Decimal("0.01"),
            Decimal("0.50"),
            order_kind=QuickOrderKind.LIMIT,
        ),
    ],
)
def test_invalid_market_order_drafts_rejected(bad_draft: QuickTradeDraft) -> None:
    with pytest.raises(ValueError):
        QuickTradeFlow(FakeClient()).build_payload(bad_draft)


def test_auto_preview_does_not_create() -> None:
    client = FakeClient()
    flow = QuickTradeFlow(client)
    preview = asyncio.run(flow.preview_order(draft()))
    assert preview.fees_or_cost == "{'value': '10.00', 'currency': 'USD'}"
    assert len(client.orders.preview_calls) == 1
    assert client.orders.create_calls == []


def test_submit_uses_latest_preview_payload() -> None:
    client = FakeClient()
    flow = QuickTradeFlow(client)
    preview = asyncio.run(flow.preview_order(draft()))
    submitted = asyncio.run(flow.submit_previewed_order(preview))
    assert submitted.order_id == "order-1"
    assert len(client.orders.create_calls) == 1
    assert client.orders.create_calls[0]["marketSlug"] == "market-a"


def test_submit_cancels_unfilled_limit_order() -> None:
    client = FakeClient()
    client.orders.create_response = {"id": "order-1", "status": "ORDER_STATE_OPEN"}
    flow = QuickTradeFlow(client)
    preview = asyncio.run(flow.preview_order(limit_draft()))
    submitted = asyncio.run(flow.submit_previewed_order(preview))
    assert submitted.order_id == "order-1"
    assert submitted.status == "ORDER_STATE_OPEN; canceled unfilled limit order"
    assert client.cancel_calls == [("market-a", "order-1")]
    assert client.refreshed == 1


def test_submit_does_not_cancel_filled_limit_order() -> None:
    client = FakeClient()
    client.orders.create_response = {"id": "order-1", "status": "ORDER_STATE_FILLED"}
    flow = QuickTradeFlow(client)
    preview = asyncio.run(flow.preview_order(limit_draft()))
    submitted = asyncio.run(flow.submit_previewed_order(preview))
    assert submitted.status == "ORDER_STATE_FILLED"
    assert client.cancel_calls == []
    assert client.refreshed == 1


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("unavailable", True),
        ("ORDER_STATE_OPEN", True),
        ("ORDER_STATE_PENDING", True),
        ("ORDER_STATE_PARTIALLY_FILLED", True),
        ("ORDER_STATE_FILLED", False),
        ("ORDER_STATE_COMPLETED", False),
        ("ORDER_STATE_EXECUTED", False),
    ],
)
def test_unfilled_limit_cancel_status_detection(status: str, expected: bool) -> None:
    assert should_cancel_unfilled_limit_order(status) is expected


def test_stale_preview_rejected() -> None:
    flow = QuickTradeFlow(FakeClient())
    preview = asyncio.run(flow.preview_order(draft()))
    flow.invalidate_preview()
    with pytest.raises(ValueError):
        asyncio.run(flow.submit_previewed_order(preview))


def test_duplicate_submit_guard() -> None:
    flow = QuickTradeFlow(FakeClient())
    preview = asyncio.run(flow.preview_order(draft()))
    flow.submitting = True
    with pytest.raises(RuntimeError):
        asyncio.run(flow.submit_previewed_order(preview))


def test_timeout_reconciles_without_retry() -> None:
    client = FakeClient()
    client.orders.timeout_create = True
    flow = QuickTradeFlow(client)
    preview = asyncio.run(flow.preview_order(draft()))
    with pytest.raises(RuntimeError, match="Order state unknown"):
        asyncio.run(flow.submit_previewed_order(preview))
    assert len(client.orders.create_calls) == 1
    assert client.reconciled == 1


def test_amount_and_current_price_helpers() -> None:
    assert parse_trade_amount("10.25") == Decimal("10.25")
    assert parse_trade_amount("0") is None
    order_book = OrderBookSummary(best_bid=Decimal("0.40"), best_ask=Decimal("0.60"))
    assert current_price_for_side(QuickTradeSide.BUY_YES, order_book) == Decimal("0.60")
    assert current_price_for_side(QuickTradeSide.BUY_NO, order_book) == Decimal("0.60")
    assert current_price_for_side(QuickTradeSide.SELL_YES, order_book) == Decimal("0.40")
    assert current_price_for_side(QuickTradeSide.SELL_NO, order_book) == Decimal("0.40")
