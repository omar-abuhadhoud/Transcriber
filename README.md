# Transcriber

GPU-first desktop transcription app for Arabic media files, powered by Qwen3-ASR. The GitHub repo is kept light: Python packages and the model weights are installed after download instead of being committed to source control.

## Requirements

- Windows 10/11
- Python 3.10 or newer
- NVIDIA GPU with a current NVIDIA driver
- Internet connection for first setup

## One-command setup

```bat
setup\setup_windows_gpu.bat
```

The setup creates `.venv`, installs the app dependencies from `requirements.txt`, downloads the default engine's model into `models/`, and checks that torch can see a CUDA GPU.

Start the app after setup:

```bat
.venv\Scripts\python.exe main.py
```

## Simple user installer

For a new non-technical user, edit `setup\install_transcriber.bat` and replace:

```bat
https://github.com/YOUR_USERNAME/Transcriber.git
```

with your real GitHub repo URL. Then the user can run:

```bat
setup\install_transcriber.bat
```

That installer checks for Python, Git, and an NVIDIA GPU driver, downloads the project into `%USERPROFILE%\Transcriber`, runs the GPU setup, and launches the app.

After setup, the local exe is created here:

```text
%USERPROFILE%\Transcriber\dist\Transcriber\Transcriber.exe
```

A Desktop shortcut named `Transcriber` is also created. On later updates, the exe is rebuilt only when source or build files changed.

Setup downloads the weights for **both** engines, into their own subfolders:

```text
%USERPROFILE%\Transcriber\models\qwen3-asr-1.7b
%USERPROFILE%\Transcriber\models\qwen3-asr-0.6b
```

That is about 5.4 GB in total, downloaded once. A model already present is not downloaded
again, so rerunning setup is cheap.

The exe also uses this same install-level `models` folder. Do not put the model inside `dist\Transcriber\models` unless you intentionally want an exe-local fallback.

On later updates it keeps the heavy local files:

- `.venv` is reused unless `requirements.txt` changes.
- `models/` is reused unless model files are missing.
- The update normally downloads only changed source code.

If installation fails, ask the user to send these logs:

```text
%LOCALAPPDATA%\Transcriber\logs\install_transcriber.log
%USERPROFILE%\Transcriber\.transcriber_state\logs\setup_windows_gpu.log
```

## Transcription engines

Two engines ship with the app, picked from the dropdown in the app header:

| Engine | Model repo | Weights folder | VRAM |
| --- | --- | --- | --- |
| Qwen3-ASR 1.7B (default) | `Qwen/Qwen3-ASR-1.7B-hf` | `models/qwen3-asr-1.7b/` | ~4.7 GB |
| Qwen3-ASR 0.6B | `Qwen/Qwen3-ASR-0.6B-hf` | `models/qwen3-asr-0.6b/` | ~3.2 GB |

Each model downloads on first use into its own folder, so engines never overwrite each other.
The engine picker is disabled while anything is queued or transcribing, so a single run never
spans two models. Switching unloads the previous model first, because only one of these fits
in 8 GB of VRAM.

Set the engine used at startup with:

```bat
set TRANSCRIBER_ENGINE=qwen3-asr-0.6b
```

## Speed tiers

The **Speed** picker next to the engine dropdown controls how many 30-second windows are
sent to the GPU in one `generate()` call. More at once is faster, because the model weights
are read from VRAM once per batch instead of once per window, but each window in flight
needs its own working memory (KV cache).

| Tier | Windows at once | VRAM with 1.7B | with 0.6B |
| --- | --- | --- | --- |
| Fast | 4 | ~4.7 GB | ~2.4 GB |
| Faster | 8 | ~5.6 GB | ~3.3 GB |
| Turbo | 16 | ~7.4 GB | ~5.1 GB |
| Ultra | 24 | ~9.2 GB | ~6.9 GB |

`transcriber/speed.py` estimates each tier as `engine weights + 0.225 GB per window`
(measured on 30-second windows, the worst case) and compares it with the installed VRAM,
read once at startup via `nvidia-smi` so no CUDA context is created just to draw the UI.
Tiers that do not fit are shown disabled with a tooltip explaining why, and the largest
tier that still leaves comfortable headroom is marked *recommended*. Because the two
engines differ in weight size, the list is recomputed when the engine changes; a tier that
no longer fits falls back to the recommended one.

Note that batch size slightly perturbs output: results are identical run-to-run for a fixed
tier, but changing tier can alter roughly 0.1-0.3% of characters, because different batch
shapes select different GPU kernels and float addition is not associative.

### How the plug works

`transcriber/base.py` defines the `TranscriptionEngine` contract, `transcriber/registry.py`
maps an engine name to its class, and the app only ever calls
`transcribe_module.run_transcription(...)`, so the UI is independent of the engine.

Qwen3-ASR decodes a whole request in one call, so audio is split on silence into windows of
at most 30 seconds, which are then sent to the GPU in batches. `transcriber/audio.py` decodes
with PyAV and `transcriber/vad.py` runs Silero VAD (`transcriber/assets/silero_vad_v6.onnx`,
MIT licensed) over onnxruntime to find the cut points. Each window produces one progress event,
which keeps the progress bar moving on long files.

To add an engine, subclass `TranscriptionEngine` in `transcriber/engines/`, implement `load()`
and `transcribe()`, and register it in `ENGINES` in `transcriber/registry.py`. Engine modules
are imported lazily, so an engine's dependencies are only required when that engine is actually
selected. A new engine must also be added to `hiddenimports` in `Transcriber.spec`, because
PyInstaller cannot see the runtime `importlib` lookup.

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
setup\setup_windows_gpu.bat --skip-exe
```

## Uninstall

Run:

```bat
setup\uninstall_transcriber.bat
```

This removes `%USERPROFILE%\Transcriber`, the Desktop shortcut, and installer logs. It does not remove Python, Git, or NVIDIA drivers because those are shared system tools.
