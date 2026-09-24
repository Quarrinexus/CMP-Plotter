"""What's plotted: panels holding lines, and how those lines are coloured and labelled."""

from dataclasses import dataclass, field, replace

from matplotlib.colors import to_rgb
import numpy as np

from cmp_plotter.axis_functions import file_part
from cmp_plotter.columns import sample_of
from cmp_plotter.datasets import describe
from cmp_plotter.background import describe as describe_background
from cmp_plotter.smoothing import describe as describe_smoothing

# What linked panels share, line by line: the data input, and the colour.
LINKED = ("run", "x", "x_fn", "y", "y_fn", "colour")

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
    colour: str | None = None  # None: picked automatically, see line_colours
    shown: tuple | None = None  # (run, x, x_fn, y, y_fn, smoothing, fitting) as last drawn
    error: str = ""  # why the last draw failed, if it did

    def copy(self):
        return replace(self, shown=None, error="")

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

    def parts(self):
        """(run, y part, x part, smoothing, fitting) as they'd appear in a filename."""
        run, x, x_fn, y, y_fn, smoothed, fitted = self.shown
        return run, file_part(y_fn, y), file_part(x_fn, x), smoothed, fitted


@dataclass
class Panel:
    """One subplot: its lines and which of them the controls edit.

    An FFT panel has a `source`, the cell of a data panel, and shares that
    panel's `lines` list itself, so the two stay locked together."""
    lines: list = field(default_factory=lambda: [Line()])
    selected: int = 0
    source: tuple | None = None
    window: str = "hann"  # FFT window, a key of spectrum.WINDOWS
    pad: int = 1  # FFT zero-padding factor
    f_max: float | None = None  # highest frequency drawn; None: all
    link_group: int | None = None  # panels with the same number plot the same data

    @property
    def line(self):
        return self.lines[self.selected]

    def copy(self):
        """An independent data panel with copies of the lines."""
        return Panel([l.copy() for l in self.lines], self.selected)


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
    differs = [len({p[i] for p in parts}) > 1 for i in range(5)]
    if not any(differs[:3]):
        differs[1] = True  # identical, or only processed differently: say what's on y
    labels = []
    for run, y, x, smoothed, fitted in parts:
        bits = [describe(run)] if differs[0] else []
        if differs[1]:
            bits.append(y)
        if differs[2]:
            bits.append(f"vs {x}")
        if differs[3] and smoothed:
            bits.append(describe_smoothing(*smoothed))
        if differs[4] and fitted:
            bits.append(describe_background(*fitted))
        labels.append(" · ".join(bits))
    return labels


def shared(labels):
    """One axis label for several lines, from (full, without-sample) pairs."""
    for texts in zip(*labels):
        unique = list(dict.fromkeys(texts))
        if len(unique) == 1:
            return unique[0]
    return " / ".join(dict.fromkeys(plain for _, plain in labels))
