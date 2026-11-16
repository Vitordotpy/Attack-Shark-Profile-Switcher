"""Install / uninstall plumbing shared by the installer and the app itself.

Everything is per-user (HKCU, %LOCALAPPDATA%), so neither installing nor
uninstalling ever needs administrator rights.
"""

from __future__ import annotations

import os
import subprocess
import winreg

import app_paths

CREATE_NO_WINDOW = 0x08000000

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
RUN_VALUE = app_paths.APP_NAME
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AttackSharkProfileSwitcher"
SHORTCUT_NAME = app_paths.APP_NAME + ".lnk"
# Left behind by the Python (install.bat) version; removed so the two never
# both start at login and fight over the mouse.
LEGACY_STARTUP_LINK = "Attack Shark Profile Switcher.lnk"


def default_install_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Programs", app_paths.APP_NAME)


def shell_folder(name: str) -> str:
    """Desktop / Programs / Startup, honouring OneDrive or GPO redirection."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
            path = winreg.QueryValueEx(key, name)[0]
        if path:
            return os.path.expandvars(path)
    except OSError:
        pass
    fallback = {
        "Desktop": os.path.join(os.path.expanduser("~"), "Desktop"),
        "Programs": os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                                 "Start Menu", "Programs"),
        "Startup": os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                                "Start Menu", "Programs", "Startup"),
    }
    return fallback[name]


def desktop_shortcut() -> str:
    return os.path.join(shell_folder("Desktop"), SHORTCUT_NAME)


def start_menu_shortcut() -> str:
    return os.path.join(shell_folder("Programs"), SHORTCUT_NAME)


# -- shortcuts ----------------------------------------------------------------

def create_shortcut(link: str, target: str, workdir: str = "", icon: str = "",
                    description: str = "") -> None:
    """Write a .lnk through the shell's own COM object.

    Values travel in environment variables, never inside the command text, so
    no path can break the quoting.
    """
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:X6_LNK);"
              "$s.TargetPath = $env:X6_TARGET; $s.WorkingDirectory = $env:X6_DIR;"
              "$s.IconLocation = $env:X6_ICON; $s.Description = $env:X6_DESC; $s.Save()")
    env = dict(os.environ, X6_LNK=link, X6_TARGET=target, X6_DIR=workdir,
               X6_ICON=icon or target, X6_DESC=description)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env=env, check=True, timeout=60, capture_output=True,
                   creationflags=CREATE_NO_WINDOW)


def remove_file(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# -- start with Windows (HKCU Run key) ----------------------------------------

def set_run_at_login(exe: str | None, enable: bool) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enable:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, f'"{exe}"')
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass
    # Clear a stale "disabled in Task Manager" flag so the checkbox means it.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_APPROVED_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE)
    except OSError:
        pass


def run_at_login_status(exe: str) -> tuple[bool, str]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value = winreg.QueryValueEx(key, RUN_VALUE)[0]
    except OSError:
        return False, "not registered to start at login"
    if os.path.normcase(value.strip('"')) != os.path.normcase(exe):
        return False, "the startup entry points at another copy"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_APPROVED_KEY) as key:
            flag = winreg.QueryValueEx(key, RUN_VALUE)[0]
        if flag and flag[0] & 0x01:
            return False, "switched off in Task Manager > Startup"
    except OSError:
        pass
    return True, ""


# -- "Installed apps" entry ---------------------------------------------------

def register_uninstaller(install_dir: str, size_kb: int) -> None:
    exe = os.path.join(install_dir, app_paths.EXE_NAME)
    values = {
        "DisplayName": app_paths.APP_FULL_NAME,
        "DisplayVersion": app_paths.APP_VERSION,
        "Publisher": app_paths.PUBLISHER,
        "DisplayIcon": exe,
        "InstallLocation": install_dir,
        "UninstallString": f'"{exe}" --uninstall',
        "QuietUninstallString": f'"{exe}" --uninstall --quiet',
        "URLInfoAbout": "https://github.com/Vitordotpy/Attack-Shark-Profile-Switcher",
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name in ("NoModify", "NoRepair"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)


def installed_dir() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return winreg.QueryValueEx(key, "InstallLocation")[0]
    except OSError:
        return None


def remove_registration() -> None:
    set_run_at_login(None, False)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    for link in (desktop_shortcut(), start_menu_shortcut()):
        remove_file(link)


def remove_legacy() -> None:
    """Retire the Python (install.bat) version: its shortcuts and running copy."""
    for folder in ("Startup", "Desktop", "Programs"):
        remove_file(os.path.join(shell_folder(folder), LEGACY_STARTUP_LINK))
    try:
        import psutil
    except ImportError:
        return
    victims = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            cmd = proc.info["cmdline"] or []
            if not name.startswith("python"):
                continue
            scripts = [c for c in cmd if c.lower().endswith("switcher.py")]
            # Only our switcher: a switcher.py with sharkctl.py next to it.
            if scripts and os.path.exists(os.path.join(os.path.dirname(scripts[0]), "sharkctl.py")):
                proc.kill()
                victims.append(proc)
        except (psutil.Error, OSError):
            pass
    psutil.wait_procs(victims, timeout=5)


# -- processes ------------------------------------------------------------------

def stop_running(exe_path: str, keep_pid: int | None = None) -> None:
    """End any running copy of the installed app (needed to replace its files)."""
    try:
        import psutil
    except ImportError:
        subprocess.run(["taskkill", "/F", "/IM", app_paths.EXE_NAME],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
        return
    target = os.path.normcase(os.path.abspath(exe_path))
    victims = []
    for proc in psutil.process_iter(["pid", "exe", "name"]):
        try:
            exe = proc.info["exe"]
            if (exe and os.path.normcase(exe) == target and proc.info["pid"] != keep_pid):
                proc.kill()
                victims.append(proc)
        except (psutil.Error, OSError):
            pass
    psutil.wait_procs(victims, timeout=5)


def delete_later(folder: str) -> None:
    """Remove a folder a few seconds after this process exits (its own .exe is in it)."""
    # A plain string: cmd.exe parses its own command line, and a list would be
    # re-quoted by subprocess in a way cmd does not undo.
    subprocess.Popen(f'cmd.exe /c ping -n 4 127.0.0.1 >nul & rd /s /q "{folder}"',
                     creationflags=CREATE_NO_WINDOW, close_fds=True)
