# Polymarket Unofficial App for Win

Local manual Polymarket US quick trading window for Windows. This is a personal desktop app, not a web service, cloud backend, automatic trading system, or production trading platform.

## Disclaimer

This project is unofficial and is not affiliated with, endorsed by, sponsored by, or approved by Polymarket. It is a personal desktop client built on the public Polymarket US SDK/API. Trading involves risk and may result in loss. Use at your own responsibility and comply with Polymarket US rules, API terms, and applicable law.

This tool is intended for manual use only. It does not implement automated trading, strategy execution, market making, scraping, geoblock circumvention, or third-party account management.

## Run

Double-click:

```text
run_quick_trade.bat
```

Or run from PowerShell:

```powershell
C:\ProgramData\miniconda3\condabin\conda.bat run -n polymarket python -m polymarket_terminal.quick_trade
```

Installed console entry:

```powershell
polyquick-us
```

The default module entry also launches the same quick trade tool:

```powershell
C:\ProgramData\miniconda3\condabin\conda.bat run -n polymarket python -m polymarket_terminal
```

## Credentials

API Key ID and Secret Key stay only in memory. At startup, the login dialog tries to read:

```powershell
POLYMARKET_KEY_ID
POLYMARKET_SECRET_KEY
```

If both variables exist, the app attempts API login automatically. If they are missing or invalid, it asks for manual input. Authentication and network failures are shown as safe messages such as `Authentication failed`, `Network error`, `Request timed out`, or `Unable to connect`.

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
C:\ProgramData\miniconda3\condabin\conda.bat run -n polymarket python -m pytest -p no:cacheprovider
C:\ProgramData\miniconda3\condabin\conda.bat run -n polymarket ruff check .
C:\ProgramData\miniconda3\condabin\conda.bat run -n polymarket mypy src
C:\ProgramData\miniconda3\condabin\conda.bat run -n polymarket python -m compileall src
```

## Safety

Preview happens before create. Real submission requires explicit confirmation. Create is not retried automatically. Unknown create results trigger reconciliation and refresh.
