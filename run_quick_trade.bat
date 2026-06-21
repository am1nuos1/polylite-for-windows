@echo off
setlocal

cd /d "%~dp0"

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"

if exist "%VENV_PYTHON%" goto run_venv

where uv >nul 2>nul
if errorlevel 1 (
    echo Could not find uv or .venv.
    echo.
    echo Install uv:
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo.
    echo Then run:
    echo   uv venv --python 3.12
    echo   uv pip install -e .[dev]
    echo.
    pause
    exit /b 1
)

:run_uv
uv run python -m polymarket_terminal.quick_trade
goto handle_exit

:run_venv
"%VENV_PYTHON%" -m polymarket_terminal.quick_trade

:handle_exit
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Quick trade exited with error code %EXIT_CODE%.
    echo Check the error message above.
    pause
    exit /b %EXIT_CODE%
)

endlocal
