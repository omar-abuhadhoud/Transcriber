# Transcriber

GPU-first desktop transcription app for Arabic media files, powered by Qwen3-ASR.

## Install

Download `TranscriberSetup-<version>.exe` from the
[releases page](https://github.com/omar-abuhadhoud/Transcriber/releases) and run it.

That is the whole procedure. The wizard needs no administrator rights, and it does not
require Python, Git or a compiler on the machine — Transcriber brings its own private
Python runtime, which cannot interfere with any Python already installed.

The setup file is about 3 MB. It downloads the rest during installation:

| Component | Size | Where it goes |
| --- | --- | --- |
| Application | ~1 MB | `%LOCALAPPDATA%\Programs\Transcriber` |
| Python runtime + PyTorch (CUDA) | ~2.5 GB download | `%LOCALAPPDATA%\Transcriber\runtime` |
| Qwen3-ASR 1.7B weights | ~3.8 GB | `%LOCALAPPDATA%\Transcriber\models` |
| Qwen3-ASR 0.6B weights | ~1.5 GB | `%LOCALAPPDATA%\Transcriber\models` |

Requirements: Windows 10 or 11 (64-bit), an NVIDIA GPU with a current driver, and an
internet connection for the first install.

## Updates

The app checks the releases page at startup and shows a bar across the top when a newer
version exists. **Update now** downloads that release's setup file and runs it.

An update replaces the application only. The wizard finds the runtime and the weights
already on disk and keeps them, so a typical update downloads a few megabytes instead of
ten gigabytes. Concretely, it reinstalls:

- **the GPU runtime** only when `requirements.txt` changed — it is compared by hash, so
  any edit at all triggers a reinstall and an unchanged file never does;
- **a model** only when its weights are missing or incomplete, judged by the engine's own
  rule rather than a copy of it in the installer.

The runtime and the models live outside the program folder, which is what makes this
safe: the installer replaces the program folder wholesale and cannot disturb them.

Set `TRANSCRIBER_NO_UPDATE_CHECK=1` to stop the app contacting GitHub at startup.

## Uninstall

Uninstall from **Settings → Apps**, or run `unins000.exe` in the install folder.

The uninstaller asks what to do with the downloaded data, with separate boxes for the
speech models and the GPU runtime, showing each one's measured size. Both default to
**keeping** the data, so an uninstall never silently discards a 10 GB download and a
later reinstall starts immediately. Logs, settings and recovery files always go.

## Releasing a new version

1. Bump `__version__` in [`transcriber/version.py`](transcriber/version.py). Everything
   else reads it from there: the setup file name, the exe's version resource, the
   registry entry the next update compares against, and the app's own update check.
2. Build and publish:

   ```powershell
   powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1 -Release
   ```

   Without `-Release` it only builds `installer\build\TranscriberSetup-<version>.exe`.
   With it, the GitHub CLI creates the release and uploads the setup file.

The release tag must be `v<version>` and match `__version__` exactly. The app compares
the two, so a mismatch either offers an update forever or never offers one.

Building requires [Inno Setup 6](https://jrsoftware.org/isinfo.php)
(`winget install JRSoftware.InnoSetup`), and `-Release` also requires the GitHub CLI
(`winget install GitHub.cli`).

### How the wizard is put together

| File | Role |
| --- | --- |
| [`installer/Transcriber.iss`](installer/Transcriber.iss) | The wizard: pages, upgrade detection, runtime download, uninstall page |
| [`installer/provision.py`](installer/provision.py) | Installs the runtime's packages and the weights, and decides what to skip |
| [`installer/build_installer.ps1`](installer/build_installer.ps1) | Stages the app payload, compiles, optionally publishes |
| [`transcriber/install_state.py`](transcriber/install_state.py) | What is already installed; read by both the wizard and the app |
| [`transcriber/update.py`](transcriber/update.py) | Finds newer releases and hands them to the wizard |

The wizard bootstraps itself: it downloads a standalone CPython build (which, unlike
python.org's embeddable zip, includes the tkinter that the UI needs), unpacks it with the
`tar.exe` built into Windows, and from then on runs `provision.py` under that runtime.
`provision.py` reports progress through a small file the wizard polls, because Inno
Setup cannot read a running process's output.

The shortcut points at a copy of `pythonw.exe` named `Transcriber.exe`, so the taskbar
shows the app rather than a generic Python process.

## Run from source

For development, without the installer:

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Model weights download on first use into `%LOCALAPPDATA%\Transcriber\models`. A checkout
is not a managed install, so the app links to the releases page instead of offering to
update itself.

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

Point the app at weights somewhere else with `TRANSCRIBER_MODEL_DIR`.

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
Tiers that do not fit are greyed out in the dropdown and say how much VRAM they would
need, and the largest tier that still leaves comfortable headroom is marked
*recommended*. Both pickers are plain `CTkOptionMenu`s so the header reads as one strip;
the speed picker used to be a button opening a hand-built popup window, which looked
different and could be left on screen because an override-redirect window does not
reliably receive the focus-out event that closed it. Because the two
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
selected. The installer picks the new engine up on its own: it asks the registry what exists
and downloads whatever is missing.

## Where things live

| Path | Contents | Survives an update |
| --- | --- | --- |
| `%LOCALAPPDATA%\Programs\Transcriber` | The program | Replaced |
| `%LOCALAPPDATA%\Transcriber\runtime` | Python + PyTorch | Kept |
| `%LOCALAPPDATA%\Transcriber\models` | Model weights | Kept |
| `%LOCALAPPDATA%\Transcriber\state` | What is installed | Kept |
| `%LOCALAPPDATA%\Transcriber\logs` | Setup and crash logs | Kept |

If an install fails, the log to send is
`%LOCALAPPDATA%\Transcriber\logs\setup-<version>.log`.
