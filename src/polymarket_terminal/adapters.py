from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from decimal import Decimal

from polymarket_terminal.models import (
    UNAVAILABLE,
    AccountSummary,
    MarketSummary,
    OpenOrderRow,
    OrderBookSummary,
    PositionRow,
    SubmittedOrder,
)
from polymarket_terminal.pricing import (
    calculate_estimated_pnl,
    calculate_pnl_percent,
    calculate_total_estimated_pnl,
    calculate_total_pnl_percent,
    parse_decimal,
)


def read_field(raw: object, *names: str) -> object | None:
    for name in names:
        if isinstance(raw, Mapping) and name in raw:
            value: object = raw[name]
            return value
        if not isinstance(raw, Mapping) and hasattr(raw, name):
            attr: object = getattr(raw, name)
            return attr
    return None


def read_nested(raw: object, *path: str) -> object | None:
    current: object | None = raw
    for name in path:
        if current is None:
            return None
        current = read_field(current, name)
    return current


def read_text(raw: object, *names: str) -> str:
    value = read_field(raw, *names)
    if value is None:
        return UNAVAILABLE
    text = str(value)
    return text if text else UNAVAILABLE


def read_decimal(raw: object, *names: str) -> Decimal | None:
    value = read_field(raw, *names)
    if isinstance(value, Mapping) and "value" in value:
        value = value["value"]
    return parse_decimal(value)


def read_bool(raw: object, *names: str) -> bool:
    value = read_field(raw, *names)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() == "true"
    return False


def read_outcomes(raw: object) -> tuple[str, ...]:
    outcomes_raw = read_field(raw, "outcomes", "outcomeNames", "tokens")
    single_outcome = read_field(raw, "outcome")
    if isinstance(outcomes_raw, str):
        try:
            parsed = json.loads(outcomes_raw)
        except json.JSONDecodeError:
            return (outcomes_raw,) if outcomes_raw else ()
        if isinstance(parsed, list):
            return tuple(str(item) for item in parsed)
        return ()
    if isinstance(outcomes_raw, Iterable) and not isinstance(outcomes_raw, (bytes, Mapping)):
        return tuple(str(item) for item in outcomes_raw)
    if single_outcome is not None:
        return (str(single_outcome),)
    market_sides = read_field(raw, "marketSides")
    if isinstance(market_sides, Iterable) and not isinstance(market_sides, (str, bytes, Mapping)):
        labels = [read_text(side, "description") for side in market_sides]
        return tuple(label for label in labels if label != UNAVAILABLE)
    return ()


def read_market_side_labels(raw: object) -> tuple[str, ...]:
    market_sides = read_field(raw, "marketSides")
    if not isinstance(market_sides, Iterable) or isinstance(
        market_sides,
        (str, bytes, Mapping),
    ):
        return ()
    long_labels: list[str] = []
    short_labels: list[str] = []
    fallback_labels: list[str] = []
    for side in market_sides:
        label = read_text(side, "description")
        if label == UNAVAILABLE:
            continue
        fallback_labels.append(label)
        if read_bool(side, "long"):
            long_labels.append(label)
        else:
            short_labels.append(label)
    ordered_labels = long_labels + short_labels
    return tuple(ordered_labels or fallback_labels)


def adapt_market(
    raw: object,
    live: bool | None = None,
    event_title: str = UNAVAILABLE,
) -> MarketSummary:
    wrapped = read_field(raw, "market")
    if wrapped is not None:
        raw = wrapped
    is_live = read_bool(raw, "live") if live is None else live or read_bool(raw, "live")
    return MarketSummary(
        title=read_text(raw, "title", "question", "name"),
        slug=read_text(raw, "slug", "marketSlug", "market_slug"),
        active=read_text(raw, "active", "isActive", "status"),
        outcomes=read_outcomes(raw),
        side_labels=read_market_side_labels(raw),
        market_type=read_text(raw, "marketType", "type"),
        sports_market_type=read_text(raw, "sportsMarketType"),
        live=is_live,
        event_title=event_title,
    )


def adapt_search_markets(raw: object) -> tuple[MarketSummary, ...]:
    events = read_field(raw, "events")
    if not isinstance(events, Iterable) or isinstance(events, (str, bytes, Mapping)):
        return ()
    markets: list[MarketSummary] = []
    for event in events:
        event_live = read_bool(event, "live")
        event_title = read_text(event, "title", "question", "name")
        event_markets = read_field(event, "markets")
        if isinstance(event_markets, Iterable) and not isinstance(
            event_markets,
            (str, bytes, Mapping),
        ):
            markets.extend(
                adapt_market(market, live=event_live, event_title=event_title)
                for market in event_markets
            )
    return tuple(markets)


def adapt_order_book(bbo: object, book: object | None = None) -> OrderBookSummary:
    bid_size = read_decimal(bbo, "bidSize", "bidDepth")
    ask_size = read_decimal(bbo, "askSize", "askDepth")
    last_update = (
        read_text(book, "transactTime", "lastUpdated") if book is not None else UNAVAILABLE
    )
    return OrderBookSummary(
        best_bid=read_decimal(bbo, "bestBid", "bestBidQuote"),
        best_ask=read_decimal(bbo, "bestAsk", "bestAskQuote"),
        bid_size=bid_size,
        ask_size=ask_size,
        last_update_time=last_update,
    )


def adapt_position(raw: object) -> PositionRow | None:
    metadata = read_field(raw, "marketMetadata", "market_metadata", "market")
    market = read_text(metadata, "title", "question", "name")
    market_slug = read_text(raw, "marketSlug", "market_slug", "slug")
    if market_slug == UNAVAILABLE:
        market_slug = read_text(metadata, "slug", "marketSlug", "market_slug")
    outcome = read_text(raw, "outcome", "outcomeName", "asset")
    direction = read_text(raw, "direction", "side", "positionSide")
    net_contracts = read_decimal(
        raw,
        "netPositionDecimal",
        "net_position_decimal",
        "netPosition",
        "size",
        "quantity",
    )
    if net_contracts == Decimal("0"):
        return None
    current_value = read_decimal(raw, "cashValue", "currentValue", "value")
    cost_basis = read_decimal(raw, "cost", "costBasis", "cost_basis")
    estimated = calculate_estimated_pnl(current_value, cost_basis)
    return PositionRow(
        market=market,
        market_slug=market_slug,
        outcome=outcome,
        direction=direction,
        net_contracts=net_contracts,
        cost_basis=cost_basis,
        current_value=current_value,
        estimated_pnl=estimated,
        estimated_pnl_percent=calculate_pnl_percent(estimated, cost_basis),
        realized_pnl=read_decimal(raw, "realizedPnl", "realizedPnL", "realized", "realized_pnl"),
        last_updated=read_text(raw, "updatedAt", "lastUpdated", "timestamp"),
    )


def adapt_positions(raw_positions: object) -> tuple[PositionRow, ...]:
    if isinstance(raw_positions, Mapping):
        positions = read_field(raw_positions, "positions")
        if isinstance(positions, Mapping):
            raw_positions = positions.values()
        elif isinstance(positions, Iterable) and not isinstance(positions, (str, bytes)):
            raw_positions = positions
        else:
            raw_positions = raw_positions.values()
    if not isinstance(raw_positions, Iterable) or isinstance(raw_positions, (str, bytes)):
        return ()
    rows = [adapt_position(raw) for raw in raw_positions]
    return tuple(row for row in rows if row is not None)


def adapt_account_summary(
    raw_balance: object,
    positions: tuple[PositionRow, ...],
    open_count: int,
) -> AccountSummary:
    pnls = [position.estimated_pnl for position in positions]
    costs = [position.cost_basis for position in positions]
    return AccountSummary(
        current_balance=read_decimal(raw_balance, "currentBalance", "balance", "cash"),
        buying_power=read_decimal(raw_balance, "buyingPower", "buying_power", "available"),
        asset_notional=read_decimal(raw_balance, "assetNotional", "asset_notional"),
        open_orders_count=open_count,
        total_estimated_pnl=calculate_total_estimated_pnl(pnls),
        total_estimated_pnl_percent=calculate_total_pnl_percent(pnls, costs),
    )


def first_balance(raw_balance_response: object) -> object:
    balances = read_field(raw_balance_response, "balances")
    if isinstance(balances, Iterable) and not isinstance(balances, (str, bytes, Mapping)):
        return next(iter(balances), {})
    return raw_balance_response


def adapt_open_order(raw: object) -> OpenOrderRow:
    return OpenOrderRow(
        order_id=read_text(raw, "id", "orderId", "order_id"),
        market=read_text(raw, "market", "marketTitle", "title"),
        market_slug=read_text(raw, "marketSlug", "market_slug", "slug"),
        outcome=read_text(raw, "outcome", "outcomeName"),
        side=read_text(raw, "side", "intent"),
        price=read_decimal(raw, "price", "limitPrice", "limit_price"),
        quantity=read_decimal(raw, "quantity", "size"),
        filled_quantity=read_decimal(raw, "filledQuantity", "filled_quantity", "filled"),
        remaining_quantity=read_decimal(
            raw,
            "remainingQuantity",
            "remaining_quantity",
            "remaining",
        ),
        status=read_text(raw, "status", "state"),
        created_time=read_text(raw, "createdAt", "created_time", "createdTime"),
    )


def adapt_open_orders(raw: object) -> tuple[OpenOrderRow, ...]:
    orders = read_field(raw, "orders")
    if isinstance(orders, Iterable) and not isinstance(orders, (str, bytes, Mapping)):
        return tuple(adapt_open_order(order) for order in orders)
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, Mapping)):
        return tuple(adapt_open_order(order) for order in raw)
    return ()


def adapt_close_position_response(raw: object) -> SubmittedOrder:
    executions = read_field(raw, "executions")
    execution_count = len(executions) if isinstance(executions, list) else 0
    return SubmittedOrder(
        order_id=read_text(raw, "id", "orderId", "order_id"),
        status=f"executions={execution_count}" if execution_count else UNAVAILABLE,
    )


def preview_fees_or_cost(raw: object) -> str:
    value = read_field(raw, "fee", "fees", "cost", "estimatedCost")
    if value is None:
        return UNAVAILABLE
    return str(value)
