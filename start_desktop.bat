@echo off
setlocal

cd /d "%~dp0"

set "PROJECT_PYTHON=%~dp0..\.venv\Scripts\python.exe"

if exist "%PROJECT_PYTHON%" (
    "%PROJECT_PYTHON%" -m invoice_desktop.main
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3.12 -m invoice_desktop.main
    ) else (
        python -m invoice_desktop.main
    )
)

if errorlevel 1 (
    echo.
    echo Launch failed.
    echo Checked project interpreter: %PROJECT_PYTHON%
    echo If needed, install dependencies with:
    echo "%PROJECT_PYTHON%" -m pip install -r requirements-python.txt
    pause
)

endlocal