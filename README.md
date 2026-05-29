# Transcriptor

GPU-first desktop transcription app for Arabic media files. The GitHub repo is kept light: Python packages, CUDA runtime DLLs, and the Whisper model are installed after download instead of being committed to source control.

## Requirements

- Windows 10/11
- Python 3.10 or newer
- NVIDIA GPU with a current NVIDIA driver
- Internet connection for first setup

## One-command setup

```bat
setup_windows_gpu.bat
```

The setup creates `.venv`, installs the app dependencies from `requirements.txt`, downloads the model into `models/`, and checks that CTranslate2 can see a CUDA GPU.

Start the app after setup:

```bat
.venv\Scripts\python.exe main.py
```

## Simple user installer

For a new non-technical user, edit `install_transcriptor.bat` and replace:

```bat
https://github.com/YOUR_USERNAME/Transcriptor.git
```

with your real GitHub repo URL. Then the user can run:

```bat
install_transcriptor.bat
```

That installer checks for Python, Git, and an NVIDIA GPU driver, downloads the project into `%USERPROFILE%\Transcriptor`, runs the GPU setup, and launches the app.

On later updates it keeps the heavy local files:

- `.venv` is reused unless `requirements.txt` changes.
- `models/` is reused unless model files are missing.
- The update normally downloads only changed source code.

If installation fails, ask the user to send these logs:

```text
%LOCALAPPDATA%\Transcriptor\logs\install_transcriptor.log
%USERPROFILE%\Transcriptor\.transcriptor_state\logs\setup_windows_gpu.log
```

## Model

The default model is:

```text
Systran/faster-whisper-large-v3
```

Use another Faster Whisper model at setup time:

```bat
setup_windows_gpu.bat --model Systran/faster-whisper-medium
```

You can also set `TRANSCRIPTOR_MODEL_REPO` before running the app. If `models/model.bin` is missing, the app will try to download the configured model on first transcription.

## Build an executable

Install the build tools:

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Then build:

```bat
.venv\Scripts\pyinstaller.exe Transcriber.spec
```

Do not commit generated folders such as `.venv`, `models`, `build`, or `dist`.
