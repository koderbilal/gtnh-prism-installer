"""Tkinter GUI: Install / Update tabs plus a Prism-style Java chooser."""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Callable, Optional

from . import __version__, javas
from .i18n import detect_language, set_language, t
from .install import JavaChoice, default_instance_name, default_java_major, detect_variant, install_instance
from .prism import InstanceInfo, PrismPaths, detect_prism, list_instances, load_paths, minecraft_dir, read_instance
from .theme import FG, apply_dark, center_on, dark_titlebar, style_text
from .update import OPTIONAL_ITEMS, MigrationOptions, detect_user_mods, present_items, update_instance
from .util import Cancelled, Reporter, platform_info
from .versions import GtnhVersion, fetch_versions, upgrade_skips_major


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        apply_dark(self)
        self.title(f"{t('app_title')} v{__version__}")
        height = min(990, self.winfo_screenheight() - 90)
        self.geometry(f"940x{height}")
        self.minsize(840, 700)

        self.versions: list[GtnhVersion] = []
        self.prism: Optional[PrismPaths] = None
        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._busy = False
        self._reporter: Optional[Reporter] = None
        self._callbacks: dict[int, Callable] = {}
        self._cb_id = 0

        self._build_banner()
        self._build_header()
        self._build_footer()  # packed at the bottom first so the log never gets pushed off-screen
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=6)
        self.install_tab = InstallTab(self.notebook, self)
        self.update_tab = UpdateTab(self.notebook, self)
        self.notebook.add(self.install_tab, text=t("tab_install"))
        self.notebook.add(self.update_tab, text=t("tab_update"))

        self.after(100, self._pump)
        self._detect_prism()
        self.reload_versions()

    def current_majors(self) -> tuple[list[int], list[int]]:
        tab = self.update_tab if self.notebook.index(self.notebook.select()) == 1 else self.install_tab
        return tab.majors()

    # ------------------------------------------------------------------ layout
    def _build_banner(self) -> None:
        bar = ttk.Frame(self, style="Card.TFrame")
        bar.pack(fill="x")
        inner = ttk.Frame(bar, style="Card.TFrame")
        inner.pack(fill="x", padx=18, pady=14)
        titles = ttk.Frame(inner, style="Card.TFrame")
        titles.pack(side="left")
        ttk.Label(titles, text=t("app_name"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text=t("app_subtitle"), style="Sub.TLabel").pack(anchor="w")
        ttk.Label(inner, text=f"v{__version__}", style="Badge.TLabel").pack(side="right")

    def _build_header(self) -> None:
        f = ttk.Frame(self)
        f.pack(fill="x", padx=14, pady=(12, 0))
        ttk.Label(f, text=t("prism_folder")).grid(row=0, column=0, sticky="w")
        self.prism_var = tk.StringVar()
        self.prism_combo = ttk.Combobox(f, textvariable=self.prism_var)
        self.prism_combo.grid(row=0, column=1, sticky="ew", padx=6)
        self.prism_combo.bind("<<ComboboxSelected>>", lambda e: self._prism_changed())
        self.prism_combo.bind("<Return>", lambda e: self._prism_changed())
        ttk.Button(f, text=t("browse"), command=self._browse_prism).grid(row=0, column=2)
        self.instances_label = ttk.Label(f, text="")
        self.instances_label.grid(row=1, column=1, sticky="w", padx=6)
        f.columnconfigure(1, weight=1)

    def _build_footer(self) -> None:
        f = ttk.Frame(self)
        f.pack(side="bottom", fill="x", padx=14, pady=(0, 12))
        self.progress_label = ttk.Label(f, text="")
        self.progress_label.pack(fill="x")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=2)
        self.progress = ttk.Progressbar(row, mode="determinate", maximum=1000)
        self.progress.pack(side="left", fill="x", expand=True)
        self.cancel_btn = ttk.Button(row, text=t("cancel"), command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(6, 0))
        self.log_text = tk.Text(f, height=6, state="disabled", wrap="word")
        style_text(self.log_text)
        self.log_text.pack(fill="x", pady=(6, 0))

    # ------------------------------------------------------------------ Prism folder
    def _detect_prism(self) -> None:
        found = detect_prism()
        self._detected = {str(p.data_dir): p for p in found}
        self.prism_combo["values"] = list(self._detected)
        if found:
            self.prism_var.set(str(found[0].data_dir))
            self._prism_changed()
        else:
            self.instances_label.config(text=t("prism_not_found"))

    def _browse_prism(self) -> None:
        d = filedialog.askdirectory(title=t("prism_folder"))
        if d:
            self.prism_var.set(d)
            self._prism_changed()

    def _prism_changed(self) -> None:
        p = Path(self.prism_var.get()).expanduser()
        if not p.is_dir():
            self.prism = None
            self.instances_label.config(text=t("prism_not_found"))
        else:
            self.prism = load_paths(p)
            self.instances_label.config(text=t("instances_folder", path=self.prism.instances_dir))
        self.update_tab.reload_instances()

    # ------------------------------------------------------------------ background tasks
    def run_bg(self, work: Callable[[], object], done: Callable[[object, Optional[BaseException]], None]) -> None:
        """Run `work` in a thread; `done(result, error)` is invoked on the Tk thread."""
        self._cb_id += 1
        cid = self._cb_id
        self._callbacks[cid] = done

        def runner() -> None:
            try:
                self._events.put(("result", cid, work(), None))
            except BaseException as e:  # noqa: BLE001 - surfaced to the UI
                self._events.put(("result", cid, None, e))

        threading.Thread(target=runner, daemon=True).start()

    def start_task(self, work: Callable[[Reporter], object], done: Callable[[object], None]) -> None:
        if self._busy:
            return
        self._busy = True
        self.set_buttons_enabled(False)
        self.cancel_btn.config(state="normal")
        self._clear_log()
        reporter = Reporter(
            log=lambda m: self._events.put(("log", m)),
            progress=lambda label, frac: self._events.put(("progress", label, frac)),
        )
        self._reporter = reporter

        def finished(result: object, error: Optional[BaseException]) -> None:
            self._busy = False
            self.cancel_btn.config(state="disabled")
            self.set_buttons_enabled(True)
            self.progress.config(value=0)
            self.progress_label.config(text="")
            if isinstance(error, Cancelled):
                self.log(t("cancelled"))
            elif error is not None:
                self.log(f"{t('error')}: {error}")
                messagebox.showerror(t("error"), str(error), parent=self)
            else:
                done(result)

        self.run_bg(lambda: work(reporter), finished)

    def _cancel(self) -> None:
        if self._reporter:
            self._reporter.cancel_event.set()

    def set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.install_tab.action_btn.config(state=state)
        self.update_tab.action_btn.config(state=state)

    def _pump(self) -> None:
        try:
            while True:
                ev = self._events.get_nowait()
                if ev[0] == "log":
                    self.log(ev[1])
                elif ev[0] == "progress":
                    _, label, frac = ev
                    self.progress_label.config(text=label)
                    if frac is None:
                        self.progress.config(mode="indeterminate")
                        self.progress.step(10)
                    else:
                        self.progress.config(mode="determinate", value=int(frac * 1000))
                elif ev[0] == "result":
                    _, cid, result, error = ev
                    cb = self._callbacks.pop(cid, None)
                    if cb:
                        cb(result, error)
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def log(self, msg: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    # ------------------------------------------------------------------ versions
    def reload_versions(self) -> None:
        self.progress_label.config(text=t("loading_versions"))

        def done(result, error):
            self.progress_label.config(text="")
            if error:
                self.log(f"{t('error')}: {error}")
                messagebox.showerror(t("error"), str(error), parent=self)
                return
            self.versions = result  # type: ignore[assignment]
            self.install_tab.fill_versions()
            self.update_tab.fill_versions()

        self.run_bg(fetch_versions, done)


# ============================================================================== Java panel

class JavaPanel(ttk.LabelFrame):
    """Java choice. Default: Java 25 (or the newest the pack supports), fetched automatically.
    Ticking the checkbox lets the user detect, browse for or download a Java of their own."""

    def __init__(self, parent: tk.Misc, app: App, majors_provider: Callable[[], tuple[list[int], list[int]]]):
        super().__init__(parent, text=t("java_group"))
        self.app = app
        self.majors_provider = majors_provider
        self.use_java = tk.BooleanVar(value=False)
        self.path = tk.StringVar()
        self.skip_compat = tk.BooleanVar(value=False)

        ttk.Checkbutton(self, text=t("java_override"), variable=self.use_java, command=self._toggle).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(8, 2)
        )
        self.default_label = ttk.Label(self, text="", style="Muted.TLabel")
        self.default_label.grid(row=1, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 6))

        self.custom = ttk.Frame(self)
        self.custom.grid(row=2, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 8))
        self.custom.columnconfigure(1, weight=1)
        ttk.Label(self.custom, text=t("java_exe")).grid(row=0, column=0, sticky="w")
        self.entry = ttk.Entry(self.custom, textvariable=self.path)
        self.entry.grid(row=0, column=1, columnspan=4, sticky="ew", padx=(8, 0), pady=3)
        self.btn_detect = ttk.Button(self.custom, text=t("java_detect"), command=self._detect)
        self.btn_detect.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=3)
        self.btn_browse = ttk.Button(self.custom, text=t("browse"), command=self._browse)
        self.btn_browse.grid(row=1, column=2, sticky="w", padx=(6, 0), pady=3)
        self.btn_download = ttk.Button(self.custom, text=t("java_download"), command=self._open_download)
        self.btn_download.grid(row=1, column=3, sticky="e", padx=(6, 0), pady=3)
        self.btn_test = ttk.Button(self.custom, text=t("java_test"), command=self._test)
        self.btn_test.grid(row=1, column=4, sticky="e", padx=(6, 0), pady=3)
        self.custom.columnconfigure(3, weight=1)
        self.chk_skip = ttk.Checkbutton(self.custom, text=t("java_skip_compat"), variable=self.skip_compat)
        self.chk_skip.grid(row=2, column=0, columnspan=5, sticky="w", pady=(2, 0))
        self.columnconfigure(0, weight=1)
        self._toggle()

    def default_major(self) -> int:
        return default_java_major(self.majors_provider()[1])

    def refresh_default(self) -> None:
        self.default_label.config(text=t("java_default", major=self.default_major()))

    def _toggle(self) -> None:
        custom = self.use_java.get()
        state = "normal" if custom else "disabled"
        for w in (self.entry, self.btn_detect, self.btn_browse, self.btn_download, self.btn_test, self.chk_skip):
            w.config(state=state)
        self.refresh_default()
        if custom:
            self.default_label.grid_remove()
        else:
            self.default_label.grid()

    def set_path(self, path: Path) -> None:
        self.use_java.set(True)
        self._toggle()
        self.path.set(str(path))

    def _detect(self) -> None:
        self.btn_detect.config(state="disabled")
        self.app.log(t("java_detecting"))
        java_dir = self.app.prism.java_dir if self.app.prism else None

        def done(result, error):
            self.btn_detect.config(state="normal")
            if error:
                return messagebox.showerror(t("error"), str(error), parent=self)
            if not result:
                return messagebox.showinfo(t("java_group"), t("java_detect_none"), parent=self)
            DetectDialog(self.app, self, result)  # type: ignore[arg-type]

        self.app.run_bg(lambda: javas.detect_system_javas(java_dir), done)

    def _browse(self) -> None:
        start = str(self.app.prism.java_dir) if self.app.prism else str(Path.home())
        f = filedialog.askopenfilename(title=t("java_exe"), initialdir=start)
        if f:
            self.path.set(f)

    def _test(self) -> None:
        p = self.path.get().strip()
        if not p:
            return
        major, line = javas.probe_java(Path(p))
        if major is None:
            messagebox.showerror(t("java_group"), t("java_test_fail", line=line), parent=self)
        else:
            messagebox.showinfo(t("java_group"), t("java_test_ok", major=major, line=line), parent=self)

    def _open_download(self) -> None:
        if not self.app.prism:
            messagebox.showwarning(t("warning"), t("no_prism"), parent=self)
            return
        JavaDialog(self.app, self)

    def choice(self) -> Optional[JavaChoice]:
        if not self.use_java.get():
            return JavaChoice(auto_major=self.default_major())
        if not self.path.get().strip():
            return None
        return JavaChoice(Path(self.path.get().strip()), self.skip_compat.get())

    def confirm_compat(self) -> bool:
        """Warn if the chosen Java major is outside the recommended set for the selected pack."""
        ch = self.choice()
        if not ch or not ch.path or ch.ignore_compat:
            return True
        recommended, _ = self.majors_provider()
        major, _line = javas.probe_java(ch.path)
        if major is not None and recommended and major not in recommended:
            return messagebox.askyesno(
                t("warning"),
                t("java_incompatible", major=major, rec=", ".join(map(str, sorted(recommended)))),
                parent=self,
            )
        return True


class DetectDialog(tk.Toplevel):
    """Lists the detected Javas; clicking one fills in its location."""

    def __init__(self, app: App, panel: JavaPanel, found: list[javas.DetectedJava]):
        super().__init__(app)
        self.panel, self.found = panel, found
        self.title(t("java_detect_title"))
        center_on(self, app, 760, 380)
        self.transient(app)
        dark_titlebar(self)

        ttk.Label(self, text=t("java_detect_hint"), style="Muted.TLabel").pack(anchor="w", padx=12, pady=(12, 6))
        box = ttk.Frame(self)
        box.pack(fill="both", expand=True, padx=12)
        cols = ("major", "version", "name", "path")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", selectmode="browse")
        for c, text, w in (
            ("major", t("java_col_major"), 60),
            ("version", t("java_col_version"), 110),
            ("name", t("java_col_name"), 170),
            ("path", t("java_col_path"), 380),
        ):
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        for i, j in enumerate(found):
            self.tree.insert("", "end", iid=str(i), values=(f"Java {j.major}", j.version, j.name, str(j.exe)))
        self.tree.bind("<ButtonRelease-1>", self._clicked)
        self.tree.bind("<Return>", self._clicked)
        ttk.Button(self, text=t("cancel"), command=self.destroy).pack(anchor="e", padx=12, pady=10)
        self.grab_set()

    def _clicked(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel:
            self.panel.set_path(self.found[int(sel[0])].exe)
            self.destroy()


class JavaDialog(tk.Toplevel):
    """Same layout as Prism's 'Install Java' window: vendor / major / version table."""

    def __init__(self, app: App, panel: JavaPanel):
        super().__init__(app)
        self.app, self.panel = app, panel
        self.title(t("java_dialog_title"))
        center_on(self, app, 820, 480)
        self.transient(app)
        self.builds: list[javas.JavaBuild] = []
        self.vendor_keys = list(javas.VENDORS)
        self.majors: list[int] = []
        self._gen = 0

        left = ttk.Frame(self)
        left.pack(side="left", fill="y", padx=6, pady=6)
        ttk.Label(left, text=t("java_vendor_hdr")).pack(anchor="w")
        self.vendor_list = tk.Listbox(left, exportselection=False, width=16, height=6)
        for k in self.vendor_keys:
            self.vendor_list.insert("end", javas.VENDORS[k])
        self.vendor_list.pack(fill="y")
        self.vendor_list.bind("<<ListboxSelect>>", lambda e: self._vendor_changed())

        mid = ttk.Frame(self)
        mid.pack(side="left", fill="y", pady=6)
        ttk.Label(mid, text=t("java_major_hdr")).pack(anchor="w")
        self.major_list = tk.Listbox(mid, exportselection=False, width=12)
        self.major_list.pack(fill="y", expand=True)
        self.major_list.bind("<<ListboxSelect>>", lambda e: self._major_changed())
        self.major_search = tk.StringVar()
        ttk.Entry(mid, textvariable=self.major_search, width=12).pack(fill="x", pady=(4, 0))
        self.major_search.trace_add("write", lambda *_: self._fill_majors())

        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        cols = ("version", "name", "released", "type")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        for c, key, w in (
            ("version", "java_col_version", 90),
            ("name", "java_col_name", 250),
            ("released", "java_col_released", 90),
            ("type", "java_col_type", 50),
        ):
            self.tree.heading(c, text=t(key))
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._sel_changed())
        self.status = ttk.Label(right, text="")
        self.status.pack(anchor="w")
        self.search = tk.StringVar()
        ttk.Entry(right, textvariable=self.search).pack(fill="x", pady=(4, 0))
        self.search.trace_add("write", lambda *_: self._fill_builds())

        bottom = ttk.Frame(right)
        bottom.pack(fill="x", pady=(6, 0))
        ttk.Button(bottom, text=t("refresh"), command=self._vendor_changed).pack(side="left")
        self.recommended = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text=t("recommended"), variable=self.recommended, command=self._fill_majors).pack(
            side="left", padx=8
        )
        ttk.Button(bottom, text=t("cancel"), command=self.destroy).pack(side="right")
        self.dl_btn = ttk.Button(bottom, text=t("download"), command=self._download, state="disabled")
        self.dl_btn.pack(side="right", padx=6)

        self.vendor_list.selection_set(1)  # Adoptium, like most users want
        self._vendor_changed()

    # --- data loading (async so the UI stays responsive)
    def _vendor_changed(self) -> None:
        sel = self.vendor_list.curselection()
        if not sel:
            return
        self.vendor = self.vendor_keys[sel[0]]
        self._gen += 1
        gen = self._gen
        self.status.config(text="…")
        self.major_list.delete(0, "end")
        self.tree.delete(*self.tree.get_children())

        def done(result, error):
            if gen != self._gen or not self.winfo_exists():
                return
            self.status.config(text="")
            self.majors = result if not error else []
            self._fill_majors()

        self.app.run_bg(lambda: javas.list_majors(self.vendor), done)

    def _fill_majors(self) -> None:
        recommended, _ = self.app.current_majors()
        shown = [m for m in self.majors if (not self.recommended.get() or not recommended or m in recommended)]
        needle = self.major_search.get().strip()
        if needle:
            shown = [m for m in shown if needle in str(m)]
        self.major_list.delete(0, "end")
        for m in shown:
            self.major_list.insert("end", f"Java {m}")
        self._shown_majors = shown
        if shown:
            self.major_list.selection_set(0)
            self._major_changed()
        else:
            self.tree.delete(*self.tree.get_children())

    def _major_changed(self) -> None:
        sel = self.major_list.curselection()
        if not sel:
            return
        major = self._shown_majors[sel[0]]
        self._gen += 1
        gen = self._gen
        self.status.config(text="…")
        self.dl_btn.config(state="disabled")

        def done(result, error):
            if gen != self._gen or not self.winfo_exists():
                return
            self.status.config(text="")
            self.builds = [] if error else result  # type: ignore[assignment]
            self._fill_builds()

        vendor = self.vendor
        self.app.run_bg(lambda: javas.list_builds(vendor, major), done)

    def _fill_builds(self) -> None:
        self.tree.delete(*self.tree.get_children())
        needle = self.search.get().strip().lower()
        for i, b in enumerate(self.builds):
            if needle and needle not in f"{b.version} {b.name}".lower():
                continue
            self.tree.insert("", "end", iid=str(i), values=(b.version, b.name, b.released, b.kind))
        if not self.builds:
            self.status.config(text=t("no_builds"))

    def _sel_changed(self) -> None:
        self.dl_btn.config(state="normal" if self.tree.selection() else "disabled")

    def _download(self) -> None:
        sel = self.tree.selection()
        if not sel or not self.app.prism:
            return
        build = self.builds[int(sel[0])]
        java_dir = self.app.prism.java_dir
        panel = self.panel
        self.destroy()

        def work(reporter: Reporter):
            return javas.install_java(build, java_dir, reporter)

        def done(exe):
            panel.set_path(exe)  # type: ignore[arg-type]
            self.app.log(t("java_ready", path=exe))

        self.app.start_task(work, done)


# ============================================================================== Tabs

class InstallTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, app: App):
        super().__init__(parent)
        self.app = app
        self._name_edited = False

        top = ttk.Frame(self)
        top.pack(fill="both", expand=True, padx=6, pady=6)
        cols = ("version", "date", "channel", "java")
        self.tree = ttk.Treeview(top, columns=cols, show="headings", selectmode="browse", height=9)
        for c, key, w in (("version", "col_version", 160), ("date", "col_date", 110), ("channel", "col_channel", 110), ("java", "col_java", 110)):
            self.tree.heading(c, text=t(key))
            self.tree.column(c, width=w)
        sb = ttk.Scrollbar(top, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._selection_changed())

        opts = ttk.Frame(self)
        opts.pack(fill="x", padx=6)
        self.show_beta = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text=t("show_beta"), variable=self.show_beta, command=self.fill_versions).pack(side="left")
        ttk.Button(opts, text=t("refresh"), command=app.reload_versions).pack(side="left", padx=8)
        ttk.Button(opts, text=t("changelog"), command=self._open_changelog).pack(side="left")

        vf = ttk.Frame(self)
        vf.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Label(vf, text=t("variant")).pack(side="left")
        self.variant = tk.StringVar(value="modern")
        self.rb_modern = ttk.Radiobutton(vf, text=t("variant_modern"), value="modern", variable=self.variant, command=self._variant_changed)
        self.rb_java8 = ttk.Radiobutton(vf, text=t("variant_java8"), value="java8", variable=self.variant, command=self._variant_changed)
        self.rb_modern.pack(side="left", padx=6)
        self.rb_java8.pack(side="left")

        nf = ttk.Frame(self)
        nf.pack(fill="x", padx=6, pady=6)
        ttk.Label(nf, text=t("instance_name")).pack(side="left")
        self.name = tk.StringVar()
        e = ttk.Entry(nf, textvariable=self.name)
        e.pack(side="left", fill="x", expand=True, padx=6)
        e.bind("<Key>", lambda ev: setattr(self, "_name_edited", True))

        self.java = JavaPanel(self, app, self.majors)
        self.java.pack(fill="x", padx=6, pady=4)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=6, pady=6)
        self.keep_zip = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom, text=t("keep_zip"), variable=self.keep_zip).pack(side="left")
        self.action_btn = ttk.Button(bottom, text=t("install_btn"), command=self._install, style="Accent.TButton")
        self.action_btn.pack(side="right")

    # ---
    def _visible(self) -> list[GtnhVersion]:
        return [v for v in self.app.versions if v.is_stable or self.show_beta.get()]

    def fill_versions(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._shown = self._visible()
        for i, v in enumerate(self._shown):
            self.tree.insert("", "end", iid=str(i), values=(v.id, v.release_date, t(f"channel_{v.channel}"), v.max_java))
        if self._shown:
            self.tree.selection_set("0")

    def selected(self) -> Optional[GtnhVersion]:
        sel = self.tree.selection()
        return self._shown[int(sel[0])] if sel and hasattr(self, "_shown") else None

    def majors(self) -> tuple[list[int], list[int]]:
        v = self.selected()
        return (v.recommended_majors(self.variant.get()), v.all_majors(self.variant.get())) if v else ([], [])

    def _selection_changed(self) -> None:
        v = self.selected()
        if not v:
            return
        self.rb_modern.config(state="normal" if v.modern_url else "disabled")
        self.rb_java8.config(state="normal" if v.java8_url else "disabled")
        if self.variant.get() == "modern" and not v.modern_url:
            self.variant.set("java8")
        self._variant_changed()

    def _variant_changed(self) -> None:
        v = self.selected()
        if v and not self._name_edited:
            self.name.set(default_instance_name(v, self.variant.get()))
        self.java.refresh_default()

    def _open_changelog(self) -> None:
        v = self.selected()
        if v and v.changelog_url:
            webbrowser.open(v.changelog_url)

    def _install(self) -> None:
        v, prism = self.selected(), self.app.prism
        if not prism:
            return messagebox.showwarning(t("warning"), t("no_prism"), parent=self)
        if not v:
            return messagebox.showwarning(t("warning"), t("no_version"), parent=self)
        if not self.java.confirm_compat():
            return
        variant, name, java, keep = self.variant.get(), self.name.get().strip() or default_instance_name(v, self.variant.get()), self.java.choice(), self.keep_zip.get()

        def done(path):
            self.app.update_tab.reload_instances()
            messagebox.showinfo(t("info"), t("done_install", path=path), parent=self)

        self.app.start_task(lambda r: install_instance(prism, v, variant, name, java, r, keep), done)


class UpdateTab(ttk.Frame):
    def __init__(self, parent: tk.Misc, app: App):
        super().__init__(parent)
        self.app = app
        self.instances: list[InstanceInfo] = []
        self.extra_mods: list[str] = []
        self.selected_mods: list[str] = []
        self.stock_known = False
        self._name_edited = False

        f = ttk.Frame(self)
        f.pack(fill="x", padx=6, pady=(8, 0))
        ttk.Label(f, text=t("update_instance")).grid(row=0, column=0, sticky="w")
        self.inst_combo = ttk.Combobox(f, state="readonly")
        self.inst_combo.grid(row=0, column=1, sticky="ew", padx=6)
        self.inst_combo.bind("<<ComboboxSelected>>", lambda e: self._instance_changed())
        self.detected = ttk.Label(f, text="")
        self.detected.grid(row=0, column=2, sticky="w")
        ttk.Label(f, text=t("target_version")).grid(row=1, column=0, sticky="w", pady=4)
        self.target_combo = ttk.Combobox(f, state="readonly")
        self.target_combo.grid(row=1, column=1, sticky="ew", padx=6)
        self.target_combo.bind("<<ComboboxSelected>>", lambda e: self._target_changed())
        self.show_beta = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=t("show_beta"), variable=self.show_beta, command=self.fill_versions).grid(row=1, column=2, sticky="w")
        f.columnconfigure(1, weight=1)

        self.warn = ttk.Label(self, text="", foreground="#f5a524", wraplength=860, justify="left")
        self.warn.pack(fill="x", padx=6)

        vf = ttk.Frame(self)
        vf.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(vf, text=t("variant")).pack(side="left")
        self.variant = tk.StringVar(value="modern")
        ttk.Radiobutton(vf, text=t("variant_modern"), value="modern", variable=self.variant, command=self._target_changed).pack(side="left", padx=6)
        ttk.Radiobutton(vf, text=t("variant_java8"), value="java8", variable=self.variant, command=self._target_changed).pack(side="left")
        ttk.Label(vf, text="   " + t("instance_name")).pack(side="left")
        self.name = tk.StringVar()
        e = ttk.Entry(vf, textvariable=self.name)
        e.pack(side="left", fill="x", expand=True, padx=6)
        e.bind("<Key>", lambda ev: setattr(self, "_name_edited", True))

        self.java = JavaPanel(self, app, self.majors)
        self.java.pack(fill="x", padx=6, pady=6)

        always = ttk.LabelFrame(self, text=t("always_group"))
        always.pack(fill="x", padx=6, pady=2)
        ttk.Label(always, text=t("always_text"), wraplength=840, justify="left").pack(fill="x", padx=6, pady=4)

        opt = ttk.LabelFrame(self, text=t("optional_group"))
        opt.pack(fill="x", padx=6, pady=4)
        self.opt_vars: dict[str, tk.BooleanVar] = {}
        self.opt_checks: dict[str, ttk.Checkbutton] = {}
        for n, item in enumerate(OPTIONAL_ITEMS):
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(opt, text=t(f"opt_{item.id}"), variable=var)
            cb.grid(row=n // 2, column=n % 2, sticky="w", padx=8, pady=1)
            self.opt_vars[item.id] = var
            self.opt_checks[item.id] = cb
        row = (len(OPTIONAL_ITEMS) + 1) // 2
        mods_row = ttk.Frame(opt)
        mods_row.grid(row=row, column=0, columnspan=2, sticky="w", padx=8)
        self.mods_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(mods_row, text=t("opt_mods"), variable=self.mods_var, command=self._mods_toggled).pack(side="left")
        self.mods_btn = ttk.Button(mods_row, text=t("opt_mods_choose"), command=self._choose_mods, state="disabled")
        self.mods_btn.pack(side="left", padx=6)
        self.mods_count = ttk.Label(mods_row, text="")
        self.mods_count.pack(side="left")
        self.mem_var = tk.BooleanVar(value=True)
        self.jvm_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text=t("opt_memory"), variable=self.mem_var).grid(row=row + 1, column=0, sticky="w", padx=8)
        ttk.Checkbutton(opt, text=t("opt_jvm_args"), variable=self.jvm_var).grid(row=row + 1, column=1, sticky="w", padx=8)

        ttk.Label(self, text=t("backup_notice"), wraplength=860, justify="left").pack(fill="x", padx=6, pady=2)
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=6, pady=6)
        self.action_btn = ttk.Button(bottom, text=t("update_btn"), command=self._update, style="Accent.TButton")
        self.action_btn.pack(side="right")

    # --- state
    def majors(self) -> tuple[list[int], list[int]]:
        v = self.target()
        return (v.recommended_majors(self.variant.get()), v.all_majors(self.variant.get())) if v else ([], [])

    def reload_instances(self) -> None:
        prism = self.app.prism
        self.instances = list_instances(prism.instances_dir) if prism else []
        self.inst_combo["values"] = [
            f"{'★ ' if i.is_gtnh else ''}{i.name}  [{i.path.name}]" for i in self.instances
        ]
        if self.instances:
            self.inst_combo.current(0)
            self._instance_changed()
        else:
            self.inst_combo.set("")

    def selected_instance(self) -> Optional[InstanceInfo]:
        i = self.inst_combo.current()
        return self.instances[i] if 0 <= i < len(self.instances) else None

    def _instance_changed(self) -> None:
        inst = self.selected_instance()
        if not inst:
            return
        self.detected.config(text=t("detected_version", v=inst.version or t("unknown")))
        self.variant.set(detect_variant(inst.path))
        mc = minecraft_dir(inst.path)
        present = {i.id for i in present_items(mc, OPTIONAL_ITEMS)}
        for iid, cb in self.opt_checks.items():
            cb.config(state="normal" if iid in present else "disabled")
            if iid not in present:
                self.opt_vars[iid].set(False)
        self.extra_mods, self.selected_mods = [], []
        self.mods_var.set(False)
        self._mods_toggled()
        self.fill_versions()

    def fill_versions(self) -> None:
        inst = self.selected_instance()
        vs = [v for v in self.app.versions if v.is_stable or self.show_beta.get()]
        self._targets = vs
        self.target_combo["values"] = [f"{v.id}  ({v.release_date})" for v in vs]
        if not vs:
            return
        # newest stable by default
        idx = next((i for i, v in enumerate(vs) if v.is_stable), 0)
        self.target_combo.current(idx)
        self._target_changed()

    def target(self) -> Optional[GtnhVersion]:
        i = self.target_combo.current()
        return self._targets[i] if hasattr(self, "_targets") and 0 <= i < len(self._targets) else None

    def _target_changed(self) -> None:
        v, inst = self.target(), self.selected_instance()
        if not v:
            return
        if self.variant.get() == "modern" and not v.modern_url:
            self.variant.set("java8")
        if not self._name_edited:
            self.name.set(default_instance_name(v, self.variant.get()))
        skip = bool(inst and upgrade_skips_major(inst.version, v.id))
        self.warn.config(text=t("skip_major_warning") if skip else "")
        self.java.refresh_default()

    # --- extra mods
    def _mods_toggled(self) -> None:
        on = self.mods_var.get()
        self.mods_btn.config(state="normal" if on else "disabled")
        if on and not self.extra_mods:
            self._scan_mods()
        self.mods_count.config(text=f"({len(self.selected_mods)})" if on else "")

    def _scan_mods(self) -> None:
        inst, v = self.selected_instance(), self.target()
        if not inst or not v:
            return
        variant, versions = self.variant.get(), list(self.app.versions)
        self.mods_count.config(text="…")
        self.mods_btn.config(state="disabled")

        def done(result, error):
            self.mods_btn.config(state="normal")
            if error or not self.mods_var.get():
                self.mods_count.config(text="")
                return
            self.extra_mods, self.stock_known = result  # type: ignore[misc]
            self.selected_mods = list(self.extra_mods) if self.stock_known else []
            self.mods_count.config(text=f"({len(self.selected_mods)})")
            self._choose_mods()

        self.app.run_bg(lambda: detect_user_mods(inst.path, versions, inst.version, v, variant), done)

    def _choose_mods(self) -> None:
        if not self.extra_mods:
            messagebox.showinfo(t("mods_dialog_title"), t("mods_none"), parent=self)
            return
        dlg = tk.Toplevel(self)
        dlg.title(t("mods_dialog_title"))
        dlg.geometry("560x420")
        dlg.transient(self)
        hint = t("mods_hint") if self.stock_known else t("mods_hint_all")
        ttk.Label(dlg, text=hint, wraplength=520).pack(fill="x", padx=8, pady=6)
        lb = tk.Listbox(dlg, selectmode="extended", exportselection=False)
        sb = ttk.Scrollbar(dlg, command=lb.yview)
        lb.config(yscrollcommand=sb.set)
        for i, m in enumerate(self.extra_mods):
            lb.insert("end", m)
            if m in self.selected_mods:
                lb.selection_set(i)
        sb.pack(side="right", fill="y")
        lb.pack(fill="both", expand=True, padx=8)

        def ok() -> None:
            self.selected_mods = [self.extra_mods[i] for i in lb.curselection()]
            self.mods_count.config(text=f"({len(self.selected_mods)})")
            dlg.destroy()

        ttk.Button(dlg, text=t("ok"), command=ok).pack(pady=6)

    # --- go
    def _update(self) -> None:
        prism, inst, v = self.app.prism, self.selected_instance(), self.target()
        if not prism:
            return messagebox.showwarning(t("warning"), t("no_prism"), parent=self)
        if not inst:
            return messagebox.showwarning(t("warning"), t("no_instance"), parent=self)
        if not v:
            return messagebox.showwarning(t("warning"), t("no_version"), parent=self)
        if not self.java.confirm_compat():
            return
        opts = MigrationOptions(
            optional={k for k, var in self.opt_vars.items() if var.get()},
            extra_mods=list(self.selected_mods) if self.mods_var.get() else [],
            copy_memory=self.mem_var.get(),
            copy_jvm_args=self.jvm_var.get(),
        )
        variant, name, java = self.variant.get(), self.name.get().strip() or default_instance_name(v, self.variant.get()), self.java.choice()

        def done(path):
            self.reload_instances()
            messagebox.showinfo(t("info"), t("done_update", path=path), parent=self)

        self.app.start_task(lambda r: update_instance(prism, inst.path, v, variant, name, java, opts, r), done)


class LanguageDialog(tk.Tk):
    """First screen: pick English or Turkish (preselected from the system language)."""

    def __init__(self) -> None:
        super().__init__()
        apply_dark(self)
        self.title(t("lang_window"))
        self.resizable(False, False)
        self.choice: Optional[str] = None
        self.lang = tk.StringVar(value=detect_language())

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="x")
        ttk.Label(card, text="GTNH", style="Title.TLabel").pack(padx=30, pady=(22, 0))
        ttk.Label(card, text=t("lang_prompt"), style="Sub.TLabel", justify="center").pack(padx=30, pady=(4, 18))

        body = ttk.Frame(self)
        body.pack(fill="x", padx=30, pady=18)
        big = tkfont.nametofont("TkDefaultFont").copy()
        big.configure(size=12, weight="bold")
        for code, label in (("en", "English"), ("tr", "Türkçe")):
            row = tk.Radiobutton(
                body, text=label, value=code, variable=self.lang, indicatoron=False, font=big,
                bg="#2a2e40", fg=FG, selectcolor="#2f4a94", activebackground="#353a52", activeforeground=FG,
                relief="flat", bd=0, padx=20, pady=10, cursor="hand2", highlightthickness=0,
            )
            row.pack(fill="x", pady=4)
        ttk.Button(body, text=t("lang_continue"), style="Accent.TButton", command=self._continue).pack(fill="x", pady=(14, 0))
        self.bind("<Return>", lambda e: self._continue())
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        w, h = 340, self.winfo_reqheight()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _continue(self) -> None:
        self.choice = self.lang.get()
        self.destroy()


def ask_language() -> Optional[str]:
    dlg = LanguageDialog()
    dlg.mainloop()
    return dlg.choice


def main(prompt_language: bool = True) -> None:
    if prompt_language:
        lang = ask_language()
        if lang is None:  # window closed without choosing
            sys.exit(0)
        set_language(lang)
    App().mainloop()
