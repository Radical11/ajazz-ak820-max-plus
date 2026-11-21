"""
storage.py - Where AK820 Studio keeps its data (%APPDATA%\\AK820Studio on Windows).
Small JSON helpers with atomic writes.
"""

from __future__ import annotations

import json
import os
import tempfile

if os.name == "nt":
    ROOT = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "AK820Studio")
else:
    ROOT = os.path.join(os.path.expanduser("~/.config"), "ak820-studio")

PROFILES_DIR = os.path.join(ROOT, "profiles")
os.makedirs(PROFILES_DIR, exist_ok=True)


def data_path(name: str) -> str:
    return os.path.join(ROOT, name)


def legacy_path(name: str) -> str:
    return os.path.join(os.path.expanduser("~/.config/ajazz-ak820"), name)


def read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
