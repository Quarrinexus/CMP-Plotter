"""Tk widgets used by the main window: the line editor with its colour picker,
the axes editor, the layout grid and the overwrite question."""

import tkinter as tk
from tkinter import ttk

from matplotlib.colors import hsv_to_rgb, rgb_to_hsv, to_hex, to_rgb
import numpy as np
from PIL import Image, ImageDraw, ImageTk

from goose_plotter import theme
from goose_plotter.model import (AUTO_MARKER_SIZE, GRID_AXES, GRID_STYLES, GRIDS, LEGENDS,
                                 MARKERS, RANGES, STYLES)

SELECTED = "#e8a33d"  # frame around the selected panel
MAX_GRID = 6  # the layout picker offers up to MAX_GRID x MAX_GRID panels


class ColourPicker(ttk.Frame):
    """Hue/saturation field plus a brightness strip; calls `on_change('#rrggbb')`."""

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
                                     background=theme.SURFACE, cursor="hand2")
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
                item, fill=SELECTED if on else theme.BACKGROUND,
                outline="#b5781c" if on else theme.BORDER)
        self.label["text"] = f"{rows} × {cols}"

    def _hover(self, event):
        self._show(*self._cell_at(event))

    def _click(self, event):
        rows, cols = self._cell_at(event)
        self.destroy()
        self.on_pick(rows, cols)


class OverwriteDialog(tk.Toplevel):
    """Modal. `replace` says whether to write over the file, and `dont_ask`
    whether the box to stop asking was ticked (it's off to start with)."""

    def __init__(self, parent, name, folder):
        super().__init__(parent)
        self.title("Replace file?")
        self.resizable(False, False)
        self.transient(parent)
        self.replace = False
        self.dont_ask = tk.BooleanVar(value=False)
        body = ttk.Frame(self, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=f"{name} already exists in {folder}.",
                  wraplength=360).pack(anchor=tk.W)
        ttk.Label(body, text="Replace it with this figure?",
                  foreground=theme.MUTED).pack(anchor=tk.W, pady=(4, 0))
        ttk.Checkbutton(body, text="Don't ask me again", variable=self.dont_ask).pack(
            anchor=tk.W, pady=(12, 0))
        buttons = ttk.Frame(body)
        buttons.pack(anchor=tk.E, pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        # Not the default: Enter shouldn't write over data by accident.
        ttk.Button(buttons, text="Replace", command=self._replace).pack(
            side=tk.RIGHT, padx=(0, 6))
        self.bind("<Escape>", lambda _: self.destroy())
        self.grab_set()
        self.focus_set()

    def _replace(self):
        self.replace = True
        self.destroy()


class SaveOptionsPopup(tk.Toplevel):
    """How Save figure writes the figure: its size (as on screen, or typed in
    inches or cm), dpi and background. Changes apply as they're made, through
    `on_change(options)`, which returns why they can't be used, or ""."""

    DEFAULTS = {"size": "screen", "width": 6.0, "height": 4.0, "unit": "in", "dpi": 200,
                "transparent": False}
    CM = 2.54  # per inch

    def __init__(self, parent, options, screen_inches, on_change):
        super().__init__(parent)
        self.title("Save options")
        self.resizable(False, False)
        self.transient(parent)
        self.on_change, self.screen = on_change, screen_inches
        self.size = tk.StringVar(value=options["size"])
        self.unit = tk.StringVar(value=options["unit"])
        scale = self.CM if options["unit"] == "cm" else 1
        self.width = tk.StringVar(value=f"{options['width'] * scale:.3g}")
        self.height = tk.StringVar(value=f"{options['height'] * scale:.3g}")
        self.dpi = tk.StringVar(value=str(options["dpi"]))
        self.transparent = tk.BooleanVar(value=options["transparent"])
        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Size", foreground=theme.MUTED).pack(anchor=tk.W)
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(2, 0))
        for key, text in (("screen", "As on screen"), ("custom", "Custom")):
            ttk.Radiobutton(row, text=text, variable=self.size, value=key, style="Toolbutton",
                            command=self._apply).pack(side=tk.LEFT, padx=(0, 4))
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(row, text="Width").pack(side=tk.LEFT)
        self.boxes = [ttk.Entry(row, textvariable=self.width, width=7)]
        self.boxes[0].pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(row, text="Height").pack(side=tk.LEFT)
        self.boxes.append(ttk.Entry(row, textvariable=self.height, width=7))
        self.boxes[1].pack(side=tk.LEFT, padx=(4, 8))
        self.units = []
        for key in ("in", "cm"):
            button = ttk.Radiobutton(row, text=key, variable=self.unit, value=key,
                                     style="Toolbutton", command=self._change_unit)
            button.pack(side=tk.LEFT, padx=(0, 4))
            self.units.append(button)

        ttk.Label(body, text="Resolution", foreground=theme.MUTED).pack(
            anchor=tk.W, pady=(10, 0))
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(row, text="DPI").pack(side=tk.LEFT)
        dpi = ttk.Entry(row, textvariable=self.dpi, width=7)
        dpi.pack(side=tk.LEFT, padx=(4, 8))
        self.pixels = ttk.Label(row, foreground=theme.HINT)
        self.pixels.pack(side=tk.LEFT)

        ttk.Label(body, text="Background", foreground=theme.MUTED).pack(
            anchor=tk.W, pady=(10, 0))
        ttk.Checkbutton(body, text="Transparent", variable=self.transparent,
                        command=self._apply).pack(anchor=tk.W, pady=(2, 0))

        self.problem = ttk.Label(body, foreground=theme.ERROR, wraplength=300)
        self.problem.pack(anchor=tk.W, pady=(10, 0))
        ttk.Label(body, text="Enter in a box applies; kept for every figure",
                  foreground=theme.HINT).pack(anchor=tk.W)
        ttk.Button(body, text="Close", command=self.destroy).pack(anchor=tk.E, pady=(6, 0))
        for box in (*self.boxes, dpi):
            for key in ("<Return>", "<KP_Enter>"):
                box.bind(key, lambda _: self._apply())
            box.bind("<FocusOut>", lambda _: self._apply())
        self.bind("<Escape>", lambda _: self.destroy())
        self._show()

    def _change_unit(self):
        """Show the typed size in the other unit (it's kept in inches)."""
        factor = self.CM if self.unit.get() == "cm" else 1 / self.CM
        for var in (self.width, self.height):
            try:
                var.set(f"{float(var.get()) * factor:.3g}")
            except ValueError:
                pass
        self._apply()

    def options(self):
        """The boxes as options, or raises ValueError saying what's wrong."""
        scale = self.CM if self.unit.get() == "cm" else 1
        try:
            width, height = float(self.width.get()) / scale, float(self.height.get()) / scale
        except ValueError:
            raise ValueError("Width and height need to be numbers.") from None
        try:
            dpi = int(float(self.dpi.get()))
        except ValueError:
            raise ValueError("DPI needs to be a number.") from None
        if not (width > 0 and height > 0):
            raise ValueError("Width and height need to be more than 0.")
        if not 10 <= dpi <= 2400:
            raise ValueError("DPI needs to be from 10 to 2400.")
        return {"size": self.size.get(), "width": width, "height": height,
                "unit": self.unit.get(), "dpi": dpi, "transparent": self.transparent.get()}

    def _apply(self):
        try:
            options = self.options()
        except ValueError as err:
            self.problem["text"] = str(err)
            return
        self.problem["text"] = self.on_change(options)
        self._show()

    def _show(self):
        """Grey out the size boxes when it's as on screen, and give the size in pixels."""
        custom = self.size.get() == "custom"
        for widget in (*self.boxes, *self.units):
            widget.state(["!disabled" if custom else "disabled"])
        try:
            options = self.options()
        except ValueError:
            self.pixels["text"] = ""
            return
        inches = (options["width"], options["height"]) if custom else self.screen
        self.pixels["text"] = (f"{round(inches[0] * options['dpi'])} x "
                               f"{round(inches[1] * options['dpi'])} pixels")


# Dash patterns for the previews, in multiples of the line width (as matplotlib's).
DASHES = {"-": None, "--": (3.7, 1.6), ":": (1, 1.65), "-.": (6.4, 1.6, 1, 1.6)}


def line_sample(style, marker, colour, width=1.0, size=(44, 16)):
    """A small picture of a line: its style (a key of STYLES, "auto" drawn
    solid), marker (a key of MARKERS) and colour. Drawn 4x and shrunk, for
    smooth edges."""
    k = 4
    w, h = size[0] * k, size[1] * k
    image = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(image)
    lw = max(1.0, width * 1.6) * k  # a little heavier than on the plot, to read at this size
    y = h / 2
    pattern = DASHES.get("-" if style == "auto" else style)
    if style != "none":
        if pattern is None:
            draw.line((0, y, w, y), fill=colour, width=round(lw))
        else:
            x, i = 0.0, 0
            while x < w:
                length = pattern[i % len(pattern)] * lw
                if i % 2 == 0:
                    draw.line((x, y, min(x + length, w), y), fill=colour, width=round(lw))
                x, i = x + length, i + 1
    r = 2.6 * k
    for cx in (w * 0.2, w * 0.5, w * 0.8) if marker else ():
        box = (cx - r, y - r, cx + r, y + r)
        if marker == ".":
            draw.ellipse((cx - r / 2, y - r / 2, cx + r / 2, y + r / 2), fill=colour)
        elif marker == "o":
            draw.ellipse(box, fill=colour)
        elif marker == "s":
            draw.rectangle(box, fill=colour)
        elif marker == "^":
            draw.polygon(((cx - r, y + r), (cx + r, y + r), (cx, y - r)), fill=colour)
        elif marker == "x":
            draw.line(box, fill=colour, width=k * 2)
            draw.line((cx - r, y + r, cx + r, y - r), fill=colour, width=k * 2)
    return ImageTk.PhotoImage(image.resize(size, Image.LANCZOS))


class LineStylePopup(tk.Toplevel):
    """Colour, line style, width, marker and its size, and legend name for the selected line,
    in its own window. Changes apply as they're made: `on_colour('#rrggbb')`,
    `on_reset()` for the automatic colour, and `on_change(merge, **settings)`
    for the rest, with `merge` true while a slider is being dragged."""

    WIDTHS = (0.2, 5.0)
    SIZES = (1.0, 12.0)

    def __init__(self, parent, on_change, on_colour, on_reset):
        super().__init__(parent)
        self.title("Line")
        self.resizable(False, False)
        self.transient(parent)
        self.on_change = on_change
        self.loading = False  # while show() fills the controls
        self.images = {}
        self.style, self.marker = tk.StringVar(), tk.StringVar()
        self.width, self.name = tk.DoubleVar(), tk.StringVar()
        self.size = tk.DoubleVar()
        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Colour", foreground=theme.MUTED).pack(anchor=tk.W)
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(2, 10))
        self.picker = ColourPicker(row, on_colour)
        self.picker.pack(side=tk.LEFT)
        side = ttk.Frame(row)
        side.pack(side=tk.LEFT, anchor=tk.N, padx=(12, 0))
        self.swatch = tk.Label(side, width=6, height=2, relief=tk.SOLID, borderwidth=1)
        self.swatch.pack(anchor=tk.W)
        self.hex = ttk.Label(side, font="TkFixedFont")
        self.hex.pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(side, text="Automatic", command=on_reset).pack(anchor=tk.W, pady=(8, 0))

        ttk.Label(body, text="Line", foreground=theme.MUTED).pack(anchor=tk.W)
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(2, 10))
        self.style_buttons = {}
        for key in STYLES:
            button = ttk.Radiobutton(row, variable=self.style, value=key, style="Toolbutton",
                                     compound=tk.TOP, text=STYLES[key],
                                     command=lambda: self._changed(style=self.style.get()))
            button.pack(side=tk.LEFT, padx=(0, 4))
            self.style_buttons[key] = button

        ttk.Label(body, text="Width", foreground=theme.MUTED).pack(anchor=tk.W)
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, fill=tk.X, pady=(2, 10))
        self.scale = ttk.Scale(row, from_=self.WIDTHS[0], to=self.WIDTHS[1], length=220,
                               variable=self.width, command=lambda _: self._slide("width"))
        self.scale.pack(side=tk.LEFT)
        self.scale.bind("<ButtonRelease-1>", lambda _: self._changed())  # the drag ends
        self.width_label = ttk.Label(row, width=9)
        self.width_label.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(row, text="Auto", command=lambda: self._changed(width=None)).pack(
            side=tk.LEFT)

        ttk.Label(body, text="Marker", foreground=theme.MUTED).pack(anchor=tk.W)
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(2, 4))
        self.marker_buttons = {}
        for key in MARKERS:
            button = ttk.Radiobutton(row, variable=self.marker, value=key, style="Toolbutton",
                                     compound=tk.TOP, text=MARKERS[key],
                                     command=lambda: self._changed(marker=self.marker.get()))
            button.pack(side=tk.LEFT, padx=(0, 4))
            self.marker_buttons[key] = button
        # Its size, like Width: the slider's text says when it's the automatic one.
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, fill=tk.X, pady=(0, 10))
        ttk.Label(row, text="Size", width=5).pack(side=tk.LEFT)
        self.size_scale = ttk.Scale(row, from_=self.SIZES[0], to=self.SIZES[1], length=180,
                                    variable=self.size, command=lambda _: self._slide("size"))
        self.size_scale.pack(side=tk.LEFT)
        self.size_scale.bind("<ButtonRelease-1>", lambda _: self._changed())
        self.size_label = ttk.Label(row, width=9)
        self.size_label.pack(side=tk.LEFT, padx=(8, 0))
        self.size_auto = ttk.Button(row, text="Auto",
                                    command=lambda: self._changed(marker_size=None))
        self.size_auto.pack(side=tk.LEFT)

        ttk.Label(body, text="Name in the legend", foreground=theme.MUTED).pack(anchor=tk.W)
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(2, 0))
        entry = ttk.Entry(row, textvariable=self.name, width=40)
        entry.pack(side=tk.LEFT)
        ttk.Button(row, text="Auto", command=lambda: self._changed(label=None)).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Label(body, text="Enter applies; clear it for none, Auto for the automatic one",
                  foreground=theme.HINT).pack(anchor=tk.W)
        for key in ("<Return>", "<KP_Enter>"):
            entry.bind(key, lambda _: self._changed(label=self.name.get().strip()))
        ttk.Button(body, text="Close", command=self.destroy).pack(anchor=tk.E, pady=(10, 0))
        self.bind("<Escape>", lambda _: self.destroy())

    def _slide(self, which):
        """A drag of the width or size slider; one undo step until it ends."""
        if self.loading:
            return
        value = round((self.width if which == "width" else self.size).get(), 1)
        (self.width_label if which == "width" else self.size_label)["text"] = f"{value:g}"
        self._changed(merge=True, **{"width" if which == "width" else "marker_size": value})

    def _changed(self, merge=False, **settings):
        if not self.loading:
            self.on_change(merge, **settings)

    def show(self, line, colour, move_picker=True, auto_name=""):
        """Show `line`'s settings, its previews in `colour`, without calling back;
        `auto_name` is its automatic legend name, shown when it has no name of its own.

        `move_picker` false: the colour came from the picker, which already shows
        it; moving it would round-trip through hex."""
        self.loading = True
        try:
            self.swatch["background"] = colour
            self.hex["text"] = colour
            if move_picker:
                self.picker.set(colour)
            self.style.set(line.style)
            self.marker.set(line.marker)
            width = line.auto_width if line.width is None else line.width
            self.width.set(width)
            self.width_label["text"] = f"{width:g}" + (" (auto)" if line.width is None else "")
            size = AUTO_MARKER_SIZE if line.marker_size is None else line.marker_size
            self.size.set(size)
            self.size_label["text"] = f"{size:g}" + (" (auto)" if line.marker_size is None else "")
            # Only a line with markers has a size to set.
            for widget in (self.size_scale, self.size_auto):
                widget.state(["!disabled" if line.marker else "disabled"])
            self.name.set(auto_name if line.label is None else line.label)
            # The lines alone and the markers alone, heavy enough to tell apart.
            for key, button in self.style_buttons.items():
                self.images["style", key] = line_sample(key, "", colour, 1.6)
                button["image"] = self.images["style", key]
            for key, button in self.marker_buttons.items():
                self.images["marker", key] = line_sample("none", key, colour)
                button["image"] = self.images["marker", key]
        finally:
            self.loading = False


class AxesPopup(tk.Toplevel):
    """The selected panel's ranges, title, axis labels, legend and grid, in their
    own window. Enter in a box, or a legend or grid button, calls `on_apply()`,
    which reads `values()`; Use current view calls `on_use_view()`, and a
    text's Auto `on_auto(name)`. The Ticks box is for every panel, not just
    this one: it calls `on_ticks(inward)`."""

    # Panel field -> its buttons' texts, for the Grid rows.
    GRID_ROWS = (("grid", "show", GRIDS), ("grid_axis", "axis", GRID_AXES),
                 ("grid_style", "style", GRID_STYLES))

    TEXTS = (("title", "Title"), ("x_label", "x label"), ("y_label", "y label"))

    def __init__(self, parent, on_apply, on_use_view, ticks_in, on_ticks, on_auto):
        super().__init__(parent)
        self.resizable(False, False)
        self.transient(parent)
        self.ranges = {name: tk.StringVar() for name in RANGES}
        self.texts = {name: tk.StringVar() for name, _ in self.TEXTS}
        self.legend = tk.StringVar()
        self.choices = {name: tk.StringVar() for name, _, _ in self.GRID_ROWS}
        body = ttk.Frame(self, padding=12)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(body, text="Range", foreground=theme.MUTED).pack(anchor=tk.W)
        boxes = []
        for axis in "xy":
            row = ttk.Frame(body)
            row.pack(anchor=tk.W, pady=(2, 0))
            ttk.Label(row, text=f"{axis} from", width=7).pack(side=tk.LEFT)
            for end, name in (("from", f"{axis}_min"), ("to", f"{axis}_max")):
                if end == "to":
                    ttk.Label(row, text="to").pack(side=tk.LEFT, padx=(6, 6))
                box = ttk.Entry(row, textvariable=self.ranges[name], width=12)
                box.pack(side=tk.LEFT)
                boxes.append(box)
        row = ttk.Frame(body)
        row.pack(anchor=tk.W, pady=(6, 10))
        ttk.Button(row, text="Use current view", command=on_use_view).pack(side=tk.LEFT)
        ttk.Label(row, text="blank: automatic", foreground=theme.HINT).pack(
            side=tk.LEFT, padx=(8, 0))

        ttk.Label(body, text="Text", foreground=theme.MUTED).pack(anchor=tk.W)
        for name, label in self.TEXTS:
            row = ttk.Frame(body)
            row.pack(anchor=tk.W, pady=(2, 0))
            ttk.Label(row, text=label, width=7).pack(side=tk.LEFT)
            box = ttk.Entry(row, textvariable=self.texts[name], width=30)
            box.pack(side=tk.LEFT)
            boxes.append(box)
            ttk.Button(row, text="Auto", width=5, command=lambda name=name: on_auto(name)).pack(
                side=tk.LEFT, padx=(6, 0))
        ttk.Label(body, text="clear for none, Auto for the automatic text; $B$ for maths",
                  foreground=theme.HINT).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(body, text="Legend", foreground=theme.MUTED).pack(anchor=tk.W)
        keys = list(LEGENDS)
        for chunk in (keys[:3], keys[3:]):  # two rows, to keep the window narrow
            row = ttk.Frame(body)
            row.pack(anchor=tk.W, pady=(2, 0))
            for key in chunk:
                ttk.Radiobutton(row, text=LEGENDS[key], variable=self.legend, value=key,
                                style="Toolbutton", command=on_apply).pack(
                    side=tk.LEFT, padx=(0, 4))

        ttk.Label(body, text="Grid", foreground=theme.MUTED).pack(anchor=tk.W, pady=(10, 0))
        for name, label, texts in self.GRID_ROWS:
            row = ttk.Frame(body)
            row.pack(anchor=tk.W, pady=(2, 0))
            ttk.Label(row, text=label, width=7).pack(side=tk.LEFT)
            for key, text in texts.items():
                ttk.Radiobutton(row, text=text, variable=self.choices[name], value=key,
                                style="Toolbutton", command=on_apply).pack(
                    side=tk.LEFT, padx=(0, 4))
        ttk.Label(body, text="Ticks", foreground=theme.MUTED).pack(anchor=tk.W, pady=(10, 0))
        self.ticks_in = tk.BooleanVar(value=ticks_in)
        ttk.Checkbutton(body, text="Point inward (all panels)", variable=self.ticks_in,
                        command=lambda: on_ticks(self.ticks_in.get())).pack(
            anchor=tk.W, pady=(2, 0))
        ttk.Label(body, text="Enter in a box applies", foreground=theme.HINT).pack(
            anchor=tk.W, pady=(10, 0))
        ttk.Button(body, text="Close", command=self.destroy).pack(anchor=tk.E, pady=(6, 0))
        for box in boxes:
            for key in ("<Return>", "<KP_Enter>"):
                box.bind(key, lambda _: on_apply())
        self.bind("<Escape>", lambda _: self.destroy())

    def values(self):
        """The boxes as typed ({name: text}), and the buttons' keys ({name: key}
        for the legend and grid)."""
        typed = {name: var.get() for name, var in (self.ranges | self.texts).items()}
        chosen = {name: var.get() for name, var in self.choices.items()}
        return typed, {"legend": self.legend.get()} | chosen

    def set_view(self, xlim, ylim):
        for axis, (low, high) in (("x", xlim), ("y", ylim)):
            self.ranges[f"{axis}_min"].set(f"{low:.6g}")
            self.ranges[f"{axis}_max"].set(f"{high:.6g}")

    def show(self, panel, number, auto):
        """Fill the boxes from `panel`, number `number` in the grid; a text left
        automatic shows the one drawn, from `auto` ({name: text})."""
        self.title(f"Axes of panel {number}")
        for name, var in self.ranges.items():
            value = getattr(panel, name)
            var.set("" if value is None else f"{value:.6g}")
        for name, var in self.texts.items():
            text = getattr(panel, name)
            var.set(auto.get(name, "") if text is None else text)
        self.legend.set(panel.legend)
        for name, var in self.choices.items():
            var.set(getattr(panel, name))
