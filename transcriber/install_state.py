"""What the installer has already provisioned, and whether it is still valid.

The wizard asks this module three questions before it does any work:

    is the GPU runtime installed, and does it match this build's requirements.txt?
    which model weights are already on disk?
    which app version is currently installed?

Every "yes" is work skipped, which is what keeps an update small: only the app's own
source is replaced, while the ~4.6 GB runtime and ~5.3 GB of weights stay untouched.

Deliberately stdlib-only: it runs inside the installer before any dependency exists.
"""

import hashlib
import json
import os
from datetime import datetime, timezone

from transcriber.paths import (
    get_model_candidates,
    get_runtime_dir,
    get_runtime_python,
    get_state_dir,
)

STATE_FILENAME = "install.json"

# Bumped when the shape of install.json changes in a way older readers misread.
STATE_VERSION = 1


def state_path():
    return os.path.join(get_state_dir(), STATE_FILENAME)


def load_state():
    """The recorded install state, or an empty skeleton when nothing is installed.

    A corrupt or unreadable file is treated as "nothing installed" rather than an
    error: the worst outcome is that the installer redoes work, which is safe,
    whereas refusing to start would leave the user with no way forward.
    """
    empty = {"state_version": STATE_VERSION, "app": {}, "runtime": {}, "models": {}}
    try:
        with open(state_path(), "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        return empty

    if not isinstance(data, dict):
        return empty
    for key in ("app", "runtime", "models"):
        if not isinstance(data.get(key), dict):
            data[key] = {}
    return data


def save_state(state):
    """Write the state file atomically, so an interrupted install cannot corrupt it."""
    directory = get_state_dir()
    os.makedirs(directory, exist_ok=True)
    state["state_version"] = STATE_VERSION
    state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    target = state_path()
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)
    os.replace(temporary, target)
    return target


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_app_version():
    return load_state().get("app", {}).get("version") or None


def runtime_is_installed():
    """True when a usable interpreter exists in the runtime folder."""
    return os.path.exists(get_runtime_python())


def runtime_matches(requirements_path):
    """True when the installed runtime was built from this exact requirements.txt.

    Hashing the file rather than comparing version numbers means any edit at all --
    a new package, a changed pin, a different index URL -- reinstalls, and an
    unchanged file never does.
    """
    if not runtime_is_installed():
        return False
    if not os.path.exists(requirements_path):
        return False

    recorded = load_state().get("runtime", {}).get("requirements_sha256")
    if not recorded:
        return False
    return recorded == file_sha256(requirements_path)


def record_runtime(requirements_path, python_version):
    state = load_state()
    state["runtime"] = {
        "python_version": python_version,
        "requirements_sha256": file_sha256(requirements_path),
        "path": get_runtime_dir(),
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return save_state(state)


def record_app(version, install_dir):
    state = load_state()
    state["app"] = {
        "version": version,
        "install_dir": install_dir,
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return save_state(state)


def _engine_instances():
    """Every registered engine, constructed but not loaded.

    Constructing is cheap and torch-free: engine modules import only the stdlib at
    module level and pull torch in inside load(). That is what lets the installer ask
    about weights before any dependency has been installed.
    """
    import importlib

    from transcriber.registry import ENGINES

    engines = []
    for name, spec in ENGINES.items():
        module = importlib.import_module(spec.module)
        engine_class = getattr(module, spec.class_name)
        engines.append((name, spec.label, engine_class()))
    return engines


def find_model_dir(engine):
    """Where this engine's weights already are, or None.

    Delegates to the engine's own completeness rule instead of repeating it here. The
    Qwen engines, for instance, accept "config.json plus any .safetensors" rather than
    a fixed file list, and an installer that guessed differently would either
    re-download 5.3 GB it already had or declare a half-downloaded folder complete.
    """
    model_dir = engine.get_model_dir()
    if engine.has_required_model_files(model_dir):
        return model_dir
    return None


def model_status():
    """[(name, label, installed, location_or_None)] for every engine.

    Import failures are reported as "not installed" rather than raised: a broken engine
    module should cost the user one redundant download, not a dead wizard.
    """
    try:
        engines = _engine_instances()
    except Exception:
        return []

    rows = []
    for name, label, engine in engines:
        location = find_model_dir(engine)
        rows.append((name, label, location is not None, location))
    return rows


def record_model(name, location):
    state = load_state()
    state["models"][name] = {
        "path": location,
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return save_state(state)


def summary():
    """One dict describing everything the wizard needs to decide what to skip."""
    return {
        "app_version": installed_app_version(),
        "runtime_installed": runtime_is_installed(),
        "runtime_dir": get_runtime_dir(),
        "models": model_status(),
    }
