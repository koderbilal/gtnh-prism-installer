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


TAB_ACTIVE = "#313857"


class ScrollPage(ttk.Frame):
    """Vertically scrollable page; the scrollbar only appears when the content does not fit."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self._sync())
        self.canvas.bind("<Configure>", lambda e: self._sync())
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(seq, self._wheel, add="+")

    def _sync(self) -> None:
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.itemconfigure(self._win, width=width)
        need = self.body.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, width, max(need, height)))
        if need > height + 1:
            if not self.bar.winfo_ismapped():
                self.bar.pack(side="right", fill="y")
        else:
            self.bar.pack_forget()
            self.canvas.yview_moveto(0)

    def _wheel(self, event: tk.Event) -> None:
        if not self.winfo_ismapped() or not self.bar.winfo_ismapped():
            return
        if event.widget.winfo_toplevel() is not self.winfo_toplevel():
            return
        if event.widget.winfo_class() in ("Treeview", "Listbox", "Text"):
            return
        if event.num == 4:
            step = -1
        elif event.num == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step * 3, "units")


class TabView(ttk.Frame):
    """Tab strip with equal-size tabs, a lighter selected tab and a blue line on top of it."""

    def __init__(self, parent: tk.Misc, on_change=None):
        super().__init__(parent)
        self._on_change = on_change
        self._tabs: list[tuple[tk.Frame, tk.Frame, tk.Label, ScrollPage]] = []
        self._current = -1
        self.strip = ttk.Frame(self)
        self.strip.pack(fill="x")
        self.content = tk.Frame(self, bg=BG, highlightthickness=1, highlightbackground=BORDER, bd=0)
        self.content.pack(fill="both", expand=True)

    def add(self, text: str) -> ScrollPage:
        i = len(self._tabs)
        cell = tk.Frame(self.strip, bg=PANEL, cursor="hand2")
        cell.grid(row=0, column=i, sticky="ew", padx=(0, 3))
        self.strip.columnconfigure(i, uniform="tabs", minsize=150)
        line = tk.Frame(cell, bg=PANEL, height=3)
        line.pack(fill="x")
        label = tk.Label(cell, text=text, bg=PANEL, fg=MUTED, padx=24, pady=9, font=("TkDefaultFont", 10, "bold"), cursor="hand2")
        label.pack(fill="x")
        page = ScrollPage(self.content)
        self._tabs.append((cell, line, label, page))
        for w in (cell, line, label):
            w.bind("<Button-1>", lambda e, n=i: self.select(n))
        if i == 0:
            self.select(0)
        return page

    def select(self, index: int) -> None:
        if index == self._current:
            return
        for n, (cell, line, label, page) in enumerate(self._tabs):
            active = n == index
            bg = TAB_ACTIVE if active else PANEL
            cell.config(bg=bg)
            label.config(bg=bg, fg=FG if active else MUTED)
            line.config(bg=ACCENT if active else bg)
            if active:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        self._current = index
        if self._on_change:
            self._on_change(index)

    def index(self) -> int:
        return max(self._current, 0)
