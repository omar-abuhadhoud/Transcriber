import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS_FILE = ROOT / "requirements.txt"
DEV_REQUIREMENTS_FILE = ROOT / "requirements-dev.txt"
STATE_DIR = ROOT / ".transcriptor_state"
LOG_DIR = STATE_DIR / "logs"
LOG_FILE = LOG_DIR / "setup_windows_gpu.log"
REQUIREMENTS_HASH_FILE = STATE_DIR / "requirements.sha256"
BUILD_HASH_FILE = STATE_DIR / "build.sha256"
EXE_PATH = ROOT / "dist" / "Transcriber" / "Transcriber.exe"
EXE_DIR = EXE_PATH.parent
DEFAULT_MODEL_REPO = os.environ.get("TRANSCRIPTOR_MODEL_REPO", "Systran/faster-whisper-large-v3")
BUILD_INPUT_FILES = [
    "main.py",
    "media_item.py",
    "transcribe_module.py",
    "util.py",
    "global_vars.py",
    "stopwatch.py",
    "Transcriber.spec",
    "requirements.txt",
    "requirements-dev.txt",
    "icon.ico",
]
MODEL_FILES = [
    "config.json",
    "model.bin",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.json",
]
GPU_DLL_NAMES = (
    "cublas64_12.dll",
    "cublasLt64_12.dll",
    "cudart64_12.dll",
    "cudnn64_9.dll",
)
GPU_DLL_PATTERNS = (
    "cuda*.dll",
    "cublas*.dll",
    "cudnn*.dll",
)
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


def find_gpu_dlls():
    search_roots = [
        VENV_DIR / "Scripts",
        VENV_DIR / "Lib" / "site-packages",
    ]
    found = {}

    for root in search_roots:
        if not root.exists():
            continue
        for dll_name in GPU_DLL_NAMES:
            if dll_name in found:
                continue
            matches = list(root.rglob(dll_name))
            if matches:
                found[dll_name] = matches[0]

    return found


def copy_gpu_dlls_to_venv_scripts():
    if os.name != "nt":
        return

    scripts_dir = VENV_DIR / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    search_roots = [
        VENV_DIR / "Lib" / "site-packages" / "nvidia",
        VENV_DIR / "Lib" / "site-packages" / "torch" / "lib",
        VENV_DIR / "Lib" / "site-packages" / "ctranslate2",
    ]

    copied = 0
    for root in search_roots:
        if not root.exists():
            continue

        for pattern in GPU_DLL_PATTERNS:
            for source_path in root.rglob(pattern):
                target_path = scripts_dir / source_path.name
                if target_path.exists() and target_path.stat().st_size == source_path.stat().st_size:
                    continue
                shutil.copy2(source_path, target_path)
                copied += 1
                log(f"Copied GPU DLL to venv Scripts: {source_path} -> {target_path}")

    if copied:
        log(f"Copied {copied} GPU DLL(s) into {scripts_dir}")
    else:
        log(f"GPU DLLs already available in {scripts_dir} or no package DLLs needed copying.")


def verify_gpu_dlls_available():
    copy_gpu_dlls_to_venv_scripts()
    found = find_gpu_dlls()
    missing = [dll_name for dll_name in GPU_DLL_NAMES if dll_name not in found]
    if missing:
        raise RuntimeError(
            "Missing CUDA runtime DLLs after dependency install: "
            + ", ".join(missing)
            + ". Run setup again, or install the latest NVIDIA CUDA/cuDNN pip packages."
        )
    for dll_name, path in found.items():
        log(f"CUDA DLL available: {dll_name} -> {path}")


def verify_exe_gpu_dlls():
    dll_dirs = [EXE_DIR, EXE_DIR / "_internal"]
    missing = [
        dll_name
        for dll_name in GPU_DLL_NAMES
        if not any((dll_dir / dll_name).exists() for dll_dir in dll_dirs)
    ]
    if missing:
        raise RuntimeError(
            "The exe build is missing CUDA DLLs: "
            + ", ".join(missing)
            + ". Rebuild with the updated Transcriber.spec."
        )
    log("Exe CUDA DLL check passed.")


def stop_running_transcriptor():
    if os.name != "nt":
        return

    result = run_quiet(["tasklist", "/FI", "IMAGENAME eq Transcriber.exe"])
    if "Transcriber.exe" not in result.stdout:
        log("No running Transcriber.exe process found.")
        return

    progress(86, "Closing running Transcriptor app")
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
                stop_running_transcriptor()
            log(f"Build folder is locked; retry {attempt}/5: {exc}")
            time.sleep(2)

    raise PermissionError(
        f"Could not remove {dist_app_dir}. Close Transcriptor and any Explorer/terminal window inside that folder, then rerun setup."
    )


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
    progress(80, "Checking CUDA GPU runtime")
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
    progress(85, "CUDA GPU runtime ready")
    verify_gpu_dlls_available()


def build_exe(python, force=False):
    current_hash = build_sha256()

    if not force and EXE_PATH.exists() and BUILD_HASH_FILE.exists():
        previous_hash = BUILD_HASH_FILE.read_text(encoding="utf-8").strip()
        if previous_hash == current_hash:
            progress(95, "Exe already up to date")
            log(f"Using existing exe: {EXE_PATH}")
            return

    stop_running_transcriptor()
    install_build_requirements(python)
    remove_locked_build_folder()
    progress(92, "Building Transcriptor exe")
    run([python, "-m", "PyInstaller", "--noconfirm", "Transcriber.spec"])
    if not EXE_PATH.exists():
        raise FileNotFoundError(f"PyInstaller did not create expected exe: {EXE_PATH}")
    verify_exe_gpu_dlls()

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
    shortcut_path = desktop / "Transcriptor.lnk"
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
        file.write(f"Transcriptor setup started at {datetime.now().isoformat(timespec='seconds')}\n")
        file.write(f"Project folder: {ROOT}\n")
    progress(5, "Starting GPU setup")

    parser = argparse.ArgumentParser(description="Install Transcriptor for a Windows CUDA workstation.")
    parser.add_argument("--model", default=DEFAULT_MODEL_REPO, help="Hugging Face model repo to download.")
    parser.add_argument("--skip-model", action="store_true", help="Create models/ but do not download the model.")
    parser.add_argument("--skip-gpu-check", action="store_true", help="Skip the CUDA visibility check.")
    parser.add_argument("--force-deps", action="store_true", help="Reinstall Python dependencies even if requirements.txt did not change.")
    parser.add_argument("--skip-exe", action="store_true", help="Skip building the local exe and Desktop shortcut.")
    parser.add_argument("--force-exe", action="store_true", help="Rebuild the exe even if source files did not change.")
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
