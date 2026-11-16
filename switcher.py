"""Switch the Attack Shark V8's profile automatically when a game is running.

Watches for the executables listed in config.json. While any of them is running
the mouse sits on `game_profile`; otherwise it returns to `default_profile`.
Runs from the system tray.

    python switcher.py              # normal run, with tray icon
    python switcher.py --dry-run    # log decisions, never touch the mouse
    python switcher.py --no-tray    # headless, for testing
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import json
import logging
import os
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from PIL import Image

import psutil

import app_paths

if app_paths.IS_WINDOWS:
    import winreg
import detect_games
import overlay as overlay_module
import sharkctl
from sharkctl import HidError

HERE = app_paths.CODE_DIR
CONFIG_PATH = app_paths.CONFIG_PATH
LOG_DIR = app_paths.LOG_DIR
LOG_PATH = app_paths.LOG_PATH

DEFAULT_CONFIG = {
    "default_profile": 1,
    "game_profile": 2,
    "poll_seconds": 2,
    "games": [],
    # Flat keys, not a nested "popup" object: load_config merges shallowly, so a
    # nested dict in a user's config would replace these defaults wholesale.
    "popup_enabled": True,
    "popup_duration_ms": 1800,
    "check_updates": True,
}

UPDATE_FIRST_CHECK_S = 20           # after start, so login is not slowed down
UPDATE_INTERVAL_S = 24 * 60 * 60

log = logging.getLogger("switcher")

# "Local\" scopes the lock to the logon session, so separate users can each run
# their own copy while a single user cannot start two.
MUTEX_NAME = r"Local\shark-profile-switcher-single-instance"
_instance_mutex = None          # module-level: the handle must outlive this call


def acquire_single_instance() -> bool:
    """Claim the single-instance lock. False means a copy is already running.

    A named mutex rather than a PID or lock file: Windows drops it when the
    process ends by any route - clean exit, crash, or Stop-Process - so there is
    never a stale lock to detect and clean up.
    """
    global _instance_mutex
    if not app_paths.IS_WINDOWS:
        return _acquire_lock_file()
    error_already_exists = 183

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                      ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p

    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        # Never block startup over a failure to create the lock itself.
        log.warning("could not create the instance lock (error %d); continuing",
                    ctypes.get_last_error())
        return True
    if ctypes.get_last_error() == error_already_exists:
        kernel32.CloseHandle(handle)
        return False

    _instance_mutex = handle
    return True


def _acquire_lock_file() -> bool:
    """Linux: an exclusive flock, released by the kernel when we exit."""
    global _instance_mutex
    import fcntl
    run_dir = os.environ.get("XDG_RUNTIME_DIR") or app_paths.LOG_DIR
    os.makedirs(run_dir, exist_ok=True)
    handle = open(os.path.join(run_dir, "attack-shark.lock"), "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _instance_mutex = handle
    return True


# The file name enable_start_at_boot.ps1 creates in the Startup folder - kept
# in sync with that script rather than queried from it, since it never changes.
BOOT_SHORTCUT_NAME = "Attack Shark Profile Switcher.lnk"

# Windows keeps a per-shortcut on/off switch here, written when a Startup item
# is toggled in Task Manager > Startup or Settings > Startup Apps. Bit 0 of the
# first byte set means off; a missing key or value means it was never toggled,
# which is on. Crucially the entry is keyed by file name and outlives the .lnk,
# so deleting and recreating the shortcut does not clear it - which is why
# toggling this checkbox off and on again cannot by itself fix a blocked entry.
STARTUP_APPROVED_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                        r"\StartupApproved\StartupFolder")


def startup_folder() -> str:
    """The user's Startup folder, honouring shell-folder redirection (Windows).

    Read from the shell's own record rather than joined onto %APPDATA%, so this
    agrees with the [Environment]::GetFolderPath('Startup') the PowerShell
    scripts use - that follows a redirected folder where the join would not.
    """
    if not app_paths.IS_WINDOWS:
        return ""
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        ) as key:
            path = winreg.QueryValueEx(key, "Startup")[0]
        if path:
            return os.path.expandvars(path)
    except OSError:
        pass
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup")


BOOT_SHORTCUT_PATH = os.path.join(startup_folder(), BOOT_SHORTCUT_NAME)


def _boot_shortcut_blocked() -> bool:
    """Whether Windows has been told not to run our Startup item."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_KEY) as key:
            value = winreg.QueryValueEx(key, BOOT_SHORTCUT_NAME)[0]
    except OSError:
        return False            # never toggled, so Windows will run it
    return bool(value) and bool(value[0] & 0x01)


def _boot_shortcut_is_ours() -> bool:
    """Whether the shortcut launches *this* copy's switcher.py.

    Scans the .lnk's bytes for our script path instead of pulling in pywin32 to
    parse the shell-link format: the command line is stored as UTF-16, so a
    substring test is enough to tell our own shortcut from one left behind by a
    copy run out of a different folder. Errs towards True - a shortcut that
    cannot be read must not make a working checkbox report as off.
    """
    try:
        with open(BOOT_SHORTCUT_PATH, "rb") as handle:
            blob = handle.read()
    except OSError:
        return True
    needle = os.path.join(HERE, "switcher.py").lower().encode("utf-16-le")
    return needle in blob.lower()


def boot_status() -> tuple[bool, str]:
    """Whether it will really start at login, and why not when it won't.

    All three conditions have to hold. Checking only the first - that the file
    is there - is what let a shortcut Windows refuses to run keep reporting
    itself as enabled.

    Deliberately says nothing about the other locations
    disable_start_at_boot.ps1 sweeps (registry Run keys, Scheduled Tasks): this
    tool only ever creates the shortcut, so an entry elsewhere is something
    this checkbox could not speak to anyway.
    """
    if not app_paths.IS_WINDOWS:
        import linux_desktop
        return linux_desktop.autostart_status()
    if app_paths.FROZEN:
        # The installed .exe starts through the HKCU Run key, not a shortcut.
        return _frozen_boot_status()
    if not os.path.exists(BOOT_SHORTCUT_PATH):
        return False, "no startup shortcut"
    if _boot_shortcut_blocked():
        return False, "switched off in Task Manager > Startup"
    if not _boot_shortcut_is_ours():
        return False, "the startup shortcut points at another copy"
    return True, ""


def _frozen_boot_status() -> tuple[bool, str]:
    import setup_common
    return setup_common.run_at_login_status(sys.executable)


def is_boot_enabled() -> bool:
    """Whether the login shortcut exists *and* Windows will act on it."""
    return boot_status()[0]


def set_boot_enabled(enable: bool) -> tuple[bool, str]:
    """Enable or disable start at boot via the PowerShell scripts.

    Delegated rather than reimplemented here so there is exactly one place -
    enable_start_at_boot.ps1 / disable_start_at_boot.ps1 - that knows how to
    create or remove the shortcut, matching install.ps1 and manual use.
    """
    if not app_paths.IS_WINDOWS:
        import linux_desktop
        return linux_desktop.set_autostart(enable)
    if app_paths.FROZEN:
        import setup_common
        try:
            setup_common.set_run_at_login(sys.executable, enable)
        except OSError as exc:
            return False, str(exc)
        enabled, reason = boot_status()
        return (True, "") if enabled == enable else (False, reason or "the change did not take effect")

    script = os.path.join(
        HERE, "enable_start_at_boot.ps1" if enable else "disable_start_at_boot.ps1")
    # -NoProfile matters here: loading the user's PowerShell profile is most of
    # the startup cost, and this is on the path of a menu click.
    args = ["powershell", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", script]
    if enable:
        # sys.executable is pythonw.exe under the tray, which the script
        # accepts fine - it derives pythonw.exe from whatever it's given.
        args += ["-PythonPath", sys.executable]
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as exc:
        return False, str(exc)

    detail = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        return False, detail
    # A zero exit only says the script ran. Confirm the state it was meant to
    # produce is the state actually observable now, so the checkbox can never
    # settle on "on" while Windows still refuses to launch it - and so a
    # disable that silently removed nothing is reported as the failure it is.
    enabled, reason = boot_status()
    if enabled != enable:
        return False, reason or "the change did not take effect"
    return True, detail


def setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s",
                            "%Y-%m-%d %H:%M:%S")
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(fmt)
    log.addHandler(handler)
    if sys.stderr:                      # absent under pythonw.exe
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        log.addHandler(console)


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
            json.dump(DEFAULT_CONFIG, handle, indent=2)
        log.warning("created default %s - add your games to it", CONFIG_PATH)
        return dict(DEFAULT_CONFIG)
    # utf-8-sig, not utf-8: Notepad and PowerShell both write a BOM, which
    # json.load rejects outright.
    with open(CONFIG_PATH, encoding="utf-8-sig") as handle:
        config = json.load(handle)
    log.info("config: %s", CONFIG_PATH)
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged


class Switcher:
    """Polls for game processes and drives the mouse profile.

    `override` pins a profile and suspends game-aware switching; None means auto.
    The desired profile is re-asserted whenever a write fails, so an unplugged
    dongle or a sleeping mouse self-heals once the device comes back.
    """

    def __init__(self, config: dict, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.games = {name.lower() for name in config["games"]}
        self.override: int | None = None
        self.applied: int | None = None      # last profile confirmed written
        self.active_game: str | None = None
        self.device: sharkctl.HidInfo | None = None
        self._stop = threading.Event()
        self._on_change = lambda: None
        self._on_game_switch = lambda profile, context: None
        self._on_reload = lambda: None
        self._config_mtime = self._mtime()

    # -- device -------------------------------------------------------------

    def _apply(self, profile: int) -> bool:
        if self.dry_run:
            log.info("[dry-run] would switch to Profile %d", profile)
            self.applied = profile
            return True
        try:
            if self.device is None:
                self.device = sharkctl.find_device()
            sharkctl.set_profile(profile, self.device)
        except (HidError, ValueError) as exc:
            # Force re-enumeration: the interface path changes across replugs.
            self.device = None
            self.applied = None
            log.warning("switch to Profile %d failed: %s", profile, exc)
            return False
        log.info("switched to Profile %d", profile)
        self.applied = profile
        return True

    # -- detection ----------------------------------------------------------

    def running_game(self) -> str | None:
        if not self.games:
            return None
        for proc in psutil.process_iter(["name", "cmdline"]):
            name = proc.info["name"]
            if name and name.lower() in self.games:
                return name
            # Linux truncates process names to 15 characters, and games under
            # Wine/Proton show up as "wine64-preloader" or similar with the
            # real "Z:\...\game.exe" in the command line - so also try the
            # basename of the first command-line entries.
            for arg in (proc.info.get("cmdline") or [])[:2]:
                base = arg.replace("\\", "/").rsplit("/", 1)[-1].lower()
                if base in self.games:
                    return base
        return None

    def desired_profile(self) -> int:
        if self.override is not None:
            return self.override
        return (self.config["game_profile"] if self.active_game
                else self.config["default_profile"])

    # -- loop ---------------------------------------------------------------

    @staticmethod
    def _mtime() -> float | None:
        try:
            return os.path.getmtime(CONFIG_PATH)
        except OSError:
            return None

    def _reload_if_changed(self) -> None:
        """Pick up config.json edits (settings window, Detect games, by hand)."""
        mtime = self._mtime()
        if mtime == self._config_mtime:
            return
        self._config_mtime = mtime
        try:
            config = load_config()
        except (OSError, ValueError) as exc:
            log.warning("config.json changed but could not be read: %s", exc)
            return
        log.info("config.json changed - reloading")
        self.config = config
        self.games = {name.lower() for name in config["games"]}
        if self.override is not None and self.override > sharkctl.profile_count():
            self.override = None
        self.applied = None             # re-send the active profile's settings
        self._on_reload()

    def tick(self) -> None:
        self._reload_if_changed()
        found = self.running_game() if self.override is None else None
        transition = found != self.active_game
        if transition:
            if found:
                log.info("game detected: %s", found)
            else:
                log.info("game exited: %s", self.active_game)
            self.active_game = found
            self._on_change()

        want = self.desired_profile()
        if want != self.applied:
            if self._apply(want):
                self._on_change()
                # Announce game transitions only. Pinning from the tray forces
                # `found` to None, which would otherwise look exactly like
                # "game exited" - hence the override check. Announcing only
                # after a successful _apply keeps a failed write silent rather
                # than claiming a switch that never happened.
                if transition and self.override is None:
                    self._on_game_switch(want, self.active_game or "Desktop")

    def run(self) -> None:
        log.info("watching %d game executable(s), poll every %ss",
                 len(self.games), self.config["poll_seconds"])
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("unexpected error in watch loop")
            self._stop.wait(self.config["poll_seconds"])

    def stop(self) -> None:
        self._stop.set()

    def revert(self) -> None:
        """Return the mouse to the desktop profile on shutdown."""
        target = self.config["default_profile"]
        if self.applied != target:
            log.info("reverting to Profile %d", target)
            self._apply(target)

    def set_override(self, profile: int | None) -> None:
        self.override = profile
        # Re-sync the game state before ticking. Without this, returning to auto
        # while a game is running looks like the game just started and would pop
        # up the overlay for what was actually a menu click.
        self.active_game = self.running_game() if profile is None else None
        log.info("mode: %s", f"pinned to Profile {profile}" if profile else "auto")
        self.tick()
        self._on_change()


# -- tray -------------------------------------------------------------------

def open_log() -> None:
    if app_paths.IS_WINDOWS:
        subprocess.Popen(["explorer", "/select,", LOG_PATH])
    else:
        app_paths.open_path(LOG_DIR)


def run_tray(switcher: Switcher, popup: overlay_module.Overlay) -> None:
    import pystray

    def title() -> str:
        state = (f"pinned to Profile {switcher.override}" if switcher.override
                 else (f"in game: {switcher.active_game}" if switcher.active_game
                       else "desktop"))
        return f"Attack Shark - Profile {switcher.applied or '?'} ({state})"

    logo_path = app_paths.asset("logo.png")
    icon_image = Image.open(logo_path)

    icon = pystray.Icon(
        "shark-profile-switcher",
        icon_image,
        title())

    def refresh() -> None:
        icon.title = title()
        icon.update_menu()

    switcher._on_change = refresh

    def choose(profile: int | None):
        return lambda _icon, _item: switcher.set_override(profile)

    def is_selected(profile: int | None):
        return lambda _item: switcher.override == profile

    def toggle_popups(_icon, _item) -> None:
        popup.enabled = not popup.enabled
        log.info("popups %s", "enabled" if popup.enabled else "disabled")

    # Applying the change shells out to PowerShell and takes a second or two, so
    # the checkbox cannot be driven off the filesystem alone: pystray bakes the
    # check state into the Win32 menu when update_menu() runs and does not
    # re-evaluate it on right-click, so reopening the menu mid-flight would show
    # the old state and look like the click did nothing. Hold the requested
    # state here, show that immediately, and fall back to disk once it lands.
    boot_pending: list[bool | None] = [None]     # None = nothing in flight
    boot_lock = threading.Lock()

    def boot_state() -> bool:
        pending = boot_pending[0]
        return is_boot_enabled() if pending is None else pending

    def boot_label(_item) -> str:
        return ("Start at boot  (applying...)" if boot_pending[0] is not None
                else "Start at boot")

    def toggle_boot(_icon, _item) -> None:
        boot_pending[0] = not boot_state()
        refresh()               # flips the checkbox now, not in three seconds

        def worker() -> None:
            with boot_lock:     # serialise; rapid clicks converge on the last
                target = boot_pending[0]
                if target is None:
                    return      # a previous worker already applied this
                ok, detail = set_boot_enabled(target)
                verb = "enable" if target else "disable"
                if ok:
                    log.info("start at boot %sd", verb)
                else:
                    log.warning("could not %s start at boot: %s", verb, detail)
                    try:
                        icon.notify(f"Could not {verb} start at boot.",
                                    "Attack Shark profile switcher")
                    except Exception:
                        pass
                # Leave it set if a newer click superseded this one - that
                # worker owns it and will clear it when it finishes.
                if boot_pending[0] == target:
                    boot_pending[0] = None
            refresh()           # drop the "applying" label, resync with disk
        threading.Thread(target=worker, name="toggle-boot", daemon=True).start()

    def detect_games_now(_icon, _item) -> None:
        # Same reasoning as toggle_boot: this walks Steam/Epic install
        # directories on disk, which is not instant.
        def worker() -> None:
            try:
                proposals = detect_games.find_all_games()
                added = detect_games.merge_into_config(proposals, CONFIG_PATH)
            except Exception:
                log.exception("game detection failed")
                return
            if added:
                log.info("game detection: added %d new game(s): %s",
                         len(added), ", ".join(added))
            else:
                log.info("game detection: %d candidate(s) found, nothing new",
                         len(proposals))
            # Pick up the new list without requiring a restart.
            switcher.config = load_config()
            switcher.games = {n.lower() for n in switcher.config["games"]}
            try:
                icon.notify(
                    f"Added {len(added)} new game(s) to config.json." if added
                    else "No new games found.",
                    "Attack Shark profile switcher")
            except Exception:
                pass  # balloon notifications aren't guaranteed everywhere
        threading.Thread(target=worker, name="detect-games", daemon=True).start()

    def quit_app(_icon, _item) -> None:
        switcher.stop()
        switcher.revert()
        popup.stop()
        icon.stop()

    editor: list[subprocess.Popen | None] = [None]

    def edit_profiles(_icon, _item) -> None:
        # Its own process: the popup overlay already owns this process's Tk.
        # No need to wait for it - Switcher.tick reloads config.json when the
        # window saves.
        if editor[0] is not None and editor[0].poll() is None:
            return                  # already open
        try:
            editor[0] = subprocess.Popen(
                app_paths.self_command("--settings", "--config", CONFIG_PATH))
        except OSError:
            log.exception("could not open the settings window")

    def on_reload() -> None:
        icon.menu = build_menu()
        refresh()

    switcher._on_reload = on_reload

    # -- updates --------------------------------------------------------------
    update: list = [None]               # the newer updater.Release, if any
    updating = [False]

    def check_updates(announce: bool) -> None:
        import updater
        try:
            release = updater.check()
        except updater.UpdateError as exc:
            log.info("update check: %s", exc)
            return
        if release is None:
            log.info("update check: up to date (%s)", app_paths.APP_VERSION)
            return
        first_time = update[0] is None or update[0].version != release.version
        update[0] = release
        log.info("update available: %s -> %s", app_paths.APP_VERSION, release.version)
        refresh()
        if announce and first_time:
            try:
                icon.notify(f"Versao {release.version} disponivel. Clique com o botao direito "
                            "no icone > Update.", "Attack Shark")
            except Exception:
                pass

    def update_loop() -> None:
        stop = switcher._stop
        if stop.wait(UPDATE_FIRST_CHECK_S):
            return
        while True:
            if switcher.config.get("check_updates", True):
                check_updates(announce=True)
            if stop.wait(UPDATE_INTERVAL_S):
                return

    def do_update(_icon=None, _item=None) -> None:
        import updater
        release = update[0]
        if release is None or updating[0]:
            return
        if not updater.can_self_update(release):
            updater.open_release_page(release)
            return
        updating[0] = True
        refresh()

        def worker() -> None:
            try:
                try:
                    icon.notify(f"Baixando a versao {release.version}...", "Attack Shark")
                except Exception:
                    pass
                path = updater.download_installer(release)
                log.info("starting update to %s", release.version)
                updater.run_installer(path)     # closes this app and restarts it
            except updater.UpdateError as exc:
                log.warning("update failed: %s", exc)
                try:
                    icon.notify(f"A atualizacao falhou: {exc}", "Attack Shark")
                except Exception:
                    pass
                updating[0] = False
                refresh()
        threading.Thread(target=worker, name="update", daemon=True).start()

    def update_label(_item) -> str:
        release = update[0]
        if release is None:
            return "Update"
        return (f"Updating to {release.version}..." if updating[0]
                else f"⬆  Update to {release.version}")

    def build_menu() -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _item: title(), None, enabled=False),
            pystray.MenuItem(update_label, do_update,
                             visible=lambda _item: update[0] is not None,
                             enabled=lambda _item: not updating[0]),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Auto (game-aware)", choose(None),
                             checked=is_selected(None), radio=True),
            *[pystray.MenuItem(f"Pin to {sharkctl.profile_label(n)}", choose(n),
                               checked=is_selected(n), radio=True)
              for n in range(1, sharkctl.profile_count() + 1)],
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show popups", toggle_popups,
                             checked=lambda _item: popup.enabled),
            pystray.MenuItem(boot_label, toggle_boot,
                             checked=lambda _item: boot_state()),
            pystray.MenuItem("Settings (profiles, games, logs)", edit_profiles, default=True),
            pystray.MenuItem("Detect games", detect_games_now),
            pystray.MenuItem("Edit games list",
                             lambda _i, _it: app_paths.open_path(CONFIG_PATH)),
            pystray.MenuItem("Open log",
                             lambda _i, _it: open_log()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_app),
        )

    icon.menu = build_menu()

    threading.Thread(target=switcher.run, daemon=True).start()
    threading.Thread(target=update_loop, name="update-check", daemon=True).start()
    icon.run()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="log decisions without touching the mouse")
    parser.add_argument("--no-tray", action="store_true",
                        help="run headless instead of in the system tray")
    parser.add_argument("--config", help="use an alternate config file")
    parser.add_argument("--allow-multiple", action="store_true",
                        help="skip the single-instance check (for testing)")
    parser.add_argument("--settings", action="store_true",
                        help="open the settings window instead of the tray app")
    parser.add_argument("--uninstall", action="store_true",
                        help="remove the installed app (used by Windows' Installed apps)")
    parser.add_argument("--quiet", action="store_true",
                        help="with --uninstall: no questions")
    args = parser.parse_args()

    if args.config:
        global CONFIG_PATH
        CONFIG_PATH = os.path.abspath(args.config)
    else:
        app_paths.ensure_config()
    sharkctl.set_config_path(CONFIG_PATH)

    if args.uninstall:
        import uninstall
        return uninstall.run(quiet=args.quiet)
    if args.settings:
        import profiles_editor
        return profiles_editor.run(CONFIG_PATH)

    setup_logging()

    # Before anything with a side effect: no logging setup beyond the file, no
    # device access, no Tk thread, no tray icon.
    if not args.allow_multiple and not acquire_single_instance():
        log.info("another instance is already running - opening its settings window")
        if sys.stderr:                  # absent under pythonw.exe
            print("Attack Shark profile switcher is already running.",
                  file=sys.stderr)
        # Double-clicking the desktop icon while it runs should show something.
        if not args.no_tray:
            try:
                subprocess.Popen(app_paths.self_command("--settings", "--config", CONFIG_PATH))
            except OSError:
                pass
        return 0

    # Logged every run: a start-at-boot problem is otherwise invisible until a
    # login fails to bring it up, with nothing in the log to say why.
    boot_enabled, boot_reason = boot_status()
    log.info("start at boot: %s",
             "on" if boot_enabled else "off (%s)" % boot_reason)

    config = load_config()
    switcher = Switcher(config, dry_run=args.dry_run)
    atexit.register(switcher.revert)

    # Wired here rather than in run_tray so --no-tray runs get popups too.
    # Started unconditionally: the Tk thread is idle when disabled, and this
    # surfaces any initialisation failure at startup instead of mid-game.
    popup = overlay_module.Overlay(
        duration_ms=config["popup_duration_ms"],
        logo_path=app_paths.asset("logo.png"),
        enabled=config["popup_enabled"])
    popup.start()
    switcher._on_game_switch = lambda profile, context: popup.show(
        sharkctl.profile_label(profile), context)

    if not config["games"]:
        log.warning("no games configured - edit %s", CONFIG_PATH)

    if args.no_tray:
        try:
            switcher.run()
        except KeyboardInterrupt:
            pass
        finally:
            switcher.stop()
            switcher.revert()
            popup.stop()
        return 0

    run_tray(switcher, popup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
