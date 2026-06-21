from __future__ import annotations

from collections.abc import Callable
from typing import Any

from polymarket_terminal.adapters import (
    adapt_account_summary,
    adapt_close_position_response,
    adapt_market,
    adapt_open_orders,
    adapt_order_book,
    adapt_positions,
    adapt_search_markets,
    first_balance,
)
from polymarket_terminal.credentials import Credentials
from polymarket_terminal.models import (
    AccountSummary,
    MarketSummary,
    OpenOrderRow,
    OrderBookSummary,
    PositionRow,
    SubmittedOrder,
)


class SdkUnavailableError(RuntimeError):
    pass


class PolymarketClient:
    """Thin SDK boundary. Method names are finalized only after SDK inspection."""

    def __init__(self, credentials: Credentials) -> None:
        self.credentials = credentials
        self._sdk: Any | None = None

    @classmethod
    def public(cls) -> PolymarketClient:
        return cls(Credentials(api_key_id="", secret_key=""))

    async def connect(self) -> None:
        try:
            from polymarket_us import AsyncPolymarketUS  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - depends on local SDK install
            raise SdkUnavailableError("Polymarket US SDK is unavailable") from exc
        self._sdk = AsyncPolymarketUS(
            key_id=self.credentials.api_key_id,
            secret_key=self.credentials.secret_key,
        )

    async def close(self) -> None:
        if self._sdk is not None:
            close: Callable[[], Any] | None = getattr(self._sdk, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        self._sdk = None

    @property
    def sdk(self) -> Any:
        if self._sdk is None:
            raise SdkUnavailableError("Client is not connected")
        return self._sdk

    @property
    def orders(self) -> Any:
        return self.sdk.orders

    async def balances_raw(self) -> object:
        result: object = await self.sdk.account.balances()
        return result

    async def positions(self) -> tuple[PositionRow, ...]:
        raw: object = await self.sdk.portfolio.positions()
        return adapt_positions(raw)

    async def open_orders(self) -> tuple[OpenOrderRow, ...]:
        raw: object = await self.sdk.orders.list()
        return adapt_open_orders(raw)

    async def close_position(self, market_slug: str, slippage_ticks: int) -> SubmittedOrder:
        raw: object = await self.sdk.orders.close_position(
            {
                "marketSlug": market_slug,
                "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_MANUAL",
                "synchronousExecution": True,
                "maxBlockTime": "5",
                "slippageTolerance": {"ticks": slippage_ticks},
            }
        )
        return adapt_close_position_response(raw)

    async def account_summary(self) -> AccountSummary:
        raw_balance = await self.balances_raw()
        positions = await self.positions()
        open_orders = await self.open_orders()
        return adapt_account_summary(first_balance(raw_balance), positions, len(open_orders))

    async def search_markets(self, query: str, limit: int = 20) -> tuple[MarketSummary, ...]:
        raw: object = await self.sdk.search.query({"query": query, "limit": limit})
        markets = adapt_search_markets(raw)
        if markets:
            return markets[:limit]
        listed: object = await self.sdk.markets.list({"active": True, "limit": 200})
        listed_markets = adapt_search_markets({"events": [{"markets": self._read_markets(listed)}]})
        query_text = query.casefold()
        return tuple(
            market
            for market in listed_markets
            if query_text in market.title.casefold()
            or query_text in market.slug.casefold()
            or any(query_text in outcome.casefold() for outcome in market.outcomes)
        )[:limit]

    async def event_markets_by_slug(self, slug: str, limit: int = 20) -> tuple[MarketSummary, ...]:
        raw: object = await self.sdk.events.retrieve_by_slug(slug)
        return adapt_search_markets({"events": [raw]})[:limit]

    async def event_markets(
        self,
        params: dict[str, object],
        limit: int = 20,
    ) -> tuple[MarketSummary, ...]:
        raw: object = await self.sdk.events.list({**params, "limit": max(limit, 50)})
        return adapt_search_markets(raw)[:limit]

    def _read_markets(self, raw: object) -> object:
        if isinstance(raw, dict):
            return raw.get("markets", ())
        return getattr(raw, "markets", ())

    async def market(self, slug: str) -> MarketSummary:
        raw: object = await self.sdk.markets.retrieve_by_slug(slug)
        return adapt_market(raw)

    async def order_book(self, slug: str) -> OrderBookSummary:
        bbo: object = await self.sdk.markets.bbo(slug)
        book: object = await self.sdk.markets.book(slug)
        order_book = adapt_order_book(bbo, book)
        if order_book.best_bid is not None or order_book.best_ask is not None:
            return order_book
        market_raw: object = await self.sdk.markets.retrieve_by_slug(slug)
        return adapt_order_book(market_raw, book)

    async def reconcile_after_unknown_order_state(self) -> None:
        await self.sdk.orders.list()
        await self.sdk.portfolio.activities()
        await self.sdk.portfolio.positions()
        await self.sdk.account.balances()

    async def refresh_after_order_change(self) -> None:
        await self.sdk.orders.list()
        await self.sdk.portfolio.positions()
        await self.sdk.account.balances()
