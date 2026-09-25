"""Interactive plotter window: pick datasets and axes, plot, save. See README.md."""

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
import numpy as np
from PIL import Image, ImageDraw, ImageTk

from goose_plotter.axis_functions import apply_function, is_identity, rename
from goose_plotter import background, derivative, session, smoothing, spectrum, theme
from goose_plotter.columns import label, lookup, with_unit, without_unit
from goose_plotter.model import (GRID_AXES, GRID_STYLES, GRIDS, LEGENDS, RANGES, SYNC, X_UNITS,
                               Panel, clear_ranges, legend_labels, line_colours, shared)
from goose_plotter.profile import load_profile, save_format
from goose_plotter.datasets import (FormatError, describe, detect_format, find_datasets,
                                  load_dataset, read_lines, run_number)
from goose_plotter.format_dialog import FormatDialog
from goose_plotter.settings import load_settings, save_settings
from goose_plotter.widgets import (MAX_GRID, SELECTED, AxesPopup, LayoutPicker, LineStylePopup,
                                 OverwriteDialog, SaveOptionsPopup, line_sample)

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


def text_problem(text):
    """Why matplotlib can't draw `text` (bad mathtext, e.g. '$B'), or ''.

    Found by drawing it on a scratch figure: on the real one the error would
    come from every later redraw instead."""
    fig = Figure()
    FigureCanvasAgg(fig)
    fig.text(0, 0, text)
    try:
        fig.canvas.draw()
    except Exception as err:  # ValueError from the mathtext parser, mostly
        return str(err).strip().splitlines()[0] if str(err).strip() else "can't be drawn"
    return ""


def swap_icon(colour=theme.MUTED):
    """A two-way arrow (up beside down) for the swap-axes button."""
    # Drawn, not typed: Tk's X core fonts can show arrow characters as '®'.
    image = Image.new("RGBA", (18, 22))
    draw = ImageDraw.Draw(image)
    draw.line((5, 5, 5, 20), fill=colour, width=2)
    draw.polygon(((0, 7), (5, 1), (10, 7)), fill=colour)
    draw.line((12, 1, 12, 16), fill=colour, width=2)
    draw.polygon(((7, 14), (12, 20), (17, 14)), fill=colour)
    return ImageTk.PhotoImage(image)


def axes_icon(colour=theme.MUTED):
    """A little plot (axes and a curve) for the button that opens the axes editor."""
    k = 4  # drawn large and shrunk, for smooth edges
    image = Image.new("RGBA", (18 * k, 22 * k))
    draw = ImageDraw.Draw(image)
    draw.line((2 * k, 3 * k, 2 * k, 19 * k, 17 * k, 19 * k), fill=colour, width=2 * k)
    curve = [(x * k, (16 - 11 * (x - 4) / 12 + 2.5 * np.sin(x / 1.6)) * k) for x in range(4, 17)]
    draw.line(curve, fill=colour, width=int(1.6 * k), joint="curve")
    return ImageTk.PhotoImage(image.resize((18, 22), Image.LANCZOS))


class Plotter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GOOSE Plotter")
        # The pixel goose; kept on self, as Tk drops an image nothing refers to.
        self.icon = tk.PhotoImage(file=Path(__file__).with_name("icon.png"))
        self.iconphoto(True, self.icon)
        theme.apply(self)  # before any widget is made or reads a style
        # Starts maximised. This is the size it returns to when un-maximised:
        # room for the controls with a section or two open, screen allowing.
        self.geometry(f"1150x{min(820, self.winfo_screenheight() - 80)}")
        try:
            self.state("zoomed")  # Windows and macOS
        except tk.TclError:
            self.attributes("-zoomed", True)  # Linux (X11)
        self.frames = {}  # dataset name -> DataFrame, so each file is read once
        self.datasets = {}  # dataset name -> file, from the data folder
        self.rows, self.cols = 1, 1
        self.panels = {(0, 0): Panel()}  # (row, col) -> Panel
        self.selected = (0, 0)
        self.axes = {}  # (row, col) -> matplotlib Axes
        self.artists = {}  # (row, col) -> {matplotlib Line2D: line index}
        # What each panel drew where its text is automatic, for the editors to show:
        # (row, col) -> {"title"/"x_label"/"y_label": text}, and -> {line index: legend name}.
        self.auto_text, self.auto_names = {}, {}
        self.style_popup = None
        self.axes_popup = None
        self.save_popup = None
        self.picker = None  # the SpanSelector while a fit range is being dragged
        self.derive_pick = None  # (source cell, operation) while the user clicks where it goes
        self.link_pick = None  # cell while the user clicks a panel to link its data to
        self.cache = {}  # _data_key -> (x, y and labels, span), see _line_data
        # One step of undo: the state before the last change, and after it.
        self.undo_state = self.last_state = None
        self.merging = False  # the last change was a colour pick; see _changed
        self.restoring = False
        self.status_timer = None  # the pending clear of an info message, see _say
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
        # The scrollbar's slot keeps its width whether it's showing or not, so
        # the plot doesn't shift when the column starts or stops scrolling.
        slot = ttk.Frame(side)
        slot.pack(side=tk.LEFT, fill=tk.Y)
        self.side_scroll = ttk.Scrollbar(slot, orient=tk.VERTICAL, command=self.side.yview,
                                         style="Side.Vertical.TScrollbar")
        slot.configure(width=self.side_scroll.winfo_reqwidth())
        slot.pack_propagate(False)
        self.side.configure(yscrollcommand=self.side_scroll.set)
        controls = ttk.Frame(self.side, padding=(10, 10, 10, 0))
        self.side.create_window(0, 0, window=controls, anchor=tk.NW)
        self.side_inner = controls
        controls.bind("<Configure>", self._fit_side)
        self.side.bind("<Configure>", self._fit_side)
        for sequence in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.bind_all(sequence, self._scroll_side, add="+")
        # Files: folders, format and sessions, set now and then, so a toggle at
        # the top; open at start only if a folder still needs choosing.
        files = self._collapsible(
            controls, (0, 0), lambda _: "Files",
            start_open=not (self.settings.get("data_dir") and self.settings.get("output_dir")))
        self.data_label = self._folder_row(files, "Data folder", "data_dir")
        self.output_label = self._folder_row(files, "Output folder", "output_dir")
        ttk.Button(files, text="Data format...", command=self.edit_format).pack(
            anchor=tk.W, pady=(0, 2))
        ttk.Label(files, text="Session").pack(anchor=tk.W, pady=(10, 2))
        buttons = ttk.Frame(files)
        buttons.pack(anchor=tk.W, pady=(0, 2))
        ttk.Button(buttons, text="Open session...", command=self.open_session).pack(
            side=tk.LEFT)
        ttk.Button(buttons, text="Save session...", command=self.save_session).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Separator(controls).pack(fill=tk.X, pady=(10, 8))
        # Labels beside their boxes, not above, to keep the column short.
        row = ttk.Frame(controls)
        row.pack(fill=tk.X)
        row.columnconfigure(1, weight=1)
        self.run = self._row_combo(row, 0, "Dataset", postcommand=self._refresh_runs)
        ttk.Label(controls, text="Lines").pack(anchor=tk.W, pady=(8, 2))
        lines = ttk.Frame(controls)
        lines.pack(anchor=tk.W, fill=tk.X)
        self.line_list = tk.Listbox(lines, height=4, width=24, exportselection=False,
                                    activestyle="none")
        self.line_list.pack(side=tk.LEFT)
        line_scroll = ttk.Scrollbar(lines, orient=tk.VERTICAL, command=self.line_list.yview)
        line_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.line_list["yscrollcommand"] = line_scroll.set
        self.line_list.bind("<<ListboxSelect>>", self._on_line_select)
        # Three boxes sharing the list's height equally: add, remove, and the
        # line's look (colour, style), which opens the line editor. The frame
        # doesn't grow to fit them; they shrink to fit it.
        line_buttons = ttk.Frame(lines, width=48)
        line_buttons.pack(side=tk.LEFT, padx=(6, 0), fill=tk.Y)
        line_buttons.grid_propagate(False)
        line_buttons.columnconfigure(0, weight=1)
        add = ttk.Button(line_buttons, text="+", style="Box.TButton", command=self.add_line)
        self.remove_button = ttk.Button(line_buttons, text="-", style="Box.TButton",
                                        command=self.remove_line)
        self.style_button = ttk.Button(line_buttons, style="Box.TButton",
                                       command=self.open_style)
        for i, box in enumerate((add, self.remove_button, self.style_button)):
            box.grid(row=2 * i, column=0, sticky="nsew")
            line_buttons.rowconfigure(2 * i, weight=1, uniform="box")
            if i:
                line_buttons.rowconfigure(2 * i - 1, minsize=4)  # the gap above it

        axes = ttk.Frame(controls)
        axes.pack(anchor=tk.W, fill=tk.X)
        axis_boxes = ttk.Frame(axes)
        axis_boxes.pack(side=tk.LEFT)
        # Narrower than Dataset, to leave room for the two buttons beside them.
        self.x = self._combo(axis_boxes, "X axis", [], width=21)
        self.x_fn = self._function_box(axis_boxes, "x")
        self.y = self._combo(axis_boxes, "Y axis", [], width=21)
        self.y_fn = self._function_box(axis_boxes, "y")
        # Beside the axis boxes: swap x and y, then the axes editor.
        axis_buttons = ttk.Frame(axes)
        axis_buttons.pack(side=tk.LEFT, padx=(6, 0))
        self.swap_icon, self.axes_icon = swap_icon(), axes_icon()
        ttk.Button(axis_buttons, image=self.swap_icon, command=self.swap).pack(
            side=tk.LEFT)
        ttk.Button(axis_buttons, image=self.axes_icon, command=self.open_axes).pack(
            side=tk.LEFT, padx=(4, 0))
        # Why the selected line isn't drawn; shown only when it isn't.
        self.error_label = ttk.Label(controls, foreground=theme.ERROR, wraplength=300)
        self.axes_block = axes

        # The rest is in tabs, one shown at a time, so the column stays short.
        # Not a ttk.Notebook: that is as tall as its tallest tab.
        ttk.Separator(controls).pack(fill=tk.X, pady=(10, 8))
        strip = ttk.Frame(controls)
        strip.pack(anchor=tk.W, fill=tk.X)
        self.tab = tk.StringVar()
        self.tabs = {}
        # Equal shares of the column's width.
        for i, name in enumerate(("Process", "Operations", "Linking")):
            strip.columnconfigure(i, weight=1, uniform="tab")
            ttk.Radiobutton(strip, text=name, value=name, variable=self.tab, width=1,
                            style="Tab.Toolbutton", command=self._show_tab).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 2, 0))
            self.tabs[name] = ttk.Frame(controls)
        # Smoothing's and FFT's toggles add the 10 px above them.
        self._smoothing_box(self.tabs["Process"])
        self._background_box(self.tabs["Process"])
        self._fft_box(self.tabs["Operations"])
        self._derivative_box(self.tabs["Operations"])
        self._link_box(self.tabs["Linking"])
        self.tab.set("Process")
        self._show_tab()
        self.bind("<Escape>", lambda _: self.stop_picking())
        self._bind_keys()

        # The bottom of the column, below the scrolling part: the status, the
        # name to save under, then the buttons in a square (panels above,
        # saving below), so they stay at the very bottom. Each row spans the column.
        self.status = ttk.Label(save, wraplength=300)
        self.status.pack(anchor=tk.W, pady=(6, 0))
        row = ttk.Frame(save)
        row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(row, text="Save as").pack(side=tk.LEFT, padx=(0, 6))
        self.filename = tk.StringVar()
        self.auto_name = ""  # last default name put in the box
        # Width 1: the box takes the column's width without widening it (a long
        # name scrolls in it).
        name_box = ttk.Entry(row, textvariable=self.filename, width=1)
        name_box.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        for key in ("<Return>", "<KP_Enter>"):
            name_box.bind(key, lambda _: self.save())
        buttons = ttk.Frame(save)
        buttons.pack(fill=tk.X, pady=(8, 0))
        buttons.columnconfigure((0, 1), weight=1, uniform="button")
        self.delete_button = ttk.Button(buttons, text="Delete panel", command=self.delete_panel)
        for i, button in enumerate((
                ttk.Button(buttons, text="Layout...", command=self.choose_layout),
                self.delete_button,
                ttk.Button(buttons, text="Options...", command=self.open_save_options),
                ttk.Button(buttons, text="Save figure", command=self.save))):
            row, col = divmod(i, 2)
            button.grid(row=row, column=col, sticky="ew", padx=(0, 3) if col == 0 else (3, 0),
                        pady=(6, 0) if row else 0)

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

    # --- keyboard ---------------------------------------------------------

    def _bind_keys(self):
        """Shortcuts for the main window (the dialogs are other toplevels, so
        these don't fire there). Keys a text box uses are left to it."""
        for key in ("s", "S"):  # S: with Caps Lock on
            self.bind(f"<Control-{key}>", lambda _: self.save())
        for key in ("d", "D"):
            self.bind(f"<Control-{key}>", lambda _: self.add_line())
        for key in ("z", "Z"):
            self.bind(f"<Control-{key}>", lambda _: self.undo())
        # Entries delete a character on Ctrl+D; here it copies the line instead.
        for cls in ("TEntry", "TSpinbox", "TCombobox"):
            for key in ("d", "D"):
                self.bind_class(cls, f"<Control-{key}>", lambda _: None)
        self.bind("<Delete>", lambda e: self._typing(e) or self.remove_line())
        # Up/Down step through lines; the Lines list and the boxes (a combobox
        # opens on Down) do their own thing with them.
        for key, step in (("<Up>", -1), ("<Down>", 1)):
            self.bind(key, lambda e, step=step: (
                isinstance(e.widget, (tk.Listbox, tk.Entry, ttk.Entry))
                or self._step_line(step)))
        for key, move in (("Left", (0, -1)), ("Right", (0, 1)), ("Up", (-1, 0)),
                          ("Down", (1, 0))):
            self.bind(f"<Control-{key}>", lambda e, move=move: (
                self._typing(e) or self._step_panel(*move)))

    @staticmethod
    def _typing(event):
        """Whether the key went to a box that can be typed in."""
        w = event.widget
        return isinstance(w, (tk.Entry, ttk.Entry)) and "readonly" not in str(w.cget("state"))

    def _step_line(self, step):
        at = self.panel.selected + step
        if 0 <= at < len(self.panel.lines):
            self._select_line(at)

    def _step_panel(self, dr, dc):
        """Select the panel beside the selected one, if there is one."""
        cell = (self.selected[0] + dr, self.selected[1] + dc)
        if cell in self.axes:
            self.stop_picking()
            self._select_panel(cell)

    def _select_panel(self, cell):
        self.selected = cell
        self.merging = False  # as in _select_line
        for c in self.axes:
            self._frame(c)
        self._load_controls()
        self.canvas.draw()

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

    def _show_tab(self):
        """Show the chosen tab's frame and hide the others."""
        for name, frame in self.tabs.items():
            if name == self.tab.get():
                frame.pack(anchor=tk.W, fill=tk.X, pady=(2, 0))
            else:
                frame.pack_forget()
        self.side.yview_moveto(0)

    def _show_error(self):
        """Show why the selected line isn't drawn, under the axes, if it isn't."""
        error = self.panel.line.error
        if error and self.panel.line.run not in self.frames:
            error = f"Could not load dataset: {error}"
        self.error_label["text"] = plain(error)
        if not error:
            self.error_label.pack_forget()
        elif not self.error_label.winfo_manager():
            self.error_label.pack(anchor=tk.W, fill=tk.X, pady=(8, 0), after=self.axes_block)

    def _scroll_side(self, event):
        """Mouse wheel over the controls scrolls them, when they're scrollable."""
        if not self.side_scroll.winfo_manager() or not str(event.widget).startswith(str(self.side)):
            return
        up = event.num == 4 or getattr(event, "delta", 0) > 0
        self.side.yview_scroll(-1 if up else 1, "units")

    def _combo(self, parent, label, values, default="", width=24, pady=(8, 2), **kwargs):
        ttk.Label(parent, text=label).pack(anchor=tk.W, pady=pady)
        var = tk.StringVar(value=default)
        box = ttk.Combobox(parent, textvariable=var, values=values,
                           state="readonly", width=width, **kwargs)
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
        label = ttk.Label(toggle, foreground=theme.MUTED)
        label.pack(side=tk.LEFT)
        body = ttk.Frame(parent)

        def refresh():
            is_open = bool(body.winfo_manager())
            arrow.delete("all")
            points = (1, 2, 9, 2, 5, 8) if is_open else (2, 1, 8, 5, 2, 9)
            arrow.create_polygon(points, fill=theme.MUTED, outline="")
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

    def _row_combo(self, parent, row, label, **kwargs):
        """'label [box]' on grid row `row` of `parent` (the box in column 1).

        Width 1: the box takes the room the column leaves it, never widening it."""
        ttk.Label(parent, text=label, width=7).grid(row=row, column=0, sticky=tk.W,
                                                   pady=(0, 3))
        var = tk.StringVar()
        box = ttk.Combobox(parent, textvariable=var, state="readonly", width=1, **kwargs)
        box.grid(row=row, column=1, sticky="ew", pady=(0, 3))
        box.bind("<<ComboboxSelected>>", lambda _: self.apply_controls())
        var.box = box
        return var

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
        ttk.Label(body, text=f"e.g. 1/{name}; Enter applies",
                  foreground=theme.HINT).pack(anchor=tk.W)
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

        body = self._collapsible(parent, (10, 0), text, start_open=True)
        # The method, and beside it for SG the order; then the window, and what
        # it's counted in (the menu says).
        top = ttk.Frame(body)
        top.pack(anchor=tk.W, pady=(2, 0))
        method = ttk.Combobox(top, textvariable=self.smooth, state="readonly", width=15,
                              values=list(smoothing.METHODS.values()))
        method.pack(side=tk.LEFT)
        method.bind("<<ComboboxSelected>>", lambda _: self.apply_controls())
        sizes = ttk.Frame(body)
        sizes.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(sizes, text="Window").pack(side=tk.LEFT)
        window = ttk.Spinbox(sizes, textvariable=self.window, from_=3, to=100001,
                             increment=2, width=6, command=self.apply_controls)
        window.pack(side=tk.LEFT, padx=(4, 4))
        unit = ttk.Combobox(sizes, textvariable=self.window_unit, state="readonly", width=7,
                            values=list(smoothing.UNITS.values()))
        unit.pack(side=tk.LEFT)
        unit.bind("<<ComboboxSelected>>", lambda _: self.apply_controls())
        orders = ttk.Frame(top)
        ttk.Label(orders, text="Order").pack(side=tk.LEFT)
        order = ttk.Spinbox(orders, textvariable=self.order, from_=0, to=10, width=2,
                            command=self.apply_controls)
        order.pack(side=tk.LEFT, padx=(4, 0))
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
                orders.pack(side=tk.LEFT, padx=(10, 0))
            else:
                orders.pack_forget()
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

        body = self._collapsible(parent, (10, 0), text, start_open=True)
        # The mode and the polynomial's degree; then the x range fitted (blank
        # ends: the whole line), typed or picked on the plot.
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(2, 0))
        mode = ttk.Combobox(row, textvariable=self.fit_mode, state="readonly", width=9,
                            values=list(background.MODES.values()))
        mode.pack(side=tk.LEFT)
        mode.bind("<<ComboboxSelected>>", lambda _: self.apply_controls())
        ttk.Label(row, text="Degree").pack(side=tk.LEFT, padx=(10, 0))
        degree = ttk.Spinbox(row, textvariable=self.degree, from_=0, to=30, width=3,
                             command=self.apply_controls)
        degree.pack(side=tk.LEFT, padx=(4, 0))
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(row, text="Fit x").pack(side=tk.LEFT)
        start = ttk.Entry(row, textvariable=self.fit_from, width=7)
        start.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(row, text="to").pack(side=tk.LEFT)
        end = ttk.Entry(row, textvariable=self.fit_to, width=7)
        end.pack(side=tk.LEFT, padx=(4, 6))
        ttk.Button(row, text="Pick", width=5, command=self.pick_range).pack(side=tk.LEFT)
        for box in (degree, start, end):
            for key in ("<Return>", "<KP_Enter>"):
                box.bind(key, lambda _: self.apply_controls())
        self.fit_mode.show = body.refresh

    def _fft_box(self, parent):
        """A collapsed 'FFT' toggle: make an FFT panel of this one, or set one up."""
        self.fft_window, self.fft_pad, self.f_max = tk.StringVar(), tk.StringVar(), tk.StringVar()

        def text(is_open):
            p = self.panel
            used = (f": of panel {self._number(p.source)}"
                    if p.source is not None and p.operation == "fft" and not is_open else "")
            return f"FFT{used}"

        body = self._collapsible(parent, (10, 0), text, start_open=True)
        # For a data panel: the two ways to make its FFT.
        make = ttk.Frame(body)
        self._make_buttons(make, lambda: "fft")
        ttk.Label(make, text="use 1/x on B for F in T", foreground=theme.HINT).pack(
            anchor=tk.W)
        # For an FFT panel: its settings.
        settings = ttk.Frame(body)
        source_label = ttk.Label(settings, foreground=theme.MUTED, wraplength=230)
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
        ttk.Label(row, text="blank: all", foreground=theme.HINT).pack(side=tk.LEFT)
        ttk.Button(settings, text="Back to data", command=self.back_to_data).pack(
            anchor=tk.W, pady=(6, 0))
        for box in (window, pad):
            box.bind("<<ComboboxSelected>>", lambda _: self.apply_fft())
        for key in ("<Return>", "<KP_Enter>"):
            f_max.bind(key, lambda _: self.apply_fft())

        # For a derivative panel: where to make an FFT instead.
        other = ttk.Label(body, foreground=theme.MUTED, wraplength=230)

        def refresh():
            body.refresh()
            p = self.panel
            shown = make if not p.derived else settings if p.operation == "fft" else other
            for frame in (make, settings, other):
                if frame is not shown:
                    frame.pack_forget()
            shown.pack(anchor=tk.W, fill=tk.X, pady=(2, 0) if shown is other else 0)
            if shown is make:
                return
            if shown is other:
                other["text"] = f"Select {self._data_panel_name(p)} to make its FFT."
                return
            source_label["text"] = f"FFT of {self._derived_from(p)}"
            self.fft_window.set(spectrum.WINDOWS[p.window])
            self.fft_pad.set(str(p.pad))
            self.f_max.set("" if p.f_max is None else f"{p.f_max:g}")
        self.fft_window.show = refresh

    def _make_buttons(self, parent, operation):
        """'New panel' and 'Existing panel...' on a row, making the derived panel
        `operation()` names; the section's toggle says which it is."""
        row = ttk.Frame(parent)
        row.pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(row, text="New panel",
                   command=lambda: self.new_derived_panel(operation())).pack(side=tk.LEFT)
        ttk.Button(row, text="Existing panel...",
                   command=lambda: self.existing_derived_panel(operation())).pack(
            side=tk.LEFT, padx=(6, 0))

    def _derivative_box(self, parent):
        """A 'Derivative' toggle: make a derivative panel of this one, or set one up."""
        self.derivative_order = tk.StringVar(value="d1")  # also the new panel's, for a data panel
        self.derivative_window = tk.StringVar()

        def text(is_open):
            p = self.panel
            used = (f": {derivative.ORDERS[p.operation].lower()} of panel {self._number(p.source)}"
                    if p.source is not None and p.derived and p.operation != "fft"
                    and not is_open else "")
            return f"Derivative{used}"

        body = self._collapsible(parent, (10, 0), text, start_open=True)
        # The order: which derivative to make, or which this derivative panel shows.
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(row, text="Order").pack(side=tk.LEFT, padx=(0, 6))
        orders = []
        for key, name in derivative.ORDERS.items():
            button = ttk.Radiobutton(row, text=name, variable=self.derivative_order, value=key,
                                     style="Toolbutton", command=self.apply_derivative)
            button.pack(side=tk.LEFT, padx=(0, 4))
            orders.append(button)
        # For a data panel: the two ways to make its derivative.
        make = ttk.Frame(body)
        self._make_buttons(make, self.derivative_order.get)
        # For a derivative panel: its settings.
        settings = ttk.Frame(body)
        source_label = ttk.Label(settings, foreground=theme.MUTED, wraplength=230)
        source_label.pack(anchor=tk.W, pady=(4, 0))
        row = ttk.Frame(settings)
        row.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(row, text="Window").pack(side=tk.LEFT)
        window = ttk.Spinbox(row, textvariable=self.derivative_window, from_=5, to=100001,
                             increment=2, width=6, command=self.apply_derivative)
        window.pack(side=tk.LEFT, padx=(4, 6))
        ttk.Label(row, text="points, odd", foreground=theme.HINT).pack(side=tk.LEFT)
        ttk.Label(settings, text="wider for less noise; 2nd needs more",
                  foreground=theme.HINT).pack(anchor=tk.W)
        ttk.Button(settings, text="Back to data", command=self.back_to_data).pack(
            anchor=tk.W, pady=(6, 0))
        for key in ("<Return>", "<KP_Enter>"):
            window.bind(key, lambda _: self.apply_derivative())
        # For an FFT panel: where to make a derivative instead.
        other = ttk.Label(body, foreground=theme.MUTED, wraplength=230)

        def refresh():
            body.refresh()
            p = self.panel
            derived = p.derived
            shown = make if not derived else other if p.operation == "fft" else settings
            for frame in (make, settings, other):
                if frame is not shown:
                    frame.pack_forget()
            shown.pack(anchor=tk.W, fill=tk.X, pady=(2, 0) if shown is other else 0)
            for button in orders:  # an FFT panel has no order to choose
                button.state(["disabled" if shown is other else "!disabled"])
            if shown is other:
                other["text"] = f"Select {self._data_panel_name(p)} to make its derivative."
            elif derived:
                self.derivative_order.set(p.operation)
                source_label["text"] = (f"{derivative.ORDERS[p.operation]} derivative of "
                                        f"{self._derived_from(p)}")
                self.derivative_window.set(p.derivative_window)
        self.derivative_order.show = refresh

    def _link_box(self, parent):
        """Linked data: panels that plot the same data. No toggle, as it has
        the Linking tab to itself."""
        body = ttk.Frame(parent)
        body.pack(anchor=tk.W, fill=tk.X, pady=(8, 0))
        status = ttk.Label(body, foreground=theme.MUTED, wraplength=230)
        status.pack(anchor=tk.W, pady=(2, 0))
        # Link, unlink and freeze (pause syncing, keeping the link), on a row.
        row = ttk.Frame(body)
        row.pack(fill=tk.X, pady=(4, 0))
        row.columnconfigure((0, 1, 2), weight=1, uniform="link")
        ttk.Button(row, text="Link...", width=1, command=self.link_panels).grid(
            row=0, column=0, sticky="ew")
        unlink = ttk.Button(row, text="Unlink", width=1, command=self.unlink_panel)
        unlink.grid(row=0, column=1, sticky="ew", padx=6)
        freeze = ttk.Button(row, width=1, command=self.freeze)
        freeze.grid(row=0, column=2, sticky="ew")
        # What this panel shares with the group, in pairs: x beside y, and so on.
        ttk.Label(body, text="Sync").pack(anchor=tk.W, pady=(12, 2))
        boxes = ttk.Frame(body)
        boxes.pack(anchor=tk.W, fill=tk.X)
        self.sync_vars = {}
        names = {"run": "Dataset", "x": "X axis", "x_fn": "X function", "y": "Y axis",
                 "y_fn": "Y function", "colour": "Colour", "smoothing": "Smoothing",
                 "background": "Background", "style": "Line style"}
        places = {"run": (0, 0), "colour": (0, 1), "x": (1, 0), "y": (1, 1), "x_fn": (2, 0),
                  "y_fn": (2, 1), "smoothing": (3, 0), "background": (3, 1), "style": (4, 0)}
        for key in SYNC:
            var = self.sync_vars[key] = tk.BooleanVar()
            row, col = places[key]
            ttk.Checkbutton(boxes, text=names[key], variable=var,
                            command=lambda key=key: self.set_sync(key)).grid(
                row=row, column=col, sticky=tk.W, padx=(0, 16), pady=1)
        ttk.Label(body, text="syncs between panels that both tick it",
                  foreground=theme.HINT).pack(anchor=tk.W, pady=(2, 0))

        def refresh():
            others = self._link_partners(self.selected)
            frozen = self.panels[self.selected].frozen
            status["text"] = (f"Linked to panel{'s' if len(others) > 1 else ''} "
                              f"{self._numbers(others)}{', frozen' if frozen else ''}"
                              if others else "Not linked")
            unlink.state(["!disabled" if others else "disabled"])
            freeze["text"] = "Unfreeze" if frozen else "Freeze"
            freeze.state(["!disabled" if others else "disabled"])
            synced = self.panels[self.selected].synced
            for key, var in self.sync_vars.items():
                var.set(key in synced)
        self.link_status = refresh

    def _folder_row(self, parent, label, key):
        """'Data folder' etc.: the chosen path, with Browse... to change it."""
        ttk.Label(parent, text=label).pack(anchor=tk.W, pady=(0, 2))
        row = ttk.Frame(parent)
        row.pack(anchor=tk.W, fill=tk.X, pady=(0, 6))
        ttk.Button(row, text="Browse...",
                   command=lambda: self.choose_folder(key, label)).pack(side=tk.RIGHT)
        # Width 1: the name takes whatever the rest of the column leaves, so the
        # row never widens the column (a long name is cut off).
        path = ttk.Label(row, width=1, anchor=tk.W)
        path.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._show_folder(path, key)
        return path

    def _show_folder(self, widget, key):
        """Show the folder's name (the full path is too long for the column)."""
        folder = self.settings.get(key)
        widget["text"] = Path(folder).name or folder if folder else "(not set)"
        widget["foreground"] = theme.MUTED if folder else theme.ERROR

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
        error = self._read_folder()
        self._build_axes()
        self._load_controls()
        self._say(error, error=True)

    def _read_folder(self):
        """Forget what was read from the old data folder and read the new one's
        profile and file list. Returns the profile's error, if any."""
        self.profile, error = load_profile(self.data_dir)
        self.frames.clear()
        self.cache.clear()
        self._refresh_runs()
        return error

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
        self._show_axes()
        self.fft_window.show()
        self.derivative_order.show()
        self.link_status()
        self.delete_button.state(["!disabled" if len(self.panels) > 1 else "disabled"])
        self._say("")
        self._show_error()
        self._show_colour()

    def _fill_line_list(self):
        p, colours = self.panel, line_colours(self.panel, self.profile.samples)
        self.line_list.delete(0, tk.END)
        for l, colour in zip(p.lines, colours):
            name = f"{l.y} · {run_number(l.run) or l.run}" if l.run else "(no dataset)"
            if l.label:
                name = f"{plain(l.label)} · {name}"
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
        old_y = (l.y, l.y_fn, l.background == "subtract")
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
            self._clear_ranges(self.panel.lines, "x")
        if (l.y, l.y_fn, l.background == "subtract") != old_y:
            self._clear_ranges(self.panel.lines, "y")
        self._sync_inputs(self.selected)
        if l.run in self.datasets and l.run not in self.frames:
            try:
                self._load(l)
            except FormatError as err:  # ask how the file is laid out
                self.edit_format(l.run, f"Couldn't read {l.run}: {err}")
                if l.run not in self.frames:  # still unreadable; don't ask again
                    self._redraw_selected()
                    return
            except Exception:  # anything else is reported by the redraw below
                pass
        # Same axes: keep the zoom, as smoothing and fits are often tuned zoomed
        # in. A background change moves y by orders of magnitude, so only x.
        keep, others = "", ""
        if before and before[:5] == (l.run, l.x, l.x_fn, l.y, l.y_fn):
            keep = "xy" if before[6] == l.fitting else "x"
            if self.panel.derived:  # any change reshapes a spectrum or derivative
                keep = "x"
            others = "x"  # the other panels redrawn plot the same data as before
        self._redraw_selected(keep, others)

    def _redraw_selected(self, keep="", others="x", merge=False):
        """Redraw the selected panel and those tied to it (its derived or data panel,
        and panels linked to it), keeping the selected one's x and/or y limits
        if `keep` says and the others' if `others` does."""
        views = {}
        for cell in self._tied(self.selected):
            ax = self.axes[cell]
            wanted = keep if cell == self.selected else others
            # Only limits the user set (zooming turns autoscaling off); a view
            # that was just fitted to the old data should refit to the new.
            wanted = "".join(a for a in wanted if not getattr(ax, f"get_autoscale{a}_on")())
            views[cell] = wanted, ax.get_xlim(), ax.get_ylim()
        for cell in views:  # data panels first: the derived panels use what they draw
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
        self._changed(merge)

    # --- lines ------------------------------------------------------------

    def _select_line(self, index):
        self.stop_picking()
        self.merging = False  # a colour picked for another line is another step
        self._set_selected_line(self.selected, index)
        self._load_controls()

    def _set_selected_line(self, cell, index):
        """Select line `index` in `cell` and the panels tied to it."""
        for c in self._tied(cell):
            self.panels[c].selected = index

    def _on_line_select(self, _):
        chosen = self.line_list.curselection()
        if chosen and chosen[0] != self.panel.selected:
            self._select_line(chosen[0])

    def add_line(self):
        """Add a copy of the selected line; it takes the next free colour.

        Linked panels get one too, each a copy of its own line there, so it
        keeps that panel's smoothing, background and so on."""
        at = self.panel.selected + 1
        for lines in self._group_lists(self.selected):
            new = lines[at - 1].copy()
            new.colour, new.label = None, None  # its own colour and name
            lines.insert(at, new)
        self._set_selected_line(self.selected, at)
        self._redraw_selected()

    def remove_line(self):
        """Remove the selected line, here and in linked panels."""
        p = self.panel
        if len(p.lines) > 1:
            at = p.selected
            for lines in self._group_lists(self.selected):
                del lines[at]
            self._set_selected_line(self.selected, min(at, len(p.lines) - 1))
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
        self._tidy_link_groups()
        for cell in self.axes:
            self._draw_panel(cell)
        self._update_filename()
        self.canvas.draw()
        self._changed()

    def _line_data(self, l):
        """(x, y, x labels, y labels) for a line: its columns through its function,
        background and smoothing. Raises LineError, with the text Line.error holds.

        Kept by settings, so linked panels (a data panel and its FFT, say) with
        the same line do the work once."""
        cached = self.cache.get(self._data_key(l))
        if cached:
            result, span = cached
            if l.smooth and l.in_x and l.span is None:
                l.span = span  # as working it out would have set it
            return result
        key = self._data_key(l)  # before a missing span is filled in below
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
        self.cache[key] = self.cache[self._data_key(l)] = result, l.span
        return result

    @staticmethod
    def _data_key(l):
        """What a line's data depends on: its settings through smoothing."""
        return l.run, l.x, l.x_fn, l.y, l.y_fn, l.smoothing, l.fitting

    def _prune_cache(self):
        """Keep only the data of lines still in the panels."""
        wanted = {self._data_key(l) for p in self.panels.values() for l in p.lines}
        for key in [k for k in self.cache if k not in wanted]:
            del self.cache[key]

    def _draw_panel(self, cell):
        """Draw a panel's lines; problems are written into the panel itself.

        A derived panel draws each line's spectrum or derivative."""
        ax, p = self.axes[cell], self.panels[cell]
        derived, fft = p.derived, p.operation == "fft"
        ax.clear()
        self.artists[cell] = {}
        drawn, indices, x_labels, y_labels, errors, resolutions = [], [], [], [], [], []
        self.auto_text[cell], self.auto_names[cell] = {}, {}
        for i, (l, colour) in enumerate(zip(p.lines, line_colours(p, self.profile.samples))):
            l.shown, l.error = None, ""
            if not l.run:
                continue
            try:
                x, y, x_label, y_label = self._line_data(l)
            except LineError as err:
                l.error = str(err)
                errors.append(l.error)
                continue
            if fft:
                try:
                    frequency, amplitude = spectrum.spectrum(x, y, p.window, p.pad)
                except ValueError as err:
                    l.error = f"FFT error: {err}"
                    errors.append(l.error)
                    continue
                if p.f_max:
                    below = frequency <= p.f_max
                    frequency, amplitude = frequency[below], amplitude[below]
                resolutions.append(spectrum.resolution(x[np.isfinite(y)]))
                x, y = frequency, amplitude
                unit, _ = lookup(self.profile.units, l.x)
                x_label = (spectrum.frequency_label(l.x_fn, unit),) * 2
                y_label = ("FFT amplitude  (units of y)",) * 2
            elif derived:
                try:
                    x, y = derivative.derivative(x, y, int(p.operation[1]), p.derivative_window)
                except ValueError as err:
                    l.error = f"Derivative error: {err}"
                    errors.append(l.error)
                    continue
                y_label = (derivative.LABELS[p.operation],) * 2
            # What's on screen, so Save names the plot shown rather than
            # whatever is typed but not yet applied.
            l.shown = (l.run, l.x, l.x_fn, l.y, l.y_fn, l.smoothing, l.fitting)
            (artist,) = ax.plot(x, y, color=colour, **l.plot_style())
            self.artists[cell][artist] = i
            drawn.append(l)
            indices.append(i)
            x_labels.append(x_label)
            y_labels.append(y_label)

        if drawn:
            heading = title(dict.fromkeys(l.run for l in drawn))
            if derived:  # short, as these often sit beside or under their data
                heading = "FFT" if fft else derivative.HEADINGS[p.operation]
                if p.source is not None:
                    heading += f" of panel {self._number(p.source)}"
            if fft and np.isfinite(resolutions[0]):  # the frequency resolution
                heading += f" · ΔF {resolutions[0]:.3g}"
            auto = self.auto_text[cell] = {"title": heading, "x_label": shared(x_labels),
                                           "y_label": shared(y_labels)}
            self.auto_names[cell] = dict(zip(indices, legend_labels(drawn)))
            ax.set_title(auto["title"] if p.title is None else p.title)
            ax.set_xlabel(auto["x_label"] if p.x_label is None else p.x_label)
            ax.set_ylabel(auto["y_label"] if p.y_label is None else p.y_label)
            if p.grid != "off":
                if p.grid == "minor":  # fainter, between the major lines
                    for axis in ("x", "y") if p.grid_axis == "both" else (p.grid_axis,):
                        getattr(ax, f"{axis}axis").minorticks_on()  # only where there's grid
                    ax.grid(True, which="minor", axis=p.grid_axis, ls=p.grid_style,
                            lw=0.3, alpha=0.4)
                ax.grid(True, which="major", axis=p.grid_axis, ls=p.grid_style,
                        lw=0.4, alpha=0.8)
            if self.settings.get("ticks_in") is True:  # a preference for every panel
                ax.tick_params(which="both", direction="in")
            if p.legend != "off" and (p.legend != "auto" or len(drawn) > 1):
                for artist, l, i in zip(ax.lines, drawn, indices):  # "": left out
                    artist.set_label(self.auto_names[cell][i] if l.label is None else l.label)
                if p.legend == "outside":  # constrained layout makes room for it
                    ax.legend(fontsize=8, loc="center left", bbox_to_anchor=(1.02, 0.5))
                else:
                    ax.legend(fontsize=8, loc="best" if p.legend == "auto" else p.legend)
            # Typed ranges; an end left blank stays where autoscaling put it.
            if p.x_min is not None or p.x_max is not None:
                ax.set_xlim(p.x_min, p.x_max)
            if p.y_min is not None or p.y_max is not None:
                ax.set_ylim(p.y_min, p.y_max)
            if derived and errors:  # some lines drawn, others not: say why
                ax.text(0.01, 0.99, errors[0], ha="left", va="top", transform=ax.transAxes,
                        color=theme.ERROR, fontsize=8)
        elif errors:
            self._hint(ax, errors[0], colour=theme.ERROR, size=9)
        else:
            self._hint(ax, "Pick a dataset" if self.data_dir else "Pick a data folder")
        self._frame(cell)
        self.toolbar.update()  # new data, so reset the toolbar's zoom history

    @staticmethod
    def _hint(ax, text, colour=theme.HINT, size=14):
        """Empty axes with a message in the middle, e.g. 'Pick a dataset'."""
        ax.text(0.5, 0.5, text, ha="center", va="center", wrap=True,
                transform=ax.transAxes, color=colour, fontsize=size)
        # No ticks rather than hidden ones: clearing the axes brings ticks back,
        # but tick_params settings survive it and would hide them for good.
        ax.set_xticks([])
        ax.set_yticks([])

    def _frame(self, cell):
        """Orange frame on the selected panel, when there's more than one, and a
        paler dashed one on the panels linked to it (its FFTs and derivatives too)."""
        several = len(self.axes) > 1
        if several and cell == self.selected:
            colour, width = SELECTED, 2.5
        else:
            colour, width = "black", 0.8
        # Dashed: linked to the selected panel.
        dashed = (colour == "black" and self.selected in self.panels
                  and cell in self._link_partners(self.selected))
        if dashed:
            colour, width = PARTNER, 2.0
        for spine in self.axes[cell].spines.values():
            spine.set_edgecolor(colour)
            spine.set_linewidth(width)
            spine.set_linestyle((0, (4, 2)) if dashed else "-")

    # --- panels and layout ------------------------------------------------

    def _on_click(self, event):
        """Select the clicked panel, and the line under the mouse if any."""
        if self.picker:  # the click starts a fit-range drag instead
            return
        # Out of any box, so the shortcuts for lines and panels work next.
        self.canvas.get_tk_widget().focus_set()
        cell = next((c for c, ax in self.axes.items() if ax is event.inaxes), None)
        if cell is None:
            return
        if self.derive_pick is not None:  # the click chooses where it goes
            source, operation = self.derive_pick
            self._put_derived(source, cell, operation)
            return
        if self.link_pick is not None:  # the click chooses whose data to link to
            self._link(self.link_pick, cell)
            return
        hit = next((i for artist, i in self.artists[cell].items()
                    if artist.contains(event)[0]), None)
        if hit is not None:
            self._set_selected_line(cell, hit)
        elif cell == self.selected:
            return  # clicked empty space in the panel already selected
        self._select_panel(cell)

    def choose_layout(self):
        LayoutPicker(self, self.rows, self.cols, self.set_layout)

    def set_layout(self, rows, cols):
        """Resize the grid. Panels keep their cell; new cells copy the selected one."""
        template = self.panel
        self.panels = {
            (r, c): self.panels.get((r, c)) or template.copy()
            for r in range(rows) for c in range(cols)
        }
        # A derived panel whose data panel is gone keeps its lines and what it
        # shows; _build_axes forgets that source.
        if self.selected not in self.panels:
            self.selected = (0, 0)
        self.rows, self.cols = rows, cols
        self._build_axes()
        self._load_controls()

    def delete_panel(self):
        """Delete the selected panel. The panels after it, in reading order, move
        back one place; the grid loses the row or column that leaves empty, if
        one does, or else keeps an empty panel in its last cell."""
        self.stop_picking()
        if len(self.panels) == 1:
            return
        order = sorted(self.panels)  # reading order
        gone, number = self.selected, self._number(self.selected)
        kept = [c for c in order if c != gone]
        moved = dict(zip(kept, order))  # old cell -> new cell
        panels = {moved[c]: self.panels[c] for c in kept}
        for p in panels.values():  # a panel derived from the deleted one keeps its lines
            if p.source is not None:
                p.source = moved.get(p.source)
        if self.cols == 1:
            self.rows -= 1
        elif self.rows == 1:
            self.cols -= 1
        else:
            panels[order[-1]] = Panel()
        self.panels = panels
        # The panel that took its place, or the new last one.
        self.selected = order[min(order.index(gone), len(kept) - 1)]
        self._build_axes()
        self._load_controls()
        self._say(f"Deleted panel {number}; Ctrl+Z brings it back.")

    def swap(self):
        """Swap X and Y, with their functions (x <-> y), for every line in the panel."""
        p = self.panel
        if p.derived:  # a spectrum or derivative of the other axis: nothing like the old one
            clear_ranges(p)
        else:  # its ranges swap with its axes; linked panels' clear as their x and y change
            p.x_min, p.x_max, p.y_min, p.y_max = p.y_min, p.y_max, p.x_min, p.x_max
            p.x_label, p.y_label = p.y_label, p.x_label
        for l in p.lines:
            l.x, l.y = l.y, l.x
            l.x_fn, l.y_fn = rename(l.y_fn.strip(), "y", "x"), rename(l.x_fn.strip(), "x", "y")
            l.span = l.fit_from = l.fit_to = None  # in the old x; meaningless now
        self._sync_inputs(self.selected)
        self._redraw_selected(others="")

    # --- derived panels: FFTs and derivatives -----------------------------

    def _number(self, cell):
        """A panel's number as the user sees it: 1, 2, ... across then down."""
        return cell[0] * self.cols + cell[1] + 1

    def _derived_from(self, p):
        """'panel 1, linked to it' for a derived panel, or what it is without one."""
        if p.source is None:
            return "its own lines; it no longer follows a panel."
        return f"panel {self._number(p.source)}, linked to it (see Linking)."

    def _data_panel_name(self, p):
        return f"panel {self._number(p.source)}" if p.source is not None else "a data panel"

    @staticmethod
    def _kind(operation):
        """'FFT', 'first derivative' or 'second derivative', for messages."""
        return "FFT" if operation == "fft" else f"{derivative.ORDERS[operation].lower()} derivative"

    def _derive_source(self, operation):
        """The selected panel, if it can have a derived panel made of it."""
        if self.panel.derived:
            self._say(f"This panel is already {'an' if self.panel.operation == 'fft' else 'a'} "
                      f"{self._kind(self.panel.operation)}; select its data panel "
                      f"to make its {self._kind(operation)}.", error=True)
            return None
        return self.selected

    def _derived(self, source, operation):
        """A new derived panel of `source`: copies of its lines, in its link group
        (starting one if it has none), sharing everything with it so it follows
        every change, as a Sync tick list the user can then trim or Freeze."""
        p = self.panels[source]
        if p.link_group is None:
            p.link_group = max((q.link_group or 0 for q in self.panels.values()), default=0) + 1
        everything = " ".join(SYNC)
        p.sync = everything
        return Panel([l.copy() for l in p.lines], p.selected, source=source,
                     operation=operation, link_group=p.link_group, sync=everything)

    def new_derived_panel(self, operation):
        """Add a row below the grid, with the selected panel's FFT or derivative under it."""
        self.stop_picking()
        source = self._derive_source(operation)
        if source is None:
            return
        if self.rows >= MAX_GRID:
            self._say("The layout is full; put it in an existing panel.", error=True)
            return
        row = self.rows
        for c in range(self.cols):
            self.panels[row, c] = Panel()
        self.panels[row, source[1]] = self._derived(source, operation)
        self.rows += 1
        self.selected = (row, source[1])
        self._build_axes()
        self._load_controls()

    def existing_derived_panel(self, operation):
        """Wait for a click on the panel the selected one's FFT or derivative should go in."""
        self.stop_picking()
        source = self._derive_source(operation)
        if source is None:
            return
        if len(self.panels) == 1:
            self._say("There's only one panel; put it in a new panel.", error=True)
            return
        self.derive_pick = source, operation
        self._say(f"Click the panel to put the {self._kind(operation)} in; Esc cancels.")

    def _put_derived(self, source, target, operation):
        self.stop_picking()
        old = self.panels[target]
        if target == source:
            self._say(f"Click a different panel for the {self._kind(operation)}.", error=True)
            return
        if old.derived and old.source == source:  # derived from it: change what it shows
            if old.operation != operation:
                clear_ranges(old)  # in the old operation's units
                old.title = old.x_label = old.y_label = None
                old.operation = operation
        else:
            dependents = [c for c, p in self.panels.items() if p.source == target]
            if (not old.derived and any(l.shown for l in old.lines)) or dependents:
                also = (", and the panels derived from it will stop following it"
                        if dependents else "")
                if not messagebox.askyesno(
                        "Replace panel?",
                        f"Replace panel {self._number(target)}'s lines with the "
                        f"{self._kind(operation)} of panel {self._number(source)}{also}?",
                        parent=self):
                    return
            for c in dependents:  # derived from what's replaced: they keep their lines
                self.panels[c].source = None
            self.panels[target] = self._derived(source, operation)
        self.selected = target
        self._build_axes()
        self._load_controls()

    def apply_fft(self):
        """Copy the FFT box into the selected FFT panel and redraw it."""
        p = self.panel
        if p.operation != "fft":
            return
        p.window = next(k for k, v in spectrum.WINDOWS.items() if v == self.fft_window.get())
        p.pad = int(self.fft_pad.get())
        try:
            f_max = float(self.f_max.get()) if self.f_max.get().strip() else None
            p.f_max = f_max if f_max is None or f_max > 0 else None
        except ValueError:  # not a number: keep the old one (shown again below)
            pass
        self._redraw_selected()

    def apply_derivative(self):
        """Copy the Derivative box into the selected derivative panel and redraw it.
        On a data panel the order only sets which derivative the buttons make."""
        p = self.panel
        if not p.derived or p.operation == "fft":
            return
        if self.derivative_order.get() != p.operation:
            clear_ranges(p, "y")  # dy/dx and d2y/dx2 are in different units
            p.operation = self.derivative_order.get()
        try:
            window = int(self.derivative_window.get())
            p.derivative_window = window if window > 0 else p.derivative_window
        except ValueError:  # not a number: keep the old one (shown again below)
            pass
        self._redraw_selected(keep="x")

    def back_to_data(self):
        """Make the selected derived panel plot its lines themselves. It stays in
        its link group, as a linked data panel."""
        p = self.panel
        if p.derived:
            p.operation, p.source = "", None
            clear_ranges(p)  # in frequency or dy/dx; it's back to plotting the data
            p.title = p.x_label = p.y_label = None
            self._build_axes()
            self._load_controls()

    # --- axes -------------------------------------------------------------

    def _show_axes(self):
        if self.axes_popup and self.axes_popup.winfo_exists():
            auto = {k: plain(v) for k, v in self.auto_text.get(self.selected, {}).items()}
            self.axes_popup.show(self.panel, self._number(self.selected), auto)

    def open_axes(self):
        """The axes editor for the selected panel: ranges, text and legend."""
        if self.axes_popup and self.axes_popup.winfo_exists():
            self.axes_popup.lift()
        else:
            self.axes_popup = AxesPopup(self, self.apply_axes, self.use_view,
                                        self.settings.get("ticks_in") is True, self.set_ticks_in,
                                        self.auto_axis_text)
            self._undo_keys(self.axes_popup)
        self._show_axes()

    def apply_axes(self):
        """Copy the axes editor into the selected panel and redraw it."""
        self.stop_picking()
        if not (self.axes_popup and self.axes_popup.winfo_exists()):
            return
        p = self.panel
        typed, chosen = self.axes_popup.values()
        for name in RANGES:
            try:
                value = float(typed[name]) if typed[name].strip() else None
            except ValueError:  # not a number: keep the old one (shown again below)
                continue
            if value is None or np.isfinite(value):  # inf or nan would break drawing
                setattr(p, name, value)
        problem = ""
        auto = self.auto_text.get(self.selected, {})
        for name, _ in AxesPopup.TEXTS:
            text = typed[name].strip()
            if getattr(p, name) is None and text == plain(auto.get(name, "")):
                continue  # still the automatic text, as shown: keep it automatic
            why = text_problem(text) if text else ""
            if why:  # keep the old text (shown again below)
                problem = f"Can't draw that {name.replace('_', ' ')}: {plain(why)}"
            else:
                setattr(p, name, text)
        for name, keys in (("legend", LEGENDS), ("grid", GRIDS), ("grid_axis", GRID_AXES),
                           ("grid_style", GRID_STYLES)):
            if chosen[name] in keys:
                setattr(p, name, chosen[name])
        for axis in "xy":
            low, high = getattr(p, f"{axis}_min"), getattr(p, f"{axis}_max")
            if low is not None and high is not None and low == high:
                problem = f"The {axis} range needs two different ends."
                setattr(p, f"{axis}_max", None)
        # Not the old view: that would put back the range just changed.
        self._redraw_selected(keep="")
        if problem:  # after the redraw, which clears the status
            self._say(problem, error=True)

    def auto_axis_text(self, name):
        """The axes editor's Auto: back to the automatic title or label."""
        setattr(self.panel, name, None)
        self._redraw_selected(keep="xy")

    def set_ticks_in(self, inward):
        """Point every panel's ticks inward, or back out, and remember it."""
        self.settings["ticks_in"] = inward
        try:
            save_settings(self.settings)
        except OSError as err:
            self._say(f"Couldn't remember that: {err}", error=True)
        for cell in self.axes:
            self._draw_panel(cell)
        self.canvas.draw()

    def use_view(self):
        """Fill the range boxes with what the selected panel shows now, e.g. after zooming."""
        ax = self.axes[self.selected]
        self.axes_popup.set_view(ax.get_xlim(), ax.get_ylim())
        self.apply_axes()

    # --- linked data ------------------------------------------------------

    def _link_groups(self):
        """Lists of cells whose panels plot the same data, each in grid order."""
        groups = {}
        for cell in sorted(self.panels):
            if self.panels[cell].link_group is not None:
                groups.setdefault(self.panels[cell].link_group, []).append(cell)
        return list(groups.values())

    def _link_partners(self, cell):
        """The other cells whose panels plot the same data as `cell`'s."""
        if cell not in self.panels or self.panels[cell].link_group is None:
            return []
        group = self.panels[cell].link_group
        return [c for c in sorted(self.panels)
                if c != cell and self.panels[c].link_group == group]

    def _tied(self, cell):
        """Every panel a change to `cell`'s lines shows in: it and those linked to it."""
        return [cell, *self._link_partners(cell)]

    def _group_lists(self, cell):
        """The lists of lines in `cell`'s linked group, `cell`'s first."""
        lists = []
        for c in [cell, *self._link_partners(cell)]:
            if not any(self.panels[c].lines is lines for lines in lists):
                lists.append(self.panels[c].lines)
        return lists

    def _clear_ranges(self, lines, axes):
        """Clear typed ranges on the panel drawing `lines`, when what's plotted on
        those axes changes."""
        for p in self.panels.values():
            if p.lines is lines:
                clear_ranges(p, axes)

    def _sync_inputs(self, cell):
        """Copy `cell`'s lines' settings to the linked panels' lines, line by
        line: each SYNC key that both panels share."""
        me = self.panels[cell]
        if me.frozen:
            return
        for other in (self.panels[c] for c in self._link_partners(cell)):
            if other.frozen:
                continue
            lines = other.lines
            keys = [k for k in SYNC if k in me.synced & other.synced]
            for mine, theirs in zip(lines, me.lines):
                old_x, old_y = (mine.x, mine.x_fn), (mine.y, mine.y_fn, mine.background)
                for key in keys:
                    for attr in SYNC[key]:
                        # A value in the plotted x only means the same with the same x.
                        if attr in X_UNITS and (mine.x, mine.x_fn) != (theirs.x, theirs.x_fn):
                            continue
                        setattr(mine, attr, getattr(theirs, attr))
                    if key in ("x", "x_fn") and (mine.x, mine.x_fn) != old_x:
                        # In the old x; x comes before the keys that could set them.
                        mine.span = mine.fit_from = mine.fit_to = None
                        self._clear_ranges(lines, "x")
                new_y = (mine.y, mine.y_fn, mine.background)
                if new_y[:2] != old_y[:2] or (new_y[2] == "subtract") != (old_y[2] == "subtract"):
                    self._clear_ranges(lines, "y")

    def freeze(self):
        """Freeze or unfreeze the selected panel's link. Frozen, it stays in its
        group (lines are still added and removed in step) but no settings cross
        either way; unfreezing sends its synced settings to the others."""
        p = self.panels[self.selected]
        p.frozen = not p.frozen
        self._sync_inputs(self.selected)  # does nothing if it was just frozen
        self._redraw_selected("x", "x")

    def set_sync(self, key):
        """Tick or untick `key` in the selected panel's sync. Ticking it sends
        the selected panel's setting to the others that share it, as an edit would."""
        p = self.panels[self.selected]
        synced = p.synced | {key} if self.sync_vars[key].get() else p.synced - {key}
        p.sync = " ".join(k for k in SYNC if k in synced)
        self._sync_inputs(self.selected)
        self._redraw_selected("x", "x")

    def _tidy_link_groups(self):
        """Drop groups left with one panel (after an unlink or a smaller layout),
        and forget a derived panel's source once it no longer follows it."""
        for group in self._link_groups():
            if len(group) == 1:
                self.panels[group[0]].link_group = None
                self.panels[group[0]].frozen = False  # nothing left to freeze against
        for p in self.panels.values():
            source = self.panels.get(p.source)
            if p.source is not None and (source is None or p.link_group is None
                                         or source.link_group != p.link_group):
                p.source = None

    def _numbers(self, cells):
        """'2, 3 and 5' for those panels."""
        numbers = [str(self._number(c)) for c in cells]
        return numbers[0] if len(numbers) == 1 else f"{', '.join(numbers[:-1])} and {numbers[-1]}"

    def link_panels(self):
        """Wait for a click on the panel whose data the selected one should plot."""
        self.stop_picking()
        if len(self.panels) == 1:
            self._say("There's only one panel; choose a bigger Layout first.", error=True)
            return
        self.link_pick = self.selected
        self._say("Click the panel to plot the same data as; Esc cancels.")

    def _link(self, cell, target):
        """Link `cell` (and any group it's in) to `target`'s data.

        `cell`'s side takes `target`'s number of lines, and whatever both
        sides sync (by default the data input and colours)."""
        self.stop_picking()
        if target == cell:
            self._say("Click a different panel to link to.", error=True)
            return
        mine, theirs = self.panels[cell].link_group, self.panels[target].link_group
        if mine is not None and mine == theirs:
            self._say("Those panels are already linked.")
            return
        source = self.panels[target].lines
        followers = [lines for lines in self._group_lists(cell) if lines is not source]
        extra = sum(max(0, len(lines) - len(source)) for lines in followers)
        if extra and not messagebox.askyesno(
                "Link panels?",
                f"Panel {self._number(target)} has {len(source)} line"
                f"{'s' if len(source) > 1 else ''}, so {extra} of panel "
                f"{self._number(cell)}'s will be removed. Link anyway?", parent=self):
            return
        group = next((g for g in (theirs, mine) if g is not None),
                     max((p.link_group or 0 for p in self.panels.values()), default=0) + 1)
        for c, p in self.panels.items():  # merge both groups, or start one
            if c in (cell, target) or (p.link_group is not None and p.link_group in (mine, theirs)):
                p.link_group = group
        for lines in followers:  # same number of lines as the target's
            del lines[len(source):]
            while len(lines) < len(source):
                new = source[len(lines)].copy()
                new.colour = None
                lines.append(new)
        self._sync_inputs(target)
        for p in self.panels.values():
            p.selected = min(p.selected, len(p.lines) - 1)
        self._build_axes()
        self._load_controls()

    def unlink_panel(self):
        """Take the selected panel out of its linked group; it keeps its lines."""
        self.stop_picking()
        if self.panel.link_group is not None:
            self.panel.link_group = None
            self.panels[self.selected].frozen = False
            self._build_axes()
            self._load_controls()

    # --- fit range --------------------------------------------------------

    def pick_range(self):
        """Drag across the selected panel to set the selected line's fit range."""
        self.stop_picking()
        ax = self.axes[self.selected]
        if self.panel.derived:
            self._say(f"Pick the fit range on the data panel, not its "
                      f"{self._kind(self.panel.operation)}.", error=True)
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
        """End a fit-range drag or a pick of where a derived panel or link goes, if one is under way."""
        if self.derive_pick is not None or self.link_pick is not None:
            self.derive_pick = self.link_pick = None
            self._say("")
        if self.picker:
            self.picker.disconnect_events()
            self.picker.set_visible(False)  # its shaded span, if one was drawn
            self.picker = None
            self.canvas.draw_idle()
            self._say("")

    # --- colour -----------------------------------------------------------

    def _show_colour(self, move_picker=True):
        """Recolour the lines without a redraw, so zoom survives."""
        p = self.panel
        colours = line_colours(p, self.profile.samples)
        for i, colour in enumerate(colours):
            self.line_list.itemconfigure(i, foreground=colour, selectforeground=colour)
        for cell in self._tied(self.selected):  # locked and linked panels: same colours
            for artist, i in self.artists.get(cell, {}).items():
                artist.set_color(colours[i])
            ax = self.axes.get(cell)
            if ax and ax.get_legend():  # the legend keeps its own copy of each colour
                for handle, artist in zip(ax.get_legend().legend_handles, ax.lines):
                    handle.set_color(artist.get_color())
        self._show_style(colours[p.selected], move_picker)
        # Draw now rather than on idle: while the mouse is dragging in the
        # picker, idle callbacks can be held off and the line never repaints.
        self.canvas.draw()

    def pick_colour(self, colour):
        self.panel.line.colour = colour
        self._sync_inputs(self.selected)
        # The picker already shows it; moving it would round-trip through hex.
        self._show_colour(move_picker=False)
        self._changed(merge=True)  # a drag through the picker is one step

    def reset_colour(self):
        self.panel.line.colour = None
        self._sync_inputs(self.selected)
        self._show_colour()
        self._changed()

    # --- undo -------------------------------------------------------------

    def _changed(self, merge=False):
        """Called after anything that may have changed the panels: if it did,
        the state before becomes the one Ctrl+Z goes back to.

        With `merge`, a change straight after another merging one (the colour
        picker, which calls this on every drag step) extends that step."""
        self._prune_cache()
        if self.restoring:
            return
        now = session.dump(self.panels, self.rows, self.cols)
        if self.last_state is None:  # the window's first draw
            self.last_state = now
            return
        if now == self.last_state:
            return
        if not (merge and self.merging):
            self.undo_state = self.last_state
        self.last_state, self.merging = now, merge

    def _undo_keys(self, window):
        """Ctrl+Z in an editor window too: the main window's binding misses it."""
        for key in ("z", "Z"):
            window.bind(f"<Control-{key}>", lambda _: self.undo())

    def undo(self):
        """Go back one step: the panels as they were before the last change."""
        self.stop_picking()
        self._changed()  # a colour still being picked counts as that change
        if self.undo_state is None:
            self._say("Nothing to undo.", error=True)
            return
        state, self.undo_state = self.undo_state, None
        self.restoring = True
        try:
            self._restore(state)
        finally:
            self.restoring = False
        self.last_state, self.merging = session.dump(self.panels, self.rows, self.cols), False
        self._say("Undone. (One step only.)")

    # --- sessions ---------------------------------------------------------

    def _restore(self, state, selected=None):
        """Replace the panels with those in `state` (from session.dump). Raises
        ValueError, changing nothing, if it isn't one."""
        rows, cols, panels = session.load(state)
        self.stop_picking()
        for cell, p in panels.items():  # keep the line each panel had selected
            if cell in self.panels:
                p.selected = min(self.panels[cell].selected, len(p.lines) - 1)
        self.rows, self.cols, self.panels = rows, cols, panels
        if selected in panels:
            self.selected = selected
        elif self.selected not in panels:
            self.selected = (0, 0)
        self.cache.clear()
        self._build_axes()
        self._load_controls()

    def save_session(self, path=None):
        """Write the layout, panels and lines to a JSON file, to open again later."""
        self.stop_picking()
        if path is None:
            stem = Path(self.filename.get().strip() or "plot").stem
            path = filedialog.asksaveasfilename(
                parent=self, title="Save session", defaultextension=".json",
                initialdir=self.settings.get("output_dir") or Path.home(),
                initialfile=f"{stem}-session.json",
                filetypes=[("GOOSE Plotter session", "*.json"), ("All files", "*")])
            if not path:  # cancelled; the file dialog asked about replacing already
                return
        data = {session.KEY: session.VERSION, "data_dir": self.data_dir,
                "selected": session.cell_key(self.selected),
                **session.dump(self.panels, self.rows, self.cols)}
        if self.filename.get().strip() != self.auto_name:  # a name the user typed
            data["save_as"] = self.filename.get().strip()
        try:
            Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except OSError as err:
            self._say(f"Couldn't save the session: {err}", error=True)
            return
        self._say(f"Saved session {Path(path).name}")

    def open_session(self, path=None):
        """Open a session file: its data folder (if it's still there), layout and lines."""
        self.stop_picking()
        if path is None:
            path = filedialog.askopenfilename(
                parent=self, title="Open session",
                initialdir=self.settings.get("output_dir") or Path.home(),
                filetypes=[("GOOSE Plotter session", "*.json"), ("All files", "*")])
            if not path:
                return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or session.KEY not in data:
                raise ValueError("it isn't a GOOSE Plotter session")
            if not isinstance(data[session.KEY], int) or data[session.KEY] > session.VERSION:
                raise ValueError("it's from a newer version of the plotter")
            session.load(data)  # check it all before changing anything
        except (OSError, ValueError) as err:
            self._say(f"Couldn't open {Path(path).name}: {err}", error=True)
            return
        note, folder = "", data.get("data_dir")
        if isinstance(folder, str) and folder != self.data_dir:
            if Path(folder).is_dir():
                self.settings["data_dir"] = folder
                try:
                    save_settings(self.settings)
                except OSError as err:
                    note = f"; couldn't remember its data folder: {err}"
                self._show_folder(self.data_label, "data_dir")
                if error := self._read_folder():
                    note = f"; {error}"
            else:
                note = f"; its data folder {folder} isn't there, so using this one"
        selected = data.get("selected")
        try:
            selected = session.key_cell(selected)
        except (AttributeError, ValueError):
            selected = None
        self._restore(data, selected)
        if isinstance(data.get("save_as"), str):
            self.filename.set(data["save_as"])
        self._say(f"Opened session {Path(path).name}{note}", error=bool(note))

    # --- line style -------------------------------------------------------

    def _show_style(self, colour, move_picker=True):
        """The style box's picture of the selected line, and the editor, if open."""
        line = self.panel.line
        width = line.auto_width if line.width is None else line.width
        # Within 1.2 to 2: thin lines would be faint in the box, thick ones fill it.
        self.style_image = line_sample(line.style, line.marker, colour,
                                       min(max(width, 1.2), 2.0), size=(40, 14))
        self.style_button["image"] = self.style_image
        if self.style_popup and self.style_popup.winfo_exists():
            auto = plain(self.auto_names.get(self.selected, {}).get(self.panel.selected, ""))
            self.style_popup.show(line, colour, move_picker, auto)

    def open_style(self):
        if self.style_popup and self.style_popup.winfo_exists():
            self.style_popup.lift()
        else:
            self.style_popup = LineStylePopup(self, self.apply_style, self.pick_colour,
                                              self.reset_colour)
            self._undo_keys(self.style_popup)
        self._show_colour()  # fills the editor, in the line's colour

    def apply_style(self, merge=False, **settings):
        """Set the selected line's style, width, marker or name from the editor.

        `merge`: part of a drag of the width slider, one undo step in all; the
        editor calls this with no settings when the drag ends."""
        if not settings:
            self.merging = False
            return
        l, problem = self.panel.line, ""
        if "label" in settings:  # None: Auto; else the name typed, "" for none
            label = settings.pop("label")
            auto = plain(self.auto_names.get(self.selected, {}).get(self.panel.selected, ""))
            if l.label is None and label == auto:
                pass  # still the automatic name, as shown: keep it automatic
            elif label and (why := text_problem(label)):
                problem = f"Can't draw that name: {plain(why)}"
            else:
                l.label = label
        for name, value in settings.items():
            setattr(l, name, value)
        self._sync_inputs(self.selected)  # for panels that sync the style
        # Style doesn't move the data, so keep any zoom.
        self._redraw_selected(keep="xy", merge=merge)
        if problem:  # after the redraw, which clears the status
            self._say(problem, error=True)

    # --- status and saving ------------------------------------------------

    INFO_SECONDS = 10  # how long an info message stays

    def _say(self, text, error=False):
        """Show `text` under the controls. Info clears itself after INFO_SECONDS;
        errors stay until the next message, so they aren't missed."""
        if self.status_timer:
            self.after_cancel(self.status_timer)
            self.status_timer = None
        self.status.configure(text=text, foreground=theme.ERROR if error else theme.OK)
        if text and not error:
            self.status_timer = self.after(self.INFO_SECONDS * 1000, self._expire_status)

    def _expire_status(self):
        self.status_timer = None
        # Instructions for a pick under way ("Click the panel...") stay until
        # it ends, which clears them.
        if self.derive_pick is None and self.link_pick is None and not self.picker:
            self.status.configure(text="")

    def _default_name(self):
        """The top-left panel's first line, e.g. run_005_M006_AH_vs_Norminal_FIeld.png."""
        first = self.panels[0, 0].lines[0]
        if not first.shown:
            return ""
        run, y, x, smoothed, fitted = first.parts()
        tail = f"_{background.file_part(*fitted)}" if fitted else ""
        tail += f"_{smoothing.file_part(*smoothed)}" if smoothed else ""
        corner = self.panels[0, 0]
        tail += f"_{corner.operation}" if corner.derived else ""  # _fft, _d1 or _d2
        return f"{describe(run).replace(' ', '_')}_{y}_vs_{x}{tail}.png"

    def _update_filename(self):
        """Put the default name in the Save as box, unless the user typed one."""
        current = self.filename.get().strip()
        if not current or current == self.auto_name:
            self.auto_name = self._default_name()
            self.filename.set(self.auto_name)

    def _may_overwrite(self, name, out_dir):
        """Ask before writing over a file, unless the user said not to ask again."""
        if self.settings.get("overwrite_without_asking"):
            return True
        dialog = OverwriteDialog(self, name, out_dir.name)
        self.wait_window(dialog)
        if dialog.replace and dialog.dont_ask.get():
            self.settings["overwrite_without_asking"] = True
            try:
                save_settings(self.settings)
            except OSError as err:
                self._say(f"Couldn't remember that: {err}", error=True)
        return dialog.replace

    MAX_PIXELS = 20_000  # per side of a saved figure, to keep its memory in bounds

    def _save_options(self):
        """Save figure's size, dpi and background, from the settings (each one
        checked, as the file can be edited by hand) over the defaults."""
        options = dict(SaveOptionsPopup.DEFAULTS)
        saved = self.settings.get("save_options")
        if isinstance(saved, dict):
            for key, default in SaveOptionsPopup.DEFAULTS.items():
                value = saved.get(key)
                if type(value) is type(default) or (isinstance(default, float)
                                                     and type(value) is int):
                    options[key] = value
        if options["size"] not in ("screen", "custom") or options["unit"] not in ("in", "cm"):
            return dict(SaveOptionsPopup.DEFAULTS)
        return options

    def open_save_options(self):
        if self.save_popup and self.save_popup.winfo_exists():
            self.save_popup.lift()
            return
        self.save_popup = SaveOptionsPopup(self, self._save_options(),
                                           tuple(self.fig.get_size_inches()), self.set_save_options)

    def set_save_options(self, options):
        """Keep the options from the Save options window; why not, if they can't be used."""
        inches = ((options["width"], options["height"]) if options["size"] == "custom"
                  else self.fig.get_size_inches())
        if max(inches) * options["dpi"] > self.MAX_PIXELS:
            return f"That's too big: keep each side under {self.MAX_PIXELS} pixels."
        self.settings["save_options"] = options
        try:
            save_settings(self.settings)
        except OSError as err:
            return f"Couldn't remember them: {err}"
        return ""

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
        if (out_dir / name).exists() and not self._may_overwrite(name, out_dir):
            self._say("Not saved: the file is already there.", error=True)
            return
        # The selection frame is for the screen, not the saved figure.
        selected, self.selected = self.selected, None
        for cell in self.axes:
            self._frame(cell)
        options = self._save_options()
        size = self.fig.get_size_inches()
        try:
            if options["size"] == "custom":  # just for the file; the screen keeps its own
                self.fig.set_size_inches(options["width"], options["height"], forward=False)
            self.fig.savefig(out_dir / name, dpi=options["dpi"],
                             transparent=options["transparent"])
        finally:
            self.fig.set_size_inches(size, forward=False)
            self.selected = selected
            for cell in self.axes:
                self._frame(cell)
            self.canvas.draw()
        self._say(f"Saved {out_dir.name}/{name}")


if __name__ == "__main__":
    Plotter().mainloop()
