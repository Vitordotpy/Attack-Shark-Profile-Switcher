"""Where the app keeps its files, for both the source tree and the built .exe.

Run from source, everything lives next to the scripts, as it always has.
Built with PyInstaller (sys.frozen), the program files sit in the install
folder, read-only by intent, and the user's settings live in
%APPDATA%\\Attack Shark so reinstalling or upgrading never touches them.
"""

from __future__ import annotations

import os
import shutil
import sys

APP_NAME = "Attack Shark"
APP_FULL_NAME = "Attack Shark Profile Switcher"
APP_VERSION = "2.0.0"
PUBLISHER = "Vitordotpy"
EXE_NAME = "Attack Shark.exe"

FROZEN = bool(getattr(sys, "frozen", False))
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLE_DIR = getattr(sys, "_MEIPASS", CODE_DIR)       # bundled data files
ASSETS_DIR = os.path.join(BUNDLE_DIR, "assets")

_appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
DATA_DIR = os.path.join(_appdata, APP_NAME) if FROZEN else CODE_DIR
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
TEMPLATE_CONFIG = os.path.join(BUNDLE_DIR, "config.json")

LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", DATA_DIR), "shark-profile-switcher")
LOG_PATH = os.path.join(LOG_DIR, "switcher.log")


def asset(name: str) -> str:
    return os.path.join(ASSETS_DIR, name)


def ensure_config() -> None:
    """First run of the installed app: start from the bundled config.json."""
    if FROZEN and not os.path.exists(CONFIG_PATH) and os.path.exists(TEMPLATE_CONFIG):
        os.makedirs(DATA_DIR, exist_ok=True)
        shutil.copyfile(TEMPLATE_CONFIG, CONFIG_PATH)


def self_command(*args: str) -> list[str]:
    """Command line that re-runs this program with extra arguments.

    The built .exe takes the arguments directly; from source the entry point
    is switcher.py, run windowless when pythonw.exe is available.
    """
    if FROZEN:
        return [sys.executable, *args]
    exe = sys.executable
    windowless = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(windowless):
        exe = windowless
    return [exe, os.path.join(CODE_DIR, "switcher.py"), *args]
