from __future__ import annotations

from decimal import Decimal, InvalidOperation

MIN_PRICE = Decimal("0")
MAX_PRICE = Decimal("1")
MIN_QUANTITY = Decimal("0")
MIN_NOTIONAL = Decimal("0")


def parse_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = Decimal(stripped)
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() else None
    return None


def format_currency(value: Decimal | None) -> str:
    if value is None:
        return "unavailable"
    sign = "+" if value > 0 else ""
    return f"{sign}${value.quantize(Decimal('0.01'))}"


def format_contracts(value: Decimal | None) -> str:
    if value is None:
        return "unavailable"
    return format(value.normalize(), "f")


def format_percent(value: Decimal | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value.quantize(Decimal('0.01'))}%"


def calculate_estimated_pnl(
    current_value: Decimal | None,
    cost_basis: Decimal | None,
) -> Decimal | None:
    if current_value is None or cost_basis is None:
        return None
    return current_value - cost_basis


def calculate_pnl_percent(
    estimated_pnl: Decimal | None,
    cost_basis: Decimal | None,
) -> Decimal | None:
    if estimated_pnl is None or cost_basis is None:
        return None
    denominator = abs(cost_basis)
    if denominator <= Decimal("0"):
        return None
    return (estimated_pnl / denominator) * Decimal("100")


def calculate_total_estimated_pnl(values: list[Decimal | None]) -> Decimal | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return sum(known, Decimal("0"))


def calculate_total_pnl_percent(
    estimated_pnls: list[Decimal | None],
    cost_bases: list[Decimal | None],
) -> Decimal | None:
    pnl_values = [value for value in estimated_pnls if value is not None]
    basis_values = [abs(value) for value in cost_bases if value is not None]
    denominator = sum(basis_values, Decimal("0"))
    if not pnl_values or denominator <= Decimal("0"):
        return None
    return (sum(pnl_values, Decimal("0")) / denominator) * Decimal("100")


def validate_price(price: Decimal) -> None:
    if not price.is_finite() or price <= MIN_PRICE or price >= MAX_PRICE:
        raise ValueError("Limit price must be greater than 0 and less than 1")


def validate_quantity(quantity: Decimal) -> None:
    if not quantity.is_finite() or quantity <= MIN_QUANTITY:
        raise ValueError("Quantity must be greater than 0")


def validate_notional(price: Decimal, quantity: Decimal) -> Decimal:
    validate_price(price)
    validate_quantity(quantity)
    notional = price * quantity
    if notional <= MIN_NOTIONAL:
        raise ValueError("Estimated notional must be greater than 0")
    return notional
