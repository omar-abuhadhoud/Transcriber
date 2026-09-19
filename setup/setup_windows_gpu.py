import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS_FILE = ROOT / "requirements.txt"
DEV_REQUIREMENTS_FILE = ROOT / "requirements-dev.txt"
STATE_DIR = ROOT / ".transcriber_state"
LOG_DIR = STATE_DIR / "logs"
LOG_FILE = LOG_DIR / "setup_windows_gpu.log"
REQUIREMENTS_HASH_FILE = STATE_DIR / "requirements.sha256"
BUILD_HASH_FILE = STATE_DIR / "build.sha256"
EXE_PATH = ROOT / "dist" / "Transcriber" / "Transcriber.exe"
BUILD_INPUT_FILES = [
    "main.py",
    "global_vars.py",
    "ctk_ui/app.py",
    "ctk_ui/media_item.py",
    "ctk_ui/speed_picker.py",
    "ctk_ui/stopwatch.py",
    "transcriber/transcribe_module.py",
    "transcriber/audio.py",
    "transcriber/base.py",
    "transcriber/paths.py",
    "transcriber/registry.py",
    "transcriber/speed.py",
    "transcriber/vad.py",
    "transcriber/engines/qwen_asr.py",
    "transcriber/assets/silero_vad_v6.onnx",
    "transcriber/util.py",
    "Transcriber.spec",
    "requirements.txt",
    "requirements-dev.txt",
    "icon.ico",
]


def log(message=""):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = str(message)
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def progress(percent, message):
    width = 30
    filled = max(0, min(width, round(width * percent / 100)))
    bar = "#" * filled + "-" * (width - filled)
    log(f"[{bar}] {percent:3d}% {message}")


def run(command, **kwargs):
    command = [str(part) for part in command]
    log("+ " + " ".join(command))

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )

    assert process.stdout is not None
    for line in process.stdout:
        log(line.rstrip())

    return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)


def run_quiet(command):
    command = [str(part) for part in command]
    log("+ " + " ".join(command))
    return subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def venv_python():
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_venv():
    python = venv_python()
    if python.exists():
        progress(20, "Virtual environment ready")
        log(f"Using existing virtual environment: {VENV_DIR}")
        return python

    progress(15, "Creating virtual environment")
    log("Creating virtual environment in .venv...")
    run([sys.executable, "-m", "venv", VENV_DIR])
    progress(20, "Virtual environment ready")
    return python


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_sha256():
    digest = hashlib.sha256()
    for relative_path in BUILD_INPUT_FILES:
        path = ROOT / relative_path
        if not path.exists():
            continue
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def install_requirements(python, force=False):
    current_hash = file_sha256(REQUIREMENTS_FILE)

    if not force and REQUIREMENTS_HASH_FILE.exists():
        previous_hash = REQUIREMENTS_HASH_FILE.read_text(encoding="utf-8").strip()
        if previous_hash == current_hash:
            progress(45, "Python dependencies already installed")
            log("Python dependencies are already up to date.")
            return

    progress(25, "Installing Python package tools")
    run([python, "-m", "pip", "install", "--upgrade", "pip"])
    progress(35, "Installing app dependencies")
    run([python, "-m", "pip", "install", "-r", "requirements.txt"])
    STATE_DIR.mkdir(exist_ok=True)
    REQUIREMENTS_HASH_FILE.write_text(current_hash, encoding="utf-8")
    progress(45, "Python dependencies ready")


def install_build_requirements(python):
    if not DEV_REQUIREMENTS_FILE.exists():
        raise FileNotFoundError(f"Missing build requirements file: {DEV_REQUIREMENTS_FILE}")

    progress(88, "Installing exe build tools")
    run([python, "-m", "pip", "install", "-r", "requirements-dev.txt"])


def stop_running_transcriber():
    if os.name != "nt":
        return

    result = run_quiet(["tasklist", "/FI", "IMAGENAME eq Transcriber.exe"])
    if "Transcriber.exe" not in result.stdout:
        log("No running Transcriber.exe process found.")
        return

    progress(86, "Closing running Transcriber app")
    log("Transcriber.exe is running. Closing it before rebuilding the exe.")
    kill_result = run_quiet(["taskkill", "/IM", "Transcriber.exe", "/F"])
    if kill_result.stdout:
        for line in kill_result.stdout.splitlines():
            log(line)
    time.sleep(2)


def remove_locked_build_folder():
    dist_app_dir = ROOT / "dist" / "Transcriber"
    if not dist_app_dir.exists():
        return

    for attempt in range(1, 6):
        try:
            shutil.rmtree(dist_app_dir)
            log(f"Removed old build folder: {dist_app_dir}")
            return
        except PermissionError as exc:
            if attempt == 1:
                stop_running_transcriber()
            log(f"Build folder is locked; retry {attempt}/5: {exc}")
            time.sleep(2)

    raise PermissionError(
        f"Could not remove {dist_app_dir}. Close Transcriber and any Explorer/terminal window inside that folder, then rerun setup."
    )


def engine_names():
    """Every engine the app offers. Safe before the venv exists: registry is stdlib-only."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from transcriber.registry import ENGINES

    return list(ENGINES)


def download_models(python):
    """Download weights for every engine, so the picker works offline after setup.

    Each engine knows its repo, its required files and its folder under models/, and
    skips the download when those files are already present.
    """
    names = engine_names()
    span = 35 / max(1, len(names))

    for index, name in enumerate(names):
        progress(int(50 + span * index), f"Downloading model {index + 1} of {len(names)}")
        log(f"Downloading model for engine '{name}'...")
        code = f"""
from transcriber.registry import get_engine

engine = get_engine({name!r})
print(f"Engine: {{engine.label}} ({{engine.model_repo}})")
target = engine.ensure_model_downloaded(status_callback=print)
print(f"Model ready in {{target}}")
"""
        run([python, "-c", code])

    progress(85, "Model files ready")


def verify_gpu_runtime(python):
    progress(80, "Checking CUDA GPU runtime")
    # torch loads its own CUDA libraries from torch/lib, so nothing needs copying first.
    code = r"""
import torch

print(f"torch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

if not torch.cuda.is_available():
    raise SystemExit(
        "No CUDA GPU is visible to torch. Install/update the NVIDIA driver, then rerun setup."
    )

print(f"CUDA device: {torch.cuda.get_device_name(0)}")
print(f"CUDA build: {torch.version.cuda}")
"""
    run([python, "-c", code])
    progress(85, "CUDA GPU runtime ready")


def build_exe(python, force=False):
    current_hash = build_sha256()

    if not force and EXE_PATH.exists() and BUILD_HASH_FILE.exists():
        previous_hash = BUILD_HASH_FILE.read_text(encoding="utf-8").strip()
        if previous_hash == current_hash:
            progress(95, "Exe already up to date")
            log(f"Using existing exe: {EXE_PATH}")
            return

    stop_running_transcriber()
    install_build_requirements(python)
    remove_locked_build_folder()
    progress(92, "Building Transcriber exe")
    run([python, "-m", "PyInstaller", "--noconfirm", "Transcriber.spec"])
    if not EXE_PATH.exists():
        raise FileNotFoundError(f"PyInstaller did not create expected exe: {EXE_PATH}")

    STATE_DIR.mkdir(exist_ok=True)
    BUILD_HASH_FILE.write_text(current_hash, encoding="utf-8")
    progress(95, "Exe ready")
    log(f"Built exe: {EXE_PATH}")


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def create_desktop_shortcut():
    if os.name != "nt":
        return

    if not EXE_PATH.exists():
        log("Desktop shortcut skipped because exe does not exist.")
        return

    desktop = Path(os.environ.get("USERPROFILE", str(ROOT))) / "Desktop"
    shortcut_path = desktop / "Transcriber.lnk"
    icon_path = ROOT / "icon.ico"
    script = (
        "$WshShell = New-Object -ComObject WScript.Shell; "
        f"$Shortcut = $WshShell.CreateShortcut({ps_quote(shortcut_path)}); "
        f"$Shortcut.TargetPath = {ps_quote(EXE_PATH)}; "
        f"$Shortcut.WorkingDirectory = {ps_quote(EXE_PATH.parent)}; "
        f"$Shortcut.IconLocation = {ps_quote(icon_path)}; "
        "$Shortcut.Save()"
    )

    progress(98, "Creating Desktop shortcut")
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])
    log(f"Desktop shortcut ready: {shortcut_path}")


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write("\n" + "=" * 72 + "\n")
        file.write(f"Transcriber setup started at {datetime.now().isoformat(timespec='seconds')}\n")
        file.write(f"Project folder: {ROOT}\n")
    progress(5, "Starting GPU setup")

    parser = argparse.ArgumentParser(description="Install Transcriber for a Windows CUDA workstation.")
    parser.add_argument("--skip-gpu-check", action="store_true", help="Skip the CUDA visibility check.")
    parser.add_argument("--force-deps", action="store_true", help="Reinstall Python dependencies even if requirements.txt did not change.")
    parser.add_argument("--skip-exe", action="store_true", help="Skip building the local exe and Desktop shortcut.")
    parser.add_argument("--force-exe", action="store_true", help="Rebuild the exe even if source files did not change.")
    args = parser.parse_args()

    try:
        python = ensure_venv()
        install_requirements(python, force=args.force_deps)

        download_models(python)

        if not args.skip_gpu_check:
            verify_gpu_runtime(python)

        if not args.skip_exe:
            build_exe(python, force=args.force_exe)
            create_desktop_shortcut()

        progress(100, "Setup finished successfully")
        log("Setup finished successfully.")
    except Exception as exc:
        log("")
        log(f"Setup failed: {exc}")
        log(f"Full log: {LOG_FILE}")
        raise


if __name__ == "__main__":
    main()
