"""What's plotted: panels holding lines, and how those lines are coloured and labelled."""

from dataclasses import dataclass, field, replace

from matplotlib.colors import to_rgb
import numpy as np

from general_plotter.axis_functions import file_part
from general_plotter.columns import sample_of
from general_plotter.runs import SAMPLES

DEFAULT_X = "Norminal_FIeld"
DEFAULT_Y = "M006_AH"
NEUTRAL = "#2464d6"  # line colour when no sample column is plotted

# Colours for extra lines once a panel's sample colours are taken.
PALETTE = ("#2464d6", "#eb6834", "#2e9e5b", "#8e5bd1", "#c23b6e", "#1a9aa0",
           "#b58900", "#52514e")


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
    """Each line's colour: its pick, else its sample's, else an unused PALETTE one."""
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
    """One axis label for several lines, from (full, without-sample) pairs."""
    for texts in zip(*labels):
        unique = list(dict.fromkeys(texts))
        if len(unique) == 1:
            return unique[0]
    return " / ".join(dict.fromkeys(plain for _, plain in labels))
