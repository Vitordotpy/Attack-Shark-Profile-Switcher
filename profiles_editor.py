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
import time
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

import app_paths
import i18n
import sharkctl
from i18n import _
from sharkctl import HidError



def _title() -> str:
    return _("Attack Shark - Configuracoes")

LOG_PATH = app_paths.LOG_PATH

POLLING = [125, 250, 500, 1000]
RESPOSTA = [str(n) for n in range(2, 21, 2)]
# Light effect names, in sharkctl.X6_LED_MODES order (source text, translated when shown).
LED_MODE_NAMES = ["Desligado", "Estatico", "Breathing", "Neon", "Breathing colorido",
                  "DPI estatico", "DPI breathing"]

# Tk key names -> sharkctl.HID_KEYS names, for recording macros.
TK_TO_HID = {
    "Return": "ENTER", "KP_Enter": "ENTER", "Escape": "ESC", "BackSpace": "BACKSPACE", "Tab": "TAB",
    "space": "SPACE", "minus": "MINUS", "equal": "EQUAL", "bracketleft": "LBRACKET",
    "bracketright": "RBRACKET", "backslash": "BACKSLASH", "semicolon": "SEMICOLON",
    "ccedilla": "SEMICOLON", "Ccedilla": "SEMICOLON", "apostrophe": "QUOTE", "grave": "GRAVE",
    "comma": "COMMA", "period": "PERIOD", "slash": "SLASH", "Caps_Lock": "CAPSLOCK",
    "Print": "PRINTSCREEN", "Scroll_Lock": "SCROLLLOCK", "Pause": "PAUSE", "Insert": "INSERT",
    "Home": "HOME", "Prior": "PAGEUP", "Delete": "DELETE", "End": "END", "Next": "PAGEDOWN",
    "Right": "RIGHT", "Left": "LEFT", "Down": "DOWN", "Up": "UP",
    "Control_L": "LCTRL", "Shift_L": "LSHIFT", "Alt_L": "LALT", "Win_L": "LWIN", "Super_L": "LWIN",
    "Control_R": "RCTRL", "Shift_R": "RSHIFT", "Alt_R": "RALT", "ISO_Level3_Shift": "RALT",
    "Win_R": "RWIN", "Super_R": "RWIN",
}
MACRO_BUTTONS = [("forward", "Lateral da frente"), ("backward", "Lateral de tras")]


def tk_key_to_hid(keysym: str) -> str | None:
    if len(keysym) == 1 and keysym.isalnum() and keysym.isascii():
        return keysym.upper()
    if keysym.startswith("KP_") and keysym[3:].isdigit():
        return keysym[3:]
    if keysym.startswith("F") and keysym[1:].isdigit() and 1 <= int(keysym[1:]) <= 12:
        return keysym
    return TK_TO_HID.get(keysym)


NOVO_PERFIL = {"name": "Novo perfil", "dpi": 1600, "polling": 1000, "key_response_ms": 8,
               "deep_sleep_min": 10, "ripple": False, "angle_snap": False}

from ui_theme import (ACCENT, ACCENT_HI, AMBER, BG, CARD, CARD2, FG, FONT, GREEN,  # noqa: E402
                      INPUT, MONO, MUTED, RED, card, dark_title_bar, set_window_icon,
                      setup_style, styled_listbox, ScrollFrame)


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
        self.macros = {b: (self.full.get("macros") or {}).get(b) for b, _l in MACRO_BUTTONS}
        self._macros_loaded = json.dumps(self.macros, sort_keys=True)
        self.recording = False
        self._ui = queue.Queue()     # callbacks from worker threads

        root.title(_title())
        height = min(850, root.winfo_screenheight() - 80)
        root.geometry(f"940x{height}")
        root.minsize(820, 480)
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
                _title(), _("O config.json tem um erro e sera recriado ao salvar:\n{exc}", exc=exc))
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
        ttk.Label(head, text=_("Perfis do mouse e troca automatica nos jogos"),
                  style="Muted.TLabel").grid(row=1, column=1, sticky="w")
        self.pill = tk.Label(head, text="  " + _("procurando mouse...") + "  ", bg=CARD2, fg=MUTED,
                             font=(FONT, 9, "bold"), padx=10, pady=4)
        self.pill.grid(row=0, column=2, rowspan=2, sticky="e")

        # tabs
        self.nb = ttk.Notebook(root)
        self.nb.grid(row=1, column=0, sticky="nsew", padx=22)
        self.tab_profiles = ttk.Frame(self.nb, style="Card.TFrame", padding=4)
        self.tab_games = ttk.Frame(self.nb, style="Card.TFrame", padding=4)
        self.tab_macros = ttk.Frame(self.nb, style="Card.TFrame", padding=4)
        self.tab_logs = ttk.Frame(self.nb, style="Card.TFrame", padding=4)
        self.tab_about = ttk.Frame(self.nb, style="Card.TFrame", padding=4)
        self.nb.add(self.tab_profiles, text=_("Perfis"))
        self.nb.add(self.tab_games, text=_("Jogos"))
        self.nb.add(self.tab_macros, text=_("Macros"))
        self.nb.add(self.tab_logs, text=_("Logs"))
        self.nb.add(self.tab_about, text=_("Sobre"))
        # Each tab scrolls when the window is too short for it.
        self._build_profiles(self._scrolled(self.tab_profiles))
        self._build_games(self._scrolled(self.tab_games))
        self._build_macros(self._scrolled(self.tab_macros))
        self._build_logs(self._scrolled(self.tab_logs))
        self._build_about(self._scrolled(self.tab_about))

        # footer
        foot = ttk.Frame(root, padding=(22, 12, 22, 16))
        foot.grid(row=2, column=0, sticky="ew")
        foot.columnconfigure(0, weight=1)
        self.status = ttk.Label(foot, text="", style="Muted.TLabel")
        self.status.grid(row=0, column=0, sticky="w")
        ttk.Button(foot, text=_("Fechar"), command=self.close).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(foot, text=_("Salvar"), style="Accent.TButton", command=self.save).grid(row=0, column=2)
        root.bind("<Control-s>", lambda _e: None if self.recording else self.save())

    @staticmethod
    def _scrolled(tab: ttk.Frame) -> ttk.Frame:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        frame = ScrollFrame(tab)
        frame.grid(row=0, column=0, sticky="nsew")
        return frame.inner

    # -- profiles tab -----------------------------------------------------

    def _build_profiles(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        # list
        left = card(tab, row=0, column=0, rowspan=2, sticky="nsw", padx=(8, 4), pady=8)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text=_("Seus perfis"), style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.listbox = styled_listbox(left, width=22, height=12)
        self.listbox.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(10, 10))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        ttk.Button(left, text=_("+  Novo"), style="Accent.TButton", command=self.add).grid(
            row=2, column=0, columnspan=3, sticky="ew")
        ttk.Button(left, text=_("Duplicar"), style="Ghost.TButton", command=self.duplicate).grid(
            row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(left, text="↑", width=3, style="Ghost.TButton", command=lambda: self.move(-1)).grid(
            row=3, column=1, sticky="ew", padx=4, pady=(6, 0))
        ttk.Button(left, text="↓", width=3, style="Ghost.TButton", command=lambda: self.move(1)).grid(
            row=3, column=2, sticky="ew", pady=(6, 0))
        ttk.Button(left, text=_("Remover"), style="Danger.TButton", command=self.remove).grid(
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
        ttk.Button(top, text=_("Testar no mouse"), style="Ghost.TButton", command=self.test).grid(
            row=0, column=1, padx=(10, 0))

        def row_label(r, text, hint=None):
            ttk.Label(right, text=text, style="Card.TLabel").grid(row=r, column=0, sticky="w", pady=(8, 0))
            if hint:
                ttk.Label(right, text=hint, style="CardMuted.TLabel").grid(row=r + 1, column=0, sticky="nw")

        # DPI: slider + exact value
        row_label(1, "DPI", _("multiplos de 50"))
        self.dpi_scale = ttk.Scale(right, from_=50, to=6400, orient="horizontal",
                                   command=self._on_dpi_scale)
        self.dpi_scale.grid(row=1, column=1, sticky="ew", padx=12, pady=(8, 0))
        ttk.Spinbox(right, textvariable=self.v_dpi, from_=50, to=12800, increment=50,
                    width=7).grid(row=1, column=2, sticky="e", pady=(8, 0))

        # polling: segmented control
        row_label(3, _("Polling rate"), _("atualizacoes por segundo"))
        seg = ttk.Frame(right, style="Card.TFrame")
        seg.grid(row=3, column=1, columnspan=2, sticky="w", padx=12, pady=(8, 0))
        for k, hz in enumerate(POLLING):
            ttk.Radiobutton(seg, text=f"{hz} Hz", value=hz, variable=self.v_poll,
                            style="Seg.Toolbutton").grid(row=0, column=k, padx=(0, 2))

        row_label(5, _("Resposta do clique"), _("menor = mais rapido"))
        resp = ttk.Frame(right, style="Card.TFrame")
        resp.grid(row=5, column=1, columnspan=2, sticky="w", padx=12, pady=(8, 0))
        ttk.Combobox(resp, textvariable=self.v_resp, values=RESPOSTA, state="readonly",
                     width=5).grid(row=0, column=0)
        ttk.Label(resp, text="ms", style="CardMuted.TLabel").grid(row=0, column=1, padx=6)

        row_label(7, _("Dormir apos"), _("sem uso, em minutos"))
        self.sleep_scale = ttk.Scale(right, from_=1, to=15, orient="horizontal",
                                     command=lambda v: self.v_sleep.set(int(round(float(v)))))
        self.sleep_scale.grid(row=7, column=1, sticky="ew", padx=12, pady=(8, 0))
        self.sleep_label = ttk.Label(right, text="", style="Value.TLabel", width=7, anchor="e")
        self.sleep_label.grid(row=7, column=2, sticky="e", pady=(8, 0))

        toggles = ttk.Frame(right, style="Card.TFrame")
        toggles.grid(row=9, column=0, columnspan=3, sticky="w", pady=(16, 0))
        ttk.Checkbutton(toggles, text=_("Ripple control  —  suaviza tremidas do cursor"),
                        variable=self.v_ripple).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(toggles, text=_("Angle snap  —  endireita movimentos (ruim para mira)"),
                        variable=self.v_angle).grid(row=1, column=0, sticky="w", pady=(4, 0))

        # lighting
        ttk.Label(right, text=_("Iluminacao"), style="Section.TLabel").grid(
            row=10, column=0, columnspan=3, sticky="w", pady=(18, 0))
        self.v_led_mode = tk.StringVar()
        self.v_led_color = tk.StringVar()
        self.v_led_bright = tk.IntVar()
        self.v_led_speed = tk.IntVar()
        ttk.Label(right, text=_("Efeito"), style="Card.TLabel").grid(row=11, column=0, sticky="w", pady=(8, 0))
        led_row = ttk.Frame(right, style="Card.TFrame")
        led_row.grid(row=11, column=1, columnspan=2, sticky="w", padx=12, pady=(8, 0))
        self.led_mode_cb = ttk.Combobox(led_row, textvariable=self.v_led_mode, state="readonly", width=20,
                                        values=[_(n) for n in LED_MODE_NAMES])
        self.led_mode_cb.grid(row=0, column=0)
        self.led_swatch = tk.Button(led_row, width=3, relief="flat", bd=0, cursor="hand2",
                                    highlightthickness=1, highlightbackground=CARD2,
                                    command=self.pick_led_color)
        self.led_swatch.grid(row=0, column=1, padx=(12, 6), ipady=3)
        self.led_color_btn = ttk.Button(led_row, text=_("Escolher cor"), style="Ghost.TButton",
                                        command=self.pick_led_color)
        self.led_color_btn.grid(row=0, column=2)

        ttk.Label(right, text=_("Brilho"), style="Card.TLabel").grid(row=12, column=0, sticky="w", pady=(8, 0))
        self.bright_scale = ttk.Scale(right, from_=1, to=8, orient="horizontal",
                                      command=lambda v: self.v_led_bright.set(int(round(float(v)))))
        self.bright_scale.grid(row=12, column=1, sticky="ew", padx=12, pady=(8, 0))
        self.bright_label = ttk.Label(right, text="", style="Value.TLabel", width=7, anchor="e")
        self.bright_label.grid(row=12, column=2, sticky="e", pady=(8, 0))

        ttk.Label(right, text=_("Velocidade"), style="Card.TLabel").grid(row=13, column=0, sticky="w", pady=(8, 0))
        self.speed_scale = ttk.Scale(right, from_=1, to=5, orient="horizontal",
                                     command=lambda v: self.v_led_speed.set(int(round(float(v)))))
        self.speed_scale.grid(row=13, column=1, sticky="ew", padx=12, pady=(8, 0))
        self.speed_label = ttk.Label(right, text="", style="Value.TLabel", width=7, anchor="e")
        self.speed_label.grid(row=13, column=2, sticky="e", pady=(8, 0))

        for var in (self.v_name, self.v_dpi, self.v_poll, self.v_resp, self.v_sleep,
                    self.v_ripple, self.v_angle, self.v_led_mode, self.v_led_color,
                    self.v_led_bright, self.v_led_speed):
            var.trace_add("write", self._on_field)

        # bottom row: when to use + DPI stages
        bottom = ttk.Frame(tab, style="Card.TFrame")
        bottom.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(4, 8))
        bottom.columnconfigure(1, weight=1)

        uso = card(bottom, row=0, column=0, sticky="nsew", padx=(0, 4))
        ttk.Label(uso, text=_("Quando usar"), style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.v_default = tk.StringVar()
        self.v_game = tk.StringVar()
        ttk.Label(uso, text=_("Fora de jogos"), style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.cb_default = ttk.Combobox(uso, textvariable=self.v_default, state="readonly", width=18)
        self.cb_default.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(10, 0))
        ttk.Label(uso, text=_("Em jogos"), style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.cb_game = ttk.Combobox(uso, textvariable=self.v_game, state="readonly", width=18)
        self.cb_game.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(6, 0))
        self.v_default.trace_add("write", lambda *_: self._usage_changed())
        self.v_game.trace_add("write", lambda *_: self._usage_changed())

        st = card(bottom, row=0, column=1, sticky="nsew", padx=(4, 0))
        ttk.Label(st, text=_("Botao de DPI do mouse"), style="Section.TLabel").grid(
            row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(st, text=_("os 6 estagios que o botao percorre"), style="CardMuted.TLabel").grid(
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
        ttk.Label(c, text=_("Jogos que ativam o perfil de jogo"), style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(c, text=(_("Nome do executavel, sem a pasta. Para descobrir, abra o jogo e veja "
                             "Gerenciador de Tarefas > Detalhes.") if app_paths.IS_WINDOWS else
                           _("Nome do processo ou do .exe (jogos pelo Proton). Para descobrir, abra "
                             "o jogo e rode: ps -eo comm,args | grep -i nome")),
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
        ttk.Button(c, text=_("Adicionar"), style="Accent.TButton", command=self.add_game).grid(
            row=3, column=1, padx=(8, 0), pady=(12, 0))
        ttk.Button(c, text=_("Remover"), style="Danger.TButton", command=self.remove_game).grid(
            row=3, column=2, padx=(8, 0), pady=(12, 0))
        self.detect_btn = ttk.Button(c, text=_("Detectar jogos instalados (Steam e Epic)"),
                                     style="Ghost.TButton", command=self.detect_games)
        self.detect_btn.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))

    # -- macros tab -------------------------------------------------------

    def _build_macros(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        style = ttk.Style(self.root)
        style.configure("Treeview", background=INPUT, fieldbackground=INPUT, foreground=FG,
                        rowheight=28, borderwidth=0, font=(FONT, 10))
        style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading", background=CARD2, foreground=MUTED, relief="flat",
                        font=(FONT, 9, "bold"), padding=(8, 6))
        style.map("Treeview.Heading", background=[("active", INPUT)])

        side = card(tab, row=0, column=0, sticky="nsw", padx=(8, 4), pady=8)
        ttk.Label(side, text=_("Botao do mouse"), style="Section.TLabel").grid(sticky="w")
        self.v_macro_btn = tk.StringVar(value="forward")
        for key, label in MACRO_BUTTONS:
            ttk.Radiobutton(side, text=_(label), value=key, variable=self.v_macro_btn,
                            style="Seg.Toolbutton", command=self._macro_switch).grid(
                sticky="ew", pady=(8, 0))
        self.v_macro_on = tk.BooleanVar()
        ttk.Checkbutton(side, text=_("Usar macro neste botao"), variable=self.v_macro_on,
                        command=self._macro_store).grid(sticky="w", pady=(18, 0))
        ttk.Label(side, text=_("Repetir"), style="Card.TLabel").grid(sticky="w", pady=(14, 0))
        self.v_macro_loops = tk.StringVar(value="1")
        loops = ttk.Spinbox(side, from_=1, to=255, textvariable=self.v_macro_loops, width=6,
                            command=self._macro_store)
        loops.grid(sticky="w", pady=(4, 0))
        loops.bind("<KeyRelease>", lambda _e: self._macro_store())
        ttk.Label(side, text=_("vezes a cada clique"), style="CardMuted.TLabel").grid(sticky="w")
        ttk.Label(side, text=_("Sem macro, o botao faz a funcao normal dele (avancar / voltar "
                               "no navegador)."),
                  style="CardMuted.TLabel", wraplength=200, justify="left").grid(sticky="w", pady=(18, 0))

        main = card(tab, row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)
        bar = ttk.Frame(main, style="Card.TFrame")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, text=_("Passos da macro"), style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.rec_btn = ttk.Button(bar, text=_("●  Gravar"), style="Accent.TButton",
                                  command=self.toggle_record)
        self.rec_btn.grid(row=0, column=1, padx=(0, 6))
        ttk.Button(bar, text=_("Remover passo"), style="Ghost.TButton",
                   command=self.macro_remove_step).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(bar, text=_("Limpar"), style="Danger.TButton", command=self.macro_clear).grid(row=0, column=3)

        self.macro_tree = ttk.Treeview(main, columns=("n", "key", "action", "delay"),
                                       show="headings", selectmode="browse", height=9)
        for col, text, width, anchor in (("n", "#", 44, "center"), ("key", _("Tecla"), 160, "w"),
                                         ("action", _("Acao"), 140, "w"),
                                         ("delay", _("Espera depois (ms)"), 150, "center")):
            self.macro_tree.heading(col, text=text)
            self.macro_tree.column(col, width=width, anchor=anchor, stretch=col == "key")
        self.macro_tree.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(main, orient="vertical", command=self.macro_tree.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.macro_tree.configure(yscrollcommand=sb.set)
        self.macro_tree.bind("<<TreeviewSelect>>", self._macro_selected)
        self.macro_tree.bind("<KeyPress>", self._record_key)
        self.macro_tree.bind("<KeyRelease>", self._record_key)

        edit = ttk.Frame(main, style="Card.TFrame")
        edit.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(edit, text=_("Espera depois do passo selecionado"), style="Card.TLabel").grid(
            row=0, column=0, sticky="w")
        self.v_step_delay = tk.StringVar(value="10")
        ttk.Spinbox(edit, from_=10, to=sharkctl.X6_MACRO_MAX_DELAY_MS, increment=10,
                    textvariable=self.v_step_delay, width=7).grid(row=0, column=1, padx=8)
        ttk.Label(edit, text="ms", style="CardMuted.TLabel").grid(row=0, column=2)
        ttk.Button(edit, text=_("Aplicar"), style="Ghost.TButton", command=self.macro_set_delay).grid(
            row=0, column=3, padx=(10, 0))

        self.macro_hint = ttk.Label(main, text=_("Clique em Gravar e aperte as teclas: o programa "
                                                 "guarda as teclas e o tempo entre elas."),
                                    style="CardMuted.TLabel")
        self.macro_hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        send = ttk.Frame(main, style="Card.TFrame")
        send.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        send.columnconfigure(0, weight=1)
        ttk.Label(send, text=_("As macros ficam gravadas no proprio mouse."),
                  style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(send, text=_("Enviar macros para o mouse"), style="Accent.TButton",
                   command=self.send_macros).grid(row=0, column=1)
        self._macro_load()

    def _macro_current(self) -> dict:
        return self.macros.get(self.v_macro_btn.get()) or {"enabled": False, "loops": 1, "events": []}

    def _macro_load(self) -> None:
        m = self._macro_current()
        self.v_macro_on.set(bool(m.get("enabled")) and bool(m.get("events")))
        self.v_macro_loops.set(str(m.get("loops", 1)))
        self._macro_render(m.get("events", []))

    def _macro_render(self, events: list) -> None:
        self.macro_tree.delete(*self.macro_tree.get_children())
        for i, ev in enumerate(events, 1):
            action = _("Apertar") if ev["action"] == "press" else _("Soltar")
            arrow = "\u2193" if ev["action"] == "press" else "\u2191"
            self.macro_tree.insert("", "end", iid=str(i - 1),
                                   values=(i, ev["key"], f"{arrow}  {action}", ev.get("delay", 10)))

    def _macro_store(self, events: list | None = None) -> None:
        m = dict(self._macro_current())
        if events is not None:
            m["events"] = events
        try:
            m["loops"] = max(1, min(255, int(self.v_macro_loops.get())))
        except ValueError:
            m["loops"] = 1
        m["enabled"] = bool(self.v_macro_on.get())
        self.macros[self.v_macro_btn.get()] = m
        self._set_dirty(True)

    def _macro_switch(self) -> None:
        if self.recording:
            self.toggle_record()
        self._macro_load()

    def _macro_selected(self, _event=None) -> None:
        sel = self.macro_tree.selection()
        if sel:
            ev = self._macro_current()["events"][int(sel[0])]
            self.v_step_delay.set(str(ev.get("delay", 10)))

    def macro_set_delay(self) -> None:
        sel = self.macro_tree.selection()
        if not sel:
            return
        try:
            delay = int(self.v_step_delay.get())
        except ValueError:
            return
        events = [dict(e) for e in self._macro_current()["events"]]
        events[int(sel[0])]["delay"] = max(10, min(sharkctl.X6_MACRO_MAX_DELAY_MS, delay // 10 * 10))
        self._macro_store(events)
        self._macro_render(events)
        self.macro_tree.selection_set(sel[0])

    def macro_remove_step(self) -> None:
        sel = self.macro_tree.selection()
        if not sel:
            return
        events = [dict(e) for e in self._macro_current()["events"]]
        del events[int(sel[0])]
        self._macro_store(events)
        self._macro_render(events)

    def macro_clear(self) -> None:
        if self.recording:
            self.toggle_record()
        self.v_macro_on.set(False)
        self._macro_store([])
        self._macro_render([])

    def toggle_record(self) -> None:
        if not self.recording:
            self.recording = True
            self._rec_events: list = []
            self._rec_down: set = set()
            self._rec_last = None
            self.rec_btn.config(text=_("■  Parar"))
            self.macro_hint.config(text=_("Gravando... aperte as teclas da macro e depois clique em Parar."),
                                   foreground=RED)
            self._macro_render([])
            self.macro_tree.focus_set()
            return
        self.recording = False
        self.rec_btn.config(text=_("●  Gravar"))
        self.macro_hint.config(text=_("{count} passo(s) gravado(s).", count=len(self._rec_events)),
                               foreground=MUTED)
        if self._rec_events:
            self._rec_events[-1]["delay"] = 10
            self.v_macro_on.set(True)
            self._macro_store(self._rec_events)
        else:
            self._macro_load()

    def _record_key(self, event) -> str | None:
        if not self.recording:
            return None
        name = tk_key_to_hid(event.keysym)
        if name is None:
            return "break"
        press = str(event.type) in ("KeyPress", "2")
        if press and name in self._rec_down:
            return "break"                      # auto-repeat while held
        if not press and name not in self._rec_down:
            return "break"
        now = time.monotonic()
        if self._rec_events and self._rec_last is not None:
            gap = int(round((now - self._rec_last) * 100)) * 10
            self._rec_events[-1]["delay"] = max(10, min(sharkctl.X6_MACRO_MAX_DELAY_MS, gap))
        self._rec_last = now
        (self._rec_down.add if press else self._rec_down.discard)(name)
        self._rec_events.append({"key": name, "action": "press" if press else "release", "delay": 10})
        self._macro_render(self._rec_events)
        self.macro_tree.see(str(len(self._rec_events) - 1))
        if len(self._rec_events) >= sharkctl.X6_MACRO_MAX_EVENTS:
            self.toggle_record()
            self.macro_hint.config(text=_("Limite de {n} passos atingido.", n=sharkctl.X6_MACRO_MAX_EVENTS),
                                   foreground=AMBER)
        return "break"

    def _collect_macros(self) -> dict | None:
        out = {}
        for key, label in MACRO_BUTTONS:
            m = self.macros.get(key)
            if not m:
                out[key] = None
                continue
            if m.get("enabled") and not m.get("events"):
                self.nb.select(self.tab_macros)
                messagebox.showerror(_title(), _("A macro do botao '{button}' nao tem passos.", button=_(label)))
                return None
            try:
                clean = sharkctl.validate_macro(m) if m.get("events") else {"loops": m.get("loops", 1), "events": []}
            except ValueError as exc:
                self.nb.select(self.tab_macros)
                messagebox.showerror(_title(), _("Configuracao invalida: {exc}", exc=exc))
                return None
            out[key] = dict(clean, enabled=bool(m.get("enabled")))
        return out

    def send_macros(self, macros: dict | None = None, quiet: bool = False) -> bool:
        macros = macros if macros is not None else self._collect_macros()
        if macros is None:
            return False
        try:
            sharkctl.x6_apply_macros(macros)
        except HidError as exc:
            if not quiet:
                messagebox.showerror(_title(), _("Nao consegui falar com o mouse:\n{exc}", exc=exc))
            return False
        self.macro_hint.config(text=_("\u2714  Macros enviadas para o mouse."), foreground=GREEN)
        return True

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
        ttk.Label(bar, text=_("Atividade do switcher"), style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.v_follow = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text=_("Acompanhar ao vivo"), variable=self.v_follow).grid(row=0, column=1, padx=8)
        ttk.Button(bar, text=_("Copiar"), style="Ghost.TButton", command=self.copy_log).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(bar, text=_("Abrir pasta"), style="Ghost.TButton", command=self.open_log_folder).grid(row=0, column=3)

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
        ttk.Label(top, text=_("Versao {version}  \u00b7  {system}", version=app_paths.APP_VERSION, system=system),
                  style="Value.TLabel").grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Label(top, text=_("Troca automatica de perfil para mouses Attack Shark V8 e X6. "
                              "Codigo aberto, licenca MIT."),
                  style="CardMuted.TLabel").grid(row=2, column=1, sticky="w", pady=(4, 0))

        up = card(tab, row=1, column=0, sticky="ew", padx=8, pady=4)
        up.columnconfigure(0, weight=1)
        ttk.Label(up, text=_("Atualizacoes"), style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.update_status = ttk.Label(up, text=_("Clique em Verificar para procurar uma versao nova."),
                                       style="Card.TLabel")
        self.update_status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        style = ttk.Style(self.root)
        style.configure("Upd.Horizontal.TProgressbar", troughcolor=INPUT, background=ACCENT,
                        bordercolor=INPUT, lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
        self.update_bar = ttk.Progressbar(up, style="Upd.Horizontal.TProgressbar", maximum=100)
        btns = ttk.Frame(up, style="Card.TFrame")
        btns.grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.check_btn = ttk.Button(btns, text=_("Verificar agora"), style="Accent.TButton",
                                    command=self.check_update)
        self.check_btn.grid(row=0, column=0)
        self.install_btn = ttk.Button(btns, text=_("Atualizar agora"), style="Accent.TButton",
                                      command=self.install_update)
        self.v_check_updates = tk.BooleanVar(value=bool(self.full.get("check_updates", True)))
        self.v_check_updates.trace_add("write", lambda *_: self._set_dirty(True))
        ttk.Checkbutton(up, text=_("Verificar atualizacoes automaticamente (uma vez por dia)"),
                        variable=self.v_check_updates).grid(row=4, column=0, columnspan=3,
                                                            sticky="w", pady=(12, 0))

        links = card(tab, row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        ttk.Label(links, text=_("Links"), style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        import webbrowser
        repo = f"https://github.com/{app_paths.GITHUB_REPO}"
        for k, (text, url) in enumerate((("Pagina do projeto", repo),
                                         ("Versoes publicadas", repo + "/releases"),
                                         ("Relatar um problema", repo + "/issues/new/choose"))):
            ttk.Button(links, text=_(text), style="Ghost.TButton",
                       command=lambda u=url: webbrowser.open(u)).grid(
                row=1, column=k, padx=(0, 8), pady=(10, 0), sticky="w")

        lang = card(tab, row=3, column=0, sticky="ew", padx=8, pady=(4, 8))
        ttk.Label(lang, text=_("Idioma") + "  /  Language", style="Section.TLabel").grid(
            row=0, column=0, sticky="w")
        self._lang_codes = ["auto"] + list(i18n.LANGUAGES)
        self._lang_names = [_("Automatico (idioma do sistema)")] + list(i18n.LANGUAGES.values())
        current = self.full.get("language", "auto")
        index = self._lang_codes.index(current) if current in self._lang_codes else 0
        self._lang_start = self._lang_codes[index]
        self.v_lang = tk.StringVar(value=self._lang_names[index])
        ttk.Combobox(lang, textvariable=self.v_lang, values=self._lang_names, state="readonly",
                     width=32).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.v_lang.trace_add("write", lambda *_a: self._set_dirty(True))
        self._release = None

    def check_update(self) -> None:
        import updater
        self.check_btn.config(state="disabled", text=_("Verificando..."))
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
        self.check_btn.config(state="normal", text=_("Verificar agora"))
        if kind == "error":
            self.update_status.config(text=value, foreground=AMBER)
            return
        rel = value
        if not updater.is_newer(rel.version):
            self.update_status.config(
                text=_("\u2714  Voce esta na versao mais recente ({version}).",
                       version=app_paths.APP_VERSION),
                foreground=GREEN)
            return
        self._release = rel
        self.update_status.config(text=_("\u2b06  Versao {new} disponivel (voce tem a {version}).",
                                         new=rel.version, version=app_paths.APP_VERSION),
                                  foreground=ACCENT_HI)
        self.install_btn.config(text=_("Atualizar agora") if updater.can_self_update(rel)
                                else _("Abrir pagina da versao"))
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
                _title(), _("Voce tem alteracoes nao salvas, que serao perdidas. Atualizar mesmo assim?")):
            return
        self.install_btn.config(state="disabled")
        self.check_btn.config(state="disabled")
        self.update_bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        def progress(done, total):
            pct = int(100 * done / total) if total else 0
            self._ui.put(lambda: (self.update_bar.configure(value=pct),
                                  self.update_status.config(text=_("Baixando... {pct}%", pct=pct),
                                                            foreground=FG)))

        def worker():
            try:
                path = updater.download_installer(rel, progress)
            except updater.UpdateError as exc:
                msg = str(exc)
                self._ui.put(lambda: self._update_failed(msg))
                return
            self._ui.put(lambda: self.update_status.config(
                text=_("Instalando... o Attack Shark vai fechar e abrir de novo sozinho."),
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
            self.pill.config(text=_("●  Mouse conectado"), bg="#143326", fg=GREEN)
        else:
            self.pill.config(text=_("●  Mouse nao encontrado"), bg="#3a1f26", fg=RED)

    # --------------------------------------------------------- profile list

    def _labels(self) -> list[str]:
        return [f"{i + 1}.  {p.get('name') or _('(sem nome)')}" for i, p in enumerate(self.profiles)]

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
        led = self._led_of(p)
        self.v_led_mode.set(_(LED_MODE_NAMES[sharkctl.X6_LED_MODES.index(led["mode"])]))
        self.v_led_color.set(led["color"])
        self.v_led_bright.set(int(led["brightness"]))
        self.v_led_speed.set(int(led["speed"]))
        self._sync_widgets()
        self.loading = False

    @staticmethod
    def _led_of(profile: dict) -> dict:
        try:
            return sharkctl.led_settings(profile.get("led"))
        except (ValueError, TypeError):
            return dict(sharkctl.X6_LED_DEFAULT)

    def _led_mode_key(self) -> str:
        names = [_(n) for n in LED_MODE_NAMES]
        name = self.v_led_mode.get()
        return sharkctl.X6_LED_MODES[names.index(name)] if name in names else "breathing_dpi"

    def pick_led_color(self) -> None:
        chosen = colorchooser.askcolor(color=self.v_led_color.get() or "#00ff00",
                                       title=_("Escolher cor"), parent=self.root)
        if chosen and chosen[1]:
            self.v_led_color.set(chosen[1].lower())

    def _sync_widgets(self) -> None:
        try:
            self.dpi_scale.set(min(int(self.v_dpi.get()), 6400))
        except ValueError:
            pass
        self.sleep_scale.set(self.v_sleep.get())
        self.sleep_label.config(text=f"{self.v_sleep.get()} min")
        mode = self._led_mode_key()
        color = self.v_led_color.get() or "#00ff00"
        uses_color = mode in sharkctl.X6_LED_USES_COLOR
        uses_speed = mode in sharkctl.X6_LED_USES_SPEED
        self.led_swatch.config(bg=color if uses_color else CARD2, activebackground=color,
                               state="normal" if uses_color else "disabled")
        self.led_color_btn.config(state="normal" if uses_color else "disabled")
        self.bright_scale.set(self.v_led_bright.get())
        self.bright_label.config(text=f"{self.v_led_bright.get()}/8")
        self.bright_scale.state(["!disabled"] if mode != "off" else ["disabled"])
        self.speed_scale.set(self.v_led_speed.get())
        self.speed_label.config(text=f"{self.v_led_speed.get()}/5")
        self.speed_scale.state(["!disabled"] if uses_speed else ["disabled"])

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

    def _on_field(self, *_args):
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
        p["led"] = {"mode": self._led_mode_key(), "color": self.v_led_color.get() or "#00ff00",
                    "brightness": self.v_led_bright.get(), "speed": self.v_led_speed.get()}
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
            self.status.config(text=_("●  Alteracoes nao salvas   (Ctrl+S para salvar)"), foreground=AMBER)

    def add(self) -> None:
        self._insert(dict(NOVO_PERFIL, name=_("Novo perfil")))

    def duplicate(self) -> None:
        p = dict(self.profiles[self.cur])
        p["name"] = (p.get("name") or _("Perfil")) + _(" (copia)")
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
            messagebox.showinfo(_title(), _("Precisa ter pelo menos um perfil."))
            return
        name = self.profiles[self.cur].get("name") or _("este perfil")
        if not messagebox.askyesno(_title(), _("Remover {name}?", name=name)):
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
            self.games_list.insert("end", "  " + _("Nenhum jogo ainda - adicione abaixo ou use Detectar"))
            self.games_list.itemconfig(0, fg=MUTED)

    def add_game(self) -> None:
        name = os.path.basename(self.v_new_game.get().strip().strip('"'))
        if not name:
            return
        if not name.lower().endswith(".exe"):
            name += ".exe"
        if name.lower() in {g.lower() for g in self.games}:
            self.status.config(text=_("{name} ja esta na lista", name=name), foreground=MUTED)
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
        self.detect_btn.config(text=_("Procurando..."), state="disabled")

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
        self.detect_btn.config(text=_("Detectar jogos instalados (Steam e Epic)"), state="normal")
        if error:
            messagebox.showerror(_title(), _("Falha ao procurar jogos:\n{error}", error=error))
            return
        have = {g.lower() for g in self.games}
        new = [exe for exe in found if exe.lower() not in have]
        if new:
            self.games = sorted(self.games + new, key=str.lower)
            self._refresh_games()
            self._set_dirty(True)
            messagebox.showinfo(_title(), _(
                "{count} jogo(s) adicionado(s):\n\n{list}\n\nConfira a lista: a deteccao pode errar o .exe.",
                count=len(new), list="\n".join(f"{found[e]}  ({e})" for e in sorted(new))))
        else:
            messagebox.showinfo(_title(), _("Nenhum jogo novo ({count} encontrado(s)).", count=len(found)))

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
        self.log.insert("end", _("Nenhum log ainda. Ele aparece aqui assim que o switcher "
                                 "estiver rodando (icone na bandeja)."), "empty")
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
        self.status.config(text=_("Log copiado"), foreground=MUTED)

    def open_log_folder(self) -> None:
        folder = os.path.dirname(LOG_PATH)
        if os.path.isdir(folder):
            app_paths.open_path(folder)
        else:
            messagebox.showinfo(_title(), _("A pasta de logs ainda nao existe."))

    # ------------------------------------------------------- validation

    def _collect(self) -> dict | None:
        def bad(msg: str, perfil: int | None = None) -> None:
            self.nb.select(self.tab_profiles)
            if perfil is not None:
                self.cur = perfil
                self._refresh_list()
                self._load(perfil)
            messagebox.showerror(_title(), msg)

        try:
            stages = [int(v.get()) for v in self.v_stages]
        except ValueError:
            bad(_("Os estagios de DPI precisam ser numeros."))
            return None
        for d in stages:
            if not (50 <= d <= 12800 and d % 50 == 0):
                bad(_("Estagio de DPI invalido: {d}\nUse multiplos de 50, de 50 a 12800.", d=d))
                return None

        profiles = []
        for i, p in enumerate(self.profiles):
            nome = (p.get("name") or "").strip()
            if not nome:
                bad(_("O perfil {n} precisa de um nome.", n=i + 1), i)
                return None
            try:
                dpi = int(p["dpi"])
            except (ValueError, TypeError):
                bad(_("'{name}': o DPI precisa ser um numero.", name=nome), i)
                return None
            if not (50 <= dpi <= 12800 and dpi % 50 == 0):
                bad(_("'{name}': DPI invalido ({dpi}).\nUse multiplos de 50, de 50 a 12800.", name=nome, dpi=dpi), i)
                return None
            profiles.append({
                "name": nome, "dpi": dpi, "polling": int(p["polling"]),
                "key_response_ms": int(p["key_response_ms"]),
                "deep_sleep_min": int(p["deep_sleep_min"]),
                "ripple": bool(p["ripple"]), "angle_snap": bool(p["angle_snap"]),
                "led": self._led_of(p),
            })

        x6 = {"dpi_stages": stages, "profiles": profiles}
        try:
            sharkctl.validate_x6(x6)
        except (ValueError, KeyError, TypeError) as exc:
            bad(_("Configuracao invalida: {exc}", exc=exc))
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
            messagebox.showerror(_title(), _("Nao consegui falar com o mouse:\n{exc}", exc=exc))
            return
        self.status.config(text=_("▶  '{name}' aplicado no mouse (teste, ainda nao salvo)",
                                  name=x6['profiles'][self.cur]['name']), foreground=ACCENT_HI)

    def save(self) -> bool:
        x6 = self._collect()
        if x6 is None:
            return False
        if self.recording:
            self.toggle_record()
        macros = self._collect_macros()
        if macros is None:
            return False
        full = self._read_config() if os.path.exists(self.config_path) else {}
        full["x6"] = x6
        full["default_profile"] = self._default_idx + 1
        full["game_profile"] = self._game_idx + 1
        full["games"] = list(self.games)
        full["check_updates"] = bool(self.v_check_updates.get())
        full["macros"] = macros
        language = self._lang_codes[self._lang_names.index(self.v_lang.get())]
        full["language"] = language
        tmp = self.config_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(full, handle, indent=2, ensure_ascii=False)
            os.replace(tmp, self.config_path)
        except OSError as exc:
            messagebox.showerror(_title(), _("Nao consegui salvar o config.json:\n{exc}", exc=exc))
            return False
        self.dirty = False
        self.status.config(text=_("✔  Salvo. O switcher aplica em ate 2 segundos."), foreground=GREEN)
        snapshot = json.dumps(macros, sort_keys=True)
        if snapshot != self._macros_loaded and sharkctl.find_x6() is not None:
            if self.send_macros(macros, quiet=True):
                self._macros_loaded = snapshot
            else:
                self.status.config(text=_("Salvo, mas as macros nao chegaram ao mouse. Use "
                                          "'Enviar macros para o mouse' com ele conectado."),
                                   foreground=AMBER)
        if language != self._lang_start:
            self._lang_start = language
            i18n.set_language(language)
            if messagebox.askyesno(_title(), _("O idioma muda quando a janela abrir de novo. Reabrir agora?")):
                app_paths.spawn(app_paths.self_command("--settings", "--config", self.config_path))
                self.root.destroy()
        return True

    def close(self) -> None:
        if self.dirty:
            answer = messagebox.askyesnocancel(_title(), _("Salvar as alteracoes antes de fechar?"))
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
    try:
        with open(config_path, encoding="utf-8-sig") as handle:
            i18n.set_language(json.load(handle).get("language", "auto"))
    except (OSError, ValueError):
        i18n.set_language("auto")
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
