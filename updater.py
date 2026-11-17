"""Check GitHub Releases for a newer version, and install it on Windows.

Only one request is made: the public "latest release" endpoint of the
project's repository. Nothing about the user or the machine is sent.

On Windows (installed .exe) an update downloads the installer asset from the
release and runs it with --silent --update: it closes the running app,
replaces the files, keeps the user's choices and settings, and starts the new
version. Everywhere else the update is announced and the release page opened.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from typing import NamedTuple

import app_paths
from i18n import _

API_URL = f"https://api.github.com/repos/{app_paths.GITHUB_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{app_paths.GITHUB_REPO}/releases"
USER_AGENT = "AttackShark-Updater"
# Where release downloads may come from (GitHub redirects assets to its CDN).
ALLOWED_HOSTS = {"github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com"}
MAX_INSTALLER_BYTES = 200 * 1024 * 1024


class UpdateError(Exception):
    pass


class Release(NamedTuple):
    version: str            # "2.1.0"
    tag: str                # "v2.1.0"
    page_url: str
    notes: str
    installer_url: str | None
    installer_size: int


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(remote: str, local: str = app_paths.APP_VERSION) -> bool:
    return parse_version(remote) > parse_version(local)


def _flat(name: str) -> str:
    return re.sub(r"[\s._-]+", "", name).lower()


def _get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def latest_release(timeout: float = 10) -> Release:
    """The newest published release. Raises UpdateError when unreachable."""
    try:
        data = json.loads(_get(API_URL, timeout))
    except Exception as exc:
        raise UpdateError(_("Nao consegui consultar o GitHub: {exc}", exc=exc)) from None
    tag = data.get("tag_name") or ""
    if not tag:
        raise UpdateError(_("Nenhuma versao publicada ainda."))
    # GitHub renames uploads ("Instalar Attack Shark.exe" becomes
    # "Instalar.Attack.Shark.exe"), so compare names without separators.
    wanted = _flat(app_paths.INSTALLER_NAME)
    asset = next((a for a in data.get("assets", [])
                  if _flat(a.get("name", "")) == wanted), None)
    return Release(
        version=".".join(str(n) for n in parse_version(tag)),
        tag=tag,
        page_url=data.get("html_url") or RELEASES_URL,
        notes=(data.get("body") or "").strip(),
        installer_url=asset.get("browser_download_url") if asset else None,
        installer_size=int(asset.get("size") or 0) if asset else 0,
    )


def check() -> Release | None:
    """The latest release if it is newer than this copy, else None."""
    release = latest_release()
    return release if is_newer(release.version) else None


def can_self_update(release: Release) -> bool:
    return app_paths.IS_WINDOWS and app_paths.FROZEN and bool(release.installer_url)


def download_installer(release: Release, progress=lambda done, total: None) -> str:
    if not release.installer_url:
        raise UpdateError(_("Esta versao nao tem o instalador anexado."))
    host = urllib.parse.urlparse(release.installer_url).hostname or ""
    if urllib.parse.urlparse(release.installer_url).scheme != "https" or host not in ALLOWED_HOSTS:
        raise UpdateError(_("Endereco de download inesperado: {host}", host=host))
    folder = tempfile.mkdtemp(prefix="attack-shark-update-")
    path = os.path.join(folder, app_paths.INSTALLER_NAME)
    req = urllib.request.Request(release.installer_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as out:
            final_host = urllib.parse.urlparse(resp.geturl()).hostname or ""
            if final_host not in ALLOWED_HOSTS:
                raise UpdateError(_("Download redirecionado para um endereco inesperado: {host}", host=final_host))
            total = int(resp.headers.get("Content-Length") or release.installer_size or 0)
            done = 0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_INSTALLER_BYTES:
                    raise UpdateError(_("Download maior que o esperado; cancelado."))
                out.write(chunk)
                progress(done, total)
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(_("Falha ao baixar a atualizacao: {exc}", exc=exc)) from None
    if release.installer_size and os.path.getsize(path) != release.installer_size:
        raise UpdateError(_("O download veio incompleto. Tente de novo."))
    return path


def run_installer(path: str) -> None:
    """Start the downloaded installer; it will close this app and restart it."""
    # Started from its own folder (not ours, which it is about to replace) and
    # without this frozen app's internal TCL/TK/bootloader variables.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("_PYI", "_MEI")) and k not in ("TCL_LIBRARY", "TK_LIBRARY")}
    subprocess.Popen([path, "--silent", "--update"], close_fds=True, env=env,
                     cwd=os.path.dirname(path), creationflags=app_paths.CREATE_NO_WINDOW)


def open_release_page(release: Release | None = None) -> None:
    import webbrowser
    webbrowser.open(release.page_url if release else RELEASES_URL)
