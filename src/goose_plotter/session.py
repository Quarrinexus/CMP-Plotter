"""The panels and their lines as plain JSON-ready data, for session files and undo."""

from dataclasses import fields
import math

from goose_plotter import background, smoothing, spectrum
from goose_plotter.model import (GRID_AXES, GRID_STYLES, GRIDS, LEGENDS, MARKERS, OPERATIONS,
                                 STYLES, Line, Panel)
from goose_plotter.widgets import MAX_GRID

VERSION = 1
KEY = "goose_plotter_session"  # the session file's marker, holding VERSION

# Not saved: what the last draw found, and which line the controls edit.
SKIP = {"shown", "error", "lines", "selected", "source"}
# Settings that must be one of a menu's keys; anything else gets the default.
# Per class: a Line's window is smoothing's, in points; a Panel's is the FFT's.
CHOICES = {Line: {"smooth": smoothing.METHODS, "background": background.MODES,
                  "style": STYLES, "marker": MARKERS},
           Panel: {"legend": LEGENDS, "grid": GRIDS, "grid_axis": GRID_AXES,
                   "grid_style": GRID_STYLES, "operation": OPERATIONS, "window": spectrum.WINDOWS,
                   "pad": spectrum.PADDING}}

# Numbers that only make sense above 0, per class as for CHOICES; the
# controls refuse the rest too.
POSITIVE = {Line: {"width", "marker_size", "window", "span"},
            Panel: {"f_max", "derivative_window"}}


def cell_key(cell):
    return f"{cell[0]},{cell[1]}"


def key_cell(key):
    r, c = key.split(",")
    return int(r), int(c)


def _plain(obj):
    return {f.name: getattr(obj, f.name) for f in fields(obj) if f.name not in SKIP}


def dump(panels, rows, cols):
    """The layout and every panel's settings. A derived panel (an FFT or a
    derivative) stores its source cell instead of lines: on loading it shares
    its data panel's list again."""
    out = {}
    for cell, p in sorted(panels.items()):
        data = _plain(p)
        if p.source is None:
            data["lines"] = [_plain(l) for l in p.lines]
        else:
            data["source"] = cell_key(p.source)
        out[cell_key(cell)] = data
    return {"rows": rows, "cols": cols, "panels": out}


def _allowed(f, value):
    """Whether `value` fits field `f`'s type (from its annotation, e.g. 'float | None')."""
    kind = str(f.type)
    if value is None:
        return "None" in kind
    if isinstance(value, bool):
        return "bool" in kind
    if isinstance(value, (int, float)):
        if not math.isfinite(value):  # JSON's NaN and Infinity would break drawing
            return False
        return "float" in kind or ("int" in kind and isinstance(value, int))
    return isinstance(value, str) and "str" in kind


def _build(cls, data, **extra):
    """A `cls` from `data`, keeping only known fields of the right type."""
    if not isinstance(data, dict):
        raise ValueError(f"expected an object for a {cls.__name__.lower()}")
    kwargs = {}
    for f in fields(cls):
        if f.name in SKIP or f.name not in data or not _allowed(f, data[f.name]):
            continue
        value = data[f.name]
        if f.name in CHOICES[cls] and value not in CHOICES[cls][f.name]:
            continue
        if f.name in POSITIVE[cls] and value is not None and value <= 0:
            continue
        kwargs[f.name] = value
    return cls(**kwargs, **extra)


def load(state):
    """(rows, cols, panels) from `dump`'s output. Raises ValueError if it isn't one."""
    try:
        rows, cols = int(state["rows"]), int(state["cols"])
        saved = {key_cell(k): v for k, v in state["panels"].items()}
    except (KeyError, TypeError, ValueError, AttributeError) as err:
        raise ValueError(f"not a session ({err})") from None
    if not (1 <= rows <= MAX_GRID and 1 <= cols <= MAX_GRID):
        raise ValueError(f"a {rows} x {cols} layout is bigger than the plotter allows")
    grid = [(r, c) for r in range(rows) for c in range(cols)]
    panels = {}
    for cell in grid:  # data panels first: derived panels need their lists
        data = saved.get(cell)
        if data is None or (isinstance(data, dict) and "source" in data):
            continue
        lines = [_build(Line, l) for l in data.get("lines") or []] or [Line()]
        panels[cell] = _build(Panel, data, lines=lines)
    for cell in grid:
        data = saved.get(cell)
        if cell in panels:
            continue
        try:
            source = key_cell(data["source"])
        except (TypeError, KeyError, ValueError, AttributeError):
            source = None
        if source in panels and panels[source].source is None:
            panels[cell] = _build(Panel, data, lines=panels[source].lines, source=source)
        else:  # missing, or its data panel isn't there: an empty panel
            panels[cell] = Panel()
    return rows, cols, panels
