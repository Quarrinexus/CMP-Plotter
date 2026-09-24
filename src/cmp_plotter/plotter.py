"""Interactive plotter window: pick datasets and axes, plot, save. See README.md."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
import numpy as np
from PIL import Image, ImageDraw, ImageTk

from cmp_plotter.axis_functions import apply_function, is_identity, rename
from cmp_plotter import background, smoothing, spectrum
from cmp_plotter.columns import label, lookup, with_unit, without_unit
from cmp_plotter.model import Panel, legend_labels, line_colours, shared
from cmp_plotter.profile import load_profile, save_format
from cmp_plotter.datasets import (FormatError, describe, detect_format, find_datasets,
                                  load_dataset, read_lines, run_number)
from cmp_plotter.format_dialog import FormatDialog
from cmp_plotter.settings import load_settings, save_settings
from cmp_plotter.widgets import MAX_GRID, SELECTED, ColourPopup, LayoutPicker

PARTNER = "#f0c987"  # frame around the panel locked to the selected one


# Tk's X core fonts show these as '®' or the wrong symbol, though matplotlib
# draws them fine; plain() swaps them for ASCII in text Tk shows.
PLAIN = str.maketrans({"\u2212": "-", "\u2013": "-", "\u0394": "d", "\u2192": "->"})


def plain(text):
    return text.translate(PLAIN)


class LineError(Exception):
    """A line that couldn't be drawn; the text is as Line.error holds it."""


def title(names):
    """Panel title: 'run 005, 003', or the dataset names if they aren't runs."""
    numbers = [run_number(n) for n in names]
    if all(numbers):
        return "run " + ", ".join(numbers)
    return ", ".join(describe(n) for n in names)


def swap_icon(colour="#52514e"):
    """A two-way arrow (up beside down) for the swap-axes button."""
    # Drawn, not typed: Tk's X core fonts can show arrow characters as '®'.
    image = Image.new("RGBA", (18, 22))
    draw = ImageDraw.Draw(image)
    draw.line((5, 5, 5, 20), fill=colour, width=2)
    draw.polygon(((0, 7), (5, 1), (10, 7)), fill=colour)
    draw.line((12, 1, 12, 16), fill=colour, width=2)
    draw.polygon(((7, 14), (12, 20), (17, 14)), fill=colour)
    return ImageTk.PhotoImage(image)


class Plotter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CMP Plotter")
        # Room for the controls with a section or two open, screen allowing;
        # beyond that they scroll.
        self.geometry(f"1150x{min(820, self.winfo_screenheight() - 80)}")
        self.frames = {}  # dataset name -> DataFrame, so each file is read once
        self.datasets = {}  # dataset name -> file, from the data folder
        self.rows, self.cols = 1, 1
        self.panels = {(0, 0): Panel()}  # (row, col) -> Panel
        self.selected = (0, 0)
        self.axes = {}  # (row, col) -> matplotlib Axes
        self.artists = {}  # (row, col) -> {matplotlib Line2D: line index}
        self.colour_popup = None
        self.picker = None  # the SpanSelector while a fit range is being dragged
        self.fft_pick = None  # source cell while the user clicks a panel for its FFT
        self.cache = {}  # id(Line) -> (settings, its x, y and labels), see _line_data
        self.settings = load_settings()
        self.profile, profile_error = load_profile(self.data_dir)

        # The controls column scrolls, with a scrollbar only when it's taller
        # than the window; Save stays pinned below it.
        side = ttk.Frame(self)
        side.pack(side=tk.LEFT, fill=tk.Y)
        save = ttk.Frame(side, padding=(10, 0, 10, 10))
        save.pack(side=tk.BOTTOM, anchor=tk.W, fill=tk.X)
        self.side = tk.Canvas(side, highlightthickness=0, borderwidth=0, yscrollincrement=20,
                              background=ttk.Style().lookup("TFrame", "background"))
        self.side.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Style().configure("Side.Vertical.TScrollbar", arrowsize=10)
        self.side_scroll = ttk.Scrollbar(side, orient=tk.VERTICAL, command=self.side.yview,
                                         style="Side.Vertical.TScrollbar")
        self.side.configure(yscrollcommand=self.side_scroll.set)
        controls = ttk.Frame(self.side, padding=(10, 10, 10, 0))
        self.side.create_window(0, 0, window=controls, anchor=tk.NW)
        self.side_inner = controls
        controls.bind("<Configure>", self._fit_side)
        self.side.bind("<Configure>", self._fit_side)
        for sequence in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.bind_all(sequence, self._scroll_side, add="+")
        # Open at start only if a folder still needs choosing.
        folders = self._collapsible(
            controls, (0, 0), lambda _: "Folders",
            start_open=not (self.settings.get("data_dir") and self.settings.get("output_dir")))
        self.data_label = self._folder_row(folders, "Data folder", "data_dir")
        self.output_label = self._folder_row(folders, "Output folder", "output_dir")
        ttk.Button(folders, text="Data format...", command=self.edit_format).pack(
            anchor=tk.W, pady=(0, 2))
        ttk.Separator(controls).pack(fill=tk.X, pady=(10, 8))
        ttk.Label(controls, text="Lines").pack(anchor=tk.W, pady=(0, 2))
        lines = ttk.Frame(controls)
        lines.pack(anchor=tk.W, fill=tk.X)
        self.line_list = tk.Listbox(lines, height=4, width=24, exportselection=False,
                                    activestyle="none")
        self.line_list.pack(side=tk.LEFT)
        line_scroll = ttk.Scrollbar(lines, orient=tk.VERTICAL, command=self.line_list.yview)
        line_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.line_list["yscrollcommand"] = line_scroll.set
        self.line_list.bind("<<ListboxSelect>>", self._on_line_select)
        line_buttons = ttk.Frame(lines)
        line_buttons.pack(side=tk.LEFT, padx=(6, 0), fill=tk.Y)
        ttk.Button(line_buttons, text="+", width=3, command=self.add_line).pack()
        self.remove_button = ttk.Button(line_buttons, text="-", width=3,
                                        command=self.remove_line)
        self.remove_button.pack(pady=(4, 0))
        self.swatch = tk.Label(line_buttons, width=3, relief=tk.SOLID, borderwidth=1,
                               cursor="hand2")
        self.swatch.pack(pady=(4, 0), fill=tk.X)
        self.swatch.bind("<Button-1>", lambda _: self.open_colour())

        self.run = self._combo(controls, "Dataset", [], postcommand=self._refresh_runs)
        axes = ttk.Frame(controls)
        axes.pack(anchor=tk.W, fill=tk.X)
        axis_boxes = ttk.Frame(axes)
        axis_boxes.pack(side=tk.LEFT)
        self.x = self._combo(axis_boxes, "X axis", [])
        self.x_fn = self._function_box(axis_boxes, "x")
        self.y = self._combo(axis_boxes, "Y axis", [])
        self.y_fn = self._function_box(axis_boxes, "y")
        self.swap_icon = swap_icon()
        ttk.Button(axes, image=self.swap_icon, command=self.swap).pack(
            side=tk.LEFT, padx=(6, 0))
        self._smoothing_box(controls)
        self._background_box(controls)
        self._fft_box(controls)
        self.bind("<Escape>", lambda _: self.stop_picking())

        # Saving sits at the bottom of the column, below the scrolling part.
        ttk.Label(save, text="Save as").pack(anchor=tk.W, pady=(16, 2))
        self.filename = tk.StringVar()
        self.auto_name = ""  # last default name put in the box
        ttk.Entry(save, textvariable=self.filename, width=26).pack(anchor=tk.W)
        buttons = ttk.Frame(save)
        buttons.pack(anchor=tk.W, pady=(8, 0))
        ttk.Button(buttons, text="Layout...", command=self.choose_layout).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Save figure", command=self.save).pack(
            side=tk.LEFT, padx=(6, 0))
        self.status = ttk.Label(save, wraplength=230)
        self.status.pack(anchor=tk.W, pady=(12, 0))

        self.fig = Figure(figsize=(8, 5), constrained_layout=True)
        plot = ttk.Frame(self)
        plot.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot)
        self.toolbar = NavigationToolbar2Tk(self.canvas, plot, pack_toolbar=False)
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect("button_press_event", self._on_click)

        self._refresh_runs()
        self._build_axes()
        self._load_controls()
        if profile_error:
            self._say(profile_error, error=True)

    # --- controls ---------------------------------------------------------

    def _fit_side(self, _=None):
        """Size the controls column to its contents; scrollbar only if it doesn't fit."""
        width, height = self.side_inner.winfo_reqwidth(), self.side_inner.winfo_reqheight()
        self.side.configure(width=width, scrollregion=(0, 0, width, height))
        if height > self.side.winfo_height():
            if not self.side_scroll.winfo_manager():
                self.side_scroll.pack(side=tk.LEFT, fill=tk.Y)
        elif self.side_scroll.winfo_manager():
            self.side_scroll.pack_forget()
            self.side.yview_moveto(0)

    def _scroll_side(self, event):
        """Mouse wheel over the controls scrolls them, when they're scrollable."""
        if not self.side_scroll.winfo_manager() or not str(event.widget).startswith(str(self.side)):
            return
        up = event.num == 4 or getattr(event, "delta", 0) > 0
        self.side.yview_scroll(-1 if up else 1, "units")

    def _combo(self, parent, label, values, default="", **kwargs):
        ttk.Label(parent, text=label).pack(anchor=tk.W, pady=(8, 2))
        var = tk.StringVar(value=default)
        box = ttk.Combobox(parent, textvariable=var, values=values,
                           state="readonly", width=24, **kwargs)
        box.pack(anchor=tk.W)
        box.bind("<<ComboboxSelected>>", lambda _: self.apply_controls())
        var.box = box
        return var

    def _collapsible(self, parent, pady, text, start_open=False, on_open=None):
        """A triangle toggle that shows or hides the frame it returns.

        `text(is_open)` gives the toggle's label; `frame.refresh()` updates it."""
        # The triangle is drawn, not typed: Tk's X core fonts can show ▸ as '®'.
        toggle = ttk.Frame(parent, cursor="hand2")
        toggle.pack(anchor=tk.W, pady=pady)
        arrow = tk.Canvas(toggle, width=10, height=10, highlightthickness=0,
                          background=ttk.Style().lookup("TFrame", "background"))
        arrow.pack(side=tk.LEFT, padx=(0, 4))
        label = ttk.Label(toggle, foreground="#52514e")
        label.pack(side=tk.LEFT)
        body = ttk.Frame(parent)

        def refresh():
            is_open = bool(body.winfo_manager())
            arrow.delete("all")
            points = (1, 2, 9, 2, 5, 8) if is_open else (2, 1, 8, 5, 2, 9)
            arrow.create_polygon(points, fill="#52514e", outline="")
            label["text"] = text(is_open)

        def flip(_):
            if body.winfo_manager():
                body.pack_forget()
            else:
                body.pack(anchor=tk.W, fill=tk.X, after=toggle)
                if on_open:
                    on_open()
            refresh()

        for widget in (toggle, arrow, label):
            widget.bind("<Button-1>", flip)
        if start_open:
            body.pack(anchor=tk.W, fill=tk.X, after=toggle)
        refresh()
        body.refresh = refresh
        return body

    def _function_box(self, parent, name):
        """A collapsed 'Function' toggle that opens to an entry box."""
        var = tk.StringVar(value=name)

        def text(is_open):
            # Collapsed but in use: show the function so it isn't forgotten.
            expr = var.get().strip()
            used = f": {expr}" if not is_identity(expr) and not is_open else ""
            return f"Function{used}"

        body = self._collapsible(parent, (4, 0), text, on_open=lambda: entry.focus_set())
        entry = ttk.Entry(body, textvariable=var, width=16)
        entry.pack(anchor=tk.W)
        ttk.Label(body, text=f"e.g. 1/{name}, exp({name}) - Enter to apply",
                  foreground="#9a9992").pack(anchor=tk.W)
        for key in ("<Return>", "<KP_Enter>"):
            entry.bind(key, lambda _: (self.apply_controls(), body.refresh()))
        var.show_label = body.refresh
        return var

    def _smoothing_box(self, parent):
        """A collapsed 'Smoothing' toggle: method, window and (for SG) order."""
        self.smooth = tk.StringVar(value=smoothing.METHODS[""])
        self.window, self.order = tk.StringVar(value="21"), tk.StringVar(value="2")
        self.window_unit = tk.StringVar(value=smoothing.UNITS[False])

        def text(is_open):
            l = self.panel.line
            used = f": {plain(smoothing.describe(*l.smoothing))}" if l.smoothing and not is_open else ""
            return f"Smoothing{used}"

        body = self._collapsible(parent, (10, 0), text)
        method = ttk.Combobox(body, textvariable=self.smooth, state="readonly", width=24,
                              values=list(smoothing.METHODS.values()))
        method.pack(anchor=tk.W, pady=(2, 0))
        method.bind("<<ComboboxSelected>>", lambda _: self.apply_controls())
        sizes = ttk.Frame(body)
        sizes.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(sizes, text="Window").pack(side=tk.LEFT)
        window = ttk.Spinbox(sizes, textvariable=self.window, from_=3, to=100001,
                             increment=2, width=6, command=self.apply_controls)
        window.pack(side=tk.LEFT, padx=(4, 6))
        unit = ttk.Combobox(sizes, textvariable=self.window_unit, state="readonly", width=7,
                            values=list(smoothing.UNITS.values()))
        unit.pack(side=tk.LEFT)
        unit.bind("<<ComboboxSelected>>", lambda _: self.apply_controls())
        orders = ttk.Frame(body)
        ttk.Label(orders, text="Order").pack(side=tk.LEFT)
        order = ttk.Spinbox(orders, textvariable=self.order, from_=0, to=10, width=3,
                            command=self.apply_controls)
        order.pack(side=tk.LEFT, padx=(4, 0))
        hint = ttk.Label(body, foreground="#9a9992", wraplength=230)
        hint.pack(anchor=tk.W)
        for box in (window, order):
            for key in ("<Return>", "<KP_Enter>"):
                box.bind(key, lambda _: self.apply_controls())

        def step(direction):
            """Arrows on the window: 1-2-5 steps in x; odd numbers only for SG."""
            if self.window_unit.get() == smoothing.UNITS[True]:
                try:
                    span = float(self.window.get())
                except ValueError:
                    span = self.panel.line.span
                if span and span > 0:
                    self.window.set(f"{smoothing.step_nice(span, direction):g}")
                    self.apply_controls()
                return "break"
            if self.smooth.get() != smoothing.METHODS["savgol"]:
                return None  # Tk's own stepping
            try:
                n, order = int(self.window.get()), int(self.order.get())
            except ValueError:
                n, order = self.panel.line.window, self.panel.line.order
            # From an odd number to the next odd one; from an even one to the odd beside it.
            n += 2 * direction if n % 2 else direction
            # No lower than the smallest odd window the order allows (order < window - 1).
            self.window.set(max(n, 3, order + 2 if order % 2 else order + 3))
            self.apply_controls()
            return "break"
        window.bind("<<Increment>>", lambda _: step(1))
        window.bind("<<Decrement>>", lambda _: step(-1))

        def refresh():
            body.refresh()
            # Order only means something for Savitzky–Golay.
            if self.panel.line.smooth == "savgol":
                orders.pack(anchor=tk.W, pady=(4, 0), after=sizes)
            else:
                orders.pack_forget()
            hint["text"] = ("of the plotted x, e.g. in 1/B with a 1/x function"
                            if self.panel.line.in_x else "points, in the order they were taken")
        self.smooth.show = refresh

    def _background_box(self, parent):
        """A collapsed 'Background' toggle: mode, degree and the fit's x range."""
        self.fit_mode = tk.StringVar(value=background.MODES[""])
        self.degree = tk.StringVar(value="10")
        self.fit_from, self.fit_to = tk.StringVar(), tk.StringVar()

        def text(is_open):
            fitted = self.panel.line.fitting
            # Without the range, which would widen the column.
            used = (f": {plain(background.describe(*fitted[:2], None, None))}"
                    if fitted and not is_open else "")
            return f"Background{used}"

        body = self._collapsible(parent, (10, 0), text)
        mode = ttk.Combobox(body, textvariable=self.fit_mode, state="readonly", width=24,
                            values=list(background.MODES.values()))
        mode.pack(anchor=tk.W, pady=(2, 0))
        mode.bind("<<ComboboxSelected>>", lambda _: self.apply_controls())
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(row, text="Degree").pack(side=tk.LEFT)
        degree = ttk.Spinbox(row, textvariable=self.degree, from_=0, to=30, width=3,
                             command=self.apply_controls)
        degree.pack(side=tk.LEFT, padx=(4, 0))
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(row, text="Fit x from").pack(side=tk.LEFT)
        start = ttk.Entry(row, textvariable=self.fit_from, width=8)
        start.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(row, text="to").pack(side=tk.LEFT)
        end = ttk.Entry(row, textvariable=self.fit_to, width=8)
        end.pack(side=tk.LEFT, padx=(4, 0))
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(row, text="Pick on plot", command=self.pick_range).pack(side=tk.LEFT)
        ttk.Label(row, text="blank: whole line", foreground="#9a9992").pack(
            side=tk.LEFT, padx=(8, 0))
        for box in (degree, start, end):
            for key in ("<Return>", "<KP_Enter>"):
                box.bind(key, lambda _: self.apply_controls())
        self.fit_mode.show = body.refresh

    def _fft_box(self, parent):
        """A collapsed 'FFT' toggle: make an FFT panel of this one, or set one up."""
        self.fft_window, self.fft_pad, self.f_max = tk.StringVar(), tk.StringVar(), tk.StringVar()

        def text(is_open):
            source = self.panel.source
            used = f": of panel {self._number(source)}" if source and not is_open else ""
            return f"FFT{used}"

        body = self._collapsible(parent, (10, 0), text)
        # For a data panel: the two ways to make its FFT.
        make = ttk.Frame(body)
        ttk.Button(make, text="FFT to new panel", command=self.fft_new_panel).pack(
            anchor=tk.W, pady=(2, 0))
        ttk.Button(make, text="FFT to existing panel...", command=self.fft_existing_panel).pack(
            anchor=tk.W, pady=(4, 0))
        ttk.Label(make, text="of this panel's lines, locked to it; use 1/x on the "
                             "field for F in T", foreground="#9a9992", wraplength=230).pack(
            anchor=tk.W)
        # For an FFT panel: its settings.
        settings = ttk.Frame(body)
        source_label = ttk.Label(settings, foreground="#52514e", wraplength=230)
        source_label.pack(anchor=tk.W, pady=(2, 0))
        row = ttk.Frame(settings)
        row.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(row, text="Window").pack(side=tk.LEFT)
        window = ttk.Combobox(row, textvariable=self.fft_window, state="readonly", width=5,
                              values=list(spectrum.WINDOWS.values()))
        window.pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(row, text="Padding").pack(side=tk.LEFT)
        pad = ttk.Combobox(row, textvariable=self.fft_pad, state="readonly", width=2,
                           values=[str(n) for n in spectrum.PADDING])
        pad.pack(side=tk.LEFT, padx=(4, 0))
        row = ttk.Frame(settings)
        row.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(row, text="F max").pack(side=tk.LEFT)
        f_max = ttk.Entry(row, textvariable=self.f_max, width=8)
        f_max.pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(row, text="blank: all", foreground="#9a9992").pack(side=tk.LEFT)
        ttk.Button(settings, text="Unlink", command=self.unlink).pack(anchor=tk.W, pady=(6, 0))
        for box in (window, pad):
            box.bind("<<ComboboxSelected>>", lambda _: self.apply_fft())
        for key in ("<Return>", "<KP_Enter>"):
            f_max.bind(key, lambda _: self.apply_fft())

        def refresh():
            body.refresh()
            p = self.panel
            if p.source is None:
                settings.pack_forget()
                make.pack(anchor=tk.W, fill=tk.X)
                return
            make.pack_forget()
            settings.pack(anchor=tk.W, fill=tk.X)
            source_label["text"] = (f"FFT of panel {self._number(p.source)}, locked to it: "
                                    "its lines are shared.")
            self.fft_window.set(spectrum.WINDOWS[p.window])
            self.fft_pad.set(str(p.pad))
            self.f_max.set("" if p.f_max is None else f"{p.f_max:g}")
        self.fft_window.show = refresh

    def _folder_row(self, parent, label, key):
        """'Data folder' etc.: the chosen path, with Browse... to change it."""
        ttk.Label(parent, text=label).pack(anchor=tk.W, pady=(0, 2))
        row = ttk.Frame(parent)
        row.pack(anchor=tk.W, fill=tk.X, pady=(0, 6))
        ttk.Button(row, text="Browse...",
                   command=lambda: self.choose_folder(key, label)).pack(side=tk.RIGHT)
        path = ttk.Label(row, width=19, anchor=tk.W)
        path.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._show_folder(path, key)
        return path

    def _show_folder(self, widget, key):
        """Show the folder's name (the full path is too long for the column)."""
        folder = self.settings.get(key)
        widget["text"] = Path(folder).name or folder if folder else "(not set)"
        widget["foreground"] = "#52514e" if folder else "#b3261e"

    def choose_folder(self, key, title):
        folder = filedialog.askdirectory(parent=self, title=f"Choose {title.lower()}",
                                         initialdir=self.settings.get(key) or Path.home(),
                                         mustexist=True)
        if not folder:  # cancelled
            return False
        self.settings[key] = folder
        try:
            save_settings(self.settings)
        except OSError as err:
            self._say(f"Couldn't remember the folder: {err}", error=True)
        if key == "data_dir":
            self._show_folder(self.data_label, key)
            self._reload_folder()
        else:
            self._show_folder(self.output_label, key)
        return True

    def _reload_folder(self):
        """Re-read the data folder's profile and files, then redraw everything."""
        self.profile, error = load_profile(self.data_dir)
        self._say(error, error=True)
        self.frames.clear()
        self.cache.clear()
        self._refresh_runs()
        self._build_axes()
        self._load_controls()

    def edit_format(self, name=None, reason=""):
        """Open the Data format window on dataset `name` (default: the selected one)."""
        self._refresh_runs()
        name = name or self.panel.line.run or next(iter(self.datasets), None)
        if name not in self.datasets:
            self._say("No data files in the data folder." if self.data_dir
                      else "Choose a data folder first.", error=True)
            return
        lines = read_lines(self.datasets[name])
        fmt = self.profile.format
        if not fmt:
            try:
                fmt = detect_format(lines)
            except FormatError:
                fmt = {"delimiter": "tab", "header_line": 0, "data_line": 1}
        dialog = FormatDialog(self, name, lines, fmt, reason)
        self.wait_window(dialog)
        if dialog.cancelled:
            return
        try:
            save_format(self.data_dir, dialog.fmt)
        except (OSError, ValueError) as err:
            self._say(f"Couldn't save the format: {err}", error=True)
            return
        self._reload_folder()

    @property
    def data_dir(self):
        return self.settings.get("data_dir")

    def _refresh_runs(self):
        # Re-scan on every open so files added while the window is up appear.
        self.datasets = find_datasets(self.data_dir)
        self.run.box["values"] = list(self.datasets)

    @property
    def panel(self):
        return self.panels[self.selected]

    def _load_controls(self):
        """Show the selected line's settings in the controls."""
        self._fill_line_list()
        l = self.panel.line
        self.run.set(l.run)
        columns = list(self.frames[l.run].columns) if l.run in self.frames else []
        self.x.box["values"] = self.y.box["values"] = [with_unit(c, self.profile.units) for c in columns]
        self.x.set(with_unit(l.x, self.profile.units) if l.run else "")
        self.y.set(with_unit(l.y, self.profile.units) if l.run else "")
        self.x_fn.set(l.x_fn)
        self.y_fn.set(l.y_fn)
        self.x_fn.show_label()
        self.y_fn.show_label()
        self.smooth.set(smoothing.METHODS[l.smooth])
        self.window_unit.set(smoothing.UNITS[l.in_x])
        self.window.set((f"{l.span:g}" if l.span is not None else "") if l.in_x else l.window)
        self.order.set(l.order)
        self.smooth.show()
        self.fit_mode.set(background.MODES[l.background])
        self.degree.set(l.degree)
        self.fit_from.set("" if l.fit_from is None else f"{l.fit_from:.12g}")
        self.fit_to.set("" if l.fit_to is None else f"{l.fit_to:.12g}")
        self.fit_mode.show()
        self.fft_window.show()
        self._say("")  # errors pop up instead; see apply_controls
        self._show_colour()

    def _fill_line_list(self):
        p, colours = self.panel, line_colours(self.panel, self.profile.samples)
        self.line_list.delete(0, tk.END)
        for l, colour in zip(p.lines, colours):
            name = f"{l.y} · {run_number(l.run) or l.run}" if l.run else "(no dataset)"
            if l.smoothing:
                name += f" · {plain(smoothing.describe(*l.smoothing))}"
            if l.fitting:
                name += f" · {plain(background.describe(*l.fitting))}"
            self.line_list.insert(tk.END, name)
            self.line_list.itemconfigure(tk.END, foreground=colour,
                                         selectforeground=colour)
        self.line_list.selection_set(p.selected)
        self.line_list.see(p.selected)
        self.remove_button.state(["!disabled" if len(p.lines) > 1 else "disabled"])

    def apply_controls(self):
        """Copy the controls into the selected line and redraw its panel."""
        self.stop_picking()
        l = self.panel.line
        before, old_x = l.shown, (l.x, l.x_fn)
        l.run = self.run.get()
        l.x, l.y = without_unit(self.x.get()) or l.x, without_unit(self.y.get()) or l.y
        l.x_fn, l.y_fn = self.x_fn.get().strip(), self.y_fn.get().strip()
        l.smooth = next(k for k, v in smoothing.METHODS.items() if v == self.smooth.get())
        was_in_x, l.in_x = l.in_x, self.window_unit.get() == smoothing.UNITS[True]
        # The box holds the window in the units it was showing; the other is kept.
        fields = (("span" if was_in_x else "window", self.window, float if was_in_x else int),
                  ("order", self.order, int))
        for attr, var, kind in fields:
            try:
                setattr(l, attr, kind(var.get()))
            except ValueError:  # not a number: keep the old one (shown again below)
                pass
        l.background = next(k for k, v in background.MODES.items() if v == self.fit_mode.get())
        try:
            l.degree = int(self.degree.get())
        except ValueError:
            pass
        for attr, var in (("fit_from", self.fit_from), ("fit_to", self.fit_to)):
            try:
                setattr(l, attr, float(var.get()) if var.get().strip() else None)
            except ValueError:
                pass
        if (l.x, l.x_fn) != old_x:
            # A window or range in the old x means nothing in the new one.
            l.span = l.fit_from = l.fit_to = None
        if l.run in self.datasets and l.run not in self.frames:
            try:
                self._load(l)
            except FormatError as err:  # ask how the file is laid out
                self.edit_format(l.run, f"Couldn't read {l.run}: {err}")
                if l.run not in self.frames:  # still unreadable; don't pop up again
                    self._redraw_selected()
                    return
            except Exception:  # anything else is reported by the redraw below
                pass
        # Same axes: keep the zoom, as smoothing and fits are often tuned zoomed
        # in. A background change moves y by orders of magnitude, so only x.
        keep = ""
        if before and before[:5] == (l.run, l.x, l.x_fn, l.y, l.y_fn):
            keep = "xy" if before[6] == l.fitting else "x"
            if self.panel.source:  # any change reshapes a spectrum
                keep = "x"
        self._redraw_selected(keep)
        if l.error:  # a popup rather than text in the controls, to save room
            if l.run in self.frames:  # "Function error: ...", "Smoothing error: ", ...
                title, _, text = l.error.partition(": ")
            else:
                title, text = "Could not load dataset", l.error
            messagebox.showerror(title, plain(text), parent=self)

    def _redraw_selected(self, keep=""):
        """Redraw the selected panel and those locked to it, keeping the selected
        one's x and/or y limits if `keep` says, and the others' x."""
        views = {}
        for cell in self._linked(self.selected):
            ax = self.axes[cell]
            wanted = keep if cell == self.selected else "x"
            # Only limits the user set (zooming turns autoscaling off); a view
            # that was just fitted to the old data should refit to the new.
            wanted = "".join(a for a in wanted if not getattr(ax, f"get_autoscale{a}_on")())
            views[cell] = wanted, ax.get_xlim(), ax.get_ylim()
        for cell in views:  # the data panel first: the FFT panels use what it draws
            self._draw_panel(cell)
        kept = {cell: view for cell, view in views.items() if view[0] and self.axes[cell].lines}
        if kept:
            self.toolbar.push_current()  # the full view, for the toolbar's Home
            for cell, (wanted, xlim, ylim) in kept.items():
                if "x" in wanted:
                    self.axes[cell].set_xlim(xlim)
                if "y" in wanted:
                    self.axes[cell].set_ylim(ylim)
            self.toolbar.push_current()
        for cell in self.axes:  # the locked panel's frame follows the selection
            self._frame(cell)
        self._load_controls()  # loading a run can change the axis choices
        self._update_filename()
        self.canvas.draw()

    # --- lines ------------------------------------------------------------

    def _select_line(self, index):
        self.stop_picking()
        self._set_selected_line(self.selected, index)
        self._load_controls()

    def _set_selected_line(self, cell, index):
        """Select line `index` in `cell` and the panels locked to it."""
        for c in self._linked(cell):
            self.panels[c].selected = index

    def _on_line_select(self, _):
        chosen = self.line_list.curselection()
        if chosen and chosen[0] != self.panel.selected:
            self._select_line(chosen[0])

    def add_line(self):
        """Add a copy of the selected line; it takes the next free colour."""
        p = self.panel
        new = p.line.copy()
        new.colour = None
        p.lines.insert(p.selected + 1, new)
        self._set_selected_line(self.selected, p.selected + 1)
        self._redraw_selected()

    def remove_line(self):
        p = self.panel
        if len(p.lines) > 1:
            del p.lines[p.selected]
            self._set_selected_line(self.selected, min(p.selected, len(p.lines) - 1))
            self._redraw_selected()

    # --- drawing ----------------------------------------------------------

    def _load(self, line):
        """The line's dataset, with its axes moved to valid columns if needed."""
        if line.run not in self.frames:
            if line.run not in self.datasets:
                raise FileNotFoundError(f"'{line.run}' is not in the data folder")
            self.frames[line.run] = load_dataset(self.datasets[line.run], self.profile.format)
        df = self.frames[line.run]
        # Keep the line's axes if this dataset has them, else fall back to the
        # profile's default, else the first column for x and the second for y.
        columns = list(df.columns)
        for attr, i in (("x", 0), ("y", 1)):
            default = self.profile.defaults.get(attr)
            if getattr(line, attr) not in df:
                setattr(line, attr, default if default in df else columns[min(i, len(columns) - 1)])
        return df

    def _axis(self, df, column, expr):
        """Values and (label, label without sample) for one axis."""
        labels = self.profile.labels
        values, texts = df[column].to_numpy(), (label(column, labels), label(column, labels, False))
        if is_identity(expr):
            return values, texts
        values, name = apply_function(expr, values)
        return values, tuple(f"{expr},   {name} = {t}" for t in texts)

    def _build_axes(self):
        """Recreate the grid of axes and draw every panel into it."""
        self.stop_picking()
        self.fig.clear()
        grid = self.fig.subplots(self.rows, self.cols, squeeze=False)
        self.axes = {(r, c): grid[r, c] for r in range(self.rows) for c in range(self.cols)}
        # Data panels first: FFT panels use what their data panel draws.
        for cell in sorted(self.axes, key=lambda c: self.panels[c].source is not None):
            self._draw_panel(cell)
        self._update_filename()
        self.canvas.draw()

    def _line_data(self, l):
        """(x, y, x labels, y labels) for a line: its columns through its function,
        background and smoothing. Raises LineError, with the text Line.error holds.

        Kept per line, so a data panel and its FFT panels do the work once."""
        cached = self.cache.get(id(l))
        if cached and cached[0] == (l.run, l.x, l.x_fn, l.y, l.y_fn, l.smoothing, l.fitting):
            return cached[1]
        stage = "Function"
        try:
            df = self._load(l)
            x, x_label = self._axis(df, l.x, l.x_fn)
            y, y_label = self._axis(df, l.y, l.y_fn)
            # Background first, so the fit sees the unsmoothed data and
            # smoothing then works on what's left.
            stage = "Background"
            if l.fitting:
                y = background.apply(x, y, *l.fitting)
            if l.background == "subtract":
                y_label = tuple(f"{t} − fit" for t in y_label)
            stage = "Smoothing"
            if l.smooth and l.in_x and l.span is None:
                l.span = smoothing.span_for(x, l.window)
            if l.smoothing:
                y = smoothing.smooth(x, y, *l.smoothing)
        except Exception as err:  # bad file or function shouldn't kill the window
            raise LineError(f"{stage} error: {err}" if l.run in self.frames else str(err))
        result = x, y, x_label, y_label
        self.cache[id(l)] = (l.run, l.x, l.x_fn, l.y, l.y_fn, l.smoothing, l.fitting), result
        return result

    def _draw_panel(self, cell):
        """Draw a panel's lines; problems are written into the panel itself.

        An FFT panel draws each line's spectrum. Its lines' own errors are the
        data panel's to report, so it leaves Line.shown and Line.error alone."""
        ax, p = self.axes[cell], self.panels[cell]
        fft = p.source is not None
        ax.clear()
        self.artists[cell] = {}
        drawn, x_labels, y_labels, errors, resolutions = [], [], [], [], []
        for i, (l, colour) in enumerate(zip(p.lines, line_colours(p, self.profile.samples))):
            if not fft:
                l.shown, l.error = None, ""
            if not l.run:
                continue
            try:
                x, y, x_label, y_label = self._line_data(l)
            except LineError as err:
                if not fft:
                    l.error = str(err)
                errors.append(str(err))
                continue
            if fft:
                if not l.shown:  # its data panel couldn't draw it
                    continue
                try:
                    frequency, amplitude = spectrum.spectrum(x, y, p.window, p.pad)
                except ValueError as err:
                    errors.append(f"FFT error: {err}")
                    continue
                if p.f_max:
                    below = frequency <= p.f_max
                    frequency, amplitude = frequency[below], amplitude[below]
                resolutions.append(spectrum.resolution(x[np.isfinite(y)]))
                x, y = frequency, amplitude
                unit, _ = lookup(self.profile.units, l.x)
                x_label = (spectrum.frequency_label(l.x_fn, unit),) * 2
                y_label = ("FFT amplitude  (units of y)",) * 2
            else:
                # What's on screen, so Save names the plot shown rather than
                # whatever is typed but not yet applied.
                l.shown = (l.run, l.x, l.x_fn, l.y, l.y_fn, l.smoothing, l.fitting)
            # A shown fit is dashed, so it reads as a fit laid over the data.
            fit_style = {"ls": "--", "lw": 1.0} if l.background == "fit" else {}
            (artist,) = ax.plot(x, y, **({"lw": 0.7, "color": colour} | fit_style))
            self.artists[cell][artist] = i
            drawn.append(l)
            x_labels.append(x_label)
            y_labels.append(y_label)

        if drawn:
            ax.set_xlabel(shared(x_labels))
            ax.set_ylabel(shared(y_labels))
            heading = title(dict.fromkeys(l.run for l in drawn))
            if fft:  # short, as FFT panels often sit beside or under their data
                heading = f"FFT of panel {self._number(p.source)}"
                if np.isfinite(resolutions[0]):  # the frequency resolution
                    heading += f" · ΔF {resolutions[0]:.3g}"
            ax.set_title(heading)
            ax.grid(True, lw=0.4, alpha=0.8)
            if len(drawn) > 1:
                for artist, text in zip(ax.lines, legend_labels(drawn)):
                    artist.set_label(text)
                ax.legend(fontsize=8)
            if fft and errors:  # some lines drawn, others not: say why
                ax.text(0.01, 0.99, errors[0], ha="left", va="top", transform=ax.transAxes,
                        color="#b3261e", fontsize=8)
        elif errors:
            self._hint(ax, errors[0], colour="#b3261e", size=9)
        elif fft:
            self._hint(ax, f"Nothing plotted in panel {self._number(p.source)}")
        else:
            self._hint(ax, "Pick a dataset" if self.data_dir else "Pick a data folder")
        self._frame(cell)
        self.toolbar.update()  # new data, so reset the toolbar's zoom history

    @staticmethod
    def _hint(ax, text, colour="#9a9992", size=14):
        """Empty axes with a message in the middle, e.g. 'Pick a dataset'."""
        ax.text(0.5, 0.5, text, ha="center", va="center", wrap=True,
                transform=ax.transAxes, color=colour, fontsize=size)
        ax.set_xticks([])
        ax.set_yticks([])

    def _frame(self, cell):
        """Orange frame on the selected panel, when there's more than one, and a
        paler one on the panels locked to it."""
        several = len(self.axes) > 1
        partners = self._linked(self.selected) if self.selected in self.panels else ()
        if several and cell == self.selected:
            colour, width = SELECTED, 2.5
        elif several and cell in partners:
            colour, width = PARTNER, 2.0
        else:
            colour, width = "black", 0.8
        for spine in self.axes[cell].spines.values():
            spine.set_edgecolor(colour)
            spine.set_linewidth(width)

    # --- panels and layout ------------------------------------------------

    def _on_click(self, event):
        """Select the clicked panel, and the line under the mouse if any."""
        if self.picker:  # the click starts a fit-range drag instead
            return
        cell = next((c for c, ax in self.axes.items() if ax is event.inaxes), None)
        if cell is None:
            return
        if self.fft_pick is not None:  # the click chooses where an FFT goes
            self._put_fft(self.fft_pick, cell)
            return
        old, self.selected = self.selected, cell
        hit = next((i for artist, i in self.artists[cell].items()
                    if artist.contains(event)[0]), None)
        if hit is not None:
            self._set_selected_line(cell, hit)
        elif cell == old:
            return  # clicked empty space in the panel already selected
        for c in self.axes:
            self._frame(c)
        self._load_controls()
        self.canvas.draw()

    def choose_layout(self):
        LayoutPicker(self, self.rows, self.cols, self.set_layout)

    def set_layout(self, rows, cols):
        """Resize the grid. Panels keep their cell; new cells copy the selected one."""
        template = self.panel
        self.panels = {
            (r, c): self.panels.get((r, c)) or template.copy()
            for r in range(rows) for c in range(cols)
        }
        for p in self.panels.values():
            if p.source is not None and p.source not in self.panels:
                self._unlink(p)  # its data panel is gone; keep what it showed
        if self.selected not in self.panels:
            self.selected = (0, 0)
        self.rows, self.cols = rows, cols
        self._build_axes()
        self._load_controls()

    def swap(self):
        """Swap X and Y, with their functions (x <-> y), for every line in the panel."""
        for l in self.panel.lines:
            l.x, l.y = l.y, l.x
            l.x_fn, l.y_fn = rename(l.y_fn.strip(), "y", "x"), rename(l.x_fn.strip(), "x", "y")
            l.span = l.fit_from = l.fit_to = None  # in the old x; meaningless now
        self._redraw_selected()

    # --- FFT panels -------------------------------------------------------

    def _number(self, cell):
        """A panel's number as the user sees it: 1, 2, ... across then down."""
        return cell[0] * self.cols + cell[1] + 1

    def _linked(self, cell):
        """`cell` and the panels locked to it: the data panel, then its FFT panels."""
        source = self.panels[cell].source or cell
        return [source] + [c for c, p in self.panels.items() if p.source == source]

    def _fft_source(self):
        """The selected panel, if it can have an FFT made of it."""
        if self.panel.source is not None:
            self._say("This panel is already an FFT; select its data panel.", error=True)
            return None
        return self.selected

    def _fft_of(self, source):
        """A new FFT panel locked to `source`: it shares the very same list of lines."""
        p = self.panels[source]
        return Panel(p.lines, p.selected, source=source)

    @staticmethod
    def _unlink(p):
        """Make an FFT panel an ordinary data panel with its own copies of the lines."""
        p.lines = [l.copy() for l in p.lines]
        p.source = None

    def fft_new_panel(self):
        """Add a row below the grid, with the selected panel's FFT under it."""
        self.stop_picking()
        source = self._fft_source()
        if source is None:
            return
        if self.rows >= MAX_GRID:
            self._say("The layout is full; use FFT to existing panel.", error=True)
            return
        row = self.rows
        for c in range(self.cols):
            self.panels[row, c] = Panel()
        self.panels[row, source[1]] = self._fft_of(source)
        self.rows += 1
        self.selected = (row, source[1])
        self._build_axes()
        self._load_controls()

    def fft_existing_panel(self):
        """Wait for a click on the panel the selected one's FFT should go in."""
        self.stop_picking()
        source = self._fft_source()
        if source is None:
            return
        if len(self.panels) == 1:
            self._say("There's only one panel; use FFT to new panel.", error=True)
            return
        self.fft_pick = source
        self._say("Click the panel to put the FFT in; Esc cancels.")

    def _put_fft(self, source, target):
        self.stop_picking()
        old = self.panels[target]
        if target == source:
            self._say("Click a different panel for the FFT.", error=True)
            return
        if old.source != source:
            dependents = [c for c, p in self.panels.items() if p.source == target]
            if (old.source is None and any(l.shown for l in old.lines)) or dependents:
                also = (", and the FFT panels made from it will be unlinked"
                        if dependents else "")
                if not messagebox.askyesno(
                        "Replace panel?",
                        f"Replace panel {self._number(target)}'s lines with the FFT of "
                        f"panel {self._number(source)}{also}?", parent=self):
                    return
            for c in dependents:
                self._unlink(self.panels[c])
            self.panels[target] = self._fft_of(source)
        self.selected = target
        self._build_axes()
        self._load_controls()

    def apply_fft(self):
        """Copy the FFT box into the selected FFT panel and redraw it."""
        p = self.panel
        if p.source is None:
            return
        p.window = next(k for k, v in spectrum.WINDOWS.items() if v == self.fft_window.get())
        p.pad = int(self.fft_pad.get())
        try:
            f_max = float(self.f_max.get()) if self.f_max.get().strip() else None
            p.f_max = f_max if f_max is None or f_max > 0 else None
        except ValueError:  # not a number: keep the old one (shown again below)
            pass
        self._redraw_selected()

    def unlink(self):
        """Make the selected FFT panel an ordinary panel with copies of the lines."""
        if self.panel.source is not None:
            self._unlink(self.panel)
            self._build_axes()
            self._load_controls()

    # --- fit range --------------------------------------------------------

    def pick_range(self):
        """Drag across the selected panel to set the selected line's fit range."""
        self.stop_picking()
        ax = self.axes[self.selected]
        if self.panel.source is not None:
            self._say("Pick the fit range on the data panel, not its FFT.", error=True)
            return
        if not self.panel.line.shown:
            self._say("Plot the line first, then pick its fit range.", error=True)
            return
        if self.toolbar.mode:
            self._say("Turn off the toolbar's zoom or pan first.", error=True)
            return
        self.picker = SpanSelector(ax, self._picked, "horizontal", useblit=True,
                                   props={"facecolor": SELECTED, "alpha": 0.3})
        self._say("Drag across the plot to set the fit range; Esc cancels.")

    def _picked(self, start, end):
        # After the selector has finished its own handling of the release,
        # which would otherwise paint its stale background over the redraw.
        self.after_idle(self._use_range, start, end)

    def _use_range(self, start, end):
        self.stop_picking()
        if start == end:  # a click, not a drag
            return
        # 5 significant figures: plenty for a fit range, and tidy in the boxes.
        self.fit_from.set(f"{start:.5g}")
        self.fit_to.set(f"{end:.5g}")
        self.apply_controls()
        if not self.panel.line.background:
            self._say("Range set; choose Show fit or Subtract to use it.")

    def stop_picking(self):
        """End a fit-range drag or an FFT panel pick, if one is under way."""
        if self.fft_pick is not None:
            self.fft_pick = None
            self._say("")
        if self.picker:
            self.picker.disconnect_events()
            self.picker.set_visible(False)  # its shaded span, if one was drawn
            self.picker = None
            self.canvas.draw_idle()
            self._say("")

    # --- colour -----------------------------------------------------------

    def _show_colour(self, move_picker=True):
        """Recolour the swatch and lines without a redraw, so zoom survives."""
        p = self.panel
        colours = line_colours(p, self.profile.samples)
        self.swatch["background"] = colours[p.selected]
        for i, colour in enumerate(colours):
            self.line_list.itemconfigure(i, foreground=colour, selectforeground=colour)
        for cell in self._linked(self.selected):  # locked panels share the lines
            for artist, i in self.artists.get(cell, {}).items():
                artist.set_color(colours[i])
            ax = self.axes.get(cell)
            if ax and ax.get_legend():  # the legend keeps its own copy of each colour
                for handle, artist in zip(ax.get_legend().legend_handles, ax.lines):
                    handle.set_color(artist.get_color())
        if self.colour_popup and self.colour_popup.winfo_exists():
            self.colour_popup.show(colours[p.selected], move_picker)
        # Draw now rather than on idle: while the mouse is dragging in the
        # picker, idle callbacks can be held off and the line never repaints.
        self.canvas.draw()

    def open_colour(self):
        if self.colour_popup and self.colour_popup.winfo_exists():
            self.colour_popup.lift()
        else:
            self.colour_popup = ColourPopup(self, self.pick_colour, self.reset_colour)
        self._show_colour()

    def pick_colour(self, colour):
        self.panel.line.colour = colour
        # The picker already shows it; moving it would round-trip through hex.
        self._show_colour(move_picker=False)

    def reset_colour(self):
        self.panel.line.colour = None
        self._show_colour()

    # --- status and saving ------------------------------------------------

    def _say(self, text, error=False):
        self.status.configure(text=text, foreground="#b3261e" if error else "#2e7d32")

    def _default_name(self):
        """The top-left panel's first line, e.g. run_005_M006_AH_vs_Norminal_FIeld.png."""
        first = self.panels[0, 0].lines[0]
        if not first.shown:
            return ""
        run, y, x, smoothed, fitted = first.parts()
        tail = f"_{background.file_part(*fitted)}" if fitted else ""
        tail += f"_{smoothing.file_part(*smoothed)}" if smoothed else ""
        tail += "_fft" if self.panels[0, 0].source else ""
        return f"{describe(run).replace(' ', '_')}_{y}_vs_{x}{tail}.png"

    def _update_filename(self):
        """Put the default name in the Save as box, unless the user typed one."""
        current = self.filename.get().strip()
        if not current or current == self.auto_name:
            self.auto_name = self._default_name()
            self.filename.set(self.auto_name)

    def save(self):
        if not any(l.shown for p in self.panels.values() for l in p.lines):
            self._say("Nothing plotted to save.", error=True)
            return
        if not self.settings.get("output_dir") and not self.choose_folder(
                "output_dir", "Output folder"):
            self._say("Choose an output folder to save into.", error=True)
            return
        out_dir = Path(self.settings["output_dir"])
        # Only a bare name: anything path-like would escape the output folder.
        name = self.filename.get().strip().replace("/", "_").replace("\\", "_")
        if not name:
            name = self.auto_name = self._default_name()
            self.filename.set(name)
        if "." not in name.lstrip("."):
            name += ".png"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            self._say(f"Can't use the output folder: {err}", error=True)
            return
        # The selection frame is for the screen, not the saved figure.
        selected, self.selected = self.selected, None
        for cell in self.axes:
            self._frame(cell)
        try:
            self.fig.savefig(out_dir / name, dpi=200)
        finally:
            self.selected = selected
            for cell in self.axes:
                self._frame(cell)
            self.canvas.draw()
        self._say(f"Saved {out_dir.name}/{name}")


if __name__ == "__main__":
    Plotter().mainloop()
