"""The Data format window: say how a folder's files are laid out when detection fails."""

import tkinter as tk
from tkinter import ttk

from cmp_plotter.datasets import FormatError, parse

PREVIEW_LINES = 40  # of the raw file
PREVIEW_ROWS = 5  # of the parsed table
HEADER_COLOUR, DATA_COLOUR = "#fbe3bd", "#d6e6fa"

# Delimiter menu text -> name saved in the format ("Other" uses the box beside it).
CHOICES = {"Tab": "tab", "Comma": "comma", "Semicolon": "semicolon", "Spaces": "whitespace"}


class FormatDialog(tk.Toplevel):
    """Modal. When closed: `fmt` is the chosen format (None: automatic), unless `cancelled`."""

    def __init__(self, parent, name, lines, fmt, reason=""):
        super().__init__(parent)
        self.title(f"Data format - {name}")
        self.transient(parent)
        self.lines, self.fmt, self.cancelled = lines, None, True

        body = ttk.Frame(self, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=reason or "How the files in this data folder are laid out.",
                  foreground="#b3261e" if reason else "#52514e",
                  wraplength=640).pack(anchor=tk.W)
        ttk.Label(body, text=f"Start of {name} (column names orange, first data line blue):",
                  foreground="#52514e").pack(anchor=tk.W, pady=(8, 2))
        self.raw = self._scrolled(body, lambda frame: tk.Text(
            frame, height=14, width=100, wrap=tk.NONE, font="TkFixedFont"))
        self.raw.tag_configure("header", background=HEADER_COLOUR)
        self.raw.tag_configure("data", background=DATA_COLOUR)
        for i, line in enumerate(lines[:PREVIEW_LINES], 1):
            self.raw.insert(tk.END, f"{i:4d}  {line[:300]}\n")
        self.raw.configure(state=tk.DISABLED)

        choices = ttk.Frame(body)
        choices.pack(anchor=tk.W, pady=(10, 0))
        names = {v: k for k, v in CHOICES.items()}
        self.delimiter = tk.StringVar(value=names.get(fmt["delimiter"], "Other"))
        self.other = tk.StringVar(value="" if fmt["delimiter"] in names else fmt["delimiter"])
        self.header = tk.IntVar(value=fmt["header_line"])
        self.data = tk.IntVar(value=fmt["data_line"])
        ttk.Label(choices, text="Delimiter").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(choices, textvariable=self.delimiter, values=[*CHOICES, "Other"],
                     state="readonly", width=10).grid(row=1, column=0, sticky=tk.W)
        self.other_box = ttk.Entry(choices, textvariable=self.other, width=4)
        self.other_box.grid(row=1, column=1, padx=(4, 16))
        ttk.Label(choices, text="Column names on line (0: none)").grid(
            row=0, column=2, sticky=tk.W)
        ttk.Spinbox(choices, textvariable=self.header, from_=0, to=len(lines),
                    width=6).grid(row=1, column=2, sticky=tk.W)
        ttk.Label(choices, text="Data starts on line").grid(row=0, column=3, sticky=tk.W,
                                                            padx=(16, 0))
        ttk.Spinbox(choices, textvariable=self.data, from_=1, to=len(lines),
                    width=6).grid(row=1, column=3, sticky=tk.W, padx=(16, 0))

        self.summary = ttk.Label(body)
        self.summary.pack(anchor=tk.W, pady=(10, 2))
        self.table = self._scrolled(body, lambda frame: ttk.Treeview(
            frame, show="headings", height=PREVIEW_ROWS))

        buttons = ttk.Frame(body)
        buttons.pack(anchor=tk.E, pady=(10, 0))
        ttk.Button(buttons, text="Use automatic detection",
                   command=lambda: self._close(None)).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=(6, 0))
        self.save_button = ttk.Button(buttons, text="Save for this folder",
                                      command=lambda: self._close(self._format()))
        self.save_button.pack(side=tk.LEFT, padx=(6, 0))

        for var in (self.delimiter, self.other, self.header, self.data):
            var.trace_add("write", lambda *_: self._schedule())
        self.bind("<Escape>", lambda _: self.destroy())
        self._pending = None
        self._update()
        self.grab_set()
        self.focus_set()

    @staticmethod
    def _scrolled(parent, make):
        """The widget `make(frame)` returns, packed into `parent` with scrollbars."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True)
        widget = make(frame)
        widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        x = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=widget.xview)
        x.pack(side=tk.BOTTOM, fill=tk.X, before=widget)
        widget.configure(xscrollcommand=x.set)
        if isinstance(widget, tk.Text):
            y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=widget.yview)
            y.pack(side=tk.RIGHT, fill=tk.Y, before=widget)
            widget.configure(yscrollcommand=y.set)
        return widget

    def _format(self):
        choice = self.delimiter.get()
        return {"delimiter": CHOICES.get(choice) or self.other.get(),
                "header_line": self.header.get(), "data_line": self.data.get()}

    def _schedule(self):
        """Re-read after typing pauses, rather than on every keystroke."""
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(200, self._update)

    def _update(self):
        self._pending = None
        self.other_box.state(["!disabled" if self.delimiter.get() == "Other" else "disabled"])
        self.table.delete(*self.table.get_children())
        self.raw.tag_remove("header", "1.0", tk.END)
        self.raw.tag_remove("data", "1.0", tk.END)
        try:
            fmt = self._format()
            if not fmt["delimiter"]:
                raise FormatError("type the delimiter in the box beside Other")
            for tag, line in (("header", fmt["header_line"]), ("data", fmt["data_line"])):
                if 0 < line <= PREVIEW_LINES:
                    self.raw.tag_add(tag, f"{line}.0", f"{line + 1}.0")
            df = parse(self.lines, fmt)
        except (tk.TclError, FormatError) as err:  # TclError: a spinbox isn't a number
            message = "line numbers must be whole numbers" if isinstance(err, tk.TclError) else err
            self.summary.configure(text=f"Can't read the file this way: {message}",
                                   foreground="#b3261e")
            self.table["columns"] = ()
            self.save_button.state(["disabled"])
            return
        plural = "s" if len(df.columns) != 1 else ""
        self.summary.configure(text=f"{len(df.columns)} column{plural}, {len(df)} rows",
                               foreground="#2e7d32")
        self.table["columns"] = list(range(len(df.columns)))
        for i, column in enumerate(df.columns):
            self.table.heading(i, text=column)
            self.table.column(i, width=110, stretch=False)
        for row in df.head(PREVIEW_ROWS).itertuples(index=False):
            self.table.insert("", tk.END, values=[f"{v:.6g}" if isinstance(v, float) else v
                                                  for v in row])
        self.save_button.state(["!disabled"])

    def _close(self, fmt):
        self.fmt, self.cancelled = fmt, False
        self.destroy()
