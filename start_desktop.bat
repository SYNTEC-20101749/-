@echo off
setlocal

cd /d "%~dp0"

set "PROJECT_PYTHON=C:\Program Files\Python312\python.exe"

if exist "%PROJECT_PYTHON%" (
    "%PROJECT_PYTHON%" -m invoice_desktop.main
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3.8 -m invoice_desktop.main
    ) else (
        python -m invoice_desktop.main
    )
)

if errorlevel 1 (
    echo.
    echo Launch failed.
    echo Checked interpreter: %PROJECT_PYTHON%
    echo If needed, install dependencies with:
    echo pip install -r requirements-python.txt
    pause
)

endlocal