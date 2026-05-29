import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS_FILE = ROOT / "requirements.txt"
STATE_DIR = ROOT / ".transcriptor_state"
LOG_DIR = STATE_DIR / "logs"
LOG_FILE = LOG_DIR / "setup_windows_gpu.log"
REQUIREMENTS_HASH_FILE = STATE_DIR / "requirements.sha256"
DEFAULT_MODEL_REPO = os.environ.get("TRANSCRIPTOR_MODEL_REPO", "Systran/faster-whisper-large-v3")
MODEL_FILES = [
    "config.json",
    "model.bin",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.json",
]
MODEL_README_FILE = ROOT / "models" / "README_MODEL_FILES.txt"


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


def download_model(python, model_repo):
    models_dir = ROOT / "models"
    if all((models_dir / file_name).exists() for file_name in MODEL_FILES):
        progress(85, "Model files already downloaded")
        log("Model files already exist in models/.")
        return

    progress(50, "Downloading transcription model")
    log(f"Downloading model from {model_repo} into models/...")
    code = f"""
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id={model_repo!r},
    local_dir={str(models_dir)!r},
    local_dir_use_symlinks=False,
    allow_patterns={MODEL_FILES!r},
)
"""
    run([python, "-c", code])
    progress(85, "Model files ready")


def prepare_model_folder_for_manual_copy(model_repo):
    models_dir = ROOT / "models"
    models_dir.mkdir(exist_ok=True)
    MODEL_README_FILE.write_text(
        "\n".join(
            [
                "Transcriptor model folder",
                "",
                "Model download was skipped during setup.",
                "Copy your Faster Whisper model files into this folder before starting transcription.",
                "",
                "Required files:",
                *[f"- {file_name}" for file_name in MODEL_FILES],
                "",
                f"Default model repo: {model_repo}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    progress(85, "Model download skipped")
    log(f"Model download skipped. Copy model files into: {models_dir}")


def verify_gpu_runtime(python):
    progress(90, "Checking CUDA GPU runtime")
    code = r"""
import os
import sys
import site

if os.name == "nt":
    candidates = [os.path.join(sys.prefix, "Scripts")]
    for site_dir in site.getsitepackages():
        nvidia_dir = os.path.join(site_dir, "nvidia")
        for package_name in ("cublas", "cuda_runtime", "cudnn"):
            candidates.append(os.path.join(nvidia_dir, package_name, "bin"))
    for path in candidates:
        if os.path.isdir(path):
            os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(path)

import ctranslate2

cuda_devices = 0
if hasattr(ctranslate2, "get_cuda_device_count"):
    cuda_devices = ctranslate2.get_cuda_device_count()

print(f"CTranslate2 version: {ctranslate2.__version__}")
print(f"CUDA devices visible to CTranslate2: {cuda_devices}")

if cuda_devices < 1:
    raise SystemExit(
        "No CUDA GPU is visible. Install/update the NVIDIA driver, then rerun setup."
    )
"""
    run([python, "-c", code])
    progress(95, "CUDA GPU runtime ready")


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write("\n" + "=" * 72 + "\n")
        file.write(f"Transcriptor setup started at {datetime.now().isoformat(timespec='seconds')}\n")
        file.write(f"Project folder: {ROOT}\n")
    progress(5, "Starting GPU setup")

    parser = argparse.ArgumentParser(description="Install Transcriptor for a Windows CUDA workstation.")
    parser.add_argument("--model", default=DEFAULT_MODEL_REPO, help="Hugging Face model repo to download.")
    parser.add_argument("--skip-model", action="store_true", help="Create models/ but do not download the model.")
    parser.add_argument("--skip-gpu-check", action="store_true", help="Skip the CUDA visibility check.")
    parser.add_argument("--force-deps", action="store_true", help="Reinstall Python dependencies even if requirements.txt did not change.")
    args = parser.parse_args()

    try:
        python = ensure_venv()
        install_requirements(python, force=args.force_deps)

        if args.skip_model:
            prepare_model_folder_for_manual_copy(args.model)
        else:
            download_model(python, args.model)

        if not args.skip_gpu_check:
            verify_gpu_runtime(python)

        progress(100, "Setup finished successfully")
        log("Setup finished successfully.")
    except Exception as exc:
        log("")
        log(f"Setup failed: {exc}")
        log(f"Full log: {LOG_FILE}")
        raise


if __name__ == "__main__":
    main()
