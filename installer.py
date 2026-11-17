"""Graphical installer: "Instalar Attack Shark.exe".

Built by build.py into a single .exe that carries the app (app.zip) inside.
Installs per user - no administrator rights - into
%LOCALAPPDATA%\\Programs\\Attack Shark, adds the desktop / Start Menu
shortcuts, optionally starts the app with Windows, and registers it under
Settings > Apps > Installed apps so it can be removed like any program.

Unattended use (and testing):
    "Instalar Attack Shark.exe" --silent [--update] [--dir PATH] [--no-desktop]
                                [--no-start-menu] [--no-startup] [--no-launch]
    --update keeps the shortcuts and start-with-Windows choice as they are
    (what the in-app updater uses).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import zipfile
from tkinter import filedialog, messagebox, ttk

import app_paths
import i18n
import setup_common
from i18n import _
from ui_theme import (ACCENT, BG, CARD, CARD2, FG, FONT, GREEN, INPUT, MUTED, RED,
                      dark_title_bar, setup_style)

STEPS = ["Bem-vindo", "Opcoes", "Instalacao", "Pronto"]   # translated when drawn


def _title() -> str:
    return _("Instalar {app}", app=app_paths.APP_NAME)


def payload_path() -> str:
    """app.zip bundled into the installer; next to this script when testing."""
    return os.path.join(app_paths.BUNDLE_DIR, "app.zip")


def payload_size_kb() -> int:
    try:
        with zipfile.ZipFile(payload_path()) as z:
            return sum(i.file_size for i in z.infolist()) // 1024
    except (OSError, zipfile.BadZipFile):
        return 0


# -- the actual work -----------------------------------------------------------

class InstallError(Exception):
    pass


def install(target: str, desktop: bool, start_menu: bool, startup: bool,
            report=lambda pct, text: None) -> str:
    """Install into `target`; returns the path of the installed exe."""
    exe = os.path.join(target, app_paths.EXE_NAME)
    if not os.path.exists(payload_path()):
        raise InstallError(_("Arquivos do programa nao encontrados dentro do instalador."))

    report(3, _("Fechando o Attack Shark, se estiver aberto..."))
    setup_common.stop_running(exe)
    setup_common.remove_legacy()

    report(8, _("Preparando a pasta..."))
    if os.path.isdir(target) and os.listdir(target):
        if not os.path.exists(exe):
            raise InstallError(_("A pasta escolhida ja tem outros arquivos:\n{target}\n\n"
                                 "Escolha uma pasta vazia.", target=target))
        try:
            shutil.rmtree(target)       # previous version; settings live elsewhere
        except OSError as exc:
            raise InstallError(_("Nao consegui substituir a versao anterior:\n{exc}", exc=exc))
    os.makedirs(target, exist_ok=True)

    with zipfile.ZipFile(payload_path()) as z:
        members = z.infolist()
        for n, member in enumerate(members, 1):
            z.extract(member, target)
            if n % 25 == 0 or n == len(members):
                report(10 + int(70 * n / len(members)), _("Copiando arquivos... {n}/{total}", n=n, total=len(members)))
    if not os.path.exists(exe):
        raise InstallError(_("A copia terminou mas o programa nao apareceu na pasta."))

    report(84, _("Criando atalhos..."))
    icon = exe
    for wanted, link in ((desktop, setup_common.desktop_shortcut()),
                         (start_menu, setup_common.start_menu_shortcut())):
        if wanted:
            try:
                setup_common.create_shortcut(link, exe, target, icon,
                                             _("Troca de perfil automatica do mouse Attack Shark"))
            except (OSError, subprocess.SubprocessError) as exc:
                raise InstallError(_("Nao consegui criar o atalho:\n{link}\n\n{exc}", link=link, exc=exc))
        else:
            setup_common.remove_file(link)

    report(92, _("Configurando a inicializacao com o Windows..."))
    setup_common.set_run_at_login(exe, startup)

    report(96, _("Registrando em Aplicativos instalados..."))
    size_kb = sum(os.path.getsize(os.path.join(d, f))
                  for d, _dirs, files in os.walk(target) for f in files) // 1024
    setup_common.register_uninstaller(target, size_kb)

    report(100, _("Concluido"))
    return exe


def prepare_config(language: str | None) -> None:
    """Save the language picked in the installer to the user's config.json.

    On a first install the config is created from the template inside the
    payload, with the default profile names in the chosen language.
    """
    path = app_paths.CONFIG_PATH
    if language is None:
        if os.path.exists(path):
            return              # nothing picked and settings already exist: leave them
        language = "auto"       # first install: still name the profiles in the UI language
    config = None
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                config = json.load(handle)
        except (OSError, ValueError):
            config = None
    if config is None:
        try:
            with zipfile.ZipFile(payload_path()) as z:
                name = next(n for n in z.namelist() if n.replace("\\", "/").endswith("_internal/config.json"))
                config = json.loads(z.read(name).decode("utf-8-sig"))
        except (OSError, StopIteration, ValueError, zipfile.BadZipFile):
            config = {}
        for profile in (config.get("x6") or {}).get("profiles", []):
            if profile.get("name") in ("Normal", "Jogo"):
                profile["name"] = _(profile["name"])
    config["language"] = language
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)


def initial_language() -> str:
    """The language already saved by a previous install, else the system's."""
    try:
        with open(app_paths.CONFIG_PATH, encoding="utf-8-sig") as handle:
            return json.load(handle).get("language", "auto")
    except (OSError, ValueError):
        return "auto"


def launch(exe: str, *args: str) -> None:
    subprocess.Popen([exe, *args], cwd=os.path.dirname(exe), close_fds=True)


# -- UI -------------------------------------------------------------------------

class Installer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.queue: queue.Queue = queue.Queue()
        self.exe = ""
        self.previous = setup_common.installed_dir()
        self.v_dir = tk.StringVar(value=self.previous or setup_common.default_install_dir())
        self.v_desktop = tk.BooleanVar(value=True)
        self.v_start_menu = tk.BooleanVar(value=True)
        self.v_startup = tk.BooleanVar(value=True)
        self.v_open = tk.BooleanVar(value=True)
        self.language_picked: str | None = None   # set when the user changes it
        self.installing = False

        root.title(_title())
        root.geometry("680x520")
        root.resizable(False, False)
        try:
            root.iconbitmap(app_paths.asset("logo.ico"))
        except tk.TclError:
            pass
        root.protocol("WM_DELETE_WINDOW", self.cancel)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        self._header()
        self._stepper()
        self.body = ttk.Frame(root, style="Card.TFrame", padding=(32, 26))
        self.body.grid(row=2, column=0, sticky="nsew", padx=24)
        self.body.columnconfigure(0, weight=1)
        self.footer = ttk.Frame(root, padding=(24, 14, 24, 18))
        self.footer.grid(row=3, column=0, sticky="ew")
        self.footer.columnconfigure(0, weight=1)

        self.page_welcome()
        self._pump()

    # -- chrome --------------------------------------------------------------

    def _header(self) -> None:
        head = ttk.Frame(self.root, padding=(24, 18, 24, 8))
        head.grid(row=0, column=0, sticky="ew")
        try:
            self._logo = tk.PhotoImage(file=app_paths.asset("logo.png")).subsample(5)
            tk.Label(head, image=self._logo, bg=BG).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        except tk.TclError:
            pass
        ttk.Label(head, text=app_paths.APP_NAME, style="H1.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(head, text=_("Instalador  ·  versao {version}", version=app_paths.APP_VERSION),
                  style="Muted.TLabel").grid(row=1, column=1, sticky="w")
        head.columnconfigure(1, weight=1)
        # language picker: changing it redraws the window in the new language
        names = list(i18n.LANGUAGES.values())
        self.v_lang = tk.StringVar(value=i18n.LANGUAGES[i18n.current()])
        picker = ttk.Combobox(head, textvariable=self.v_lang, values=names, state="readonly", width=11)
        picker.grid(row=0, column=2, rowspan=2, sticky="e")
        picker.bind("<<ComboboxSelected>>", lambda _e: self._change_language())

    def _change_language(self) -> None:
        names = {v: k for k, v in i18n.LANGUAGES.items()}
        self.language_picked = i18n.set_language(names.get(self.v_lang.get(), "en"))
        self.root.title(_title())
        for w in self.root.grid_slaves(row=0):
            w.destroy()
        self._header()
        self._page()                    # rebuild the current page in the new language

    def _stepper(self) -> None:
        self.step_canvas = tk.Canvas(self.root, height=44, bg=BG, highlightthickness=0)
        self.step_canvas.grid(row=1, column=0, sticky="ew", padx=24, pady=(4, 10))

    def _draw_steps(self, current: int) -> None:
        c = self.step_canvas
        c.delete("all")
        c.update_idletasks()
        width = max(c.winfo_width(), 632)
        n = len(STEPS)
        xs = [int(30 + i * (width - 60) / (n - 1)) for i in range(n)]
        for i in range(n - 1):
            c.create_line(xs[i] + 12, 14, xs[i + 1] - 12, 14, width=2,
                          fill=ACCENT if i < current else CARD2)
        for i, (x, name) in enumerate(zip(xs, STEPS)):
            done, active = i < current, i == current
            fill = GREEN if done else (ACCENT if active else CARD2)
            c.create_oval(x - 11, 3, x + 11, 25, fill=fill, outline="")
            c.create_text(x, 14, text="✓" if done else str(i + 1),
                          fill="#ffffff" if (done or active) else MUTED, font=(FONT, 9, "bold"))
            c.create_text(x, 37, text=_(name), fill=FG if active else MUTED,
                          font=(FONT, 9, "bold" if active else "normal"))

    def _clear(self, step: int) -> None:
        for w in self.body.winfo_children():
            w.destroy()
        for w in self.footer.winfo_children():
            w.destroy()
        self.root.after(10, lambda: self._draw_steps(step))

    def _buttons(self, back=None, next_text=None, next_cmd=None, cancel=True) -> ttk.Button | None:
        col = 1
        if cancel:
            ttk.Button(self.footer, text=_("Cancelar"), style="Ghost.TButton",
                       command=self.cancel).grid(row=0, column=0, sticky="w")
        if back:
            ttk.Button(self.footer, text=_("Voltar"), command=back).grid(row=0, column=col, padx=(0, 8))
            col += 1
        if next_text:
            btn = ttk.Button(self.footer, text=next_text, style="Accent.TButton", command=next_cmd)
            btn.grid(row=0, column=col)
            btn.focus_set()
            self.root.bind("<Return>", lambda _e: next_cmd())
            return btn
        return None

    # -- pages -----------------------------------------------------------------

    def page_welcome(self) -> None:
        self._page = self.page_welcome
        self._clear(0)
        b = self.body
        ttk.Label(b, text=_("Troca de perfil automatica\npara o seu mouse Attack Shark"),
                  style="Card.TLabel", font=(FONT, 16, "bold"), justify="left").grid(sticky="w")
        ttk.Label(b, text=_("Em poucos segundos o programa fica pronto e rodando."),
                  style="CardMuted.TLabel", font=(FONT, 10)).grid(sticky="w", pady=(6, 18))
        for text in (_("Muda o perfil sozinho quando voce abre ou fecha um jogo"),
                     _("Tela para criar perfis de DPI, polling, resposta do clique e mais"),
                     _("Funciona com o V8 e o X6, sem o app oficial aberto"),
                     _("Nao precisa de Python nem de administrador")):
            row = ttk.Frame(b, style="Card.TFrame")
            row.grid(sticky="w", pady=3)
            tk.Label(row, text="✓", bg=CARD, fg=GREEN, font=(FONT, 11, "bold")).grid(row=0, column=0, padx=(0, 10))
            ttk.Label(row, text=text, style="Card.TLabel").grid(row=0, column=1, sticky="w")
        if self.previous:
            note = tk.Label(b, text=_("↻  Ja existe uma versao instalada. Ela sera atualizada e "
                                      "seus perfis e jogos serao mantidos."),
                            bg="#16263d", fg="#9cc7ff", font=(FONT, 9), padx=12, pady=8,
                            justify="left", wraplength=560)
            note.grid(sticky="ew", pady=(20, 0))
        self._buttons(next_text=_("Proximo  →"), next_cmd=self.page_options)

    def page_options(self) -> None:
        self._page = self.page_options
        self._clear(1)
        b = self.body
        ttk.Label(b, text=_("Onde instalar"), style="Section.TLabel").grid(sticky="w")
        row = ttk.Frame(b, style="Card.TFrame")
        row.grid(sticky="ew", pady=(8, 2))
        row.columnconfigure(0, weight=1)
        ttk.Entry(row, textvariable=self.v_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(row, text=_("Alterar..."), style="Ghost.TButton", command=self.choose_dir).grid(
            row=0, column=1, padx=(8, 0))
        mb = max(1, payload_size_kb() // 1024)
        ttk.Label(b, text=_("Espaco necessario: cerca de {mb} MB  ·  sem administrador", mb=mb),
                  style="CardMuted.TLabel").grid(sticky="w")

        ttk.Label(b, text=_("Opcoes"), style="Section.TLabel").grid(sticky="w", pady=(22, 6))
        for var, text, hint in (
                (self.v_desktop, _("Criar atalho na area de trabalho"), None),
                (self.v_start_menu, _("Adicionar ao Menu Iniciar"), None),
                (self.v_startup, _("Iniciar junto com o Windows"),
                 _("recomendado: e o que faz a troca automatica funcionar sem voce lembrar de abrir"))):
            ttk.Checkbutton(b, text=text, variable=var).grid(sticky="w", pady=(4, 0))
            if hint:
                ttk.Label(b, text="      " + hint, style="CardMuted.TLabel").grid(sticky="w")
        self._buttons(back=self.page_welcome, next_text=_("Instalar"), next_cmd=self.start_install)

    def choose_dir(self) -> None:
        chosen = filedialog.askdirectory(title=_("Escolha onde instalar"), parent=self.root,
                                         initialdir=os.path.dirname(self.v_dir.get()))
        if chosen:
            chosen = os.path.normpath(chosen)
            # Always our own subfolder, so an update can never wipe a folder of
            # unrelated files the user happened to pick.
            if os.path.basename(chosen).lower() != app_paths.APP_NAME.lower():
                chosen = os.path.join(chosen, app_paths.APP_NAME)
            self.v_dir.set(chosen)

    def page_progress(self) -> None:
        self._clear(2)
        b = self.body
        ttk.Label(b, text=_("Instalando..."), style="Card.TLabel", font=(FONT, 16, "bold")).grid(sticky="w")
        ttk.Label(b, text=_("Isso leva poucos segundos."), style="CardMuted.TLabel",
                  font=(FONT, 10)).grid(sticky="w", pady=(4, 26))
        s = ttk.Style(self.root)
        s.configure("Big.Horizontal.TProgressbar", troughcolor=INPUT, background=ACCENT,
                    bordercolor=INPUT, lightcolor=ACCENT, darkcolor=ACCENT, thickness=10)
        self.bar = ttk.Progressbar(b, style="Big.Horizontal.TProgressbar", maximum=100)
        self.bar.grid(sticky="ew")
        self.step_label = ttk.Label(b, text="", style="CardMuted.TLabel", font=(FONT, 10))
        self.step_label.grid(sticky="w", pady=(10, 0))
        self.root.unbind("<Return>")

    def page_done(self) -> None:
        self._page = self.page_done
        self._clear(3)
        b = self.body
        badge = tk.Canvas(b, width=64, height=64, bg=CARD, highlightthickness=0)
        badge.grid(sticky="w")
        badge.create_oval(2, 2, 62, 62, fill="#143326", outline=GREEN, width=2)
        badge.create_text(32, 33, text="✓", fill=GREEN, font=(FONT, 24, "bold"))
        ttk.Label(b, text=_("Tudo pronto!"), style="Card.TLabel", font=(FONT, 18, "bold")).grid(
            sticky="w", pady=(14, 4))
        ttk.Label(b, text=_("O Attack Shark ja esta rodando. Procure o icone dele perto do "
                            "relogio: clique nele\npara abrir as configuracoes, ou use o atalho "
                            "\"Attack Shark\" na area de trabalho."),
                  style="CardMuted.TLabel", font=(FONT, 10), justify="left").grid(sticky="w")
        ttk.Checkbutton(b, text=_("Abrir as configuracoes agora para revisar os perfis"),
                        variable=self.v_open).grid(sticky="w", pady=(22, 0))
        self._buttons(next_text=_("Concluir"), next_cmd=self.finish, cancel=False)

    def page_error(self, message: str) -> None:
        self._clear(2)
        b = self.body
        ttk.Label(b, text=_("Nao foi possivel instalar"), style="Card.TLabel",
                  font=(FONT, 16, "bold"), foreground=RED).grid(sticky="w")
        ttk.Label(b, text=message, style="Card.TLabel", justify="left",
                  wraplength=580).grid(sticky="w", pady=(12, 0))
        self._buttons(back=self.page_options, next_text=_("Tentar de novo"), next_cmd=self.start_install)

    # -- actions ---------------------------------------------------------------

    def start_install(self) -> None:
        target = os.path.normpath(self.v_dir.get().strip())
        if not target or not os.path.isabs(target):
            messagebox.showerror(_title(), _("Escolha uma pasta valida."), parent=self.root)
            return
        self.installing = True
        self.page_progress()
        opts = (target, self.v_desktop.get(), self.v_start_menu.get(), self.v_startup.get())

        def report(pct, text):
            self.queue.put(("progress", pct, text))

        def worker():
            try:
                exe = install(*opts, report=report)
                prepare_config(self.language_picked)
                launch(exe)
                self.queue.put(("done", exe))
            except InstallError as exc:
                self.queue.put(("error", str(exc)))
            except Exception as exc:        # never leave the window stuck
                self.queue.put(("error", _("Erro inesperado: {exc}", exc=exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _pump(self) -> None:
        while True:
            try:
                msg = self.queue.get_nowait()
            except queue.Empty:
                break
            if msg[0] == "progress":
                self.bar["value"] = msg[1]
                self.step_label.config(text=msg[2])
            elif msg[0] == "done":
                self.installing = False
                self.exe = msg[1]
                self.page_done()
            elif msg[0] == "error":
                self.installing = False
                self.page_error(msg[1])
        self.root.after(60, self._pump)

    def finish(self) -> None:
        if self.v_open.get() and self.exe:
            # The app is already running, so this opens its settings window.
            launch(self.exe, "--settings")
        self.root.destroy()

    def cancel(self) -> None:
        if self.installing:
            return
        if messagebox.askyesno(_title(), _("Cancelar a instalacao?"), parent=self.root):
            self.root.destroy()


def _say(text: str) -> None:
    # The built installer is a windowed app: there may be no console at all.
    stream = sys.stdout or sys.stderr
    if stream:
        print(text, file=stream)


def main() -> int:
    parser = argparse.ArgumentParser(description=_title())
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--dir", default=None)
    parser.add_argument("--no-desktop", action="store_true")
    parser.add_argument("--no-start-menu", action="store_true")
    parser.add_argument("--no-startup", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--update", action="store_true",
                        help="with --silent: keep the current shortcuts / startup choices")
    args = parser.parse_args()

    if args.silent:
        target = args.dir or setup_common.installed_dir() or setup_common.default_install_dir()
        desktop, start_menu, startup = (not args.no_desktop, not args.no_start_menu,
                                        not args.no_startup)
        if args.update and setup_common.installed_dir():
            exe_now = os.path.join(target, app_paths.EXE_NAME)
            desktop = os.path.exists(setup_common.desktop_shortcut())
            start_menu = os.path.exists(setup_common.start_menu_shortcut())
            startup = setup_common.run_at_login_status(exe_now)[0]
        try:
            exe = install(os.path.abspath(target), desktop, start_menu, startup)
            prepare_config(None)
        except InstallError as exc:
            _say(f"error: {exc}")
            return 1
        if not args.no_launch:
            launch(exe)
        _say(f"installed: {exe}")
        return 0

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    i18n.set_language(initial_language())
    root = tk.Tk()
    setup_style(root)
    Installer(root)
    dark_title_bar(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
