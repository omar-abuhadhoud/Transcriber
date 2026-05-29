@echo off
setlocal
cd /d "%~dp0"

set "SETUP_LOG_DIR=%CD%\.transcriptor_state\logs"
if not exist "%SETUP_LOG_DIR%" mkdir "%SETUP_LOG_DIR%" >nul 2>nul
set "SETUP_BAT_LOG=%SETUP_LOG_DIR%\setup_windows_gpu_bat.log"

echo Setup log: %SETUP_LOG_DIR%\setup_windows_gpu.log
echo [%DATE% %TIME%] setup_windows_gpu.bat started.>> "%SETUP_BAT_LOG%"

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe setup_windows_gpu.py %*
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 setup_windows_gpu.py %*
    ) else (
        python setup_windows_gpu.py %*
    )
)

if errorlevel 1 (
    echo.
    echo Setup failed. Check the error above.
    echo Full logs:
    echo %SETUP_LOG_DIR%\setup_windows_gpu.log
    echo %SETUP_BAT_LOG%
    echo [%DATE% %TIME%] setup_windows_gpu.bat failed.>> "%SETUP_BAT_LOG%"
    exit /b 1
)

echo.
echo Setup complete. Start the app with:
echo .venv\Scripts\python.exe main.py
echo [%DATE% %TIME%] setup_windows_gpu.bat finished successfully.>> "%SETUP_BAT_LOG%"
