from decimal import Decimal

from polymarket_terminal.adapters import (
    adapt_account_summary,
    adapt_close_position_response,
    adapt_open_orders,
    adapt_order_book,
    adapt_position,
    adapt_positions,
    adapt_search_markets,
)


class Obj:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


def test_positions_map_dict_style_nonzero_long() -> None:
    row = adapt_position(
        {
            "marketMetadata": {"title": "Market A", "slug": "market-a"},
            "outcome": "Yes",
            "direction": "Long",
            "netPositionDecimal": "3",
            "cashValue": "2.10",
            "cost": "1.50",
            "realizedPnl": "0.25",
        }
    )
    assert row is not None
    assert row.market == "Market A"
    assert row.net_contracts == Decimal("3")
    assert row.estimated_pnl == Decimal("0.60")


def test_positions_response_map() -> None:
    rows = adapt_positions({"positions": {"asset-1": {"netPosition": "2"}}})
    assert len(rows) == 1
    assert rows[0].net_contracts == Decimal("2")
    assert rows[0].direction == "Long"


def test_negative_position_infers_short_direction() -> None:
    rows = adapt_positions([{"netPositionDecimal": "-2"}])
    assert len(rows) == 1
    assert rows[0].direction == "Short"


def test_object_style_short_is_not_sign_flipped() -> None:
    row = adapt_position(
        Obj(
            marketMetadata=Obj(title="Market B", slug="market-b"),
            outcome="No",
            direction="Short",
            netPositionDecimal="-4",
            cashValue="-1.00",
            cost="-2.00",
        )
    )
    assert row is not None
    assert row.net_contracts == Decimal("-4")
    assert row.estimated_pnl == Decimal("1.00")


def test_zero_position_filtered() -> None:
    rows = adapt_positions([{"netPositionDecimal": "0"}, {"netPositionDecimal": "1"}])
    assert len(rows) == 1


def test_missing_fields_are_unavailable_not_zero() -> None:
    row = adapt_position({"netPositionDecimal": "1"})
    assert row is not None
    assert row.market == "unavailable"
    assert row.current_value is None
    assert row.cost_basis is None
    assert row.estimated_pnl is None


def test_account_summary_totals() -> None:
    positions = adapt_positions(
        [
            {"netPositionDecimal": "1", "cashValue": "2", "cost": "1"},
            {"netPositionDecimal": "1", "cashValue": "1", "cost": "2"},
        ]
    )
    summary = adapt_account_summary({"currentBalance": 12.0, "buyingPower": 9.0}, positions, 2)
    assert summary.current_balance == Decimal("12")
    assert summary.buying_power == Decimal("9")
    assert summary.total_estimated_pnl == Decimal("0")
    assert summary.total_estimated_pnl_percent == Decimal("0")


def test_search_events_to_markets() -> None:
    rows = adapt_search_markets(
        {
            "events": [
                {
                    "live": True,
                    "title": "FURIA vs Team Falcons",
                    "markets": [
                        {
                            "title": "Market A",
                            "slug": "market-a",
                            "active": True,
                            "marketType": "moneyline",
                            "sportsMarketType": "moneyline",
                            "outcomes": '["Yes","No"]',
                            "marketSides": [
                                {"description": "FURIA", "long": True},
                                {"description": "Team Falcons", "long": False},
                            ],
                        },
                        {"title": "Market B", "slug": "market-b", "active": False},
                    ]
                }
            ]
        }
    )
    assert [row.slug for row in rows] == ["market-a", "market-b"]
    assert rows[0].live is True
    assert rows[0].outcomes == ("Yes", "No")
    assert rows[0].side_labels == ("FURIA", "Team Falcons")
    assert rows[0].market_type == "moneyline"
    assert rows[0].sports_market_type == "moneyline"
    assert rows[0].event_title == "FURIA vs Team Falcons"


def test_market_side_labels_use_structured_long_side_order() -> None:
    rows = adapt_search_markets(
        {
            "events": [
                {
                    "markets": [
                        {
                            "slug": "market-a",
                            "marketSides": [
                                {"description": "Team Liquid", "long": False},
                                {"description": "Dallas Fuel", "long": True},
                            ],
                        },
                    ]
                }
            ]
        }
    )
    assert rows[0].side_labels == ("Dallas Fuel", "Team Liquid")


def test_order_book_and_open_orders() -> None:
    book = adapt_order_book(
        {"bestBid": {"value": "0.44", "currency": "USD"}, "bestAsk": "0.56", "bidDepth": 7},
        {"transactTime": "now"},
    )
    assert book.best_bid == Decimal("0.44")
    assert book.ask_size is None
    assert book.last_update_time == "now"

    orders = adapt_open_orders({"orders": [{"id": "1", "price": {"value": "0.50"}}]})
    assert orders[0].order_id == "1"
    assert orders[0].price == Decimal("0.50")


def test_order_book_reads_market_detail_quote_fallback() -> None:
    book = adapt_order_book(
        {
            "bestBidQuote": {"value": "0.11", "currency": "USD"},
            "bestAskQuote": {"value": "0.22", "currency": "USD"},
        }
    )
    assert book.best_bid == Decimal("0.11")
    assert book.best_ask == Decimal("0.22")


def test_close_position_response_adapter() -> None:
    submitted = adapt_close_position_response({"id": "close-1", "executions": [{"id": "exec-1"}]})
    assert submitted.order_id == "close-1"
    assert submitted.status == "executions=1"
