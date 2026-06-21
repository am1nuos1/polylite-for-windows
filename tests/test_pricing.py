from decimal import Decimal

from polymarket_terminal.pricing import (
    calculate_estimated_pnl,
    calculate_pnl_percent,
    calculate_total_estimated_pnl,
    calculate_total_pnl_percent,
    parse_decimal,
)


def test_profit_and_loss() -> None:
    assert calculate_estimated_pnl(Decimal("12.25"), Decimal("10.00")) == Decimal("2.25")
    assert calculate_estimated_pnl(Decimal("8.00"), Decimal("10.00")) == Decimal("-2.00")


def test_zero_and_negative_cost_percent() -> None:
    assert calculate_pnl_percent(Decimal("1"), Decimal("0")) is None
    assert calculate_pnl_percent(Decimal("2"), Decimal("-10")) == Decimal("20.0")


def test_missing_and_invalid_amounts() -> None:
    assert parse_decimal(None) is None
    assert parse_decimal("not money") is None
    assert calculate_estimated_pnl(None, Decimal("1")) is None


def test_large_values_and_precision() -> None:
    value = parse_decimal("12345678901234567890.123456789")
    assert value == Decimal("12345678901234567890.123456789")


def test_totals() -> None:
    assert calculate_total_estimated_pnl([Decimal("1.25"), Decimal("-0.25")]) == Decimal("1.00")
    assert calculate_total_pnl_percent(
        [Decimal("1.00"), Decimal("-0.50")],
        [Decimal("10"), Decimal("5")],
    ) == Decimal("3.333333333333333333333333333")
