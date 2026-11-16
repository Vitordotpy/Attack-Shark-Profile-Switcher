"""Settings window: Attack Shark X6 profiles, games list and live logs.

Opened from the tray menu ("Settings"), or on its own:

    python profiles_editor.py [--config path\\to\\config.json]

Saving writes config.json; the running switcher notices the change and
reloads on its own, so the window can stay open (e.g. to watch the logs).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import app_paths
import sharkctl
from sharkctl import HidError

TITLE = "Attack Shark - Configuracoes"
LOG_PATH = app_paths.LOG_PATH

POLLING = [125, 250, 500, 1000]
RESPOSTA = [str(n) for n in range(2, 21, 2)]
NOVO_PERFIL = {"name": "Novo perfil", "dpi": 1600, "polling": 1000, "key_response_ms": 8,
               "deep_sleep_min": 10, "ripple": False, "angle_snap": False}

from ui_theme import (ACCENT, ACCENT_HI, AMBER, BG, CARD, CARD2, FG, FONT, GREEN,  # noqa: E402
                      INPUT, MONO, MUTED, RED, card, dark_title_bar, set_window_icon,
                      setup_style, styled_listbox)


class App:
    def __init__(self, root: tk.Tk, config_path: str):
        self.root = root
        self.config_path = config_path
        self.dirty = False
        self.loading = False

        self.full = self._read_config()
        x6 = dict(sharkctl.X6_DEFAULTS)
        x6.update(self.full.get("x6") or {})
        self.profiles = [dict(sharkctl.X6_DEFAULTS["profiles"][0], **p) for p in x6["profiles"]]
        self.stages = [str(d) for d in x6["dpi_stages"]]
        self.games = sorted(self.full.get("games", []), key=str.lower)
        self._default_idx = int(self.full.get("default_profile", 1)) - 1
        self._game_idx = int(self.full.get("game_profile", 2)) - 1
        self.cur = 0
        self._ui = queue.Queue()     # callbacks from worker threads

        root.title(TITLE)
        root.geometry("920x660")
        root.minsize(860, 620)
        set_window_icon(root, app_paths.asset("logo.ico"), app_paths.asset("logo.png"))
        root.protocol("WM_DELETE_WINDOW", self.close)

        self._build()
        self._refresh_list()
        self._load(0)
        self._refresh_games()
        self._set_dirty(False)
        self._pump()
        self._check_device()
        self._log_pos = 0
        self._tail_log(first=True)

    # ------------------------------------------------------------------ io

    def _read_config(self) -> dict:
        try:
            with open(self.config_path, encoding="utf-8-sig") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return {}
        except ValueError as exc:
            messagebox.showwarning(
                TITLE, f"O config.json tem um erro e sera recriado ao salvar:\n{exc}")
            return {}

    # -------------------------------------------------------------- layout

    def _build(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        # header
        head = ttk.Frame(root, padding=(22, 16, 22, 10))
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(1, weight=1)
        try:
            self._logo = tk.PhotoImage(file=app_paths.asset("logo.png")).subsample(6)
            tk.Label(head, image=self._logo, bg=BG).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        except tk.TclError:
            pass
        ttk.Label(head, text="Attack Shark", style="H1.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(head, text="Perfis do mouse e troca automatica nos jogos",
                  style="Muted.TLabel").grid(row=1, column=1, sticky="w")
        self.pill = tk.Label(head, text="  procurando mouse...  ", bg=CARD2, fg=MUTED,
                             font=(FONT, 9, "bold"), padx=10, pady=4)
        self.pill.grid(row=0, column=2, rowspan=2, sticky="e")

        # tabs
        self.nb = ttk.Notebook(root)
        self.nb.grid(row=1, column=0, sticky="nsew", padx=22)
        self.tab_profiles = ttk.Frame(self.nb, style="Card.TFrame", padding=4)
        self.tab_games = ttk.Frame(self.nb, style="Card.TFrame", padding=4)
        self.tab_logs = ttk.Frame(self.nb, style="Card.TFrame", padding=4)
        self.tab_about = ttk.Frame(self.nb, style="Card.TFrame", padding=4)
        self.nb.add(self.tab_profiles, text="Perfis")
        self.nb.add(self.tab_games, text="Jogos")
        self.nb.add(self.tab_logs, text="Logs")
        self.nb.add(self.tab_about, text="Sobre")
        self._build_profiles(self.tab_profiles)
        self._build_games(self.tab_games)
        self._build_logs(self.tab_logs)
        self._build_about(self.tab_about)

        # footer
        foot = ttk.Frame(root, padding=(22, 12, 22, 16))
        foot.grid(row=2, column=0, sticky="ew")
        foot.columnconfigure(0, weight=1)
        self.status = ttk.Label(foot, text="", style="Muted.TLabel")
        self.status.grid(row=0, column=0, sticky="w")
        ttk.Button(foot, text="Fechar", command=self.close).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(foot, text="Salvar", style="Accent.TButton", command=self.save).grid(row=0, column=2)
        root.bind("<Control-s>", lambda _e: self.save())

    # -- profiles tab -----------------------------------------------------

    def _build_profiles(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        # list
        left = card(tab, row=0, column=0, rowspan=2, sticky="nsw", padx=(8, 4), pady=8)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Seus perfis", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.listbox = styled_listbox(left, width=22, height=12)
        self.listbox.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(10, 10))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        ttk.Button(left, text="+  Novo", style="Accent.TButton", command=self.add).grid(
            row=2, column=0, columnspan=3, sticky="ew")
        ttk.Button(left, text="Duplicar", style="Ghost.TButton", command=self.duplicate).grid(
            row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(left, text="↑", width=3, style="Ghost.TButton", command=lambda: self.move(-1)).grid(
            row=3, column=1, sticky="ew", padx=4, pady=(6, 0))
        ttk.Button(left, text="↓", width=3, style="Ghost.TButton", command=lambda: self.move(1)).grid(
            row=3, column=2, sticky="ew", pady=(6, 0))
        ttk.Button(left, text="Remover", style="Danger.TButton", command=self.remove).grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        # editor
        right = card(tab, row=0, column=1, sticky="nsew", padx=(4, 8), pady=(8, 4))
        right.columnconfigure(1, weight=1)
        self.v_name = tk.StringVar()
        self.v_dpi = tk.StringVar()
        self.v_poll = tk.IntVar()
        self.v_resp = tk.StringVar()
        self.v_sleep = tk.IntVar()
        self.v_ripple = tk.BooleanVar()
        self.v_angle = tk.BooleanVar()

        top = ttk.Frame(right, style="Card.TFrame")
        top.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        top.columnconfigure(0, weight=1)
        name = ttk.Entry(top, textvariable=self.v_name, font=(FONT, 13, "bold"))
        name.grid(row=0, column=0, sticky="ew")
        ttk.Button(top, text="Testar no mouse", style="Ghost.TButton", command=self.test).grid(
            row=0, column=1, padx=(10, 0))

        def row_label(r, text, hint=None):
            ttk.Label(right, text=text, style="Card.TLabel").grid(row=r, column=0, sticky="w", pady=(8, 0))
            if hint:
                ttk.Label(right, text=hint, style="CardMuted.TLabel").grid(row=r + 1, column=0, sticky="nw")

        # DPI: slider + exact value
        row_label(1, "DPI", "multiplos de 50")
        self.dpi_scale = ttk.Scale(right, from_=50, to=6400, orient="horizontal",
                                   command=self._on_dpi_scale)
        self.dpi_scale.grid(row=1, column=1, sticky="ew", padx=12, pady=(8, 0))
        ttk.Spinbox(right, textvariable=self.v_dpi, from_=50, to=12800, increment=50,
                    width=7).grid(row=1, column=2, sticky="e", pady=(8, 0))

        # polling: segmented control
        row_label(3, "Polling rate", "atualizacoes por segundo")
        seg = ttk.Frame(right, style="Card.TFrame")
        seg.grid(row=3, column=1, columnspan=2, sticky="w", padx=12, pady=(8, 0))
        for k, hz in enumerate(POLLING):
            ttk.Radiobutton(seg, text=f"{hz} Hz", value=hz, variable=self.v_poll,
                            style="Seg.Toolbutton").grid(row=0, column=k, padx=(0, 2))

        row_label(5, "Resposta do clique", "menor = mais rapido")
        resp = ttk.Frame(right, style="Card.TFrame")
        resp.grid(row=5, column=1, columnspan=2, sticky="w", padx=12, pady=(8, 0))
        ttk.Combobox(resp, textvariable=self.v_resp, values=RESPOSTA, state="readonly",
                     width=5).grid(row=0, column=0)
        ttk.Label(resp, text="ms", style="CardMuted.TLabel").grid(row=0, column=1, padx=6)

        row_label(7, "Dormir apos", "sem uso, em minutos")
        self.sleep_scale = ttk.Scale(right, from_=1, to=15, orient="horizontal",
                                     command=lambda v: self.v_sleep.set(int(round(float(v)))))
        self.sleep_scale.grid(row=7, column=1, sticky="ew", padx=12, pady=(8, 0))
        self.sleep_label = ttk.Label(right, text="", style="Value.TLabel", width=7, anchor="e")
        self.sleep_label.grid(row=7, column=2, sticky="e", pady=(8, 0))

        toggles = ttk.Frame(right, style="Card.TFrame")
        toggles.grid(row=9, column=0, columnspan=3, sticky="w", pady=(16, 0))
        ttk.Checkbutton(toggles, text="Ripple control  —  suaviza tremidas do cursor",
                        variable=self.v_ripple).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(toggles, text="Angle snap  —  endireita movimentos (ruim para mira)",
                        variable=self.v_angle).grid(row=1, column=0, sticky="w", pady=(4, 0))

        for var in (self.v_name, self.v_dpi, self.v_poll, self.v_resp, self.v_sleep,
                    self.v_ripple, self.v_angle):
            var.trace_add("write", self._on_field)

        # bottom row: when to use + DPI stages
        bottom = ttk.Frame(tab, style="Card.TFrame")
        bottom.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(4, 8))
        bottom.columnconfigure(1, weight=1)

        uso = card(bottom, row=0, column=0, sticky="nsew", padx=(0, 4))
        ttk.Label(uso, text="Quando usar", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.v_default = tk.StringVar()
        self.v_game = tk.StringVar()
        ttk.Label(uso, text="Fora de jogos", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.cb_default = ttk.Combobox(uso, textvariable=self.v_default, state="readonly", width=18)
        self.cb_default.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(10, 0))
        ttk.Label(uso, text="Em jogos", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.cb_game = ttk.Combobox(uso, textvariable=self.v_game, state="readonly", width=18)
        self.cb_game.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(6, 0))
        self.v_default.trace_add("write", lambda *_: self._usage_changed())
        self.v_game.trace_add("write", lambda *_: self._usage_changed())

        st = card(bottom, row=0, column=1, sticky="nsew", padx=(4, 0))
        ttk.Label(st, text="Botao de DPI do mouse", style="Section.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(st, text="os 6 estagios que o botao percorre", style="CardMuted.TLabel").grid(
            row=1, column=0, columnspan=6, sticky="w")
        self.v_stages = []
        for k in range(6):
            var = tk.StringVar(value=self.stages[k])
            var.trace_add("write", lambda *_: self._set_dirty(True))
            ttk.Spinbox(st, textvariable=var, from_=50, to=12800, increment=50, width=6).grid(
                row=2 + k // 3, column=k % 3, padx=(0, 6), pady=(8, 0), sticky="w")
            self.v_stages.append(var)

    # -- games tab --------------------------------------------------------

    def _build_games(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        c = card(tab, row=0, column=0, sticky="nsew", padx=8, pady=8)
        c.columnconfigure(0, weight=1)
        c.rowconfigure(2, weight=1)
        ttk.Label(c, text="Jogos que ativam o perfil de jogo", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(c, text=("Nome do executavel, sem a pasta. Para descobrir, abra o jogo e veja "
                           "Gerenciador de Tarefas > Detalhes." if app_paths.IS_WINDOWS else
                           "Nome do processo ou do .exe (jogos pelo Proton). Para descobrir, abra "
                           "o jogo e rode: ps -eo comm,args | grep -i nome"),
                  style="CardMuted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 10))

        wrap = ttk.Frame(c, style="Card.TFrame")
        wrap.grid(row=2, column=0, columnspan=3, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self.games_list = styled_listbox(wrap, height=12)
        self.games_list.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.games_list.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.games_list.configure(yscrollcommand=sb.set)
        self.games_list.bind("<Delete>", lambda _e: self.remove_game())

        self.v_new_game = tk.StringVar()
        entry = ttk.Entry(c, textvariable=self.v_new_game)
        entry.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        entry.bind("<Return>", lambda _e: self.add_game())
        ttk.Button(c, text="Adicionar", style="Accent.TButton", command=self.add_game).grid(
            row=3, column=1, padx=(8, 0), pady=(12, 0))
        ttk.Button(c, text="Remover", style="Danger.TButton", command=self.remove_game).grid(
            row=3, column=2, padx=(8, 0), pady=(12, 0))
        self.detect_btn = ttk.Button(c, text="Detectar jogos instalados (Steam e Epic)",
                                     style="Ghost.TButton", command=self.detect_games)
        self.detect_btn.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))

    # -- logs tab ---------------------------------------------------------

    def _build_logs(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        c = card(tab, row=0, column=0, sticky="nsew", padx=8, pady=8)
        c.columnconfigure(0, weight=1)
        c.rowconfigure(1, weight=1)

        bar = ttk.Frame(c, style="Card.TFrame")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, text="Atividade do switcher", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.v_follow = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Acompanhar ao vivo", variable=self.v_follow).grid(row=0, column=1, padx=8)
        ttk.Button(bar, text="Copiar", style="Ghost.TButton", command=self.copy_log).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(bar, text="Abrir pasta", style="Ghost.TButton", command=self.open_log_folder).grid(row=0, column=3)

        self.log = tk.Text(c, bg="#0c0e13", fg=MUTED, insertbackground=FG, relief="flat",
                           borderwidth=0, highlightthickness=0, font=(MONO, 10),
                           wrap="none", padx=12, pady=10, state="disabled")
        self.log.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(c, orient="vertical", command=self.log.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)
        self.log.tag_configure("time", foreground="#5b6378")
        self.log.tag_configure("INFO", foreground="#c9cedb")
        self.log.tag_configure("WARNING", foreground=AMBER)
        self.log.tag_configure("ERROR", foreground=RED)
        self.log.tag_configure("switch", foreground=GREEN)
        self.log.tag_configure("game", foreground=ACCENT_HI)
        self.log.tag_configure("empty", foreground=MUTED, font=(FONT, 10, "italic"))

    # ------------------------------------------------------- device status

    # -- about tab ----------------------------------------------------------

    def _build_about(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(0, weight=1)
        top = card(tab, row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(1, weight=1)
        try:
            self._about_logo = tk.PhotoImage(file=app_paths.asset("logo.png")).subsample(3)
            tk.Label(top, image=self._about_logo, bg=CARD).grid(row=0, column=0, rowspan=3, padx=(0, 18))
        except tk.TclError:
            pass
        ttk.Label(top, text=app_paths.APP_FULL_NAME, style="Section.TLabel",
                  font=(FONT, 14, "bold")).grid(row=0, column=1, sticky="w")
        system = "Windows" if app_paths.IS_WINDOWS else "Linux"
        ttk.Label(top, text=f"Versao {app_paths.APP_VERSION}  \u00b7  {system}",
                  style="Value.TLabel").grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Label(top, text="Troca automatica de perfil para mouses Attack Shark V8 e X6. "
                            "Codigo aberto, licenca MIT.",
                  style="CardMuted.TLabel").grid(row=2, column=1, sticky="w", pady=(4, 0))

        up = card(tab, row=1, column=0, sticky="ew", padx=8, pady=4)
        up.columnconfigure(0, weight=1)
        ttk.Label(up, text="Atualizacoes", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.update_status = ttk.Label(up, text="Clique em Verificar para procurar uma versao nova.",
                                       style="Card.TLabel")
        self.update_status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        style = ttk.Style(self.root)
        style.configure("Upd.Horizontal.TProgressbar", troughcolor=INPUT, background=ACCENT,
                        bordercolor=INPUT, lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
        self.update_bar = ttk.Progressbar(up, style="Upd.Horizontal.TProgressbar", maximum=100)
        btns = ttk.Frame(up, style="Card.TFrame")
        btns.grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.check_btn = ttk.Button(btns, text="Verificar agora", style="Accent.TButton",
                                    command=self.check_update)
        self.check_btn.grid(row=0, column=0)
        self.install_btn = ttk.Button(btns, text="Atualizar agora", style="Accent.TButton",
                                      command=self.install_update)
        self.v_check_updates = tk.BooleanVar(value=bool(self.full.get("check_updates", True)))
        self.v_check_updates.trace_add("write", lambda *_: self._set_dirty(True))
        ttk.Checkbutton(up, text="Verificar atualizacoes automaticamente (uma vez por dia)",
                        variable=self.v_check_updates).grid(row=4, column=0, columnspan=3,
                                                            sticky="w", pady=(12, 0))

        links = card(tab, row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        ttk.Label(links, text="Links", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        import webbrowser
        repo = f"https://github.com/{app_paths.GITHUB_REPO}"
        for k, (text, url) in enumerate((("Pagina do projeto", repo),
                                         ("Versoes publicadas", repo + "/releases"),
                                         ("Relatar um problema", repo + "/issues"))):
            ttk.Button(links, text=text, style="Ghost.TButton",
                       command=lambda u=url: webbrowser.open(u)).grid(
                row=1, column=k, padx=(0, 8), pady=(10, 0), sticky="w")
        self._release = None

    def check_update(self) -> None:
        import updater
        self.check_btn.config(state="disabled", text="Verificando...")
        self.install_btn.grid_remove()

        def worker():
            try:
                result = ("ok", updater.latest_release())
            except updater.UpdateError as exc:
                result = ("error", str(exc))
            self._ui.put(lambda: self._update_checked(*result))
        threading.Thread(target=worker, daemon=True).start()

    def _update_checked(self, kind: str, value) -> None:
        import updater
        self.check_btn.config(state="normal", text="Verificar agora")
        if kind == "error":
            self.update_status.config(text=value, foreground=AMBER)
            return
        rel = value
        if not updater.is_newer(rel.version):
            self.update_status.config(
                text=f"\u2714  Voce esta na versao mais recente ({app_paths.APP_VERSION}).",
                foreground=GREEN)
            return
        self._release = rel
        self.update_status.config(text=f"\u2b06  Versao {rel.version} disponivel "
                                       f"(voce tem a {app_paths.APP_VERSION}).", foreground=ACCENT_HI)
        self.install_btn.config(text="Atualizar agora" if updater.can_self_update(rel)
                                else "Abrir pagina da versao")
        self.install_btn.grid(row=0, column=1, padx=(8, 0))

    def install_update(self) -> None:
        import updater
        rel = self._release
        if rel is None:
            return
        if not updater.can_self_update(rel):
            updater.open_release_page(rel)
            return
        if self.dirty and not messagebox.askyesno(
                TITLE, "Voce tem alteracoes nao salvas, que serao perdidas. Atualizar mesmo assim?"):
            return
        self.install_btn.config(state="disabled")
        self.check_btn.config(state="disabled")
        self.update_bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        def progress(done, total):
            pct = int(100 * done / total) if total else 0
            self._ui.put(lambda: (self.update_bar.configure(value=pct),
                                  self.update_status.config(text=f"Baixando... {pct}%",
                                                            foreground=FG)))

        def worker():
            try:
                path = updater.download_installer(rel, progress)
            except updater.UpdateError as exc:
                msg = str(exc)
                self._ui.put(lambda: self._update_failed(msg))
                return
            self._ui.put(lambda: self.update_status.config(
                text="Instalando... o Attack Shark vai fechar e abrir de novo sozinho.",
                foreground=GREEN))
            updater.run_installer(path)
        threading.Thread(target=worker, daemon=True).start()

    def _update_failed(self, message: str) -> None:
        self.update_bar.grid_remove()
        self.install_btn.config(state="normal")
        self.check_btn.config(state="normal")
        self.update_status.config(text=message, foreground=RED)

    def _check_device(self) -> None:
        def worker():
            try:
                ok = sharkctl.find_device() is not None
            except Exception:
                ok = False
            self._ui.put(lambda: self._set_pill(ok))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(3000, self._check_device)

    def _pump(self) -> None:
        # Tk may only be touched from its own thread: workers queue callbacks.
        while True:
            try:
                fn = self._ui.get_nowait()
            except queue.Empty:
                break
            fn()
        self.root.after(150, self._pump)

    def _set_pill(self, ok: bool) -> None:
        if ok:
            self.pill.config(text="●  Mouse conectado", bg="#143326", fg=GREEN)
        else:
            self.pill.config(text="●  Mouse nao encontrado", bg="#3a1f26", fg=RED)

    # --------------------------------------------------------- profile list

    def _labels(self) -> list[str]:
        return [f"{i + 1}.  {p.get('name') or '(sem nome)'}" for i, p in enumerate(self.profiles)]

    def _refresh_list(self) -> None:
        labels = self._labels()
        self.listbox.delete(0, "end")
        for text in labels:
            self.listbox.insert("end", "  " + text)
        self.listbox.selection_set(self.cur)
        self.listbox.see(self.cur)
        n = len(self.profiles)
        self._default_idx = min(max(self._default_idx, 0), n - 1)
        self._game_idx = min(max(self._game_idx, 0), n - 1)
        self.cb_default["values"] = labels
        self.cb_game["values"] = labels
        was = self.loading
        self.loading = True
        self.v_default.set(labels[self._default_idx])
        self.v_game.set(labels[self._game_idx])
        self.loading = was

    def _usage_changed(self) -> None:
        if self.loading:
            return
        labels = list(self.cb_default["values"])
        if self.v_default.get() in labels:
            self._default_idx = labels.index(self.v_default.get())
        if self.v_game.get() in labels:
            self._game_idx = labels.index(self.v_game.get())
        self._set_dirty(True)

    def _load(self, i: int) -> None:
        self.cur = i
        p = self.profiles[i]
        self.loading = True
        self.v_name.set(p.get("name", ""))
        self.v_dpi.set(str(p.get("dpi", 800)))
        self.v_poll.set(int(p.get("polling") or 1000))
        self.v_resp.set(str(p.get("key_response_ms") or 8))
        self.v_sleep.set(int(p.get("deep_sleep_min") or 10))
        self.v_ripple.set(bool(p.get("ripple")))
        self.v_angle.set(bool(p.get("angle_snap")))
        self._sync_widgets()
        self.loading = False

    def _sync_widgets(self) -> None:
        try:
            self.dpi_scale.set(min(int(self.v_dpi.get()), 6400))
        except ValueError:
            pass
        self.sleep_scale.set(self.v_sleep.get())
        self.sleep_label.config(text=f"{self.v_sleep.get()} min")

    def _on_dpi_scale(self, value) -> None:
        if self.loading:
            return
        snapped = int(round(float(value) / 50.0)) * 50
        if self.v_dpi.get() != str(snapped):
            self.v_dpi.set(str(snapped))

    def _on_select(self, _event=None) -> None:
        sel = self.listbox.curselection()
        if sel and sel[0] != self.cur:
            self._load(sel[0])

    def _on_field(self, *_):
        if self.loading:
            return
        p = self.profiles[self.cur]
        p["name"] = self.v_name.get().strip()
        p["dpi"] = self.v_dpi.get().strip()
        p["polling"] = self.v_poll.get()
        p["key_response_ms"] = self.v_resp.get()
        p["deep_sleep_min"] = self.v_sleep.get()
        p["ripple"] = self.v_ripple.get()
        p["angle_snap"] = self.v_angle.get()
        self.loading = True
        self._sync_widgets()
        self.loading = False
        label = "  " + self._labels()[self.cur]
        if self.listbox.get(self.cur) != label:
            self._refresh_list()
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self.loading:
            return
        self.dirty = dirty
        if dirty:
            self.status.config(text="●  Alteracoes nao salvas   (Ctrl+S para salvar)", foreground=AMBER)

    def add(self) -> None:
        self._insert(dict(NOVO_PERFIL))

    def duplicate(self) -> None:
        p = dict(self.profiles[self.cur])
        p["name"] = (p.get("name") or "Perfil") + " (copia)"
        self._insert(p)

    def _insert(self, profile: dict) -> None:
        self.profiles.insert(self.cur + 1, profile)
        if self._default_idx > self.cur:
            self._default_idx += 1
        if self._game_idx > self.cur:
            self._game_idx += 1
        self.cur += 1
        self._refresh_list()
        self._load(self.cur)
        self._set_dirty(True)

    def remove(self) -> None:
        if len(self.profiles) == 1:
            messagebox.showinfo(TITLE, "Precisa ter pelo menos um perfil.")
            return
        name = self.profiles[self.cur].get("name") or "este perfil"
        if not messagebox.askyesno(TITLE, f"Remover {name}?"):
            return
        del self.profiles[self.cur]
        for attr in ("_default_idx", "_game_idx"):
            idx = getattr(self, attr)
            if idx > self.cur or idx == len(self.profiles):
                setattr(self, attr, idx - 1)
        self.cur = min(self.cur, len(self.profiles) - 1)
        self._refresh_list()
        self._load(self.cur)
        self._set_dirty(True)

    def move(self, step: int) -> None:
        j = self.cur + step
        if not 0 <= j < len(self.profiles):
            return
        self.profiles[self.cur], self.profiles[j] = self.profiles[j], self.profiles[self.cur]
        for attr in ("_default_idx", "_game_idx"):
            idx = getattr(self, attr)
            if idx == self.cur:
                setattr(self, attr, j)
            elif idx == j:
                setattr(self, attr, self.cur)
        self.cur = j
        self._refresh_list()
        self._set_dirty(True)

    # ------------------------------------------------------------- games

    def _refresh_games(self) -> None:
        self.games_list.delete(0, "end")
        for g in self.games:
            self.games_list.insert("end", "  " + g)
        if not self.games:
            self.games_list.insert("end", "  Nenhum jogo ainda - adicione abaixo ou use Detectar")
            self.games_list.itemconfig(0, fg=MUTED)

    def add_game(self) -> None:
        name = os.path.basename(self.v_new_game.get().strip().strip('"'))
        if not name:
            return
        if not name.lower().endswith(".exe"):
            name += ".exe"
        if name.lower() in {g.lower() for g in self.games}:
            self.status.config(text=f"{name} ja esta na lista", foreground=MUTED)
        else:
            self.games = sorted(self.games + [name], key=str.lower)
            self._refresh_games()
            self._set_dirty(True)
        self.v_new_game.set("")

    def remove_game(self) -> None:
        sel = self.games_list.curselection()
        if not sel or not self.games:
            return
        del self.games[sel[0]]
        self._refresh_games()
        self._set_dirty(True)

    def detect_games(self) -> None:
        self.detect_btn.config(text="Procurando...", state="disabled")

        def worker():
            try:
                import detect_games
                found = detect_games.find_all_games()
            except Exception as exc:
                found, error = {}, exc
            else:
                error = None
            self._ui.put(lambda: self._detect_done(found, error))
        threading.Thread(target=worker, daemon=True).start()

    def _detect_done(self, found: dict, error) -> None:
        self.detect_btn.config(text="Detectar jogos instalados (Steam e Epic)", state="normal")
        if error:
            messagebox.showerror(TITLE, f"Falha ao procurar jogos:\n{error}")
            return
        have = {g.lower() for g in self.games}
        new = [exe for exe in found if exe.lower() not in have]
        if new:
            self.games = sorted(self.games + new, key=str.lower)
            self._refresh_games()
            self._set_dirty(True)
            messagebox.showinfo(TITLE, f"{len(new)} jogo(s) adicionado(s):\n\n"
                                + "\n".join(f"{found[e]}  ({e})" for e in sorted(new))
                                + "\n\nConfira a lista: a deteccao pode errar o .exe.")
        else:
            messagebox.showinfo(TITLE, f"Nenhum jogo novo ({len(found)} encontrado(s)).")

    # -------------------------------------------------------------- logs

    def _tail_log(self, first: bool = False) -> None:
        try:
            size = os.path.getsize(LOG_PATH)
        except OSError:
            size = None
        if size is None:
            if first or self._log_pos != -1:
                self._log_set_empty()
                self._log_pos = -1
        elif size != self._log_pos and (self.v_follow.get() or first or self._log_pos == -1):
            self._log_render()
            self._log_pos = size
        self.root.after(1000, self._tail_log)

    def _log_set_empty(self) -> None:
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", "Nenhum log ainda. Ele aparece aqui assim que o switcher "
                               "estiver rodando (icone na bandeja).", "empty")
        self.log.config(state="disabled")

    def _log_render(self) -> None:
        try:
            with open(LOG_PATH, encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()[-500:]
        except OSError:
            return
        at_end = self.log.yview()[1] > 0.98
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        for line in lines:
            line = line.rstrip("\n")
            # "2026-11-16 10:00:00  INFO    message"
            stamp, rest = line[:19], line[19:]
            level = rest.strip().split(" ", 1)[0] if rest.strip() else ""
            tag = level if level in ("INFO", "WARNING", "ERROR") else "INFO"
            low = rest.lower()
            if tag == "INFO" and "switched to" in low:
                tag = "switch"
            elif tag == "INFO" and ("game detected" in low or "game exited" in low):
                tag = "game"
            if stamp[:2] == "20" and len(stamp) == 19:
                self.log.insert("end", stamp[11:], "time")
                self.log.insert("end", rest + "\n", tag)
            else:
                self.log.insert("end", line + "\n", tag)
        self.log.config(state="disabled")
        if at_end or self.v_follow.get():
            self.log.see("end")

    def copy_log(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log.get("1.0", "end"))
        self.status.config(text="Log copiado", foreground=MUTED)

    def open_log_folder(self) -> None:
        folder = os.path.dirname(LOG_PATH)
        if os.path.isdir(folder):
            app_paths.open_path(folder)
        else:
            messagebox.showinfo(TITLE, "A pasta de logs ainda nao existe.")

    # ------------------------------------------------------- validation

    def _collect(self) -> dict | None:
        def bad(msg: str, perfil: int | None = None) -> None:
            self.nb.select(self.tab_profiles)
            if perfil is not None:
                self.cur = perfil
                self._refresh_list()
                self._load(perfil)
            messagebox.showerror(TITLE, msg)

        try:
            stages = [int(v.get()) for v in self.v_stages]
        except ValueError:
            bad("Os estagios de DPI precisam ser numeros.")
            return None
        for d in stages:
            if not (50 <= d <= 12800 and d % 50 == 0):
                bad(f"Estagio de DPI invalido: {d}\nUse multiplos de 50, de 50 a 12800.")
                return None

        profiles = []
        for i, p in enumerate(self.profiles):
            nome = (p.get("name") or "").strip()
            if not nome:
                bad(f"O perfil {i + 1} precisa de um nome.", i)
                return None
            try:
                dpi = int(p["dpi"])
            except (ValueError, TypeError):
                bad(f"'{nome}': o DPI precisa ser um numero.", i)
                return None
            if not (50 <= dpi <= 12800 and dpi % 50 == 0):
                bad(f"'{nome}': DPI invalido ({dpi}).\nUse multiplos de 50, de 50 a 12800.", i)
                return None
            profiles.append({
                "name": nome, "dpi": dpi, "polling": int(p["polling"]),
                "key_response_ms": int(p["key_response_ms"]),
                "deep_sleep_min": int(p["deep_sleep_min"]),
                "ripple": bool(p["ripple"]), "angle_snap": bool(p["angle_snap"]),
            })

        x6 = {"dpi_stages": stages, "profiles": profiles}
        try:
            sharkctl.validate_x6(x6)
        except (ValueError, KeyError, TypeError) as exc:
            bad(f"Configuracao invalida: {exc}")
            return None
        return x6

    # ----------------------------------------------------------- actions

    def test(self) -> None:
        x6 = self._collect()
        if x6 is None:
            return
        try:
            sharkctl.x6_apply(x6["profiles"][self.cur], x6["dpi_stages"])
        except HidError as exc:
            messagebox.showerror(TITLE, f"Nao consegui falar com o mouse:\n{exc}")
            return
        self.status.config(text=f"▶  '{x6['profiles'][self.cur]['name']}' aplicado no mouse "
                                "(teste, ainda nao salvo)", foreground=ACCENT_HI)

    def save(self) -> bool:
        x6 = self._collect()
        if x6 is None:
            return False
        full = self._read_config() if os.path.exists(self.config_path) else {}
        full["x6"] = x6
        full["default_profile"] = self._default_idx + 1
        full["game_profile"] = self._game_idx + 1
        full["games"] = list(self.games)
        full["check_updates"] = bool(self.v_check_updates.get())
        tmp = self.config_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(full, handle, indent=2, ensure_ascii=False)
            os.replace(tmp, self.config_path)
        except OSError as exc:
            messagebox.showerror(TITLE, f"Nao consegui salvar o config.json:\n{exc}")
            return False
        self.dirty = False
        self.status.config(text="✔  Salvo. O switcher aplica em ate 2 segundos.", foreground=GREEN)
        return True

    def close(self) -> None:
        if self.dirty:
            answer = messagebox.askyesnocancel(TITLE, "Salvar as alteracoes antes de fechar?")
            if answer is None:
                return
            if answer and not self.save():
                return
        self.root.destroy()


def run(config_path: str) -> int:
    """Open the window on the given config.json; returns when it closes."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # crisp text on high-DPI screens
    except Exception:
        pass
    sharkctl.set_config_path(config_path)
    root = tk.Tk()
    setup_style(root)
    App(root, os.path.abspath(config_path))
    dark_title_bar(root)
    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=app_paths.CONFIG_PATH)
    args = parser.parse_args()
    app_paths.ensure_config()
    return run(args.config)


if __name__ == "__main__":
    sys.exit(main())
