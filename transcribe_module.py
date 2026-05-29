import os
import sys
import time
import site

DEVICE = "cuda"
COMPUTE_TYPE = "float16"
MODEL_REPO_ID = os.environ.get("TRANSCRIPTOR_MODEL_REPO", "Systran/faster-whisper-large-v3")


def _add_gpu_dll_directories():
    """Make CUDA/cuDNN DLLs visible when they were installed into the venv."""
    if os.name != "nt":
        return

    candidates = [
        os.path.join(sys.prefix, "Scripts"),
        os.path.join(os.path.dirname(sys.executable), "Scripts"),
    ]

    for site_dir in site.getsitepackages():
        nvidia_dir = os.path.join(site_dir, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue

        for package_name in ("cublas", "cuda_runtime", "cudnn"):
            candidates.append(os.path.join(nvidia_dir, package_name, "bin"))

    for path in candidates:
        if os.path.isdir(path):
            os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(path)


_add_gpu_dll_directories()

from faster_whisper import WhisperModel

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

MODEL_DIR = resource_path("models")


def get_model_dir():
    if getattr(sys, "frozen", False):
        external_dir = os.path.join(os.path.dirname(sys.executable), "models")
        if os.path.exists(os.path.join(external_dir, "model.bin")):
            return external_dir
    return MODEL_DIR

# --- GLOBAL MODEL (Prevents Crash) ---
_GLOBAL_MODEL = None

def load_model_globally(status_callback=None):
    global _GLOBAL_MODEL
    if _GLOBAL_MODEL is None:
        if status_callback: status_callback("Checking transcription model...")
        ensure_model_downloaded(status_callback)

        if status_callback: status_callback("Loading model into GPU memory...")
        model_dir = get_model_dir()
        model_file = os.path.join(model_dir, "model.bin")
        if not os.path.exists(model_file):
            raise FileNotFoundError(f"Model download did not create 'model.bin' in {model_dir}")
            
        _GLOBAL_MODEL = WhisperModel(model_dir, device=DEVICE, compute_type=COMPUTE_TYPE)
    return _GLOBAL_MODEL


def ensure_model_downloaded(status_callback=None):
    model_dir = get_model_dir()
    required_files = ("model.bin", "config.json", "tokenizer.json", "vocabulary.json")
    if all(os.path.exists(os.path.join(model_dir, file_name)) for file_name in required_files):
        return

    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
        download_dir = os.path.join(base_dir, "models")
    else:
        download_dir = MODEL_DIR

    os.makedirs(download_dir, exist_ok=True)

    if status_callback:
        status_callback(f"Downloading model from {MODEL_REPO_ID}...")

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=MODEL_REPO_ID,
            local_dir=download_dir,
            local_dir_use_symlinks=False,
            allow_patterns=[
                "config.json",
                "model.bin",
                "preprocessor_config.json",
                "tokenizer.json",
                "vocabulary.json",
            ],
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not download the transcription model. Run setup_windows_gpu.bat "
            "from an internet-connected machine, then start the app again."
        ) from exc

def run_transcription(audio_path, progress_callback=None, status_callback=None, check_cancel=None):
    try:
        # 1. Load the persistent model
        model = load_model_globally(status_callback)

        if status_callback: status_callback(f"Transcribing {os.path.basename(audio_path)}...")

        initial_prompt = (
            "هذا التسجيل باللهجة الأردنية العامية. "
            "يرجى كتابة النص كما هو مسموع تماماً. "
            "المصطلحات التقنية تكتب بالإنجليزية."
        )

        segments_generator, info = model.transcribe(
            audio_path,
            language="ar",
            initial_prompt=initial_prompt,
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False 
        )

        total_duration = info.duration
        
        text_buffer = []
        last_milestone = 0

        for segment in segments_generator:
            if check_cancel and check_cancel(): 
                break

            text_buffer.append(segment.text.strip())
            
            if total_duration > 0:
                current_percent = (segment.end / total_duration) * 100
            else:
                current_percent = 0

            # --- 1% UPDATE LOGIC ---
            # We now update every 1% (much smoother)
            if (current_percent - last_milestone >= 1) or (current_percent >= 99 and last_milestone < 99):
                
                chunk_text = " ".join(text_buffer)
                
                if progress_callback:
                    # Send: (0.XX float, Text Chunk)
                    progress_callback(current_percent / 100.0, chunk_text)
                
                text_buffer = [] # Clear buffer
                last_milestone = current_percent

        # Final flush for any remaining text
        if text_buffer:
            final_chunk = " ".join(text_buffer)
            if progress_callback:
                progress_callback(1.0, final_chunk)

        if status_callback: status_callback("Done!")

    except Exception as e:
        raise e
    
    # CRITICAL: Model stays alive globally.
