"""Linux desktop integration: .desktop launchers and start at login.

Follows the freedesktop.org specs, so it works on GNOME, KDE, Cinnamon, XFCE
and friends: the launcher goes in ~/.local/share/applications, start at login
is the same file in ~/.config/autostart.
"""

from __future__ import annotations

import os
import shlex
import sys

import app_paths

DESKTOP_ID = "attack-shark.desktop"
_home = os.path.expanduser("~")
APPLICATIONS_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(_home, ".local", "share"),
                                "applications")
AUTOSTART_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(_home, ".config"),
                             "autostart")
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, DESKTOP_ID)
# install.sh puts a launcher here; preferred because it survives Python moving.
LAUNCHER = os.path.join(_home, ".local", "bin", "attack-shark")


def exec_line() -> str:
    if os.path.exists(LAUNCHER):
        return shlex.quote(LAUNCHER)
    return " ".join(shlex.quote(p) for p in
                    (sys.executable, os.path.join(app_paths.CODE_DIR, "switcher.py")))


def desktop_entry(autostart: bool = False) -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={app_paths.APP_NAME}",
        "GenericName=Mouse profile switcher",
        "Comment=Troca o perfil do mouse Attack Shark automaticamente nos jogos",
        f"Exec={exec_line()}",
        f"Icon={app_paths.asset('logo.png')}",
        "Terminal=false",
        "Categories=Utility;Settings;HardwareSettings;",
        "StartupNotify=false",
    ]
    if autostart:
        lines += ["X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-Delay=5"]
    return "\n".join(lines) + "\n"


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o755)


def autostart_status() -> tuple[bool, str]:
    if not os.path.exists(AUTOSTART_FILE):
        return False, "no autostart entry"
    try:
        with open(AUTOSTART_FILE, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        return False, str(exc)
    if "Hidden=true" in text or "X-GNOME-Autostart-enabled=false" in text:
        return False, "disabled in the desktop's startup settings"
    return True, ""


def set_autostart(enable: bool) -> tuple[bool, str]:
    try:
        if enable:
            _write(AUTOSTART_FILE, desktop_entry(autostart=True))
        elif os.path.exists(AUTOSTART_FILE):
            os.remove(AUTOSTART_FILE)
    except OSError as exc:
        return False, str(exc)
    enabled, reason = autostart_status()
    return (True, "") if enabled == enable else (False, reason or "the change did not take effect")
