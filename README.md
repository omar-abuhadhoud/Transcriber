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

After setup, the local exe is created here:

```text
%USERPROFILE%\Transcriptor\dist\Transcriber\Transcriber.exe
```

A Desktop shortcut named `Transcriptor` is also created. On later updates, the exe is rebuilt only when source or build files changed.

To install/update the app without downloading the model:

```bat
install_transcriptor.bat --skip-model
```

This creates the expected `models` folder. Copy your existing Faster Whisper model files into:

```text
%USERPROFILE%\Transcriptor\models
```

The folder should contain files like `model.bin`, `config.json`, `tokenizer.json`, `vocabulary.json`, and `preprocessor_config.json`.

The exe also uses this same install-level `models` folder. Do not put the model inside `dist\Transcriber\models` unless you intentionally want an exe-local fallback.

When `--skip-model` is used, the installer opens the `models` folder and does not launch the app automatically. Start the app from the Desktop shortcut after copying the model files.

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

To skip exe creation during setup:

```bat
setup_windows_gpu.bat --skip-exe
```

## Uninstall

Run:

```bat
uninstall_transcriptor.bat
```

This removes `%USERPROFILE%\Transcriptor`, the Desktop shortcut, and installer logs. It does not remove Python, Git, or NVIDIA drivers because those are shared system tools.
