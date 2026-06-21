@echo off
setlocal

cd /d "%~dp0"

set "CONDA_BAT=C:\ProgramData\miniconda3\condabin\conda.bat"

if exist "%CONDA_BAT%" goto run_app

where conda >nul 2>nul
if errorlevel 1 (
    echo Could not find conda.
    echo Expected: C:\ProgramData\miniconda3\condabin\conda.bat
    echo.
    echo Open Anaconda Prompt or fix Conda PATH, then try again.
    pause
    exit /b 1
)

set "CONDA_BAT=conda"

:run_app
call "%CONDA_BAT%" run -n polymarket python -m polymarket_terminal.quick_trade
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Quick trade exited with error code %EXIT_CODE%.
    echo Check the error message above.
    pause
    exit /b %EXIT_CODE%
)

endlocal
