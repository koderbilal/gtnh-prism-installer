"""Dark theme for Tk/ttk (clam based)."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#171923"
PANEL = "#1f2230"
RAISED = "#2a2e40"
FIELD = "#262a3a"
BORDER = "#363b52"
FG = "#e8eaf2"
MUTED = "#9097b0"
DISABLED = "#5b6178"
ACCENT = "#5b8cff"
ACCENT_HOVER = "#7aa2ff"
ACCENT_DOWN = "#4a77e0"


def _pick_font_family(root: tk.Misc) -> str:
    families = set(tkfont.families(root))
    for name in ("Segoe UI", "Inter", "Noto Sans", "Cantarell", "Ubuntu", "DejaVu Sans"):
        if name in families:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


def dark_titlebar(window: tk.Misc) -> None:
    """Best effort: dark native title bar on Windows 10/11."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old id)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:  # noqa: BLE001 - cosmetic only
        pass


def apply_dark(root: tk.Tk) -> None:
    family = _pick_font_family(root)
    for name, size in (("TkDefaultFont", 10), ("TkTextFont", 10), ("TkMenuFont", 10), ("TkHeadingFont", 10)):
        tkfont.nametofont(name).configure(family=family, size=size)
    tkfont.nametofont("TkFixedFont").configure(size=10)

    root.configure(bg=BG)
    for pattern, value in (
        ("*Background", BG),
        ("*Foreground", FG),
        ("*activeBackground", RAISED),
        ("*activeForeground", FG),
        ("*selectBackground", ACCENT),
        ("*selectForeground", "#ffffff"),
        ("*highlightBackground", BG),
        ("*disabledForeground", DISABLED),
        ("*Listbox.background", FIELD),
        ("*Listbox.foreground", FG),
        ("*Listbox.relief", "flat"),
        ("*Listbox.highlightThickness", 1),
        ("*Listbox.highlightColor", ACCENT),
        ("*Listbox.highlightBackground", BORDER),
        ("*Entry.background", FIELD),
        ("*Entry.foreground", FG),
        ("*Text.background", FIELD),
        ("*Text.foreground", FG),
        ("*TCombobox*Listbox.background", FIELD),
        ("*TCombobox*Listbox.foreground", FG),
        ("*TCombobox*Listbox.selectBackground", ACCENT),
        ("*TCombobox*Listbox.selectForeground", "#ffffff"),
        ("*Menu.background", PANEL),
        ("*Menu.foreground", FG),
    ):
        root.option_add(pattern, value)

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(
        ".",
        background=BG,
        foreground=FG,
        fieldbackground=FIELD,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        troughcolor=FIELD,
        insertcolor=FG,
        selectbackground=ACCENT,
        selectforeground="#ffffff",
        focuscolor=BG,
        font=(family, 10),
    )
    s.map(".", foreground=[("disabled", DISABLED)])

    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=PANEL)
    s.configure("TLabel", background=BG, foreground=FG)
    s.configure("Card.TLabel", background=PANEL, foreground=FG)
    s.configure("Title.TLabel", background=PANEL, foreground=FG, font=(family, 17, "bold"))
    s.configure("Sub.TLabel", background=PANEL, foreground=MUTED)
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Badge.TLabel", background=ACCENT, foreground="#ffffff", font=(family, 9, "bold"), padding=(8, 2))

    s.configure("TLabelframe", background=BG, bordercolor=BORDER, relief="solid", borderwidth=1)
    s.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=(family, 10, "bold"))

    s.configure("TButton", background=RAISED, foreground=FG, bordercolor=BORDER, padding=(12, 6), relief="flat")
    s.map(
        "TButton",
        background=[("disabled", PANEL), ("pressed", BORDER), ("active", "#353a52")],
        bordercolor=[("focus", ACCENT)],
    )
    s.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground="#ffffff",
        bordercolor=ACCENT,
        padding=(22, 8),
        font=(family, 10, "bold"),
    )
    s.map(
        "Accent.TButton",
        background=[("disabled", RAISED), ("pressed", ACCENT_DOWN), ("active", ACCENT_HOVER)],
        foreground=[("disabled", DISABLED)],
        bordercolor=[("disabled", BORDER)],
    )

    for name in ("TCheckbutton", "TRadiobutton"):
        s.configure(name, background=BG, foreground=FG, indicatorbackground=FIELD, indicatorforeground="#ffffff")
        s.map(
            name,
            background=[("active", BG)],
            foreground=[("disabled", DISABLED)],
            indicatorbackground=[("disabled", PANEL), ("selected", ACCENT), ("pressed", RAISED)],
            indicatorforeground=[("disabled", DISABLED)],
        )

    s.configure("TEntry", fieldbackground=FIELD, foreground=FG, bordercolor=BORDER, padding=5)
    s.map(
        "TEntry",
        fieldbackground=[("disabled", PANEL)],
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
    )
    s.configure("TCombobox", fieldbackground=FIELD, background=RAISED, foreground=FG, arrowcolor=FG, padding=5)
    s.map(
        "TCombobox",
        fieldbackground=[("disabled", PANEL), ("readonly", FIELD)],
        foreground=[("disabled", DISABLED)],
        background=[("active", "#353a52")],
        arrowcolor=[("disabled", DISABLED)],
        bordercolor=[("focus", ACCENT)],
        selectbackground=[("readonly", FIELD)],
        selectforeground=[("readonly", FG)],
    )

    s.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=FG, rowheight=26, borderwidth=0)
    s.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
    s.configure("Treeview.Heading", background=RAISED, foreground=FG, relief="flat", padding=(8, 6), font=(family, 10, "bold"))
    s.map("Treeview.Heading", background=[("active", "#353a52")])

    s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(22, 9), borderwidth=0, focuscolor=RAISED, lightcolor=PANEL, darkcolor=PANEL, bordercolor=BORDER)
    s.map(
        "TNotebook.Tab",
        background=[("selected", RAISED), ("active", "#2f3348")],
        foreground=[("selected", FG), ("active", FG)],
        lightcolor=[("selected", RAISED)],
        darkcolor=[("selected", RAISED)],
        focuscolor=[("selected", RAISED)],
    )

    s.configure("TScrollbar", background=RAISED, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED, relief="flat")
    s.map("TScrollbar", background=[("active", "#3b4160")])

    s.configure(
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor=FIELD,
        bordercolor=BG,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        thickness=10,
    )
    s.configure("TSeparator", background=BORDER)

    dark_titlebar(root)


def center_on(window: tk.Toplevel, parent: tk.Misc, width: int, height: int) -> None:
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 3)
    window.geometry(f"{width}x{height}+{x}+{y}")


def style_text(widget: tk.Text) -> None:
    widget.configure(
        bg=FIELD,
        fg=FG,
        insertbackground=FG,
        selectbackground=ACCENT,
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=BORDER,
        padx=8,
        pady=6,
    )
