import os
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6 import QtCore, QtWidgets

from polymarket_terminal.models import AccountSummary, MarketSummary, OrderBookSummary, PositionRow
from polymarket_terminal.quick_trade import (
    DETAIL_WINDOW_SIZE,
    SUMMARY_WINDOW_SIZE,
    QuickTradeWindow,
    cashout_side_for_position,
    extract_slug_from_query,
    meaningful_slug_tokens,
    parse_url_search_parts,
    rank_markets_by_tokens,
    search_candidates_from_query,
)
from polymarket_terminal.quick_trade_flow import QuickTradeSide


@pytest.fixture
def app() -> QtWidgets.QApplication:
    existing = QtWidgets.QApplication.instance()
    if existing is not None:
        return existing
    return QtWidgets.QApplication([])


def test_submit_disabled_until_preview(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    assert not window.submit_button.isEnabled()
    assert not window.submit_button.autoDefault()
    assert not window.submit_button.isDefault()
    window.close()


def test_positions_summary_uses_smaller_window_and_details_expands(
    app: QtWidgets.QApplication,
) -> None:
    window = QuickTradeWindow()
    assert window.size() == SUMMARY_WINDOW_SIZE
    window.positions_detail_button.click()
    assert window.size() == DETAIL_WINDOW_SIZE
    window.positions_detail_button.click()
    assert window.size() == SUMMARY_WINDOW_SIZE
    window.close()


def test_market_box_uses_search_selection_for_lock(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    slugs: list[str] = []
    window.market_lock_requested.connect(slugs.append)
    assert window.search_input.placeholderText() == "Search game/team/market"
    assert window.lock_market_button.text() == "Lock market"
    assert window.selected_slug_input.isReadOnly()
    assert not hasattr(window, "market_slug_input")
    assert not hasattr(window, "market_details")
    window._lock_market_clicked()
    assert slugs == []
    assert "Select a search result first" in window.preview_text.toPlainText()
    window.show_search_results(
        (
            MarketSummary(
                title="FURIA vs Team Falcons",
                slug="aec-cs2-furia-fal-2026-06-21",
                active="True",
                side_labels=("FURIA", "Team Falcons"),
                sports_market_type="moneyline",
                live=True,
            ),
        )
    )
    item = window.search_results.item(0)
    assert item.text() == "LIVE | FURIA vs Team Falcons\naec-cs2-furia-fal-2026-06-21"
    assert item.data(QtCore.Qt.ItemDataRole.UserRole) == "aec-cs2-furia-fal-2026-06-21"
    assert not item.icon().isNull()
    assert "Type: Moneyline" in item.toolTip()
    assert "Sides: FURIA / Team Falcons" in item.toolTip()
    window._search_result_clicked(item)
    assert window.selected_slug_input.text() == "aec-cs2-furia-fal-2026-06-21"
    window._lock_market_clicked()
    assert slugs == ["aec-cs2-furia-fal-2026-06-21"]
    window.close()


def test_trade_side_combo_only_shows_buy_options_and_market_side_labels(
    app: QtWidgets.QApplication,
) -> None:
    window = QuickTradeWindow()
    assert [window.side_combo.itemText(index) for index in range(window.side_combo.count())] == [
        "Buy Yes",
        "Buy No",
    ]

    window.show_market(
        MarketSummary(
            title="Dallas Fuel vs Team Liquid",
            slug="ow-dal-tl-2026-06-21",
            side_labels=("Dallas Fuel", "Team Liquid"),
            sports_market_type="moneyline",
        ),
        OrderBookSummary(best_bid=Decimal("0.40"), best_ask=Decimal("0.60")),
    )
    assert [window.side_combo.itemText(index) for index in range(window.side_combo.count())] == [
        "Buy Dallas Fuel Win",
        "Buy Team Liquid Win",
    ]
    assert [window.side_combo.itemData(index) for index in range(window.side_combo.count())] == [
        QuickTradeSide.BUY_YES.value,
        QuickTradeSide.BUY_NO.value,
    ]
    assert all(
        "Sell" not in window.side_combo.itemText(index)
        for index in range(window.side_combo.count())
    )
    window.close()


def test_non_moneyline_market_can_use_specific_side_labels(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    window.show_market(
        MarketSummary(
            title="Tournament winner",
            slug="winner-market",
            side_labels=("Vitality", "NAVI"),
        ),
        OrderBookSummary(best_bid=Decimal("0.40"), best_ask=Decimal("0.60")),
    )
    assert [window.side_combo.itemText(index) for index in range(window.side_combo.count())] == [
        "Buy Vitality",
        "Buy NAVI",
    ]
    window.close()


def test_non_live_search_result_has_no_live_marker(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    window.show_search_results(
        (
            MarketSummary(
                title="Dallas Fuel vs Team Liquid",
                slug="ow-dal-tl-2026-06-21",
                live=False,
            ),
        )
    )
    item = window.search_results.item(0)
    assert item.text() == "Dallas Fuel vs Team Liquid\now-dal-tl-2026-06-21"
    assert item.icon().isNull()
    window.close()


def test_extract_slug_from_query_accepts_urls_and_plain_slugs() -> None:
    assert (
        extract_slug_from_query(
            "https://polymarket.com/esports/cs2/tesfed-league/cs2-mis-wraith-2026-06-21"
        )
        == "cs2-mis-wraith-2026-06-21"
    )
    assert extract_slug_from_query("cs2-mis-wraith-2026-06-21") == "cs2-mis-wraith-2026-06-21"


def test_search_candidates_from_url_prioritize_slug_and_team_terms() -> None:
    candidates = search_candidates_from_query(
        "https://polymarket.com/esports/cs2/tesfed-league/cs2-mis-wraith-2026-06-21"
    )
    assert candidates[0] == "cs2-mis-wraith-2026-06-21"
    assert "mis wraith" in candidates
    assert all("polymarket.com" not in candidate for candidate in candidates)


def test_url_search_parts_and_tokens() -> None:
    parts = parse_url_search_parts(
        "https://polymarket.com/esports/cs2/tesfed-league/cs2-mis-wraith-2026-06-21"
    )
    assert parts.category == "esports"
    assert parts.subcategory == "cs2"
    assert parts.series_slug == "tesfed-league"
    assert parts.market_slug == "cs2-mis-wraith-2026-06-21"
    assert meaningful_slug_tokens(parts.market_slug) == ("mis", "wraith")


def test_rank_markets_by_tokens_handles_partial_team_names() -> None:
    markets = (
        MarketSummary(title="Vitality", slug="tec-cs2-iemcologne-winner-2026-06-21-vital"),
        MarketSummary(
            title="Misa Esports - WRAITH PCIFIC",
            slug="cs2-misa-wraith-2026-06-21",
        ),
    )
    ranked = rank_markets_by_tokens(markets, ("mis", "wraith"))
    assert ranked[0].title == "Misa Esports - WRAITH PCIFIC"


def test_balance_panel_displays_safe_fields(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    window.show_balance(
        AccountSummary(current_balance=Decimal("12.34"), buying_power=Decimal("10"))
    )
    assert "Current balance: $12.34" in window.balance_label.text()
    assert "Buying Power: $10.00" in window.buying_power_label.text()
    assert "Last refresh:" in window.balance_time_label.text()
    window.close()


def test_realtime_refresh_toggle_controls_timer(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    refreshes: list[bool] = []
    window.refresh_account_requested.connect(lambda: refreshes.append(True))
    assert window.refresh_account_button.text() == "Refresh all"
    assert not window.realtime_refresh_toggle.isChecked()
    assert not window._realtime_refresh_timer.isActive()
    window.realtime_refresh_toggle.setChecked(True)
    assert window._realtime_refresh_timer.isActive()
    assert refreshes == [True]
    window.realtime_refresh_toggle.setChecked(False)
    assert not window._realtime_refresh_timer.isActive()
    window.close()


def test_positions_panel_displays_rows(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    window.show_positions(
        (
            PositionRow(
                market="FURIA vs Team Falcons",
                market_slug="aec-cs2-furia-fal-2026-06-21",
                outcome="FURIA",
                direction="Long",
                net_contracts=Decimal("10"),
                current_value=Decimal("1.20"),
                estimated_pnl=Decimal("0.20"),
            ),
        )
    )
    assert window.positions_table.rowCount() == 1
    assert window.positions_table.columnCount() == 1
    summary = window.positions_table.item(0, 0).text()
    assert "FURIA vs Team Falcons" in summary
    assert "Value $1.20" in summary
    assert "PnL $0.20" in summary

    window.positions_detail_button.click()
    headers = [
        window.positions_table.horizontalHeaderItem(index).text()
        for index in range(window.positions_table.columnCount())
    ]
    assert headers == ["Market", "Value", "PnL", "Outcome", "Side", "Net"]
    assert window.positions_table.item(0, 0).text() == "FURIA vs Team Falcons"
    assert window.positions_table.item(0, 1).text() == "$1.20"
    assert window.positions_table.item(0, 2).text() == "$0.20"
    assert window.positions_table.item(0, 3).text() == "FURIA"
    assert window.positions_table.item(0, 5).text() == "10"
    window.close()


def test_cashout_button_emits_selected_position_slug(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    slugs: list[str] = []
    window.cashout_requested.connect(slugs.append)
    window.show_positions(
        (
            PositionRow(
                market="FURIA vs Team Falcons",
                market_slug="aec-cs2-furia-fal-2026-06-21",
                outcome="FURIA",
                net_contracts=Decimal("10"),
            ),
        )
    )
    assert not window.cashout_button.isEnabled()
    window.positions_table.selectRow(0)
    assert window.cashout_button.isEnabled()
    window.cashout_amount_input.setText("2.50")
    assert window.cashout_amount_input.text() == "2.50"
    window.cashout_button.click()
    assert slugs == ["aec-cs2-furia-fal-2026-06-21"]
    window.close()


def test_cashout_side_inferred_from_position_direction() -> None:
    assert (
        cashout_side_for_position(PositionRow(direction="Long"))
        == QuickTradeSide.SELL_YES
    )
    assert (
        cashout_side_for_position(PositionRow(direction="Short"))
        == QuickTradeSide.SELL_NO
    )
    assert cashout_side_for_position(PositionRow(direction="unavailable")) is None


def test_draft_from_inputs_uses_locked_market_and_bbo(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    window.show_market(
        MarketSummary(title="Market A", slug="market-a", active="True", outcomes=("Yes", "No")),
        OrderBookSummary(best_bid=Decimal("0.40"), best_ask=Decimal("0.60")),
    )
    window.side_combo.setCurrentIndex(0)
    window.amount_input.setText("15.25")
    draft = window.draft_from_inputs()
    assert draft is not None
    assert draft.market_slug == "market-a"
    assert draft.dollar_amount == Decimal("15.25")
    assert draft.current_price == Decimal("0.60")
    window.close()


def test_missing_bbo_disables_preview(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    window.show_market(
        MarketSummary(title="Market A", slug="market-a", active="True", outcomes=("Yes", "No")),
        OrderBookSummary(),
    )
    window.amount_input.setText("10")
    assert window.draft_from_inputs() is None
    assert "Enter a manual limit price" in window.preview_text.toPlainText()
    assert not window.submit_button.isEnabled()
    window.close()


def test_missing_bbo_with_manual_price_builds_limit_draft(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    window.show_market(
        MarketSummary(title="Market A", slug="market-a", active="True", outcomes=("Yes", "No")),
        OrderBookSummary(),
    )
    window.amount_input.setText("10")
    window.manual_limit_price_input.setText("0.50")
    draft = window.draft_from_inputs()
    assert draft is not None
    assert draft.current_price == Decimal("0.50")
    assert draft.order_kind.value == "Limit"
    window.close()


def test_fill_manual_price_uses_ask_for_buy_side(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    window.show_market(
        MarketSummary(title="Market A", slug="market-a", active="True", outcomes=("Yes", "No")),
        OrderBookSummary(best_bid=Decimal("0.41"), best_ask=Decimal("0.59")),
    )
    window.side_combo.setCurrentIndex(0)
    window.fill_manual_limit_from_market_price()
    assert window.manual_limit_price_input.text() == "0.59"
    window.close()


def test_fill_manual_price_shows_error_when_bbo_missing(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    window.show_market(
        MarketSummary(title="Market A", slug="market-a", active="True", outcomes=("Yes", "No")),
        OrderBookSummary(),
    )
    window.fill_manual_limit_from_market_price()
    assert window.manual_limit_price_input.text() == ""
    assert "No current best ask" in window.preview_text.toPlainText()
    window.close()


def test_window_close_emits_disconnect(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    closed: list[bool] = []
    window.disconnected.connect(lambda: closed.append(True))
    window.close()
    assert closed == [True]


def test_disconnect_button_closes_once(app: QtWidgets.QApplication) -> None:
    window = QuickTradeWindow()
    closed: list[bool] = []
    window.disconnected.connect(lambda: closed.append(True))
    window.request_close()
    window.request_close()
    assert closed == [True]
