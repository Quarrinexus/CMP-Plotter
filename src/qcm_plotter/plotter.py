"""Interactive plotter window: pick datasets and axes, plot, save. See README.md."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from PIL import Image, ImageDraw, ImageTk

from qcm_plotter.axis_functions import apply_function, is_identity, rename
from qcm_plotter.columns import label, with_unit, without_unit
from qcm_plotter.model import Panel, legend_labels, line_colours, shared
from qcm_plotter.profile import load_profile, save_format
from qcm_plotter.datasets import (FormatError, describe, detect_format, find_datasets,
                                  load_dataset, read_lines, run_number)
from qcm_plotter.format_dialog import FormatDialog
from qcm_plotter.settings import load_settings, save_settings
from qcm_plotter.widgets import SELECTED, ColourPopup, LayoutPicker


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
        self.title("QCM Plotter")
        self.geometry("1150x760")
        self.frames = {}  # dataset name -> DataFrame, so each file is read once
        self.datasets = {}  # dataset name -> file, from the data folder
        self.rows, self.cols = 1, 1
        self.panels = {(0, 0): Panel()}  # (row, col) -> Panel
        self.selected = (0, 0)
        self.axes = {}  # (row, col) -> matplotlib Axes
        self.artists = {}  # (row, col) -> {matplotlib Line2D: line index}
        self.colour_popup = None
        self.settings = load_settings()
        self.profile, profile_error = load_profile(self.data_dir)

        controls = ttk.Frame(self, padding=10)
        controls.pack(side=tk.LEFT, fill=tk.Y)
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

        # Saving sits at the bottom of the column.
        save = ttk.Frame(controls)
        save.pack(side=tk.BOTTOM, anchor=tk.W, fill=tk.X)
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

    def _folder_row(self, parent, label, key):
        """'Data folder' etc.: the chosen path, with Browse... to change it."""
        ttk.Label(parent, text=label).pack(anchor=tk.W, pady=(0, 2))
        row = ttk.Frame(parent)
        row.pack(anchor=tk.W, fill=tk.X, pady=(0, 6))
        ttk.Button(row, text="Browse...",
                   command=lambda: self.choose_folder(key, label)).pack(side=tk.RIGHT)
        path = ttk.Label(row, width=22, anchor=tk.W)
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
        self._say("")  # errors pop up instead; see apply_controls
        self._show_colour()

    def _fill_line_list(self):
        p, colours = self.panel, line_colours(self.panel, self.profile.samples)
        self.line_list.delete(0, tk.END)
        for l, colour in zip(p.lines, colours):
            name = f"{l.y} · {run_number(l.run) or l.run}" if l.run else "(no dataset)"
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
        if l.run in self.datasets and l.run not in self.frames:
            try:
                self._load(l)
            except FormatError as err:  # ask how the file is laid out
                self.edit_format(l.run, f"Couldn't read {l.run}: {err}")
                if l.run not in self.frames:  # still unreadable; don't pop up again
                    self._redraw_selected()
                    return
        self._redraw_selected()
        if l.error:  # a popup rather than text in the controls, to save room
            title = "Function error" if l.run in self.frames else "Could not load dataset"
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
        for i, (l, colour) in enumerate(zip(p.lines, line_colours(p, self.profile.samples))):
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
            ax.set_title(title(dict.fromkeys(l.run for l in drawn)))
            ax.grid(True, lw=0.4, alpha=0.8)
            if len(drawn) > 1:
                for artist, text in zip(ax.lines, legend_labels(drawn)):
                    artist.set_label(text)
                ax.legend(fontsize=8)
        elif errors:
            self._hint(ax, errors[0], colour="#b3261e", size=9)
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
        """Recolour the swatch and lines without a redraw, so zoom survives."""
        p = self.panel
        colours = line_colours(p, self.profile.samples)
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
        return f"{describe(run).replace(' ', '_')}_{y}_vs_{x}.png"

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
        self._frame(selected)
        try:
            self.fig.savefig(out_dir / name, dpi=200)
        finally:
            self.selected = selected
            self._frame(selected)
            self.canvas.draw()
        self._say(f"Saved {out_dir.name}/{name}")


if __name__ == "__main__":
    Plotter().mainloop()
