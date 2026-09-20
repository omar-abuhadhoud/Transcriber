<div align="center">

# Transcriber

**GPU-first desktop transcription for Arabic media, powered by Qwen3-ASR.**

Queue up files, or paste a link from Instagram, Facebook, TikTok or YouTube —
Transcriber pulls the audio, runs it on your own GPU, and gives you the text.
Nothing is uploaded, and nothing leaves the machine.

[![Latest release](https://img.shields.io/github/v/release/omar-abuhadhoud/Transcriber?label=download&color=2ea44f)](https://github.com/omar-abuhadhoud/Transcriber/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/omar-abuhadhoud/Transcriber/total?color=blue)](https://github.com/omar-abuhadhoud/Transcriber/releases)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)
![GPU](https://img.shields.io/badge/GPU-NVIDIA%20CUDA-76B900)
![Python](https://img.shields.io/badge/python-3.11-3776AB)

</div>

---

## What it does

- **Runs entirely on your machine.** Audio, transcripts and downloads stay local. The
  only network traffic is fetching the model weights once and checking for updates.
- **Built for Arabic.** The engine is pinned to Arabic, so English terms inside Arabic
  speech stay in Latin script, and hallucinated scripts (CJK, Cyrillic) are stripped.
- **A queue, not one file at a time.** Add a folder's worth of media, press
  *Start All Pending*, and walk away. One file runs at a time because there is one GPU.
- **Downloads from links.** Four platforms, audio only, never re-encoded, with a
  per-platform rate limit so Instagram and TikTok do not answer with HTTP 429.
- **Two model sizes and four speed tiers**, with anything your VRAM cannot afford
  greyed out instead of failing halfway through a run.
- **Survives being interrupted.** Transcripts are written to disk as they are produced,
  so a crash or a closed lid does not lose an hour of GPU time.
- **Reads right-to-left properly.** The eye button opens the transcript in Word as RTL,
  right-aligned Arabic — not a left-aligned mess you have to reformat.
- **Installs without Python, Git or a compiler.** A 3 MB wizard that needs no
  administrator rights and brings its own private runtime.

## Contents

- [Install](#install)
- [Using Transcriber](#using-transcriber)
  - [The transcription queue](#the-transcription-queue)
  - [What each row can do](#what-each-row-can-do)
  - [Bulk actions](#bulk-actions)
  - [If it is interrupted](#if-it-is-interrupted)
- [Downloading from a link](#downloading-from-a-link)
- [Transcription engines](#transcription-engines)
- [Speed tiers](#speed-tiers)
- [How transcription works](#how-transcription-works)
- [Updates](#updates)
- [Uninstall](#uninstall)
- [Run from source](#run-from-source)
- [Project layout](#project-layout)
- [Environment variables](#environment-variables)
- [Releasing a new version](#releasing-a-new-version)
- [Where things live](#where-things-live)
- [Troubleshooting](#troubleshooting)
- [Built on](#built-on)

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

## Using Transcriber

The window is two tabs over a shared shell: a **Transcription Queue** for files already
on the machine, and a **Download** page that pulls the audio out of a link and adds it to
that queue. Both pages stay built and keep running while the other is on screen, so a
download continues while you are watching the queue, and the queue's worker keeps going
while you are pasting a link.

### The transcription queue

Press **+ Add Media Files** and pick anything PyAV can read:

```
.mp3  .mp4  .wav  .m4a  .mkv  .webm  .opus  .ogg  .flac  .aac  .mov
```

Each file becomes a row showing its name and duration, and the header keeps a running
**Total** of the queue's length. Nothing starts by itself — press ▶ on a row, or
**Start All Pending** in the footer.

While a row runs it shows a live percentage, a progress bar and a stopwatch of elapsed
wall-clock time, and the header grows a bar with a `done / total` count for the queue as
a whole. Only one file is transcribed at a time: a second concurrent run would simply
run out of VRAM, so the queue is a single worker thread feeding one GPU.

The **engine** and **speed** pickers are in the header. The engine picker is disabled
while anything is queued or running, so a single batch never spans two models.

### What each row can do

| Button | Does |
| --- | --- |
| ▶ | Queues this file, or restarts it if it already ran |
| 👁 | Opens the transcript in Word as right-to-left, right-aligned Arabic |
| **Copy** | Puts the transcript on the clipboard (the button turns green to confirm) |
| **Save** | Writes it to a `.txt` file you choose |
| **X** | Cancels whatever the row is doing and removes it, in one press |

There is deliberately no separate stop button. A run nobody wants is a run nobody wants,
and asking first only keeps the GPU busy for the length of the question.

The eye button exists because Arabic pasted into Word arrives left-aligned and
left-to-right. It writes a small RTF file with the Arabic language ID and `\rtlpar` set,
then opens it — so the transcript is readable and printable without reformatting
anything by hand.

### Bulk actions

**Start All Pending** queues every idle row in order. **Cancel All** abandons the lot and
hands the working memory back to the GPU. **Save All Finished** asks for one folder and
writes every completed transcript into it as `<original name>.txt`, disambiguating with
`(2)`, `(3)` when two rows would land on the same output name — which they do as soon as
two different folders each hold an `interview.mp3`.

### If it is interrupted

Transcripts are not held in memory until the end. Each row streams its text to its own
recovery file under `%LOCALAPPDATA%\Transcriber\recovery_tmp` as the windows come back
from the GPU, and Copy, Save and 👁 all read from that file. So the partial transcript of
an hour-long file that was cancelled at 70% is still on disk and still yours.

Recovery files are keyed to a counter rather than to the file name, so two rows for two
different `interview.mp3` files cannot truncate each other's work.

Closing the window shows a short "cleaning up" dialog while the queue stops, the model is
unloaded and the temporary files go. That wait is the GPU driver reclaiming VRAM — it
only does so once the process is really gone, which is also why an unhandled crash exits
hard instead of leaving a half-dead window holding several gigabytes.

Downloads and anything else that finishes while you are looking elsewhere announce
themselves as notifications in the bottom-right corner rather than as message boxes,
because news that needs no decision should not steal focus and demand a click.

## Downloading from a link

The **Download** tab shows one square per platform. Click one, paste a link, press
Download. When the file lands it appears on the queue tab as an ordinary row, at rest,
and a notification says so — nothing starts transcribing by itself, because a download
finishing is not a decision to occupy the GPU.

Files are saved per platform, named after the video's title or caption:

```
%LOCALAPPDATA%\Transcriber\downloads\YouTube\Me at the zoo.m4a
%LOCALAPPDATA%\Transcriber\downloads\Instagram\كيف تتعلم البرمجة بسرعة.m4a
```

Captions are not filenames, so `downloader/naming.py` strips what Windows forbids,
escapes reserved device names like `CON`, cuts long captions on a word boundary and
appends a counter when two posts share a caption. Non-ASCII is deliberately kept — most
titles here are Arabic, and stripping them would name every file the same thing.

A download already knows its duration from the post's own metadata, so the queue row it
becomes is not reopened just to measure something the platform already said.

### Only the audio, and never re-encoded

Nothing is ever transcoded. YouTube publishes a real audio-only stream, which is taken
as it is. Instagram, Facebook and TikTok only serve a muxed MP4, so `downloader/remux.py`
copies the audio packets into their own container and drops the video track — a packet
copy, not a decode, which takes a few milliseconds and loses nothing. It uses PyAV,
already a dependency for transcription, so there is still no ffmpeg binary in the install.

Re-encoding everything to MP3 would cost minutes of CPU per file and buy nothing:
transcription decodes with PyAV, which reads all of these already.

### The smallest stream that is still good for speech

Platforms offer the same audio at several bitrates, and the app asks for the smallest
one above `SPEECH_BITRATE_CAP` (80 kbps) rather than the best. Everything downloaded
here is about to be resampled to 16 kHz mono and handed to an ASR model, which cannot
tell a 49 kbps stream from a 130 kbps one — so "best audio" would spend two and a half
times the bandwidth on data discarded a moment later.

Measured on YouTube, projected over five hours of audio:

| Selector | itag | Bitrate | 5 hours |
| --- | --- | --- | --- |
| `bestaudio[ext=m4a]` (what "best" means) | 140 | 130 kbps | 279 MB |
| what the app asks for | 139 | 49 kbps | **105 MB** |

If you want the audio to keep and listen to rather than only to transcribe, set
`best_quality=True` on `DownloadOptions` and the selector asks for the largest stream
instead. The fallback chain ends in plain `bestaudio/best`, so a platform that
advertises no bitrate at all — Instagram and TikTok usually do not — is unaffected.

### Long recordings

A five-hour YouTube video is about 105 MB of audio and downloads as one continuous
stream. Four things make that survivable:

- **Resume, not restart.** `continuedl` is on and the part-file is named after the
  post's id, so a connection dropped four hours in continues from where it stopped
  rather than starting again. Retries are raised to 10 for the same reason.
- **Range requests.** `http_chunk_size` is 10 MB, which keeps YouTube from throttling
  a single long-lived socket down to a trickle.
- **Progress stays responsive.** yt-dlp calls its progress hook thousands of times on
  a file that size; the pool collapses those to ten UI updates a second, so the window
  is not spending its time redrawing a label.
- **It never blocks anything.** It occupies one of the four slots and one of YouTube's
  two, so short downloads queued behind it still run, and transcription is untouched.

If a single large file is still the bottleneck, the one remaining lever is opening
several connections to it, which needs an external downloader:

```bat
winget install aria2.aria2
set TRANSCRIBER_USE_ARIA2=1
```

With that set, yt-dlp hands the transfer to aria2c with 16 connections. It is opt-in
rather than automatic because progress reporting through an external downloader is much
coarser — a good trade for a five-hour recording, a bad one for a reel.

Worth saying plainly: for a five-hour file the download is not the slow part.
Transcribing five hours of audio on the GPU takes far longer than fetching 105 MB, and
that is the number to optimise if the wait matters.

### How many at once

| Limit | Default | Override |
| --- | --- | --- |
| Downloads transferring at once | 4 | `TRANSCRIBER_MAX_DOWNLOADS` |
| Downloads from one platform | 2 | `TRANSCRIBER_MAX_PER_PLATFORM` |
| Fragments fetched per download | 8 | `FRAGMENTS_AT_ONCE` in `downloader/ytdlp.py` |

Anything above the limits waits in its platform's queue and starts when a slot frees.
The per-platform cap exists because Instagram and TikTok answer a burst with HTTP 429.

It is enforced by giving each platform its own two-worker executor plus a global
semaphore, rather than by taking a second lock inside one shared pool. That distinction
matters: with four shared workers and a per-platform semaphore, four queued Reels would
occupy every worker and block, and a YouTube link queued behind them would never start.

Downloads are threads, not processes. They wait on sockets, so they hold no GIL, and
four extra interpreters would cost a second of startup each for nothing. They never
import torch and never open a CUDA context, so they cannot contend with a transcription
for VRAM — the one resource in this app that is genuinely scarce.

### Posts that need a login

Instagram and Facebook serve very little to a logged-out client. Tick **Use my browser
login** in the download box and pick a browser, and yt-dlp borrows that browser's
session. Chrome and Edge encrypt their cookie store while running, so close them first —
Firefox is the one that reliably works.

### Adding a platform

`downloader/base.py` defines `MediaDownloader`, which has exactly one abstract method:

```python
def download_audio(self, url, options=None, progress_callback=None, check_cancel=None)
```

A provider is a class with that method plus four attributes — `name`, `label`,
`folder_name`, and the `url_patterns` that are its own. Everything else (fetching,
naming, progress, cancellation, error translation) lives in `downloader/ytdlp.py`, so an
adapter is usually thirty lines. Register it in `PROVIDERS` in `downloader/registry.py`
and the tile appears on the page by itself: the page is built from the registry and
names no platform anywhere.

Nothing under `downloader/` knows what a platform looks like. Colours, icons,
placeholder links and help text live in `ctk_ui/provider_style.py`, and
`view_for(provider)` pairs an adapter with its styling to produce the flat object the
widgets read. The split is deliberate:

- `downloader/` is imported by the installer, which has no Tk and no window, so a hex
  colour sitting on an adapter class is dead weight there;
- an adapter should be usable from a script or a different front end without dragging
  a palette along;
- restyling the UI should not touch a single file under `downloader/`.

A platform with no entry in `STYLES` still works — it falls back to `DEFAULT_STYLE`, so
registering the adapter is enough to get a usable tile, and choosing its colours is a
separate, optional step.

Pasting a link into the wrong tile is caught as you type — the registry recognises which
platform a URL belongs to, so the box says which tile you wanted instead of failing a
minute later.

### About the tile icons

The marks on the tiles are original generic glyphs — a play triangle, a camera, a music
note, a speech bubble — on each platform's familiar colour, with its name underneath.
They are not the platforms' logos, which are registered trademarks this project has no
licence to redraw. If you hold that licence, drop a square PNG at
`ctk_ui/assets/providers/<name>.png` and it is used instead, with no code change.

The glyphs are keyed by shape (`play`, `camera`, `note`, `bubble`) rather than by
platform, so two platforms can share a mark and a new one can pick an existing shape by
naming it in `provider_style.py`.

### Keeping downloads working

`yt-dlp` is pinned with a floor rather than an exact version, on purpose. These sites
change what they serve every few weeks and yt-dlp tracks them release by release, so a
hard pin is a promise that downloads stop working a few months after the build. If a
platform breaks, updating yt-dlp inside the runtime is usually the whole fix:

```bat
%LOCALAPPDATA%\Transcriber\runtime\python.exe -m pip install -U yt-dlp
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
Tiers that do not fit are greyed out in the list and say how much VRAM they would need,
and the largest tier that still leaves comfortable headroom is marked *recommended*.

Both pickers are the same widget, [`StyledOptionMenu`](ctk_ui/dropdown.py): CustomTkinter's
option-menu button, with the list drawn by the app rather than by Tk. Tk's menu paints a
near-white 3D frame whatever `borderwidth` and `relief` say, which glares on a dark
window, and it cannot grey out a single entry — which is the whole point here. Every
font goes through [`ctk_ui/theme.py`](ctk_ui/theme.py) so the app cannot drift back into
a mix of families.

The list closes on any of: clicking outside, clicking the button again, Escape, moving
the window, or choosing a row. That redundancy is deliberate — an earlier version relied
on `<FocusOut>` alone, and an override-redirect window does not reliably receive it, so
the list could sit on screen with nothing able to dismiss it. Because the two
engines differ in weight size, the list is recomputed when the engine changes; a tier that
no longer fits falls back to the recommended one.

Note that batch size slightly perturbs output: results are identical run-to-run for a fixed
tier, but changing tier can alter roughly 0.1-0.3% of characters, because different batch
shapes select different GPU kernels and float addition is not associative.

## How transcription works

A file goes through four stages, and the row's progress bar tracks the last of them:

1. **Decode.** [`transcriber/audio.py`](transcriber/audio.py) opens the container with
   PyAV — which bundles FFmpeg, so nothing has to be installed system-wide — and
   resamples to 16 kHz mono float32, which is what the model expects whatever went in.
2. **Split on silence.** Qwen3-ASR decodes a whole request in one call, so long audio has
   to be cut. [`transcriber/vad.py`](transcriber/vad.py) runs Silero VAD
   (`transcriber/assets/silero_vad_v6.onnx`, MIT licensed) over onnxruntime to find the
   cut points, and the audio becomes windows of at most 30 seconds that start and end in
   silence rather than mid-word.
3. **Batch through the GPU.** Windows are sent `batch_size` at a time, as chosen by the
   speed tier. Each window produces one progress event, which is what keeps the bar
   moving on a long file, and cancellation is polled between them so **X** takes effect
   in a moment rather than at the end of the file.
4. **Clean and append.** The language is forced to `ar`, which keeps English terms in
   Latin script, so anything decoded outside Arabic, Latin, digits and shared punctuation
   is a hallucinated script rather than speech and is dropped. The text is appended to the
   row's recovery file as it arrives.

### The engine contract

`transcriber/base.py` defines the `TranscriptionEngine` contract, `transcriber/registry.py`
maps an engine name to its class, and the app only ever calls
`transcribe_module.run_transcription(...)`, so the UI is independent of the engine.

To add an engine, subclass `TranscriptionEngine` in `transcriber/engines/`, implement `load()`
and `transcribe()`, and register it in `ENGINES` in `transcriber/registry.py`. Engine modules
are imported lazily, so an engine's dependencies are only required when that engine is actually
selected. The installer picks the new engine up on its own: it asks the registry what exists
and downloads whatever is missing.

Memory is handed back in two steps, because they are different questions. Cancelling a run
or emptying the queue releases the *working* memory — activations, the KV cache, the
allocator blocks behind the chunks — and leaves the weights in VRAM, so the next file does
not pay to load the model again. Only shutting down, or switching engine, unloads the model
itself.

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
speech models, the GPU runtime and the audio saved from links, showing each one's
measured size. All three default to **keeping** the data, so an uninstall never silently
discards a 10 GB download and a later reinstall starts immediately. Logs, settings and
recovery files always go.

The audio box matters most of the three: models and runtimes can always be downloaded
again, but a reel that has since been deleted cannot.

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

## Project layout

| Path | Contents |
| --- | --- |
| [`main.py`](main.py) | Entry point: claims the Windows app identity and the single-instance mutex, then opens the window |
| [`ctk_ui/app.py`](ctk_ui/app.py) | The shell — window, update banner, tab strip, notifications, shutdown sequence |
| [`ctk_ui/queue_page.py`](ctk_ui/queue_page.py) | The transcription queue and its single worker thread |
| [`ctk_ui/media_item.py`](ctk_ui/media_item.py) | One row: state, progress, stopwatch, Copy / Save / view / cancel |
| [`ctk_ui/download_page.py`](ctk_ui/download_page.py) | The platform tiles, the link box and the list of transfers |
| [`ctk_ui/dropdown.py`](ctk_ui/dropdown.py), [`theme.py`](ctk_ui/theme.py) | The shared option menu, and the one place fonts and colours are defined |
| [`transcriber/registry.py`](transcriber/registry.py) | Engine name to class, and which engine is active |
| [`transcriber/engines/`](transcriber/engines/) | The Qwen3-ASR engine |
| [`transcriber/audio.py`](transcriber/audio.py), [`vad.py`](transcriber/vad.py) | Decoding, resampling, and splitting on silence |
| [`transcriber/speed.py`](transcriber/speed.py) | VRAM budget per tier, and which tiers this GPU can afford |
| [`downloader/registry.py`](downloader/registry.py) | Platform adapters, and which one a URL belongs to |
| [`downloader/ytdlp.py`](downloader/ytdlp.py), [`pool.py`](downloader/pool.py) | Shared fetch logic, and the concurrency limits above it |
| [`installer/`](installer/) | The Inno Setup wizard, the provisioning script and the build script |

## Environment variables

None of these are required; all are read at startup.

| Variable | Effect |
| --- | --- |
| `TRANSCRIBER_ENGINE` | Engine selected at startup, e.g. `qwen3-asr-0.6b` |
| `TRANSCRIBER_MODEL_DIR` | Look for model weights here first |
| `TRANSCRIBER_NO_UPDATE_CHECK` | Set to `1` to never contact GitHub at startup |
| `TRANSCRIBER_MAX_DOWNLOADS` | Downloads transferring at once (default 4) |
| `TRANSCRIBER_MAX_PER_PLATFORM` | Downloads from one platform at once (default 2) |
| `TRANSCRIBER_USE_ARIA2` | Set to `1` to hand transfers to aria2c with 16 connections |

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

## Where things live

| Path | Contents | Survives an update |
| --- | --- | --- |
| `%LOCALAPPDATA%\Programs\Transcriber` | The program | Replaced |
| `%LOCALAPPDATA%\Transcriber\runtime` | Python + PyTorch | Kept |
| `%LOCALAPPDATA%\Transcriber\models` | Model weights | Kept |
| `%LOCALAPPDATA%\Transcriber\downloads` | Audio saved from links, one folder per platform | Kept |
| `%LOCALAPPDATA%\Transcriber\recovery_tmp` | Transcripts of files still in the queue | Kept |
| `%LOCALAPPDATA%\Transcriber\state` | What is installed | Kept |
| `%LOCALAPPDATA%\Transcriber\logs` | Setup and crash logs | Kept |

If an install fails, the log to send is
`%LOCALAPPDATA%\Transcriber\logs\setup-<version>.log`.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| A platform stopped downloading | Update yt-dlp inside the runtime — see [Keeping downloads working](#keeping-downloads-working) |
| Instagram or Facebook returns almost nothing | Tick **Use my browser login** and pick Firefox; close Chrome and Edge first, as they encrypt their cookie store while running |
| Turbo and Ultra are greyed out | Those tiers need more VRAM than this GPU has; the list says how much |
| The install failed | Send `%LOCALAPPDATA%\Transcriber\logs\setup-<version>.log` |
| The app crashed | `%LOCALAPPDATA%\Transcriber\logs\runtime.log` has the traceback |
| A transcript seems lost | Look in `%LOCALAPPDATA%\Transcriber\recovery_tmp` — partial transcripts are written there as they are produced |

## Built on

[Qwen3-ASR](https://huggingface.co/Qwen) for recognition,
[Silero VAD](https://github.com/snakers4/silero-vad) (MIT) for splitting on silence,
[PyTorch](https://pytorch.org/) and [Transformers](https://github.com/huggingface/transformers)
for inference, [PyAV](https://github.com/PyAV-Org/PyAV) for decoding and remuxing,
[yt-dlp](https://github.com/yt-dlp/yt-dlp) for link downloads,
[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for the interface, and
[Inno Setup](https://jrsoftware.org/isinfo.php) for the wizard.
