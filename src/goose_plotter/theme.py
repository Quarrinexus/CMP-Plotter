"""The window's colours, and the ttk styling that uses them."""

import tkinter as tk
from tkinter import ttk

BACKGROUND = "#f7f7f5"  # the window
SURFACE = "#ffffff"  # entry fields, buttons, lists
HOVER = "#f0efeb"  # a button under the mouse
PRESSED = "#e6e5e0"
BORDER = "#d6d5cf"
BORDER_HOVER = "#b4b3ac"
TEXT = "#1f1f1c"
MUTED = "#52514e"  # section toggles, notes
HINT = "#8c8b85"  # examples and "blank: ..." notes
ACCENT = "#2464d6"  # focus, selection, sliders; the same blue as the first line
ACCENT_SOFT = "#dde8fb"  # selected rows
SELECTED_ROW = "#ebeae6"  # selected line in the Lines list, whose text is the line's colour
ERROR = "#b3261e"
OK = "#2e7d32"


def apply(root):
    """Style ttk (on top of clam) and the plain Tk widgets made after this."""
    style = ttk.Style(root)
    style.theme_use("clam")  # looks the same on every platform
    # clam draws bevels with lightcolor/darkcolor; matching them flattens it.
    style.configure(".", background=BACKGROUND, foreground=TEXT, bordercolor=BORDER,
                    lightcolor=SURFACE, darkcolor=SURFACE, troughcolor=BACKGROUND,
                    fieldbackground=SURFACE, selectbackground=ACCENT_SOFT,
                    selectforeground=TEXT, insertcolor=TEXT, focuscolor=ACCENT,
                    arrowcolor=MUTED)
    style.map(".", foreground=[("disabled", HINT)])
    style.configure("TButton", background=SURFACE)
    style.map("TButton",
              background=[("disabled", BACKGROUND), ("pressed", PRESSED), ("active", HOVER)],
              bordercolor=[("disabled", BORDER), ("active", BORDER_HOVER)],
              lightcolor=[("pressed", PRESSED), ("active", HOVER)],
              darkcolor=[("pressed", PRESSED), ("active", HOVER)])
    for field in ("TEntry", "TCombobox", "TSpinbox"):
        style.map(field,
                  bordercolor=[("focus", ACCENT), ("hover", BORDER_HOVER)],
                  lightcolor=[("focus", ACCENT)],
                  fieldbackground=[("readonly", SURFACE), ("disabled", BACKGROUND)])
    for arrows in ("TCombobox", "TSpinbox"):
        style.configure(arrows, background=SURFACE)
        style.map(arrows, background=[("pressed", PRESSED), ("active", HOVER)])
    style.configure("TScrollbar", background=BORDER, bordercolor=BACKGROUND,
                    lightcolor=BORDER, darkcolor=BORDER, gripsize=0)
    style.map("TScrollbar", background=[("pressed", BORDER_HOVER), ("active", BORDER_HOVER)],
              lightcolor=[("active", BORDER_HOVER)], darkcolor=[("active", BORDER_HOVER)])
    style.configure("TSeparator", background=BORDER)
    # Toolbuttons: the line editor's pick-one pictures. Box.TButton: the small
    # buttons beside the Lines list, which share the list's height.
    style.configure("Toolbutton", background=SURFACE, bordercolor=BORDER, padding=(6, 4))
    style.map("Toolbutton",
              background=[("selected", ACCENT_SOFT), ("pressed", PRESSED), ("active", HOVER)],
              bordercolor=[("selected", ACCENT), ("active", BORDER_HOVER)],
              lightcolor=[("selected", ACCENT_SOFT), ("active", HOVER)],
              darkcolor=[("selected", ACCENT_SOFT), ("active", HOVER)])
    style.configure("Box.TButton", padding=0)
    style.configure("TScale", background=SURFACE, bordercolor=BORDER_HOVER, gripsize=0,
                    troughcolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE, sliderlength=14)
    style.map("TScale", background=[("pressed", PRESSED), ("active", HOVER)])
    style.configure("Treeview", background=SURFACE)
    style.configure("Treeview.Heading", background=BACKGROUND, relief=tk.FLAT)
    style.map("Treeview.Heading", background=[("active", HOVER)])

    # Plain Tk widgets: the Lines list, combobox drop-downs, the Data format
    # text, dialogs and matplotlib's toolbar.
    for pattern, value in (
            ("*Background", BACKGROUND), ("*Foreground", TEXT),
            ("*activeBackground", HOVER), ("*highlightBackground", BACKGROUND),
            ("*highlightColor", ACCENT), ("*troughColor", BACKGROUND),
            ("*Listbox.background", SURFACE), ("*Listbox.selectBackground", SELECTED_ROW),
            ("*Listbox.relief", tk.FLAT), ("*Listbox.highlightThickness", 1),
            ("*Listbox.highlightBackground", BORDER),
            ("*TCombobox*Listbox.selectBackground", ACCENT_SOFT),
            ("*TCombobox*Listbox.selectForeground", TEXT),
            ("*Text.background", SURFACE), ("*Text.relief", tk.FLAT),
            ("*Text.highlightThickness", 1), ("*Text.highlightBackground", BORDER)):
        root.option_add(pattern, value)
    root.configure(background=BACKGROUND)
