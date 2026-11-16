"""`Attack Shark.exe --uninstall`: what Windows' "Installed apps" runs.

Removes the shortcuts, the start-at-login entry and the Installed apps entry,
optionally the user's settings, and finally the install folder itself - after
this process has exited, since its own .exe lives there.
"""

from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from tkinter import messagebox

import app_paths
import setup_common

TITLE = "Desinstalar Attack Shark"


def run(quiet: bool = False) -> int:
    if not app_paths.FROZEN:
        print("--uninstall only applies to the installed Attack Shark.exe")
        return 1

    install_dir = os.path.dirname(os.path.abspath(sys.executable))
    # Only ever delete the folder the installer put us in, never e.g. a build
    # output folder someone ran this from.
    registered = setup_common.installed_dir() or setup_common.default_install_dir()
    delete_folder = os.path.normcase(install_dir) == os.path.normcase(os.path.abspath(registered))
    root = None
    remove_settings = False
    if not quiet:
        root = tk.Tk()
        root.withdraw()
        try:
            root.iconbitmap(app_paths.asset("logo.ico"))
        except tk.TclError:
            pass
        if not messagebox.askyesno(
                TITLE, "Remover o Attack Shark deste computador?\n\n"
                       "O mouse fica com a configuracao que estiver ativa agora.",
                parent=root):
            root.destroy()
            return 1
        remove_settings = messagebox.askyesno(
            TITLE, "Apagar tambem seus perfis e a lista de jogos?\n\n"
                   "Escolha Nao para mante-los caso instale de novo.",
            parent=root, default="no")

    setup_common.stop_running(sys.executable, keep_pid=os.getpid())
    setup_common.remove_registration()
    if remove_settings:
        shutil.rmtree(app_paths.DATA_DIR, ignore_errors=True)

    if root is not None:
        messagebox.showinfo(TITLE, "Attack Shark foi removido.", parent=root)
        root.destroy()
    if delete_folder:
        setup_common.delete_later(install_dir)
    return 0
