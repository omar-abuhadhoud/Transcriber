"""User preferences kept outside the application install directory."""

import json
import os
import tempfile

from transcriber.paths import get_user_data_dir


def load_settings(log_error=None):
    path = os.path.join(get_user_data_dir(), "settings.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            settings = json.load(handle)
        if not isinstance(settings, dict):
            raise ValueError("Settings must be a JSON object")
        return settings
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        if log_error:
            log_error("Could not load preferences from " + path, exc)
        return {}


def save_settings(settings):
    """Replace the file atomically so an interrupted save keeps the previous copy."""
    folder = get_user_data_dir()
    os.makedirs(folder, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=folder, prefix="settings_", suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = handle.name
            json.dump(settings, handle, indent=2)
            handle.write("\n")
        os.replace(temp_path, os.path.join(folder, "settings.json"))
    finally:
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
