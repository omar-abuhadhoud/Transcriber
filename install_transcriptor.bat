@echo off
setlocal EnableDelayedExpansion

set "REPO_URL=https://github.com/Omemo7/Transcriptor.git"
set "INSTALL_DIR=%USERPROFILE%\Transcriptor"
set "BOOTSTRAP_LOG_DIR=%LOCALAPPDATA%\Transcriptor\logs"
set "PYTHON_PACKAGE=Python.Python.3.10"
set "GIT_PACKAGE=Git.Git"
set "SKIP_MODEL=0"

for %%A in (%*) do (
    if /I "%%~A"=="--skip-model" set "SKIP_MODEL=1"
)

if not exist "%BOOTSTRAP_LOG_DIR%" mkdir "%BOOTSTRAP_LOG_DIR%" >nul 2>nul
set "BOOTSTRAP_LOG=%BOOTSTRAP_LOG_DIR%\install_transcriptor.log"

echo Transcriptor installer
echo Log file: %BOOTSTRAP_LOG%
echo.
call :log ============================================================
call :log Transcriptor installer started at %DATE% %TIME%
call :log Install folder: %INSTALL_DIR%
call :log Repo URL: %REPO_URL%
call :progress 2 "Starting installer"

call :progress 5 "Checking Windows package manager"
where winget >nul 2>nul
if errorlevel 1 (
    echo Windows App Installer / winget was not found.
    echo Install Python 3.10 and Git manually, then run setup_windows_gpu.bat from the project folder.
    call :log ERROR: winget was not found.
    call :fail
    pause
    exit /b 1
)
call :log winget found.

call :progress 10 "Checking Python"
where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
)
if errorlevel 1 (
    call :progress 15 "Installing Python"
    echo Installing Python 3.10...
    call :log Installing Python package: %PYTHON_PACKAGE%
    winget install --id %PYTHON_PACKAGE% --exact --source winget --accept-package-agreements --accept-source-agreements >> "%BOOTSTRAP_LOG%" 2>&1
    if errorlevel 1 (
        echo Failed to install Python.
        call :log ERROR: Python installation failed.
        call :fail
        pause
        exit /b 1
    )
    call :log Python installation finished.
) else (
    call :log Python already installed.
)

call :progress 25 "Checking Git"
where git >nul 2>nul
if errorlevel 1 (
    call :progress 30 "Installing Git"
    echo Installing Git...
    call :log Installing Git package: %GIT_PACKAGE%
    winget install --id %GIT_PACKAGE% --exact --source winget --accept-package-agreements --accept-source-agreements >> "%BOOTSTRAP_LOG%" 2>&1
    if errorlevel 1 (
        echo Failed to install Git.
        call :log ERROR: Git installation failed.
        call :fail
        pause
        exit /b 1
    )
    call :log Git installation finished.
) else (
    call :log Git already installed.
)

call :progress 40 "Checking NVIDIA GPU driver"
nvidia-smi >nul 2>nul
if errorlevel 1 (
    echo.
    echo NVIDIA driver/GPU was not detected.
    echo Please install the latest NVIDIA driver from:
    echo https://www.nvidia.com/Download/index.aspx
    echo.
    echo After installing the driver and restarting, run this installer again.
    call :log ERROR: nvidia-smi failed. NVIDIA driver/GPU not detected.
    call :fail
    pause
    exit /b 1
)
call :log NVIDIA driver/GPU detected.

if exist "%INSTALL_DIR%\.git" (
    call :progress 50 "Updating Transcriptor source"
    echo Updating existing project...
    call :log Updating existing project with git pull.
    git -C "%INSTALL_DIR%" pull >> "%BOOTSTRAP_LOG%" 2>&1
) else (
    call :progress 50 "Downloading Transcriptor source"
    echo Downloading Transcriptor...
    call :log Cloning project.
    git clone "%REPO_URL%" "%INSTALL_DIR%" >> "%BOOTSTRAP_LOG%" 2>&1
)

if errorlevel 1 (
    echo Failed to download/update the project.
    echo Check REPO_URL inside install_transcriptor.bat.
    call :log ERROR: Git download/update failed.
    call :fail
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\setup_windows_gpu.bat" (
    echo setup_windows_gpu.bat was not found in the downloaded project.
    echo Make sure the latest setup files were committed and pushed to GitHub.
    call :log ERROR: setup_windows_gpu.bat was not found after clone/update.
    call :log Project folder contents:
    dir /b "%INSTALL_DIR%" >> "%BOOTSTRAP_LOG%" 2>&1
    call :fail
    pause
    exit /b 1
)

call :progress 65 "Running app setup"
call :log Running setup_windows_gpu.bat.
call "%INSTALL_DIR%\setup_windows_gpu.bat" %*
if errorlevel 1 (
    echo Setup failed. See logs:
    echo %BOOTSTRAP_LOG%
    echo %INSTALL_DIR%\.transcriptor_state\logs\setup_windows_gpu.log
    call :log ERROR: setup_windows_gpu.bat failed.
    call :fail
    pause
    exit /b 1
)

echo.
call :progress 100 "Installation complete"
if "%SKIP_MODEL%"=="1" (
    echo Model download was skipped.
    echo Copy your model files into:
    echo %INSTALL_DIR%\models
    if exist "%INSTALL_DIR%\dist\Transcriber\Transcriber.exe" (
        echo.
        echo Desktop shortcut created for:
        echo %INSTALL_DIR%\dist\Transcriber\Transcriber.exe
    )
    call :log Model download skipped. Waiting for manual model copy.
    start "" "%INSTALL_DIR%\models"
    pause
    exit /b 0
)

echo Launching Transcriptor...
call :log Launching app.
if exist "%INSTALL_DIR%\dist\Transcriber\Transcriber.exe" (
    start "" "%INSTALL_DIR%\dist\Transcriber\Transcriber.exe"
) else (
    start "" "%INSTALL_DIR%\.venv\Scripts\pythonw.exe" "%INSTALL_DIR%\main.py"
)
call :log Installer finished successfully.
exit /b 0

:log
echo [%DATE% %TIME%] %*>> "%BOOTSTRAP_LOG%"
exit /b 0

:progress
set "PERCENT=%~1"
set "MESSAGE=%~2"
set /a FILLED=PERCENT/5
set "BAR="
for /l %%I in (1,1,20) do (
    if %%I LEQ !FILLED! (
        set "BAR=!BAR!#"
    ) else (
        set "BAR=!BAR!-"
    )
)
echo [!BAR!] !PERCENT!%% !MESSAGE!
call :log Progress !PERCENT!%% - !MESSAGE!
exit /b 0

:fail
echo.
echo Installation did not complete.
echo Please send this log file for support:
echo %BOOTSTRAP_LOG%
if exist "%INSTALL_DIR%\.transcriptor_state\logs\setup_windows_gpu.log" (
    echo %INSTALL_DIR%\.transcriptor_state\logs\setup_windows_gpu.log
)
exit /b 0
