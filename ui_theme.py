"""Shared look for the settings window and the installer: dark, flat, blue accent."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import ttk

# -- palette ----------------------------------------------------------------
BG = "#101218"        # window
CARD = "#181b23"      # panels
CARD2 = "#20242f"     # buttons, hover
INPUT = "#262b38"     # fields
LINE = "#2e3442"      # borders
FG = "#e8eaf0"
MUTED = "#8b93a7"
ACCENT = "#2f8cff"
ACCENT_HI = "#5aa5ff"
GREEN = "#3ecf8e"
AMBER = "#f5b942"
RED = "#ff5c6c"
IS_WINDOWS = sys.platform == "win32"
FONT = "Segoe UI" if IS_WINDOWS else "Noto Sans"     # Tk falls back if missing
MONO = "Consolas" if IS_WINDOWS else "DejaVu Sans Mono"


def dark_title_bar(root: tk.Tk) -> None:
    """Ask Windows 10/11 for a dark title bar so it matches the window."""
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):           # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def setup_style(root: tk.Tk) -> None:
    root.configure(bg=BG)
    s = ttk.Style(root)
    s.theme_use("clam")
    base = (FONT, 10)
    s.configure(".", background=BG, foreground=FG, font=base, bordercolor=LINE,
                lightcolor=LINE, darkcolor=LINE, troughcolor=INPUT, focuscolor=ACCENT,
                selectbackground=ACCENT, selectforeground="#ffffff", insertcolor=FG)

    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=CARD)
    s.configure("TLabel", background=BG, foreground=FG)
    s.configure("Card.TLabel", background=CARD, foreground=FG)
    s.configure("Muted.TLabel", background=BG, foreground=MUTED)
    s.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
    s.configure("H1.TLabel", background=BG, foreground=FG, font=(FONT, 17, "bold"))
    s.configure("Section.TLabel", background=CARD, foreground=FG, font=(FONT, 11, "bold"))
    s.configure("Value.TLabel", background=CARD, foreground=ACCENT_HI, font=(FONT, 10, "bold"))

    s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0),
                bordercolor=CARD, lightcolor=CARD, darkcolor=CARD)
    # clam enlarges the selected tab ("expand") and draws outlines around the
    # others; both are neutralised so every tab has the same height and look.
    s.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(20, 9),
                borderwidth=0, font=(FONT, 10, "bold"), bordercolor=BG,
                lightcolor=BG, darkcolor=BG, focuscolor=BG)
    s.map("TNotebook.Tab",
          expand=[("selected", (0, 0, 0, 0))],
          padding=[("selected", (20, 9))],
          background=[("selected", CARD), ("active", CARD2)],
          foreground=[("selected", FG), ("active", FG)],
          bordercolor=[("selected", CARD)], lightcolor=[("selected", CARD)],
          darkcolor=[("selected", CARD)])

    s.configure("TButton", background=CARD2, foreground=FG, borderwidth=0,
                padding=(14, 7), relief="flat")
    s.map("TButton", background=[("pressed", INPUT), ("active", INPUT)])
    s.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                font=(FONT, 10, "bold"))
    s.map("Accent.TButton", background=[("pressed", "#1f6fd1"), ("active", ACCENT_HI)])
    s.configure("Ghost.TButton", background=CARD, foreground=FG, padding=(10, 6))
    s.map("Ghost.TButton", background=[("active", CARD2)])
    s.configure("Danger.TButton", background=CARD, foreground=RED, padding=(10, 6))
    s.map("Danger.TButton", background=[("active", "#3a1f26")])

    for widget in ("TEntry", "TSpinbox", "TCombobox"):
        s.configure(widget, fieldbackground=INPUT, foreground=FG, background=INPUT,
                    bordercolor=LINE, lightcolor=INPUT, darkcolor=INPUT,
                    arrowcolor=MUTED, padding=5, insertcolor=FG)
        s.map(widget, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", INPUT)], foreground=[("readonly", FG)],
              selectbackground=[("readonly", INPUT)], selectforeground=[("readonly", FG)])
    root.option_add("*TCombobox*Listbox.background", INPUT)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.font", base)

    s.configure("TCheckbutton", background=CARD, foreground=FG, indicatorbackground=INPUT,
                indicatorforeground="#ffffff", indicatorrelief="flat", padding=4)
    s.map("TCheckbutton", background=[("active", CARD)],
          indicatorbackground=[("selected", ACCENT), ("active", CARD2)])

    s.configure("Horizontal.TScale", background=ACCENT, troughcolor=INPUT,
                bordercolor=CARD, lightcolor=ACCENT, darkcolor=ACCENT, sliderthickness=16)
    s.map("Horizontal.TScale", background=[("active", ACCENT_HI)])

    s.configure("Seg.Toolbutton", background=INPUT, foreground=MUTED, padding=(12, 6),
                borderwidth=0, font=(FONT, 9, "bold"), anchor="center")
    s.map("Seg.Toolbutton",
          background=[("selected", ACCENT), ("active", CARD2)],
          foreground=[("selected", "#ffffff"), ("active", FG)])

    s.configure("Vertical.TScrollbar", background=CARD2, troughcolor=CARD, bordercolor=CARD,
                arrowcolor=MUTED, lightcolor=CARD2, darkcolor=CARD2)


def set_window_icon(root: tk.Misc, ico_path: str, png_path: str) -> None:
    """Window icon: .ico on Windows, PNG elsewhere (Tk on Linux cannot read .ico)."""
    try:
        if IS_WINDOWS:
            root.iconbitmap(ico_path)
        else:
            img = tk.PhotoImage(file=png_path)
            root.iconphoto(True, img)
            root._icon_ref = img        # keep a reference or Tk drops the image
    except tk.TclError:
        pass


def card(parent, **grid) -> ttk.Frame:
    frame = ttk.Frame(parent, style="Card.TFrame", padding=16)
    frame.grid(**grid)
    return frame


def styled_listbox(parent, **kw) -> tk.Listbox:
    return tk.Listbox(parent, bg=INPUT, fg=FG, selectbackground=ACCENT, selectforeground="#ffffff",
                      highlightthickness=0, borderwidth=0, activestyle="none",
                      font=(FONT, 11), exportselection=False, **kw)
