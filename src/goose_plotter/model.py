"""What's plotted: panels holding lines, and how those lines are coloured and labelled."""

from dataclasses import dataclass, field, replace
from uuid import uuid4

from matplotlib.colors import to_rgb
import numpy as np

from goose_plotter.axis_functions import file_part
from goose_plotter.columns import sample_of
from goose_plotter.datasets import describe
from goose_plotter.background import describe as describe_background
from goose_plotter.splicing import describe as describe_cut
from goose_plotter.smoothing import describe as describe_smoothing

# What a link between two panels can share, line by line: a Link's `sync`
# names the keys it shares.
SYNC = {"run": ("run",), "x": ("x",), "x_fn": ("x_fn",), "y": ("y",), "y_fn": ("y_fn",),
        "colour": ("colour",), "cut": ("cut", "cut_from", "cut_to"),
        "smoothing": ("smooth", "window", "in_x", "span", "order"),
        "background": ("background", "degree", "fit_from", "fit_to"),
        "style": ("style", "width", "marker", "marker_size")}
SYNC_DEFAULT = "run x x_fn y y_fn colour style"
X_UNITS = ("span", "fit_from", "fit_to", "cut_from", "cut_to")  # settings in the plotted x

AUTO_MARKER_SIZE = 3.0  # matplotlib's markersize, in points

NEUTRAL = "#2464d6"  # line colour when no sample column is plotted

# Colours for extra lines once a panel's sample colours are taken.
PALETTE = ("#2464d6", "#eb6834", "#2e9e5b", "#8e5bd1", "#c23b6e", "#1a9aa0",
           "#b58900", "#52514e")


@dataclass
class Line:
    """One plotted line. x and y are column names."""
    run: str = ""
    x: str = ""  # "": the profile's default, see Plotter._load
    x_fn: str = "x"
    y: str = ""
    y_fn: str = "y"
    smooth: str = ""  # a key of smoothing.METHODS; "" for none
    window: int = 21  # smoothing window, in points
    in_x: bool = False  # window counted in the plotted x (span) instead of points
    span: float | None = None  # window in x; None: estimated from `window` when drawn
    background: str = ""  # a key of background.MODES; "" for off
    degree: int = 10  # of the background polynomial
    fit_from: float | None = None  # the fit's x range; None: no limit
    fit_to: float | None = None
    order: int = 2  # Savitzky–Golay polynomial order
    cut: str = ""  # a key of splicing.MODES; "" for off
    cut_from: float | None = None  # the cut's x range; None: no limit
    cut_to: float | None = None
    colour: str | None = None  # None: picked automatically, see line_colours
    # How it's drawn; not in `shown`, so changing them keeps the zoom.
    style: str = "auto"  # a key of STYLES
    width: float | None = None  # None: auto_width
    marker: str = ""  # a key of MARKERS
    marker_size: float | None = None  # None: AUTO_MARKER_SIZE
    label: str | None = None  # its name in the legend; None: the automatic one, "": none
    shown: tuple | None = None  # (run, x, x_fn, y, y_fn, smoothing, fitting, cutting) as last drawn
    error: str = ""  # why the last draw failed, if it did

    def copy(self):
        return replace(self, shown=None, error="")

    @property
    def auto_width(self):
        """The width when none is set: a shown fit is a little heavier, as it's dashed."""
        return 1.0 if self.background == "fit" else 0.7

    def plot_style(self):
        """matplotlib keywords for its line and markers (colour aside)."""
        dashed = self.background == "fit"  # a shown fit reads as a fit laid over the data
        style = ("--" if dashed else "-") if self.style == "auto" else self.style
        kwargs = {"ls": "None" if style == "none" else style,
                  "lw": self.auto_width if self.width is None else self.width}
        if self.marker:
            kwargs |= {"marker": self.marker,
                       "ms": AUTO_MARKER_SIZE if self.marker_size is None else self.marker_size}
        return kwargs

    @property
    def smoothing(self):
        """(method, window or span, order, in_x), or None when unsmoothed."""
        if not self.smooth:
            return None
        return (self.smooth, self.span if self.in_x else self.window, self.order, self.in_x)

    @property
    def fitting(self):
        """(mode, degree, fit_from, fit_to), or None when the background is off."""
        if not self.background:
            return None
        return (self.background, self.degree, self.fit_from, self.fit_to)

    @property
    def cutting(self):
        """(mode, cut_from, cut_to), or None when the line isn't cut."""
        if not self.cut or (self.cut_from is None and self.cut_to is None):
            return None
        return (self.cut, self.cut_from, self.cut_to)

    def parts(self):
        """(run, y part, x part, smoothing, fitting, cutting) as they'd appear in a filename."""
        run, x, x_fn, y, y_fn, smoothed, fitted, cut = self.shown
        return run, file_part(y_fn, y), file_part(x_fn, x), smoothed, fitted, cut


@dataclass
class Link:
    """A link between two panels (the Plotter keeps them by the pair of their
    ids): which settings it shares, line by line, both ways, and whether it's
    frozen, kept but sharing nothing for now."""
    sync: str = SYNC_DEFAULT  # SYNC keys, space-separated
    frozen: bool = False

    @property
    def synced(self):
        """The SYNC keys in `sync` (unknown words, e.g. from a session, are ignored)."""
        return set(self.sync.split()) & set(SYNC)


@dataclass
class Panel:
    """One subplot: its lines and which of them the controls edit.

    A derived panel (an FFT or a derivative, by `operation`) draws that of its
    lines. It's made in its data panel's link group, with copies of its lines,
    so the two stay in step through the link (and can be frozen or partly
    synced); `source` is that data panel's cell while it still follows it.
    `id` names the panel for its links, as its cell can change."""
    lines: list = field(default_factory=lambda: [Line()])
    selected: int = 0
    source: tuple | None = None
    operation: str = ""  # a key of OPERATIONS; "" for a data panel
    window: str = "hann"  # FFT window, a key of spectrum.WINDOWS
    pad: int = 1  # FFT zero-padding factor
    f_max: float | None = None  # highest frequency drawn; None: all
    derivative_window: int = 51  # derivative panels: grid points per fit, odd
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    # Typed axis ranges, in the plotted units; None: that end is automatic.
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    # Typed text; None for the automatic one, "" for none. Mathtext like $B$ works.
    title: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    legend: str = "auto"  # a key of LEGENDS
    grid: str = "major"  # a key of GRIDS
    grid_axis: str = "both"  # a key of GRID_AXES
    grid_style: str = "-"  # a key of GRID_STYLES

    @property
    def line(self):
        return self.lines[self.selected]

    @property
    def derived(self):
        return bool(self.operation)

    def copy(self):
        """An independent data panel with copies of the lines (and nothing else of
        the panel's: ranges and such start fresh)."""
        return Panel([l.copy() for l in self.lines], self.selected)


# Line style and marker -> the text in their menus.
STYLES = {"auto": "Auto", "-": "Solid", "--": "Dashed", ":": "Dotted", "-.": "Dash-dot",
          "none": "None"}
MARKERS = {"": "None", ".": "Dots", "o": "Circles", "s": "Squares", "^": "Triangles",
           "x": "Crosses"}

RANGES = ("x_min", "x_max", "y_min", "y_max")

# Legend placement -> the text in its menu. "auto": only with two or more
# lines, wherever there's room; a placement shows it even for one line.
LEGENDS = {"auto": "Auto", "off": "Off", "upper right": "Top right",
           "upper left": "Top left", "lower left": "Bottom left",
           "lower right": "Bottom right", "outside": "Outside right"}


# What a panel draws of its lines: the lines themselves, their FFT, or a derivative.
OPERATIONS = ("", "fft", "d1", "d2")

# Grid lines -> the text on their buttons. "minor" draws the major lines too.
GRIDS = {"off": "Off", "major": "Major", "minor": "Major + minor"}
GRID_AXES = {"both": "Both", "x": "x only", "y": "y only"}
GRID_STYLES = {"-": "Solid", "--": "Dashed", ":": "Dotted"}


def clear_ranges(panel, axes="xy"):
    """Forget typed ranges on those axes, e.g. when what's plotted on them changes."""
    for name in RANGES:
        if name[0] in axes:
            setattr(panel, name, None)


def near(colour, others, distance=0.25):
    """True if `colour` is hard to tell from any of `others` (RGB distance)."""
    rgb = np.array(to_rgb(colour))
    return any(np.linalg.norm(rgb - to_rgb(o)) < distance for o in others)


def line_colours(panel, samples):
    """Each line's colour: its pick, else its sample's, else an unused PALETTE one."""
    colours = [l.colour for l in panel.lines]
    used = [c for c in colours if c]
    for i, l in enumerate(panel.lines):
        if colours[i]:
            continue
        wanted = samples.get(sample_of(samples, l.y, l.x), NEUTRAL)
        if near(wanted, used):
            wanted = next((c for c in PALETTE if not near(c, used)),
                          PALETTE[len(used) % len(PALETTE)])
        colours[i] = wanted
        used.append(wanted)
    return colours


def legend_labels(lines):
    """Legend text naming only what differs between the lines."""
    parts = [l.parts() for l in lines]
    differs = [len({p[i] for p in parts}) > 1 for i in range(6)]
    if not any(differs[:3]):
        differs[1] = True  # identical, or only processed differently: say what's on y
    labels = []
    for run, y, x, smoothed, fitted, cut in parts:
        bits = [describe(run)] if differs[0] else []
        if differs[1]:
            bits.append(y)
        if differs[2]:
            bits.append(f"vs {x}")
        if differs[3] and smoothed:
            bits.append(describe_smoothing(*smoothed))
        if differs[4] and fitted:
            bits.append(describe_background(*fitted))
        if differs[5] and cut:
            bits.append(describe_cut(*cut))
        labels.append(" · ".join(bits))
    return labels


def shared(labels):
    """One axis label for several lines, from (full, without-sample) pairs."""
    for texts in zip(*labels):
        unique = list(dict.fromkeys(texts))
        if len(unique) == 1:
            return unique[0]
    return " / ".join(dict.fromkeys(plain for _, plain in labels))
