from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlparse

from PySide6 import QtCore, QtGui, QtWidgets
from qasync import QEventLoop  # type: ignore[import-untyped]

from polymarket_terminal.auth import (
    authenticate_credentials,
    authenticate_with_prompt,
    safe_api_error_message,
    safe_market_error_message,
)
from polymarket_terminal.client import PolymarketClient
from polymarket_terminal.credentials import credentials_from_environment
from polymarket_terminal.models import (
    UNAVAILABLE,
    AccountSummary,
    MarketSummary,
    OrderBookSummary,
    PositionRow,
)
from polymarket_terminal.quick_trade_flow import (
    DEFAULT_SLIPPAGE_TICKS,
    QuickOrderKind,
    QuickTradeDraft,
    QuickTradeFlow,
    QuickTradePreview,
    QuickTradeSide,
    current_price_for_side,
    parse_trade_amount,
)

SUMMARY_WINDOW_SIZE = QtCore.QSize(960, 760)
DETAIL_WINDOW_SIZE = QtCore.QSize(1280, 760)


def live_search_icon() -> QtGui.QIcon:
    pixmap = QtGui.QPixmap(8, 28)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.fillRect(0, 0, 4, 28, QtGui.QColor("#d93025"))
    painter.end()
    return QtGui.QIcon(pixmap)


def market_type_label(market: MarketSummary) -> str:
    raw_type = (
        market.sports_market_type
        if market.sports_market_type != UNAVAILABLE
        else market.market_type
    )
    if raw_type == UNAVAILABLE:
        return UNAVAILABLE
    label = raw_type.replace("_", " ").replace("-", " ").strip()
    return label.title() if label else UNAVAILABLE


def is_moneyline_market(market: MarketSummary) -> bool:
    return "moneyline" in {
        market.market_type.casefold(),
        market.sports_market_type.casefold(),
    }


def buy_side_labels_for_market(market: MarketSummary) -> tuple[str, str]:
    labels = market.side_labels or market.outcomes
    if len(labels) >= 2:
        if is_moneyline_market(market):
            return (f"{labels[0]} Win", f"{labels[1]} Win")
        return (labels[0], labels[1])
    return ("Yes", "No")


def format_balance(value: object) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, Decimal):
        return f"${value.quantize(Decimal('0.01'))}"
    return f"${value}"


def cashout_side_for_position(position: PositionRow) -> QuickTradeSide | None:
    direction = position.direction.casefold()
    if "long" in direction:
        return QuickTradeSide.SELL_YES
    if "short" in direction:
        return QuickTradeSide.SELL_NO
    return None


def extract_slug_from_query(query: str) -> str:
    text = query.strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.path:
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            return parts[-1]
    return text.rsplit("/", 1)[-1].strip()


@dataclass(frozen=True, slots=True)
class UrlSearchParts:
    category: str = ""
    subcategory: str = ""
    series_slug: str = ""
    market_slug: str = ""


def parse_url_search_parts(query: str) -> UrlSearchParts:
    text = query.strip()
    parsed = urlparse(text)
    path = parsed.path if parsed.path else text
    parts = [part for part in path.split("/") if part]
    if not parts:
        return UrlSearchParts()
    return UrlSearchParts(
        category=parts[0] if len(parts) > 0 else "",
        subcategory=parts[1] if len(parts) > 1 else "",
        series_slug=parts[-2] if len(parts) > 1 else "",
        market_slug=parts[-1],
    )


def meaningful_slug_tokens(slug: str) -> tuple[str, ...]:
    ignored = {
        "cs2",
        "lol",
        "dota",
        "winner",
        "match",
        "league",
        "esports",
        "sports",
        "vs",
        "v",
    }
    tokens: list[str] = []
    for part in slug.casefold().split("-"):
        if not part or part in ignored or part.isdigit():
            continue
        if len(part) == 4 and part.startswith("20") and part.isdigit():
            continue
        tokens.append(part)
    return tuple(tokens)


def search_candidates_from_query(query: str) -> tuple[str, ...]:
    text = query.strip()
    slug = extract_slug_from_query(text)
    candidates: list[str] = []
    parsed = urlparse(text)
    text_candidate = "" if parsed.scheme or parsed.netloc else text
    for candidate in (slug, text_candidate):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    parts = slug.split("-")
    if len(parts) >= 2:
        filtered = [
            part
            for part in parts
            if part
            and part not in {"cs2", "lol", "dota", "winner", "match", "league"}
            and not part.isdigit()
        ]
        filtered = [
            part
            for index, part in enumerate(filtered)
            if not (
                index > 0
                and part.isdigit()
                and len(part) == 2
                and filtered[index - 1].isdigit()
            )
        ]
        team_terms = [part for part in filtered if not (part.isdigit() or len(part) == 4)]
        if len(team_terms) >= 2:
            candidates.append(" ".join(team_terms[:2]))
        if team_terms:
            candidates.append(" ".join(team_terms))
            candidates.extend(team_terms)
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return tuple(deduped)


def rank_markets_by_tokens(
    markets: tuple[MarketSummary, ...],
    tokens: tuple[str, ...],
    limit: int = 20,
) -> tuple[MarketSummary, ...]:
    if not tokens:
        return ()
    scored: list[tuple[int, MarketSummary]] = []
    for market in markets:
        text = " ".join(
            (
                market.title,
                market.slug,
                market.event_title,
                " ".join(market.outcomes),
            )
        ).casefold()
        score = sum(1 for token in tokens if token in text)
        if score:
            scored.append((score + int(market.live), market))
    scored.sort(key=lambda item: item[0], reverse=True)
    return tuple(market for _score, market in scored[:limit])


class QuickTradeWindow(QtWidgets.QMainWindow):
    search_requested = QtCore.Signal(str)
    market_lock_requested = QtCore.Signal(str)
    trade_changed = QtCore.Signal()
    submit_requested = QtCore.Signal()
    refresh_account_requested = QtCore.Signal()
    cashout_requested = QtCore.Signal(str)
    disconnected = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Polymarket Unofficial App for Win")
        self.resize(SUMMARY_WINDOW_SIZE)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._closing = False
        self.current_market: MarketSummary | None = None
        self.current_order_book = OrderBookSummary()
        self.current_positions: tuple[PositionRow, ...] = ()
        self.selected_search_slug: str | None = None
        self.position_details_visible = False

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QVBoxLayout(root)

        self.status_label = QtWidgets.QLabel("Connection: disconnected")
        self.balance_label = QtWidgets.QLabel("Current balance: unavailable")
        self.buying_power_label = QtWidgets.QLabel("Buying Power: unavailable")
        self.balance_time_label = QtWidgets.QLabel("Last refresh: unavailable")
        self.refresh_account_button = QtWidgets.QPushButton("Refresh all")
        self.refresh_account_button.clicked.connect(self.refresh_account_requested.emit)
        self.realtime_refresh_toggle = QtWidgets.QCheckBox("Realtime refresh")
        self.realtime_refresh_toggle.toggled.connect(self._realtime_refresh_toggled)
        self.warning_label = QtWidgets.QLabel("Real trading account. Orders may use real funds.")
        self.warning_label.setStyleSheet("font-weight: 600; color: #8a3b00;")
        layout.addWidget(self.status_label)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.balance_label)
        layout.addWidget(self.buying_power_label)
        layout.addWidget(self.balance_time_label)
        refresh_controls = QtWidgets.QHBoxLayout()
        refresh_controls.addWidget(self.refresh_account_button)
        refresh_controls.addWidget(self.realtime_refresh_toggle)
        layout.addLayout(refresh_controls)

        body = QtWidgets.QHBoxLayout()
        layout.addLayout(body, stretch=1)

        left_panel = QtWidgets.QWidget()
        left_panel.setFixedWidth(520)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.addWidget(self._build_market_box())
        left_layout.addWidget(self._build_trade_box())
        left_layout.addWidget(self._build_preview_box(), stretch=1)

        self.submit_button = QtWidgets.QPushButton("Submit real order")
        self.submit_button.setEnabled(False)
        self.submit_button.setDefault(False)
        self.submit_button.setAutoDefault(False)
        self.submit_button.clicked.connect(self.submit_requested.emit)
        self.disconnect_button = QtWidgets.QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.request_close)
        footer = QtWidgets.QHBoxLayout()
        footer.addWidget(self.submit_button)
        footer.addWidget(self.disconnect_button)
        left_layout.addLayout(footer)

        body.addWidget(left_panel)
        body.addWidget(self._build_positions_box(), stretch=1)

        self._preview_timer = QtCore.QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(500)
        self._preview_timer.timeout.connect(self.trade_changed.emit)
        self._realtime_refresh_timer = QtCore.QTimer(self)
        self._realtime_refresh_timer.setInterval(5000)
        self._realtime_refresh_timer.timeout.connect(self.refresh_account_requested.emit)
        for widget in (
            self.amount_input,
            self.slippage_input,
            self.manual_limit_price_input,
        ):
            widget.textChanged.connect(self.queue_auto_preview)
        self.side_combo.currentIndexChanged.connect(self.queue_auto_preview)

    def _build_market_box(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Market")
        layout = QtWidgets.QVBoxLayout(box)
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search game/team/market")
        self.search_button = QtWidgets.QPushButton("Search")
        self.search_button.clicked.connect(self._search_clicked)
        self.search_input.returnPressed.connect(self._search_clicked)
        self.search_results = QtWidgets.QListWidget()
        self.search_results.itemClicked.connect(self._search_result_clicked)
        self.selected_slug_input = QtWidgets.QLineEdit()
        self.selected_slug_input.setPlaceholderText("Selected slug")
        self.selected_slug_input.setReadOnly(True)
        self.lock_market_button = QtWidgets.QPushButton("Lock market")
        self.lock_market_button.clicked.connect(self._lock_market_clicked)
        layout.addWidget(self.search_input)
        layout.addWidget(self.search_button)
        layout.addWidget(self.search_results)
        layout.addWidget(self.selected_slug_input)
        layout.addWidget(self.lock_market_button)
        return box

    def _build_trade_box(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Quick market order")
        form = QtWidgets.QFormLayout(box)
        self.side_combo = QtWidgets.QComboBox()
        self._set_buy_side_options(("Yes", "No"))
        self.amount_input = QtWidgets.QLineEdit()
        self.amount_input.setPlaceholderText("Dollar amount")
        self.slippage_input = QtWidgets.QLineEdit(str(DEFAULT_SLIPPAGE_TICKS))
        self.manual_limit_price_input = QtWidgets.QLineEdit()
        self.manual_limit_price_input.setPlaceholderText("Used when BBO is unavailable")
        self.fill_manual_price_button = QtWidgets.QPushButton("Fill from market price")
        self.fill_manual_price_button.clicked.connect(self.fill_manual_limit_from_market_price)
        form.addRow("Side", self.side_combo)
        form.addRow("Amount USD", self.amount_input)
        form.addRow("Slippage ticks", self.slippage_input)
        form.addRow("Manual limit price", self.manual_limit_price_input)
        form.addRow("", self.fill_manual_price_button)
        return box

    def _build_preview_box(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Auto preview")
        layout = QtWidgets.QVBoxLayout(box)
        self.preview_text = QtWidgets.QTextEdit("Enter market, side, and amount.")
        self.preview_text.setReadOnly(True)
        layout.addWidget(self.preview_text)
        return box

    def _build_positions_box(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox()
        layout = QtWidgets.QVBoxLayout(box)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(QtWidgets.QLabel("Positions"))
        header.addStretch(1)
        self.positions_detail_button = QtWidgets.QPushButton("Details")
        self.positions_detail_button.setCheckable(True)
        self.positions_detail_button.toggled.connect(self._positions_detail_toggled)
        header.addWidget(self.positions_detail_button)
        layout.addLayout(header)

        self.positions_table = QtWidgets.QTableWidget(0, 1)
        self.positions_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.positions_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.positions_table.itemSelectionChanged.connect(self._position_selection_changed)
        self.cashout_amount_input = QtWidgets.QLineEdit()
        self.cashout_amount_input.setPlaceholderText("Cashout amount USD; blank = full position")
        self.cashout_button = QtWidgets.QPushButton("Cash out selected position")
        self.cashout_button.setEnabled(False)
        self.cashout_button.setDefault(False)
        self.cashout_button.setAutoDefault(False)
        self.cashout_button.clicked.connect(self._cashout_clicked)
        layout.addWidget(self.positions_table)
        layout.addWidget(self.cashout_amount_input)
        layout.addWidget(self.cashout_button)
        return box

    def set_connected(self, connected: bool) -> None:
        self.status_label.setText(
            "Connection: connected" if connected else "Connection: disconnected"
        )
        self.submit_button.setEnabled(False)

    def show_balance(self, summary: AccountSummary) -> None:
        self.balance_label.setText(f"Current balance: {format_balance(summary.current_balance)}")
        self.buying_power_label.setText(f"Buying Power: {format_balance(summary.buying_power)}")
        self.balance_time_label.setText(
            f"Last refresh: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

    def show_positions(self, positions: tuple[PositionRow, ...]) -> None:
        self.current_positions = positions
        self._render_positions()

    def _render_positions(self) -> None:
        if self.position_details_visible:
            self._render_position_details()
        else:
            self._render_position_summary()
        self._position_selection_changed()

    def _render_position_summary(self) -> None:
        self.positions_table.clear()
        self.positions_table.setColumnCount(1)
        self.positions_table.horizontalHeader().hide()
        self.positions_table.horizontalHeader().setSectionResizeMode(
            0,
            QtWidgets.QHeaderView.ResizeMode.Stretch,
        )
        self.positions_table.setRowCount(len(self.current_positions))
        for row_index, position in enumerate(self.current_positions):
            item = QtWidgets.QTableWidgetItem(
                "\n".join(
                    [
                        position.market,
                        (
                            f"Value {format_balance(position.current_value)}    "
                            f"PnL {format_balance(position.estimated_pnl)}"
                        ),
                    ]
                )
            )
            item.setData(QtCore.Qt.ItemDataRole.UserRole, row_index)
            self.positions_table.setItem(row_index, 0, item)
            self.positions_table.setRowHeight(row_index, 54)

    def _render_position_details(self) -> None:
        self.positions_table.clear()
        self.positions_table.setColumnCount(6)
        self.positions_table.setHorizontalHeaderLabels(
            ["Market", "Value", "PnL", "Outcome", "Side", "Net"]
        )
        self.positions_table.horizontalHeader().show()
        self.positions_table.horizontalHeader().setSectionResizeMode(
            0,
            QtWidgets.QHeaderView.ResizeMode.Stretch,
        )
        self.positions_table.setRowCount(len(self.current_positions))
        for row_index, position in enumerate(self.current_positions):
            values = [
                position.market,
                format_balance(position.current_value),
                format_balance(position.estimated_pnl),
                position.outcome,
                position.direction,
                "" if position.net_contracts is None else str(position.net_contracts),
            ]
            for column_index, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, row_index)
                self.positions_table.setItem(row_index, column_index, item)
        for column_index in range(1, self.positions_table.columnCount()):
            self.positions_table.resizeColumnToContents(column_index)

    def show_positions_error(self, message: str) -> None:
        self.current_positions = ()
        self.positions_table.clear()
        self.positions_table.setColumnCount(1)
        self.positions_table.horizontalHeader().hide()
        self.positions_table.setRowCount(1)
        self.positions_table.setItem(0, 0, QtWidgets.QTableWidgetItem(message))
        for column_index in range(1, self.positions_table.columnCount()):
            self.positions_table.setItem(0, column_index, QtWidgets.QTableWidgetItem(""))
        self._position_selection_changed()

    def selected_position(self) -> PositionRow | None:
        row = self.positions_table.currentRow()
        if row < 0 or row >= len(self.current_positions):
            return None
        return self.current_positions[row]

    def show_search_results(self, markets: tuple[MarketSummary, ...]) -> None:
        self.selected_search_slug = None
        self.selected_slug_input.clear()
        self.search_results.clear()
        if not markets:
            self.search_results.addItem("No matching markets")
            return
        for market in markets:
            badge = "LIVE | " if market.live else ""
            item = QtWidgets.QListWidgetItem(f"{badge}{market.title}\n{market.slug}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, market.slug)
            details = []
            type_label = market_type_label(market)
            if type_label != UNAVAILABLE:
                details.append(f"Type: {type_label}")
            labels = market.side_labels or market.outcomes
            if labels:
                details.append(f"Sides: {' / '.join(labels)}")
            if details:
                item.setToolTip("\n".join(details))
            if market.live:
                item.setIcon(live_search_icon())
            self.search_results.addItem(item)

    def show_market(self, market: MarketSummary, order_book: OrderBookSummary) -> None:
        self.current_market = market
        self.current_order_book = order_book
        self.selected_search_slug = market.slug
        self.selected_slug_input.setText(market.slug)
        self._set_buy_side_options(buy_side_labels_for_market(market))
        self.queue_auto_preview()

    def show_preview(self, preview: QuickTradePreview) -> None:
        payload = dict(preview.payload)
        self.preview_text.setPlainText(
            "\n".join(
                [
                    "Preview succeeded.",
                    f"Market: {preview.draft.market_slug}",
                    f"Side: {preview.draft.side.value}",
                    f"Intent: {payload.get('intent')}",
                    f"Order type: {payload.get('type')}",
                    f"Amount: ${preview.draft.dollar_amount}",
                    f"Reference price: {preview.draft.current_price}",
                    f"Slippage ticks: {preview.draft.slippage_ticks}",
                    f"Fees/cost: {preview.fees_or_cost}",
                    "This is a real order if submitted.",
                ]
            )
        )
        self.submit_button.setEnabled(True)

    def show_preview_error(self, message: str) -> None:
        self.preview_text.setPlainText(message)
        self.submit_button.setEnabled(False)

    def show_status(self, message: str) -> None:
        self.preview_text.setPlainText(message)

    def queue_auto_preview(self) -> None:
        self.submit_button.setEnabled(False)
        self._preview_timer.start()

    def _realtime_refresh_toggled(self, checked: bool) -> None:
        if checked:
            self._realtime_refresh_timer.start()
            self.refresh_account_requested.emit()
            return
        self._realtime_refresh_timer.stop()

    def fill_manual_limit_from_market_price(self) -> None:
        if self.current_market is None:
            self.show_preview_error("Lock a market first.")
            return
        side = self._selected_trade_side()
        price = current_price_for_side(side, self.current_order_book)
        if price is None:
            buy_sides = {QuickTradeSide.BUY_YES, QuickTradeSide.BUY_NO}
            needed = "best ask" if side in buy_sides else "best bid"
            self.show_preview_error(f"No current {needed} is available to fill.")
            return
        self.manual_limit_price_input.setText(str(price))

    def draft_from_inputs(self) -> QuickTradeDraft | None:
        if self.current_market is None:
            self.show_preview_error("Lock a market first.")
            return None
        amount = parse_trade_amount(self.amount_input.text())
        if amount is None:
            self.show_preview_error("Enter a dollar amount greater than 0.")
            return None
        side = self._selected_trade_side()
        current_price = current_price_for_side(side, self.current_order_book)
        order_kind = QuickOrderKind.MARKET
        if current_price is None:
            buy_sides = {QuickTradeSide.BUY_YES, QuickTradeSide.BUY_NO}
            needed = "best ask" if side in buy_sides else "best bid"
            limit_price = parse_trade_amount(self.manual_limit_price_input.text())
            if limit_price is None or not Decimal("0") < limit_price < Decimal("1"):
                self.show_preview_error(
                    f"Current {needed} is unavailable for {side.value}. "
                    "Enter a manual limit price to place a limit order."
                )
                return None
            current_price = limit_price
            order_kind = QuickOrderKind.LIMIT
        try:
            slippage_ticks = int(self.slippage_input.text())
        except ValueError:
            self.show_preview_error("Slippage ticks must be an integer.")
            return None
        return QuickTradeDraft(
            market_slug=self.current_market.slug,
            side=side,
            dollar_amount=amount,
            current_price=current_price,
            slippage_ticks=slippage_ticks,
            order_kind=order_kind,
        )

    def _set_buy_side_options(self, labels: tuple[str, str]) -> None:
        current_side = self._selected_trade_side(default=QuickTradeSide.BUY_YES)
        self.side_combo.blockSignals(True)
        self.side_combo.clear()
        self.side_combo.addItem(f"Buy {labels[0]}", QuickTradeSide.BUY_YES.value)
        self.side_combo.addItem(f"Buy {labels[1]}", QuickTradeSide.BUY_NO.value)
        index = 0 if current_side == QuickTradeSide.BUY_YES else 1
        self.side_combo.setCurrentIndex(index)
        self.side_combo.blockSignals(False)

    def _selected_trade_side(
        self,
        default: QuickTradeSide = QuickTradeSide.BUY_YES,
    ) -> QuickTradeSide:
        value = self.side_combo.currentData()
        if isinstance(value, str):
            try:
                return QuickTradeSide(value)
            except ValueError:
                return default
        try:
            return QuickTradeSide(self.side_combo.currentText())
        except ValueError:
            return default

    def _search_clicked(self) -> None:
        query = self.search_input.text().strip()
        if query:
            self.search_requested.emit(query)

    def _search_result_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        slug = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.selected_search_slug = slug if isinstance(slug, str) and slug else None
        self.selected_slug_input.setText(self.selected_search_slug or "")

    def _lock_market_clicked(self) -> None:
        slug = self.selected_search_slug
        if slug:
            self.market_lock_requested.emit(slug)
            return
        self.show_preview_error("Select a search result first.")

    def _position_selection_changed(self) -> None:
        position = self.selected_position()
        enabled = position is not None and position.market_slug != UNAVAILABLE
        self.cashout_button.setEnabled(enabled)

    def _positions_detail_toggled(self, checked: bool) -> None:
        self.position_details_visible = checked
        self.positions_detail_button.setText("Summary" if checked else "Details")
        self._resize_for_position_mode(checked)
        self._render_positions()

    def _resize_for_position_mode(self, details_visible: bool) -> None:
        if self.isMaximized() or self.isFullScreen():
            return
        target = DETAIL_WINDOW_SIZE if details_visible else SUMMARY_WINDOW_SIZE
        if self.size().width() == target.width() and self.size().height() == target.height():
            return
        self.resize(target)

    def _cashout_clicked(self) -> None:
        position = self.selected_position()
        if position is None or position.market_slug == UNAVAILABLE:
            self.show_preview_error("Select a position with a market slug first.")
            return
        self.cashout_requested.emit(position.market_slug)

    def request_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.disconnected.emit()
        self.close()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if not self._closing:
            self._closing = True
            self.disconnected.emit()
        super().closeEvent(event)


async def refresh_account(window: QuickTradeWindow, client: PolymarketClient) -> None:
    try:
        summary = await client.account_summary()
    except Exception as exc:
        window.show_preview_error(safe_api_error_message(exc))
    else:
        window.show_balance(summary)
    try:
        positions = await client.positions()
    except Exception as exc:
        window.show_positions_error(safe_api_error_message(exc))
    else:
        window.show_positions(positions)


async def refresh_locked_market(window: QuickTradeWindow, client: PolymarketClient) -> None:
    if window.current_market is None:
        return
    slug = window.current_market.slug
    try:
        market = await client.market(slug)
        order_book = await client.order_book(slug)
    except Exception as exc:
        window.show_preview_error(safe_market_error_message(exc))
    else:
        window.show_market(market, order_book)


async def refresh_all(window: QuickTradeWindow, client: PolymarketClient) -> None:
    await refresh_account(window, client)
    await refresh_locked_market(window, client)


async def load_market(window: QuickTradeWindow, client: PolymarketClient, slug: str) -> None:
    window.show_preview_error("Loading market...")
    try:
        market = await client.market(slug)
        order_book = await client.order_book(slug)
    except Exception as exc:
        window.show_preview_error(safe_market_error_message(exc))
    else:
        window.show_market(market, order_book)


async def search_markets(window: QuickTradeWindow, client: PolymarketClient, query: str) -> None:
    parts = parse_url_search_parts(query)
    slug = parts.market_slug or extract_slug_from_query(query)
    if slug and "-" in slug:
        try:
            market = await client.market(slug)
        except Exception:
            pass
        else:
            window.show_search_results((market,))
            return
        try:
            markets = await client.event_markets_by_slug(slug)
        except Exception:
            pass
        else:
            if markets:
                window.show_search_results(markets)
                return
    last_error: Exception | None = None
    for candidate in search_candidates_from_query(query):
        try:
            markets = await client.search_markets(candidate)
        except Exception as exc:
            last_error = exc
            continue
        if markets:
            window.show_search_results(markets)
            return
    tokens = meaningful_slug_tokens(slug)
    scoped_queries: list[dict[str, object]] = []
    if parts.category:
        scoped_queries.append({"active": True, "categories": [parts.category]})
    for tag in (parts.subcategory, parts.series_slug):
        if tag and tag != slug:
            scoped_queries.append({"active": True, "tagSlug": tag})
    for params in scoped_queries:
        try:
            markets = await client.event_markets(params, limit=100)
        except Exception as exc:
            last_error = exc
            continue
        ranked = rank_markets_by_tokens(markets, tokens)
        if ranked:
            window.show_search_results(ranked)
            return
    window.show_search_results(())
    if last_error is not None:
        window.show_preview_error(safe_market_error_message(last_error))


async def auto_preview(
    window: QuickTradeWindow,
    flow: QuickTradeFlow,
    client: PolymarketClient,
) -> None:
    flow.invalidate_preview()
    draft = window.draft_from_inputs()
    if draft is None:
        return
    try:
        preview = await flow.preview_order(draft)
    except Exception as exc:
        message = safe_api_error_message(exc)
        if draft.side in {QuickTradeSide.SELL_YES, QuickTradeSide.SELL_NO}:
            message = "Dollar sell preview rejected by API"
        window.show_preview_error(message)
        return
    window.show_preview(preview)
    await refresh_account(window, client)


async def submit_order(
    window: QuickTradeWindow,
    flow: QuickTradeFlow,
    client: PolymarketClient,
) -> None:
    preview = flow.preview
    if preview is None:
        window.show_preview_error("Preview is required before submit.")
        return
    confirm = QtWidgets.QMessageBox(window)
    confirm.setWindowTitle("Submit real order")
    confirm.setText("Submit this real market order? Orders may use real funds.")
    confirm.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    confirm.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel
    )
    confirm.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Cancel)
    accepted = confirm.exec()
    if accepted != QtWidgets.QMessageBox.StandardButton.Yes:
        return
    window.submit_button.setEnabled(False)
    window.show_status("Submitting...")
    try:
        submitted = await flow.submit_previewed_order(preview)
    except Exception as exc:
        window.show_preview_error(safe_api_error_message(exc))
    else:
        window.show_status(f"Submitted order {submitted.order_id} ({submitted.status})")
    finally:
        await refresh_all(window, client)


async def cashout_position(
    window: QuickTradeWindow,
    flow: QuickTradeFlow,
    client: PolymarketClient,
    market_slug: str,
) -> None:
    position = window.selected_position()
    if position is None or position.market_slug != market_slug:
        window.show_preview_error("Select a position to cash out.")
        return
    try:
        slippage_ticks = int(window.slippage_input.text())
    except ValueError:
        window.show_preview_error("Slippage ticks must be an integer.")
        return
    if slippage_ticks < 0:
        window.show_preview_error("Slippage ticks must be non-negative.")
        return
    cashout_amount = parse_trade_amount(window.cashout_amount_input.text())
    if window.cashout_amount_input.text().strip() and cashout_amount is None:
        window.show_preview_error("Cashout amount must be greater than 0.")
        return
    if cashout_amount is not None:
        await cashout_partial_position(
            window,
            flow,
            client,
            position,
            cashout_amount,
            slippage_ticks,
        )
        return
    confirm = QtWidgets.QMessageBox(window)
    confirm.setWindowTitle("Cash out position")
    confirm.setText(
        "\n".join(
            [
                "Close this market position?",
                f"Market: {position.market}",
                f"Outcome: {position.outcome}",
                f"Net: {position.net_contracts}",
                f"Slug: {market_slug}",
                "This submits a real close-position order and may use real funds.",
            ]
        )
    )
    confirm.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    confirm.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel
    )
    confirm.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Cancel)
    accepted = confirm.exec()
    if accepted != QtWidgets.QMessageBox.StandardButton.Yes:
        return
    window.cashout_button.setEnabled(False)
    window.show_status("Submitting cashout...")
    try:
        submitted = await client.close_position(market_slug, slippage_ticks)
    except Exception as exc:
        window.show_preview_error(safe_api_error_message(exc))
    else:
        window.show_status(f"Cashout submitted {submitted.order_id} ({submitted.status})")
    finally:
        await refresh_all(window, client)


async def cashout_partial_position(
    window: QuickTradeWindow,
    flow: QuickTradeFlow,
    client: PolymarketClient,
    position: PositionRow,
    amount: Decimal,
    slippage_ticks: int,
) -> None:
    side = cashout_side_for_position(position)
    if side is None:
        window.show_preview_error("Position direction is unavailable; cannot infer cashout side.")
        return
    try:
        order_book = await client.order_book(position.market_slug)
    except Exception as exc:
        window.show_preview_error(safe_market_error_message(exc))
        return
    current_price = current_price_for_side(side, order_book)
    order_kind = QuickOrderKind.MARKET
    if current_price is None:
        current_price = parse_trade_amount(window.manual_limit_price_input.text())
        if current_price is None or not Decimal("0") < current_price < Decimal("1"):
            window.show_preview_error(
                "Current best bid is unavailable. Enter a manual limit price for partial cashout."
            )
            return
        order_kind = QuickOrderKind.LIMIT
    draft = QuickTradeDraft(
        market_slug=position.market_slug,
        side=side,
        dollar_amount=amount,
        current_price=current_price,
        slippage_ticks=slippage_ticks,
        order_kind=order_kind,
    )
    flow.invalidate_preview()
    try:
        preview = await flow.preview_order(draft)
    except Exception:
        window.show_preview_error("Dollar cashout preview rejected by API")
        return
    window.submit_button.setEnabled(False)
    window.show_status(
        "\n".join(
            [
                "Partial cashout preview succeeded.",
                f"Market: {position.market}",
                f"Outcome: {position.outcome}",
                f"Side: {side.value}",
                f"Amount: ${amount}",
                f"Reference price: {current_price}",
                f"Order type: {draft.order_kind.value}",
                f"Fees/cost: {preview.fees_or_cost}",
            ]
        )
    )
    confirm = QtWidgets.QMessageBox(window)
    confirm.setWindowTitle("Partial cashout")
    confirm.setText(
        "\n".join(
            [
                "Submit this partial cashout order?",
                f"Market: {position.market}",
                f"Outcome: {position.outcome}",
                f"Amount: ${amount}",
                f"Side: {side.value}",
                "This submits a real sell order and may use real funds.",
            ]
        )
    )
    confirm.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    confirm.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel
    )
    confirm.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Cancel)
    accepted = confirm.exec()
    if accepted != QtWidgets.QMessageBox.StandardButton.Yes:
        return
    window.cashout_button.setEnabled(False)
    window.show_status("Submitting partial cashout...")
    try:
        submitted = await flow.submit_previewed_order(preview)
    except Exception as exc:
        window.show_preview_error(safe_api_error_message(exc))
    else:
        window.show_status(f"Partial cashout submitted {submitted.order_id} ({submitted.status})")
    finally:
        await refresh_all(window, client)


async def authenticate_quick_trade(window: QuickTradeWindow) -> PolymarketClient | None:
    env_credentials, _message = credentials_from_environment()
    if env_credentials is not None:
        client, error = await authenticate_credentials(env_credentials)
        if client is not None:
            return client
        QtWidgets.QMessageBox.warning(window, "API error", error or "Unable to connect")
    client, accepted = await authenticate_with_prompt(window)
    if not accepted or client is None:
        return None
    return client


async def run_quick_trade_app() -> int:
    window = QuickTradeWindow()
    window.show()
    await asyncio.sleep(0)
    client = await authenticate_quick_trade(window)
    if client is None:
        window.close()
        return 0
    flow = QuickTradeFlow(client)
    window.set_connected(True)
    await refresh_all(window, client)
    refresh_task: asyncio.Task[None] | None = None

    def schedule_refresh_all() -> None:
        nonlocal refresh_task
        if refresh_task is not None and not refresh_task.done():
            return
        refresh_task = asyncio.create_task(refresh_all(window, client))

    window.search_requested.connect(
        lambda query: asyncio.create_task(search_markets(window, client, query))
    )
    window.market_lock_requested.connect(
        lambda slug: asyncio.create_task(load_market(window, client, slug))
    )
    window.refresh_account_requested.connect(schedule_refresh_all)
    window.trade_changed.connect(lambda: asyncio.create_task(auto_preview(window, flow, client)))
    window.submit_requested.connect(lambda: asyncio.create_task(submit_order(window, flow, client)))
    window.cashout_requested.connect(
        lambda slug: asyncio.create_task(cashout_position(window, flow, client, slug))
    )
    stop = asyncio.Event()
    window.disconnected.connect(stop.set)
    await stop.wait()
    await client.close()
    return 0


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        raise SystemExit(loop.run_until_complete(run_quick_trade_app()))


if __name__ == "__main__":
    main()
