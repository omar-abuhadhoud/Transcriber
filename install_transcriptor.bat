@echo off
setlocal

set "REPO_URL=https://github.com/Omemo7/Transcriptor.git"
set "INSTALL_DIR=%USERPROFILE%\Transcriptor"
set "BOOTSTRAP_LOG_DIR=%LOCALAPPDATA%\Transcriptor\logs"
set "PYTHON_PACKAGE=Python.Python.3.10"
set "GIT_PACKAGE=Git.Git"

if not exist "%BOOTSTRAP_LOG_DIR%" mkdir "%BOOTSTRAP_LOG_DIR%" >nul 2>nul
set "BOOTSTRAP_LOG=%BOOTSTRAP_LOG_DIR%\install_transcriptor.log"

echo Transcriptor installer
echo Log file: %BOOTSTRAP_LOG%
echo.
call :log ============================================================
call :log Transcriptor installer started at %DATE% %TIME%
call :log Install folder: %INSTALL_DIR%
call :log Repo URL: %REPO_URL%

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

where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
)
if errorlevel 1 (
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

where git >nul 2>nul
if errorlevel 1 (
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
    echo Updating existing project...
    call :log Updating existing project with git pull.
    git -C "%INSTALL_DIR%" pull >> "%BOOTSTRAP_LOG%" 2>&1
) else (
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

call :log Running setup_windows_gpu.bat.
call "%INSTALL_DIR%\setup_windows_gpu.bat" >> "%BOOTSTRAP_LOG%" 2>&1
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
echo Launching Transcriptor...
call :log Launching app.
start "" "%INSTALL_DIR%\.venv\Scripts\pythonw.exe" "%INSTALL_DIR%\main.py"
call :log Installer finished successfully.
exit /b 0

:log
echo [%DATE% %TIME%] %*>> "%BOOTSTRAP_LOG%"
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
