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

    # Where the pre-wizard batch installer cloned the project. Weights left there are
    # used where they lie rather than moved: 5.3 GB is not worth copying, and a user
    # upgrading from that layout should not download a gigabyte they already have.
    legacy_root = os.environ.get("USERPROFILE")
    if legacy_root:
        candidates.append(os.path.join(legacy_root, "Transcriber", "models"))

    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), "models"))

    candidates.append(resource_path("models"))

    unique_candidates = []
    for path in candidates:
        normalized = os.path.abspath(path)
        if normalized not in unique_candidates:
            unique_candidates.append(normalized)
    return unique_candidates


def get_runtime_dir():
    """The private Python runtime the installer provisions.

    It lives beside the models rather than inside the program folder so that an
    upgrade, which replaces the program folder wholesale, never has to re-download
    the multi-gigabyte GPU stack installed into it.
    """
    return os.path.join(get_user_data_dir(), "runtime")


def get_runtime_python(windowed=False):
    """The interpreter inside the provisioned runtime, if it has been installed."""
    name = "pythonw.exe" if windowed else "python.exe"
    if os.name != "nt":
        name = "python"
    return os.path.join(get_runtime_dir(), name)


def get_download_dir():
    """Root for audio pulled off Instagram, Facebook, TikTok and YouTube.

    Beside the models rather than inside the program folder: an update replaces the
    program folder wholesale, and media the user downloaded must not vanish with it.
    Each provider owns a subfolder under here, named after itself.
    """
    return os.path.join(get_user_data_dir(), "downloads")


def get_state_dir():
    """Records of what the installer has already done, so it can skip that work."""
    return os.path.join(get_user_data_dir(), "state")


def get_log_dir():
    return os.path.join(get_user_data_dir(), "logs")
