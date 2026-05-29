@echo off
setlocal

set "INSTALL_DIR=%USERPROFILE%\Transcriptor"
set "DESKTOP_SHORTCUT=%USERPROFILE%\Desktop\Transcriptor.lnk"
set "LOG_DIR=%LOCALAPPDATA%\Transcriptor"

echo Transcriptor uninstaller
echo.

if /I "%INSTALL_DIR%"=="%USERPROFILE%" (
    echo Refusing to remove user profile folder.
    pause
    exit /b 1
)

if /I "%INSTALL_DIR%"=="C:\" (
    echo Refusing to remove drive root.
    pause
    exit /b 1
)

tasklist /FI "IMAGENAME eq Transcriber.exe" | find /I "Transcriber.exe" >nul 2>nul
if not errorlevel 1 (
    echo Closing running Transcriptor app...
    taskkill /IM Transcriber.exe /F >nul 2>nul
    timeout /t 2 /nobreak >nul
)

if exist "%DESKTOP_SHORTCUT%" (
    echo Removing Desktop shortcut...
    del /f /q "%DESKTOP_SHORTCUT%" >nul 2>nul
)

if exist "%LOG_DIR%" (
    echo Removing installer logs...
    rmdir /s /q "%LOG_DIR%"
)

if exist "%INSTALL_DIR%" (
    echo Removing app folder:
    echo %INSTALL_DIR%
    cd /d "%TEMP%"
    rmdir /s /q "%INSTALL_DIR%"
) else (
    echo App folder was not found:
    echo %INSTALL_DIR%
)

echo.
echo Transcriptor was removed.
echo Python, Git, and NVIDIA drivers were left installed because other apps may use them.
pause
