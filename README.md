# Polymarket Unofficial App for Win

Local manual Polymarket US quick trading window for Windows. This is a personal desktop app, not a web service, cloud backend, automatic trading system, or production trading platform.

## Disclaimer

This project is unofficial and is not affiliated with, endorsed by, sponsored by, or approved by Polymarket. It is a personal desktop client built on the public Polymarket US SDK/API. Trading involves risk and may result in loss. Use at your own responsibility and comply with Polymarket US rules, API terms, and applicable law.

This tool is intended for manual use only. It does not implement automated trading, strategy execution, market making, scraping, geoblock circumvention, or third-party account management.

## Environment Setup

Recommended setup uses `uv` on Windows PowerShell.

Install `uv`:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart PowerShell, then check:

```powershell
uv --version
python --version
```

Create the local virtual environment and install the app:

```powershell
cd C:\Users\czhang30\Desktop\polymarket
uv venv --python 3.12
uv pip install -e ".[dev]"
```

If Python 3.12 is not installed, let `uv` install/use it:

```powershell
uv python install 3.12
uv venv --python 3.12
uv pip install -e ".[dev]"
```

The project environment lives in:

```text
.venv
```

Do not commit `.venv`, API keys, or local cache folders.

## Run

Double-click from the project folder:

```text
run_quick_trade.bat
```

The batch file uses `.venv\Scripts\python.exe` when `.venv` exists. If `.venv` does not exist, it falls back to:

```powershell
uv run python -m polymarket_terminal.quick_trade
```

Run manually from PowerShell:

```powershell
uv run python -m polymarket_terminal.quick_trade
```

Installed console entry:

```powershell
uv run polymarket-quick-trade
```

The default module entry also launches the same quick trade tool:

```powershell
uv run python -m polymarket_terminal
```

## Credentials

API Key ID and Secret Key stay only in memory. At startup, the login dialog tries to read:

```powershell
POLYMARKET_KEY_ID
POLYMARKET_SECRET_KEY
```

If both variables exist, the app attempts API login automatically. If they are missing or invalid, it asks for manual input. Authentication and network failures are shown as safe messages such as `Authentication failed`, `Network error`, `Request timed out`, or `Unable to connect`.

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

After setting persistent variables, open a new PowerShell window before launching the app.

To remove persistent credentials:

```powershell
[Environment]::SetEnvironmentVariable("POLYMARKET_KEY_ID", $null, "User")
[Environment]::SetEnvironmentVariable("POLYMARKET_SECRET_KEY", $null, "User")
```

## Quick Trade

- Paste a Polymarket URL or search by team/market name.
- Select a search result, copy the selected slug if needed, then click `Lock market`.
- Choose `Buy Yes`, `Buy No`, `Sell Yes`, or `Sell No`.
- Enter a USD amount.
- The tool automatically calls `orders.preview()`.
- Click `Submit real order` only after preview succeeds. The confirmation dialog defaults to cancel.

If best bid/ask is unavailable, enter `Manual limit price`; the tool previews a limit order using the USD amount converted to whole contracts. This is a resting order and may not fill immediately.

## Positions

Positions are shown in the right column. Summary view shows market, Value, and PnL. `Details` expands the full table.

Cashout:

- Select a position row.
- Leave `Cashout amount USD` blank for full close-position.
- Enter a positive USD amount for partial cashout.
- Confirm before any real order is submitted.

## Refresh

`Refresh all` updates balance, buying power, positions, and the locked market/order book.

`Realtime refresh` runs guarded `Refresh all` polling every 5 seconds. If a previous refresh is still running, the next one is skipped.

## Verification

```powershell
uv run python -m pytest -p no:cacheprovider
uv run ruff check .
uv run mypy src
uv run python -m compileall src
```

## Safety

Preview happens before create. Real submission requires explicit confirmation. Create is not retried automatically. Unknown create results trigger reconciliation and refresh.
