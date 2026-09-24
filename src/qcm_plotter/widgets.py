"""Tk widgets used by the main window: the colour picker and the layout grid."""

import tkinter as tk
from tkinter import ttk

from matplotlib.colors import hsv_to_rgb, rgb_to_hsv, to_hex, to_rgb
import numpy as np
from PIL import Image, ImageTk

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
