# Polylite for Windows

Unofficial lightweight Windows desktop GUI for manual Polymarket US trading.

This is a local personal app built with Python, PySide6, qasync, and the official `polymarket-us` SDK. It is not a web service, cloud backend, trading bot, or production trading platform.

![Paste a Polymarket URL into the search box](wearefalcons.png)

## Features

- Search markets by Polymarket URL, market slug, team name, or keyword.
- Lock one market and trade from a small desktop window.
- Buy Yes, Buy No, Sell Yes, or Sell No with a USD amount.
- Automatically previews orders before allowing submission.
- Requires explicit confirmation before any real order is sent.
- Shows balance, buying power, positions, compact PnL, and position details.
- Supports manual refresh and optional realtime refresh polling.
- Supports full or partial cashout from a selected position.
- Keeps API credentials in process memory only.

## Requirements

- Windows
- Python 3.12
- `uv`
- Polymarket US API Key ID and Secret Key for authenticated account actions

Market search can be used without API credentials when the API allows public access. Preview, submit, balances, positions, and cashout require authenticated Polymarket US credentials.

## Install

Install `uv` in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart PowerShell, then install the app:

```powershell
git clone https://github.com/am1nuos1/polylite-for-windows.git
cd polylite-for-windows
uv python install 3.12
uv venv --python 3.12
uv pip install -e ".[dev]"
```

The local environment is created in `.venv`. Do not commit `.venv`, `.env`, API keys, or local cache folders.

## Run

Double-click:

```text
run_quick_trade.bat
```

Or run from PowerShell:

```powershell
uv run python -m polymarket_terminal.quick_trade
```

Equivalent entry points:

```powershell
uv run python -m polymarket_terminal
uv run polymarket-quick-trade
```

## Credentials

At startup, the app reads these environment variables:

```powershell
POLYMARKET_KEY_ID
POLYMARKET_SECRET_KEY
```

If both are present, the app attempts login automatically. If either is missing or invalid, the login dialog asks for manual input. Error messages are sanitized and do not echo secrets.

Set credentials for the current PowerShell session:

```powershell
$env:POLYMARKET_KEY_ID = "your-key-id"
$env:POLYMARKET_SECRET_KEY = "your-secret-key"
uv run python -m polymarket_terminal.quick_trade
```

Set credentials persistently for your Windows user:

```powershell
[Environment]::SetEnvironmentVariable("POLYMARKET_KEY_ID", "your-key-id", "User")
[Environment]::SetEnvironmentVariable("POLYMARKET_SECRET_KEY", "your-secret-key", "User")
```

Open a new PowerShell window after setting persistent variables. To remove them:

```powershell
[Environment]::SetEnvironmentVariable("POLYMARKET_KEY_ID", $null, "User")
[Environment]::SetEnvironmentVariable("POLYMARKET_SECRET_KEY", $null, "User")
```

## Usage

1. Paste a Polymarket URL or search by team/market name.
2. Select a result and click `Lock market`.
3. Choose `Buy Yes`, `Buy No`, `Sell Yes`, or `Sell No`.
4. Enter a USD amount.
5. Wait for automatic preview.
6. Click `Submit real order` only if the preview is correct.

If best bid/ask is unavailable, enter `Manual limit price`. The app previews a limit order by converting the USD amount into whole contracts. This can rest on the book and may not fill immediately.

## Positions

The right column shows positions. Compact view shows market, value, and PnL. `Details` expands the full table.

Cashout:

- Select a position row.
- Leave `Cashout amount USD` blank for full cashout.
- Enter a positive USD amount for partial cashout.
- Confirm before submission.

`Refresh all` updates balance, buying power, positions, and the locked market/order book. `Realtime refresh` polls the same refresh path every 5 seconds and skips overlapping refreshes.

## Safety Model

- No automated trading, strategies, market making, scraping, bulk actions, or third-party account management.
- Preview calls only `orders.preview()`.
- Real submission calls `orders.create()` only after a successful preview and user confirmation.
- Any market, side, amount, slippage, or price change invalidates the old preview.
- Submissions are locked while in progress and are not retried automatically.
- Timeout or unknown create status triggers account/order reconciliation.
- Missing API fields are shown as `unavailable`, not fabricated as zero.

## Development

Run checks:

```powershell
uv run python -m pytest -p no:cacheprovider
uv run ruff check .
uv run mypy src
uv run python -m compileall src
```

## Disclaimer

This project is unofficial and is not affiliated with, endorsed by, sponsored by, or approved by Polymarket. It is a personal desktop client for Polymarket US account access. Trading involves risk and may result in loss. Use it at your own responsibility and comply with Polymarket US rules, API terms, and applicable law.

## License

No license file has been added yet.
