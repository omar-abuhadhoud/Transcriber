import os
import sys


def resource_path(relative_path):
    """Absolute path to a bundled resource, in dev and in PyInstaller builds."""
    base_path = getattr(sys, "_MEIPASS", None) or os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_install_root():
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        if os.path.basename(exe_dir).lower() == "transcriber" and os.path.basename(os.path.dirname(exe_dir)).lower() == "dist":
            return os.path.dirname(os.path.dirname(exe_dir))
        return exe_dir

    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_user_data_dir():
    """Per-user folder that survives reinstalls and upgrades.

    Model weights live here rather than beside the program, so an installer can replace
    the application without touching gigabytes the user already downloaded.
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Transcriber")


def get_model_download_dir():
    """Where newly downloaded weights are written."""
    return os.path.join(get_user_data_dir(), "models")


def get_model_candidates():
    """Folders to search for model files, most specific first."""
    candidates = []

    env_model_dir = os.environ.get("TRANSCRIBER_MODEL_DIR")
    if env_model_dir:
        candidates.append(env_model_dir)

    candidates.append(get_model_download_dir())

    # Older installs kept weights beside the program; still honoured so an upgrade
    # never re-downloads what is already on disk.
    candidates.append(os.path.join(get_install_root(), "models"))

    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), "models"))

    candidates.append(resource_path("models"))

    unique_candidates = []
    for path in candidates:
        normalized = os.path.abspath(path)
        if normalized not in unique_candidates:
            unique_candidates.append(normalized)
    return unique_candidates
