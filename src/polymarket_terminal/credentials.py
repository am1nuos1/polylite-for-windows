from __future__ import annotations

from dataclasses import dataclass
from os import environ

POLYMARKET_KEY_ID_ENV = "POLYMARKET_KEY_ID"
POLYMARKET_SECRET_KEY_ENV = "POLYMARKET_SECRET_KEY"


@dataclass(slots=True)
class Credentials:
    api_key_id: str
    secret_key: str

    def clear(self) -> None:
        self.api_key_id = ""
        self.secret_key = ""

    @property
    def is_empty(self) -> bool:
        return not self.api_key_id or not self.secret_key


def credentials_from_environment() -> tuple[Credentials | None, str]:
    api_key_id = environ.get(POLYMARKET_KEY_ID_ENV, "").strip()
    secret_key = environ.get(POLYMARKET_SECRET_KEY_ENV, "").strip()
    missing = [
        name
        for name, value in (
            (POLYMARKET_KEY_ID_ENV, api_key_id),
            (POLYMARKET_SECRET_KEY_ENV, secret_key),
        )
        if not value
    ]
    if missing:
        return None, f"Environment variables not found: {', '.join(missing)}"
    return Credentials(api_key_id=api_key_id, secret_key=secret_key), (
        "Loaded API credentials from environment."
    )
