"""The panels and their lines as plain JSON-ready data, for session files and undo."""

from dataclasses import fields
import math

from goose_plotter import background, smoothing, spectrum
from goose_plotter.model import (GRID_AXES, GRID_STYLES, GRIDS, LEGENDS, MARKERS, OPERATIONS,
                                 STYLES, SYNC, Line, Panel)
from goose_plotter.widgets import MAX_GRID

VERSION = 2  # 2: derived panels have their own lines, in their data panel's link group
KEY = "goose_plotter_session"  # the session file's marker, holding VERSION
# `dump`'s own marker, so `load` reads undo snapshots and files alike; its
# absence means the layout of version 1, where a derived panel shared its
# data panel's lines and every panel carried an operation.
FORMAT = 2

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
    """The layout and every panel's settings and lines, with a derived panel's
    source cell while it has one."""
    out = {}
    for cell, p in sorted(panels.items()):
        data = _plain(p)
        data["lines"] = [_plain(l) for l in p.lines]
        if p.source is not None:
            data["source"] = cell_key(p.source)
        out[cell_key(cell)] = data
    return {"format": FORMAT, "rows": rows, "cols": cols, "panels": out}


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
    if state.get("format") != FORMAT:
        return rows, cols, _load_old(saved, grid)
    panels = {}
    for cell in grid:
        data = saved.get(cell)
        if data is None:
            panels[cell] = Panel()
            continue
        lines = [_build(Line, l) for l in data.get("lines") or []] or [Line()]
        panels[cell] = _build(Panel, data, lines=lines, source=_source(data, grid))
    return rows, cols, panels


def _source(data, grid):
    """The cell in `data`'s "source", if it's one of the grid's."""
    try:
        source = key_cell(data["source"])
    except (TypeError, KeyError, ValueError, AttributeError):
        return None
    return source if source in grid else None


def _load_old(saved, grid):
    """Panels from a version 1 layout. There a derived panel had a source and
    no lines of its own, and all panels an operation ("fft" by default). Here
    it gets copies of its data panel's lines, in its link group, sharing
    everything, as that list did."""
    panels = {}
    for cell in grid:  # data panels first: derived panels copy their lines
        data = saved.get(cell)
        if data is None or (isinstance(data, dict) and "source" in data):
            continue
        lines = [_build(Line, l) for l in data.get("lines") or []] or [Line()]
        panels[cell] = _build(Panel, data, lines=lines)
        panels[cell].operation = ""
    groups = [p.link_group for p in panels.values() if p.link_group is not None]
    for cell in grid:
        data = saved.get(cell)
        if cell in panels:
            continue
        source = _source(data, grid) if isinstance(data, dict) else None
        if source not in panels:  # missing, or its data panel isn't there: an empty panel
            panels[cell] = Panel()
            continue
        data_panel = panels[source]
        p = _build(Panel, data, lines=[l.copy() for l in data_panel.lines], source=source)
        p.operation = p.operation or "fft"
        if data_panel.link_group is None:
            data_panel.link_group = max(groups, default=0) + 1
            groups.append(data_panel.link_group)
        p.link_group = data_panel.link_group
        p.selected = min(data_panel.selected, len(p.lines) - 1)
        data_panel.sync = p.sync = " ".join(SYNC)
        panels[cell] = p
    return panels
