"""Build the Windows executables.

    python build.py

Produces, in dist\\:
    Instalar Attack Shark.exe   - the installer to hand out (one file)

Steps: a private virtualenv (.venv-build) with the runtime requirements and
PyInstaller; "Attack Shark.exe" as a folder build (faster start, fewer
antivirus false positives than a one-file app); that folder zipped into
app.zip; and the installer as a single .exe carrying app.zip inside.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
import zipfile

import app_paths

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(ROOT, ".venv-build")
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
ICON = os.path.join(ROOT, "assets", "logo.ico")
SEP = os.pathsep  # PyInstaller --add-data separator (";" on Windows)


def run(*cmd: str) -> None:
    print(">", " ".join(f'"{c}"' if " " in c else c for c in cmd), flush=True)
    subprocess.run(cmd, check=True)


def venv_python() -> str:
    py = os.path.join(VENV, "Scripts", "python.exe")
    if not os.path.exists(py):
        print("creating build virtualenv...", flush=True)
        venv.create(VENV, with_pip=True)
    run(py, "-m", "pip", "install", "--disable-pip-version-check", "-q",
        "-r", os.path.join(ROOT, "requirements.txt"), "pyinstaller>=6.0")
    return py


def version_file(name: str, description: str, original: str) -> str:
    """Windows version resource: what Explorer and Task Manager display."""
    nums = [int(x) for x in app_paths.APP_VERSION.split(".")] + [0]
    t = tuple(nums[:4])
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', '{app_paths.PUBLISHER}'),
      StringStruct('FileDescription', '{description}'),
      StringStruct('FileVersion', '{app_paths.APP_VERSION}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', '{original}'),
      StringStruct('ProductName', '{app_paths.APP_FULL_NAME}'),
      StringStruct('ProductVersion', '{app_paths.APP_VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])
  ]
)
"""
    path = os.path.join(BUILD, f"version-{name}.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def pyinstaller(py: str, *args: str) -> None:
    run(py, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--icon", ICON, "--workpath", os.path.join(BUILD, "work"),
        "--specpath", BUILD, *args)


def main() -> int:
    if sys.platform != "win32":
        print("build.py gera os executaveis do Windows e precisa rodar no Windows.")
        print("No Linux, instale pelo codigo com ./install.sh.")
        return 1
    os.chdir(ROOT)
    os.makedirs(BUILD, exist_ok=True)
    py = venv_python()

    # 1. the app, as a folder: build\app\Attack Shark\Attack Shark.exe
    app_dist = os.path.join(BUILD, "app")
    pyinstaller(
        py, "switcher.py", "--name", app_paths.APP_NAME, "--onedir",
        "--distpath", app_dist,
        "--version-file", version_file("app", app_paths.APP_NAME, app_paths.EXE_NAME),
        "--add-data", f"{os.path.join(ROOT, 'assets')}{SEP}assets",
        "--add-data", f"{os.path.join(ROOT, 'config.json')}{SEP}.",
        "--hidden-import", "pystray._win32",
        "--hidden-import", "profiles_editor",
        "--hidden-import", "uninstall",
        "--hidden-import", "updater",
        "--hidden-import", "i18n_extra",
        "--exclude-module", "linhid",
        "--exclude-module", "linux_desktop",
    )
    app_dir = os.path.join(app_dist, app_paths.APP_NAME)

    # 2. zip it for the installer
    payload = os.path.join(BUILD, "app.zip")
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for folder, _, files in os.walk(app_dir):
            for f in files:
                full = os.path.join(folder, f)
                z.write(full, os.path.relpath(full, app_dir))

    # 3. the installer, one file
    setup_name = f"Instalar {app_paths.APP_NAME}"
    pyinstaller(
        py, "installer.py", "--name", setup_name, "--onefile",
        "--distpath", DIST,
        "--version-file", version_file("installer", f"Instalador do {app_paths.APP_NAME}",
                                       setup_name + ".exe"),
        "--add-data", f"{payload}{SEP}.",
        "--add-data", f"{os.path.join(ROOT, 'assets')}{SEP}assets",
    )
    out = os.path.join(DIST, setup_name + ".exe")
    print(f"\nok: {out}  ({os.path.getsize(out) // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
