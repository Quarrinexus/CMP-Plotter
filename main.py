"""Interactive plotter: pick a dataset and axes from a window.

    python general-plotter.py

Opens blank. Choose a run from the Dataset list and the plot draws; changing
any control redraws it. The toolbar under the plot zooms and pans; Save figure
writes the current plot to output/ named after the chosen settings, e.g.
`run_005_M011_AH_vs_Norminal_FIeld.png`. That name fills the "Save as" box
and follows the plot; type your own to override it (no extension means .png;
.pdf, .svg and other matplotlib formats also work), clear it to go back.

The X and Y lists hold every column in the run, sample columns included
(`M006_AH`, `M011_AH_Loss`, ...), so any column can go against any other.

Layout... opens a grid like Word's table picker: hover to size it, click to
apply. Panels already on screen keep their place; new ones start as copies of
the selected panel. Click a panel to select it (orange frame).

Each panel holds one or more lines, listed under Lines: + adds a copy of the
selected line, - removes it. Every line has its own dataset, axes and
functions, so samples, runs or transforms can share a panel; the controls
below the list edit the selected line (click a line in the list, or on the
plot, to select it). Panels with several lines get a legend naming only what
differs between them. Swap axes swaps every line in the panel.

The swatch beside the list opens the colour picker for the selected line: hue
across, saturation down, brightness in the strip beside. Lines start in their
sample's colour from runs.SAMPLES (blue if there's no sample column), or the
next unused colour in PALETTE when that's taken in the panel; Reset goes back.

Under each axis a collapsed "Function" row opens to a box for transforming
that quantity before plotting. The boxes start as `x` and `y` (the quantity
unchanged); write e.g. `1/x`, `exp(y)`, `log10(x)`. Any other name works too
(`1/B`) as long as there is only one; numpy's usual functions (exp, log, sqrt,
sin, ...) plus pi and e are available. Press Enter to apply. Saved filenames
spell the function out with the column in place of the name, e.g.
`run_005_M006_AH_vs_1-over-Norminal_FIeld.png`.
"""

from dataclasses import dataclass, field, replace
import re
import tkinter as tk
from tkinter import messagebox, ttk

from matplotlib.colors import hsv_to_rgb, rgb_to_hsv, to_hex, to_rgb
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import numpy as np
from PIL import Image, ImageTk

from huairou_cmp.runs import OUT_DIR, SAMPLES, available_runs, load_run

DEFAULT_X = "Norminal_FIeld"
DEFAULT_Y = "M006_AH"
NEUTRAL = "#2464d6"  # line colour when no sample column is plotted
SELECTED = "#e8a33d"  # frame around the selected panel
MAX_GRID = 6  # the layout picker offers up to MAX_GRID x MAX_GRID panels

# Colours for extra lines once a panel's sample colours are taken.
PALETTE = ("#2464d6", "#eb6834", "#2e9e5b", "#8e5bd1", "#c23b6e", "#1a9aa0",
           "#b58900", "#52514e")

# Column -> axis label; anything missing is labelled with its column name.
# 'AH' and 'AH_Loss' also match per-sample columns ('M006_AH' ->
# 'M006 capacitance (bridge units)').
LABELS = {
    "Timestamp": "time  (s)",
    "T_Probe": "probe temperature  (K)",
    "T_VTI": "VTI temperature  (K)",
    "Norminal_FIeld": r"$B$  (T)",
    "AH": "capacitance (bridge units)",
    "AH_Loss": "loss (bridge units)",
}

# Column -> unit shown beside it in the dropdowns, matched like LABELS. The
# Hall channels are raw instrument readings; the file header gives no units.
UNITS = {
    "Timestamp": "s",
    "T_Probe": "K",
    "T_VTI": "K",
    "Norminal_FIeld": "T",
    "AngleHall_x": "raw",
    "AngleHall_y": "raw",
    "AH": "bridge units",
    "AH_Loss": "bridge units",
}


def lookup(table, column):
    """(entry, sample prefix) for `column` in LABELS or UNITS, else (None, '').

    An exact match wins; otherwise the longest key the column ends with, so
    'M006_AH_Loss' finds 'AH_Loss' (prefix 'M006') rather than 'AH'.
    """
    if column in table:
        return table[column], ""
    for key in sorted(table, key=len, reverse=True):
        if column.endswith(f"_{key}"):
            return table[key], column.removesuffix(f"_{key}")
    return None, ""


def label(column, with_sample=True):
    """Axis label: 'M006_AH' -> 'M006 capacitance (bridge units)', or without
    the sample name ('capacitance (bridge units)') for lines of mixed samples."""
    text, prefix = lookup(LABELS, column)
    if text is None:
        return column
    return f"{prefix} {text}" if prefix and with_sample else text


def with_unit(column):
    """Dropdown text for a column: 'Norminal_FIeld' -> 'Norminal_FIeld  (T)'."""
    unit, _ = lookup(UNITS, column)
    return f"{column}  ({unit})" if unit else column


def without_unit(text):
    """Inverse of with_unit: the option name back from its dropdown text."""
    return text.partition("  (")[0]

# Names an axis function can call; any other name stands for the quantity.
FUNCTIONS = {name: getattr(np, name) for name in (
    "exp", "log", "log10", "log2", "sqrt", "abs", "sin", "cos", "tan",
    "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "radians", "degrees",
)} | {"pi": np.pi, "e": np.e}


def quantity_name(expr):
    """The one name in `expr` that isn't a function: '1/x' -> 'x'."""
    free = set(compile(expr, "<axis function>", "eval").co_names) - FUNCTIONS.keys()
    if len(free) != 1:
        raise ValueError(f"'{expr}' should use exactly one name for the quantity, "
                         f"found {', '.join(sorted(free)) or 'none'}")
    return free.pop()


def is_identity(expr):
    """True for an empty box or a bare name like 'x': the quantity unchanged."""
    return not expr or (expr.isidentifier() and expr not in FUNCTIONS)


def apply_function(expr, values):
    """Evaluate `expr` (e.g. '1/x') with its one free name bound to `values`.

    Returns (result, name) so the axis label can say what the name meant.
    """
    name = quantity_name(expr)
    code = compile(expr, "<axis function>", "eval")
    with np.errstate(all="ignore"):  # 1/0 etc. just give inf/nan, left unplotted
        return eval(code, {"__builtins__": {}, **FUNCTIONS}, {name: values}), name


def rename(expr, old, new):
    """Rename the quantity in `expr` from `old` to `new`: '1/y' -> '1/x'.

    An empty box becomes `new`; a function using some other name ('1/B') is
    left alone.
    """
    if not expr:
        return new
    return re.sub(rf"\b{old}\b", new, expr)


def file_part(expr, option):
    """Filename piece for one axis: ('1/x', 'Norminal_FIeld') -> '1-over-Norminal_FIeld'."""
    if is_identity(expr):
        return option
    name = quantity_name(expr)
    return slug(re.sub(rf"\b{name}\b", option, expr))


def slug(expr):
    """Filename-safe form of an axis function: '1/B' -> '1-over-B'."""
    for op, word in (("**", "-pow-"), ("/", "-over-"), ("*", "-times-")):
        expr = expr.replace(op, word)
    return re.sub(r"[^\w.+-]+", "_", expr).strip("_")


def sample_of(*columns):
    """The runs.SAMPLES sample the first matching column belongs to, else ''."""
    for col in columns:
        for sample in SAMPLES:
            if col.startswith(f"{sample}_"):
                return sample
    return ""


class ColourPicker(ttk.Frame):
    """Hue across and saturation down a field, plus a brightness strip.

    Click or drag in either; `on_change` gets the new colour as '#rrggbb'.
    """

    FIELD_BRIGHTNESS = 200 / 255  # the field is drawn at this brightness

    def __init__(self, parent, on_change, width=230, height=160, strip=20):
        super().__init__(parent)
        self.on_change = on_change
        self.w, self.h, self.strip_w = width, height, strip
        self.hsv = np.array([0.0, 0.0, 1.0])

        self.field = tk.Canvas(self, width=width, height=height,
                               highlightthickness=0, cursor="crosshair")
        self.field.pack(side=tk.LEFT)
        self.strip = tk.Canvas(self, width=strip, height=height,
                               highlightthickness=0, cursor="sb_v_double_arrow")
        self.strip.pack(side=tk.LEFT, padx=(4, 0))

        # Hue runs right to left (red, magenta, blue, ... red), saturation
        # from full at the top to grey at the bottom.
        hue = 1 - np.arange(width) / width
        sat = 1 - np.arange(height) / (height - 1)
        hsv = np.stack(np.broadcast_arrays(
            hue[None, :], sat[:, None], self.FIELD_BRIGHTNESS), axis=-1)
        self.field_image = self._photo(hsv)
        self.field.create_image(0, 0, anchor=tk.NW, image=self.field_image)
        self.strip_item = self.strip.create_image(0, 0, anchor=tk.NW)
        self.field_mark = self.field.create_oval(0, 0, 0, 0, outline="white", width=2)
        self.strip_mark = self.strip.create_rectangle(0, 0, 0, 0, outline="white", width=2)

        for event in ("<Button-1>", "<B1-Motion>"):
            self.field.bind(event, self._on_field)
            self.strip.bind(event, self._on_strip)

    @staticmethod
    def _photo(hsv):
        return ImageTk.PhotoImage(Image.fromarray((hsv_to_rgb(hsv) * 255).astype(np.uint8)))

    def colour(self):
        return to_hex(hsv_to_rgb(self.hsv))

    def set(self, colour):
        """Show `colour` without calling on_change."""
        hsv = rgb_to_hsv(to_rgb(colour))
        if hsv[1] == 0:  # grey has no hue; keep the marker's current one
            hsv[0] = self.hsv[0]
        self.hsv = hsv
        self._draw()

    def _draw(self):
        h, s, v = self.hsv
        x, y = (1 - h) * (self.w - 1), (1 - s) * (self.h - 1)
        self.field.coords(self.field_mark, x - 5, y - 5, x + 5, y + 5)
        # Brightness strip for the current hue and saturation, bright at the top.
        values = 1 - np.arange(self.h) / (self.h - 1)
        hsv = np.stack(np.broadcast_arrays(h, s, values[:, None] * np.ones(self.strip_w)), axis=-1)
        self.strip_image = self._photo(hsv)
        self.strip.itemconfigure(self.strip_item, image=self.strip_image)
        y = (1 - v) * (self.h - 1)
        self.strip.coords(self.strip_mark, 1, y - 2, self.strip_w - 1, y + 2)

    def _on_field(self, event):
        self.hsv[0] = 1 - min(max(event.x / (self.w - 1), 0), 1)
        self.hsv[1] = 1 - min(max(event.y / (self.h - 1), 0), 1)
        self._draw()
        self.on_change(self.colour())

    def _on_strip(self, event):
        self.hsv[2] = 1 - min(max(event.y / (self.h - 1), 0), 1)
        self._draw()
        self.on_change(self.colour())


@dataclass
class Line:
    """One plotted line. x and y are column names."""
    run: str = ""
    x: str = DEFAULT_X
    x_fn: str = "x"
    y: str = DEFAULT_Y
    y_fn: str = "y"
    colour: str | None = None  # None: picked automatically, see line_colours
    shown: tuple | None = None  # (run, x, x_fn, y, y_fn) as last drawn
    error: str = ""  # why the last draw failed, if it did

    def copy(self):
        return replace(self, shown=None, error="")

    def parts(self):
        """(run, y part, x part) as they'd appear in a filename."""
        run, x, x_fn, y, y_fn = self.shown
        return run, file_part(y_fn, y), file_part(x_fn, x)


@dataclass
class Panel:
    """One subplot: its lines and which of them the controls edit."""
    lines: list = field(default_factory=lambda: [Line()])
    selected: int = 0

    @property
    def line(self):
        return self.lines[self.selected]

    def copy(self):
        return Panel([l.copy() for l in self.lines], self.selected)


def near(colour, others, distance=0.25):
    """True if `colour` is hard to tell from any of `others` (RGB distance)."""
    rgb = np.array(to_rgb(colour))
    return any(np.linalg.norm(rgb - to_rgb(o)) < distance for o in others)


def line_colours(panel):
    """Each line's colour: its pick, else its sample's, else the next one in
    PALETTE that doesn't look like a colour the panel already uses."""
    colours = [l.colour for l in panel.lines]
    used = [c for c in colours if c]
    for i, l in enumerate(panel.lines):
        if colours[i]:
            continue
        wanted = SAMPLES.get(sample_of(l.y, l.x), NEUTRAL)
        if near(wanted, used):
            wanted = next((c for c in PALETTE if not near(c, used)),
                          PALETTE[len(used) % len(PALETTE)])
        colours[i] = wanted
        used.append(wanted)
    return colours


def legend_labels(lines):
    """Legend text naming only what differs between the lines."""
    parts = [l.parts() for l in lines]
    differs = [len({p[i] for p in parts}) > 1 for i in range(3)]
    if not any(differs):
        differs[1] = True  # identical lines: say what's on y
    labels = []
    for run, y, x in parts:
        bits = [f"run {run}"] if differs[0] else []
        if differs[1]:
            bits.append(y)
        if differs[2]:
            bits.append(f"vs {x}")
        labels.append(" · ".join(bits))
    return labels


def shared(labels):
    """One axis label for several lines, from (full, without-sample) pairs.

    All the same: that label. Same bar the sample: the label without it (the
    legend names the samples). Otherwise the distinct ones joined with ' / '.
    """
    for texts in zip(*labels):
        unique = list(dict.fromkeys(texts))
        if len(unique) == 1:
            return unique[0]
    return " / ".join(dict.fromkeys(plain for _, plain in labels))


class ColourPopup(tk.Toplevel):
    """The colour picker in its own window, editing the selected line."""

    def __init__(self, parent, on_change, on_reset):
        super().__init__(parent)
        self.title("Line colour")
        self.resizable(False, False)
        self.transient(parent)
        self.picker = ColourPicker(self, on_change)
        self.picker.pack(padx=10, pady=(10, 6))
        row = ttk.Frame(self)
        row.pack(anchor=tk.W, padx=10, pady=(0, 10))
        self.swatch = tk.Label(row, width=3, relief=tk.SOLID, borderwidth=1)
        self.swatch.pack(side=tk.LEFT, fill=tk.Y)
        self.hex = ttk.Label(row, width=8, font="TkFixedFont")
        self.hex.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Reset", command=on_reset).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Close", command=self.destroy).pack(side=tk.LEFT, padx=(6, 0))
        self.bind("<Escape>", lambda _: self.destroy())

    def show(self, colour, move_picker=True):
        self.swatch["background"] = colour
        self.hex["text"] = colour
        if move_picker:
            self.picker.set(colour)


class LayoutPicker(tk.Toplevel):
    """Word-style grid: hover to choose rows x columns, click to apply."""

    CELL, GAP = 26, 3

    def __init__(self, parent, rows, cols, on_pick):
        super().__init__(parent)
        self.title("Layout")
        self.resizable(False, False)
        self.transient(parent)
        self.on_pick = on_pick
        size = MAX_GRID * (self.CELL + self.GAP) + self.GAP
        self.grid_canvas = tk.Canvas(self, width=size, height=size, highlightthickness=0,
                                     background="white", cursor="hand2")
        self.grid_canvas.pack(padx=10, pady=(10, 4))
        self.label = ttk.Label(self, anchor=tk.CENTER)
        self.label.pack(fill=tk.X, pady=(0, 10))
        self.cells = {}
        for r in range(MAX_GRID):
            for c in range(MAX_GRID):
                x0 = self.GAP + c * (self.CELL + self.GAP)
                y0 = self.GAP + r * (self.CELL + self.GAP)
                self.cells[r, c] = self.grid_canvas.create_rectangle(
                    x0, y0, x0 + self.CELL, y0 + self.CELL, width=1)
        self.grid_canvas.bind("<Motion>", self._hover)
        self.grid_canvas.bind("<Button-1>", self._click)
        self.bind("<Escape>", lambda _: self.destroy())
        self._show(rows, cols)
        self.grab_set()  # modal: the main window waits for a choice
        self.focus_set()

    def _cell_at(self, event):
        step = self.CELL + self.GAP
        r = min(max(int((event.y - self.GAP) // step), 0), MAX_GRID - 1)
        c = min(max(int((event.x - self.GAP) // step), 0), MAX_GRID - 1)
        return r + 1, c + 1

    def _show(self, rows, cols):
        for (r, c), item in self.cells.items():
            on = r < rows and c < cols
            self.grid_canvas.itemconfigure(
                item, fill=SELECTED if on else "#f4f3ef",
                outline="#b5781c" if on else "#c9c8c2")
        self.label["text"] = f"{rows} × {cols}"

    def _hover(self, event):
        self._show(*self._cell_at(event))

    def _click(self, event):
        rows, cols = self._cell_at(event)
        self.destroy()
        self.on_pick(rows, cols)


class Plotter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("General Plotter")
        self.geometry("1150x760")
        self.frames = {}  # run id -> DataFrame, so each file is read once
        self.rows, self.cols = 1, 1
        self.panels = {(0, 0): Panel()}  # (row, col) -> Panel
        self.selected = (0, 0)
        self.axes = {}  # (row, col) -> matplotlib Axes
        self.artists = {}  # (row, col) -> {matplotlib Line2D: line index}
        self.colour_popup = None

        controls = ttk.Frame(self, padding=10)
        controls.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(controls, text="Lines").pack(anchor=tk.W, pady=(0, 2))
        lines = ttk.Frame(controls)
        lines.pack(anchor=tk.W, fill=tk.X)
        self.line_list = tk.Listbox(lines, height=4, width=24, exportselection=False,
                                    activestyle="none")
        self.line_list.pack(side=tk.LEFT)
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
        self.x = self._combo(controls, "X axis", [])
        self.x_fn = self._function_box(controls, "x")
        self.y = self._combo(controls, "Y axis", [])
        self.y_fn = self._function_box(controls, "y")
        ttk.Label(controls, text="Save as").pack(anchor=tk.W, pady=(16, 2))
        self.filename = tk.StringVar()
        self.auto_name = ""  # last default name put in the box
        ttk.Entry(controls, textvariable=self.filename, width=26).pack(anchor=tk.W)
        buttons = ttk.Frame(controls)
        buttons.pack(anchor=tk.W, pady=(8, 0))
        ttk.Button(buttons, text="Layout...", command=self.choose_layout).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Swap axes", command=self.swap).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Button(buttons, text="Save figure", command=self.save).pack(
            side=tk.LEFT, padx=(6, 0))
        self.status = ttk.Label(controls, wraplength=230)
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

    # --- controls ---------------------------------------------------------

    def _combo(self, parent, label, values, default="", **kwargs):
        ttk.Label(parent, text=label).pack(anchor=tk.W, pady=(8, 2))
        var = tk.StringVar(value=default)
        box = ttk.Combobox(parent, textvariable=var, values=values,
                           state="readonly", width=24, **kwargs)
        box.pack(anchor=tk.W)
        box.bind("<<ComboboxSelected>>", lambda _: self.apply_controls())
        var.box = box
        return var

    def _function_box(self, parent, name):
        """A collapsed '▸ Function' toggle that opens to an entry box.

        The triangle is drawn, not typed: this Tk only has X core fonts, and
        its fallback for characters like ▸ can land on a symbol font that
        shows them as '®'. Widget text sticks to Latin-1 for the same reason.
        """
        var = tk.StringVar(value=name)
        toggle = ttk.Frame(parent, cursor="hand2")
        toggle.pack(anchor=tk.W, pady=(4, 0))
        arrow = tk.Canvas(toggle, width=10, height=10, highlightthickness=0,
                          background=ttk.Style().lookup("TFrame", "background"))
        arrow.pack(side=tk.LEFT, padx=(0, 4))
        text = ttk.Label(toggle, foreground="#52514e")
        text.pack(side=tk.LEFT)
        body = ttk.Frame(parent)
        entry = ttk.Entry(body, textvariable=var, width=16)
        entry.pack(anchor=tk.W)
        ttk.Label(body, text=f"e.g. 1/{name}, exp({name}) - Enter to apply",
                  foreground="#9a9992").pack(anchor=tk.W)

        def show_label():
            is_open = bool(body.winfo_manager())
            arrow.delete("all")
            points = (1, 2, 9, 2, 5, 8) if is_open else (2, 1, 8, 5, 2, 9)
            arrow.create_polygon(points, fill="#52514e", outline="")
            # Collapsed but in use: show the function so it isn't forgotten.
            expr = var.get().strip()
            used = f": {expr}" if not is_identity(expr) and not is_open else ""
            text["text"] = f"Function{used}"

        def flip(_):
            if body.winfo_manager():
                body.pack_forget()
            else:
                body.pack(anchor=tk.W, after=toggle)
                entry.focus_set()
            show_label()

        for widget in (toggle, arrow, text):
            widget.bind("<Button-1>", flip)
        for key in ("<Return>", "<KP_Enter>"):
            entry.bind(key, lambda _: (self.apply_controls(), show_label()))
        show_label()
        var.show_label = show_label
        return var

    def _refresh_runs(self):
        # Re-scan on every open so files added while the window is up appear.
        self.run.box["values"] = available_runs()

    @property
    def panel(self):
        return self.panels[self.selected]

    def _load_controls(self):
        """Show the selected line's settings in the controls."""
        self._fill_line_list()
        l = self.panel.line
        self.run.set(l.run)
        columns = list(self.frames[l.run].columns) if l.run in self.frames else []
        self.x.box["values"] = self.y.box["values"] = [with_unit(c) for c in columns]
        self.x.set(with_unit(l.x) if l.run else "")
        self.y.set(with_unit(l.y) if l.run else "")
        self.x_fn.set(l.x_fn)
        self.y_fn.set(l.y_fn)
        self.x_fn.show_label()
        self.y_fn.show_label()
        self._say("")  # errors pop up instead; see apply_controls
        self._show_colour()

    def _fill_line_list(self):
        p, colours = self.panel, line_colours(self.panel)
        self.line_list.delete(0, tk.END)
        for l, colour in zip(p.lines, colours):
            name = f"{l.y} · {l.run}" if l.run else "(no dataset)"
            self.line_list.insert(tk.END, name)
            self.line_list.itemconfigure(tk.END, foreground=colour,
                                         selectforeground=colour)
        self.line_list.selection_set(p.selected)
        self.line_list.see(p.selected)
        self.remove_button.state(["!disabled" if len(p.lines) > 1 else "disabled"])

    def apply_controls(self):
        """Copy the controls into the selected line and redraw its panel."""
        l = self.panel.line
        l.run = self.run.get()
        l.x, l.y = without_unit(self.x.get()) or l.x, without_unit(self.y.get()) or l.y
        l.x_fn, l.y_fn = self.x_fn.get().strip(), self.y_fn.get().strip()
        self._redraw_selected()
        if l.error:  # a popup rather than text in the controls, to save room
            title = "Function error" if l.run in self.frames else "Could not load run"
            messagebox.showerror(title, l.error.removeprefix("Function error: "), parent=self)

    def _redraw_selected(self):
        self._draw_panel(self.selected)
        self._load_controls()  # loading a run can change the axis choices
        self._update_filename()
        self.canvas.draw()

    # --- lines ------------------------------------------------------------

    def _select_line(self, index):
        self.panel.selected = index
        self._load_controls()

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
        p.selected += 1
        self._redraw_selected()

    def remove_line(self):
        p = self.panel
        if len(p.lines) > 1:
            del p.lines[p.selected]
            p.selected = min(p.selected, len(p.lines) - 1)
            self._redraw_selected()

    # --- drawing ----------------------------------------------------------

    def _load(self, line):
        """The line's run, with its axes moved to valid columns if needed."""
        if line.run not in self.frames:
            self.frames[line.run] = load_run(line.run)
        df = self.frames[line.run]
        # Keep the line's axes if this run has them, else fall back.
        for attr, default in (("x", DEFAULT_X), ("y", DEFAULT_Y)):
            if getattr(line, attr) not in df:
                setattr(line, attr, default if default in df else df.columns[0])
        return df

    def _axis(self, df, column, expr):
        """Values and (label, label without sample) for one axis, with its
        function applied if set."""
        values, texts = df[column].to_numpy(), (label(column), label(column, False))
        if is_identity(expr):
            return values, texts
        values, name = apply_function(expr, values)
        return values, tuple(f"{expr},   {name} = {t}" for t in texts)

    def _build_axes(self):
        """Recreate the grid of axes and draw every panel into it."""
        self.fig.clear()
        grid = self.fig.subplots(self.rows, self.cols, squeeze=False)
        self.axes = {(r, c): grid[r, c] for r in range(self.rows) for c in range(self.cols)}
        for cell in self.axes:
            self._draw_panel(cell)
        self._update_filename()
        self.canvas.draw()

    def _draw_panel(self, cell):
        """Draw a panel's lines; problems are written into the panel itself."""
        ax, p = self.axes[cell], self.panels[cell]
        ax.clear()
        self.artists[cell] = {}
        drawn, x_labels, y_labels, errors = [], [], [], []
        for i, (l, colour) in enumerate(zip(p.lines, line_colours(p))):
            l.shown, l.error = None, ""
            if not l.run:
                continue
            try:
                df = self._load(l)
                x, x_label = self._axis(df, l.x, l.x_fn)
                y, y_label = self._axis(df, l.y, l.y_fn)
            except Exception as err:  # bad file or function shouldn't kill the window
                l.error = f"Function error: {err}" if l.run in self.frames else str(err)
                errors.append(l.error)
                continue
            # What's on screen, so Save names the plot shown rather than
            # whatever is typed but not yet applied.
            l.shown = (l.run, l.x, l.x_fn, l.y, l.y_fn)
            (artist,) = ax.plot(x, y, lw=0.7, color=colour)
            self.artists[cell][artist] = i
            drawn.append(l)
            x_labels.append(x_label)
            y_labels.append(y_label)

        if drawn:
            ax.set_xlabel(shared(x_labels))
            ax.set_ylabel(shared(y_labels))
            ax.set_title("run " + ", ".join(dict.fromkeys(l.run for l in drawn)))
            ax.grid(True, lw=0.4, alpha=0.8)
            if len(drawn) > 1:
                for artist, text in zip(ax.lines, legend_labels(drawn)):
                    artist.set_label(text)
                ax.legend(fontsize=8)
        elif errors:
            self._hint(ax, errors[0], colour="#b3261e", size=9)
        else:
            self._hint(ax, "Pick a dataset")
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
        """Orange frame on the selected panel, when there's more than one."""
        on = cell == self.selected and len(self.axes) > 1
        for spine in self.axes[cell].spines.values():
            spine.set_edgecolor(SELECTED if on else "black")
            spine.set_linewidth(2.5 if on else 0.8)

    # --- panels and layout ------------------------------------------------

    def _on_click(self, event):
        """Select the clicked panel, and the line under the mouse if any."""
        cell = next((c for c, ax in self.axes.items() if ax is event.inaxes), None)
        if cell is None:
            return
        old, self.selected = self.selected, cell
        hit = next((i for artist, i in self.artists[cell].items()
                    if artist.contains(event)[0]), None)
        if hit is not None:
            self.panels[cell].selected = hit
        elif cell == old:
            return  # clicked empty space in the panel already selected
        self._frame(old)
        self._frame(cell)
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
        self._redraw_selected()

    # --- colour -----------------------------------------------------------

    def _show_colour(self, move_picker=True):
        """Recolour the swatch, list and lines, without a full redraw (so the
        toolbar's zoom survives)."""
        p = self.panel
        colours = line_colours(p)
        self.swatch["background"] = colours[p.selected]
        for i, colour in enumerate(colours):
            self.line_list.itemconfigure(i, foreground=colour, selectforeground=colour)
        for artist, i in self.artists.get(self.selected, {}).items():
            artist.set_color(colours[i])
        ax = self.axes.get(self.selected)
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
        run, y, x = first.parts()
        return f"run_{run}_{y}_vs_{x}.png"

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
        # Only a bare name: anything path-like would escape output/.
        name = self.filename.get().strip().replace("/", "_").replace("\\", "_")
        if not name:
            name = self.auto_name = self._default_name()
            self.filename.set(name)
        if "." not in name.lstrip("."):
            name += ".png"
        OUT_DIR.mkdir(exist_ok=True)
        # The selection frame is for the screen, not the saved figure.
        selected, self.selected = self.selected, None
        self._frame(selected)
        try:
            self.fig.savefig(OUT_DIR / name, dpi=200)
        finally:
            self.selected = selected
            self._frame(selected)
            self.canvas.draw()
        self._say(f"Saved output/{name}")


if __name__ == "__main__":
    Plotter().mainloop()
