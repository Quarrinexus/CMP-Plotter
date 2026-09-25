"""Remember the chosen data and output folders between sessions."""

import json
import os
from pathlib import Path

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
SETTINGS_FILE = CONFIG / "goose-plotter" / "settings.json"
OLD_FILE = CONFIG / "cmp-plotter" / "settings.json"  # from when it was CMP Plotter


def load_settings():
    """The saved settings, e.g. {'data_dir': '...', 'output_dir': '...'}, or {}."""
    path = SETTINGS_FILE if SETTINGS_FILE.exists() or not OLD_FILE.exists() else OLD_FILE
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # first run, or a file mangled by hand
        return {}
    return settings if isinstance(settings, dict) else {}


def save_settings(settings):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
