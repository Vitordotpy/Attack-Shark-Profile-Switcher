"""Where the app keeps its files, on Windows and Linux, from source or built.

Windows, from source: everything next to the scripts, as it always was.
Windows, built (PyInstaller, sys.frozen): program files in the install folder,
settings in %APPDATA%\\Attack Shark, so reinstalling never touches them.
Linux: XDG locations - settings in ~/.config/attack-shark, logs in
~/.local/state/attack-shark - whichever way it was started.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

APP_NAME = "Attack Shark"
APP_FULL_NAME = "Attack Shark Profile Switcher"
APP_VERSION = "2.1.0"
PUBLISHER = "Vitordotpy"
GITHUB_REPO = "Vitordotpy/Attack-Shark-Profile-Switcher"
EXE_NAME = "Attack Shark.exe"
INSTALLER_NAME = "Instalar Attack Shark.exe"   # the Release asset the updater fetches

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
FROZEN = bool(getattr(sys, "frozen", False))
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLE_DIR = getattr(sys, "_MEIPASS", CODE_DIR)       # bundled data files
ASSETS_DIR = os.path.join(BUNDLE_DIR, "assets")
TEMPLATE_CONFIG = os.path.join(BUNDLE_DIR, "config.json")

_home = os.path.expanduser("~")
if IS_WINDOWS:
    _appdata = os.environ.get("APPDATA") or _home
    DATA_DIR = os.path.join(_appdata, APP_NAME) if FROZEN else CODE_DIR
    LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", DATA_DIR), "shark-profile-switcher")
else:
    DATA_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(_home, ".config"),
                            "attack-shark")
    LOG_DIR = os.path.join(os.environ.get("XDG_STATE_HOME")
                           or os.path.join(_home, ".local", "state"), "attack-shark")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOG_PATH = os.path.join(LOG_DIR, "switcher.log")

CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


def asset(name: str) -> str:
    return os.path.join(ASSETS_DIR, name)


def ensure_config() -> None:
    """Start from the bundled config.json when the settings folder is new."""
    if DATA_DIR == CODE_DIR:
        return
    if not os.path.exists(CONFIG_PATH) and os.path.exists(TEMPLATE_CONFIG):
        os.makedirs(DATA_DIR, exist_ok=True)
        shutil.copyfile(TEMPLATE_CONFIG, CONFIG_PATH)


def self_command(*args: str) -> list[str]:
    """Command line that re-runs this program with extra arguments."""
    if FROZEN:
        return [sys.executable, *args]
    exe = sys.executable
    if IS_WINDOWS:
        windowless = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(windowless):
            exe = windowless
    return [exe, os.path.join(CODE_DIR, "switcher.py"), *args]


def open_path(path: str) -> None:
    """Open a file or folder with the desktop's default program."""
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)


def spawn(cmd: list[str], **kw) -> subprocess.Popen:
    """Start a detached child process with no console window."""
    if IS_WINDOWS:
        kw.setdefault("creationflags", CREATE_NO_WINDOW)
    else:
        kw.setdefault("start_new_session", True)
    return subprocess.Popen(cmd, close_fds=True, **kw)
