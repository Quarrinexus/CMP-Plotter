"""The panels and their lines as plain JSON-ready data, for session files and undo."""

from dataclasses import fields
import math

from goose_plotter import background, smoothing, spectrum, splicing
from goose_plotter.model import (GRID_AXES, GRID_STYLES, GRIDS, LEGENDS, MARKERS, OPERATIONS,
                                 STYLES, SYNC, Line, Link, Panel)
from goose_plotter.widgets import MAX_GRID

# 2: derived panels have their own lines, in their data panel's link group.
# 3: a title, axis label or legend name of None is the automatic one, "" none.
# 4: links are between pairs of panels, each with its own ticks and freeze.
# 5: lines can be cut (Splicing), and links can share the cut.
# 6: a line's cut is a list of ranges, all kept or all removed.
VERSION = 6
KEY = "goose_plotter_session"  # the session file's marker, holding VERSION
# `dump`'s own marker, so `load` reads undo snapshots and files alike; its
# absence means the layout of version 1, where a derived panel shared its
# data panel's lines and every panel carried an operation. Before 3, "" was
# the automatic text; before 4, links were groups, each panel with its ticks;
# before 5, there was no cut to share; in 5, a line had one cut range.
FORMAT = 6
TEXTS = {Panel: ("title", "x_label", "y_label"), Line: ("label",)}

# Not saved: what the last draw found, and which line the controls edit.
SKIP = {"shown", "error", "lines", "selected", "source"}
# Settings that must be one of a menu's keys; anything else gets the default.
# Per class: a Line's window is smoothing's, in points; a Panel's is the FFT's.
CHOICES = {Line: {"smooth": smoothing.METHODS, "background": background.MODES,
                  "cut": splicing.MODES, "style": STYLES, "marker": MARKERS},
           Panel: {"legend": LEGENDS, "grid": GRIDS, "grid_axis": GRID_AXES,
                   "grid_style": GRID_STYLES, "operation": OPERATIONS, "window": spectrum.WINDOWS,
                   "pad": spectrum.PADDING},
           Link: {}}

# Fields holding a list, and what makes the saved one fit, per class as for CHOICES.
TIDY = {Line: {"cuts": splicing.tidy}, Panel: {}, Link: {}}

# Numbers that only make sense above 0, per class as for CHOICES; the
# controls refuse the rest too.
POSITIVE = {Line: {"width", "marker_size", "window", "span"},
            Panel: {"f_max", "derivative_window"}, Link: set()}


def cell_key(cell):
    return f"{cell[0]},{cell[1]}"


def key_cell(key):
    r, c = key.split(",")
    return int(r), int(c)


def _plain(obj):
    return {f.name: getattr(obj, f.name) for f in fields(obj) if f.name not in SKIP}


def dump(panels, rows, cols, links):
    """The layout, every panel's settings and lines (with a derived panel's
    source cell while it has one), and the links, in a fixed order so equal
    states dump equal (undo compares them)."""
    out = {}
    for cell, p in sorted(panels.items()):
        data = _plain(p)
        data["lines"] = [_plain(l) for l in p.lines]
        if p.source is not None:
            data["source"] = cell_key(p.source)
        out[cell_key(cell)] = data
    saved_links = [{"a": a, "b": b, "sync": link.sync, "frozen": link.frozen}
                   for (a, b), link in sorted((tuple(sorted(pair)), link)
                                              for pair, link in links.items())]
    return {"format": FORMAT, "rows": rows, "cols": cols, "panels": out, "links": saved_links}


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
        if f.name in SKIP or f.name not in data:
            continue
        if f.name in TIDY[cls]:  # JSON's lists, checked item by item
            kwargs[f.name] = TIDY[cls][f.name](data[f.name])
            continue
        if not _allowed(f, data[f.name]):
            continue
        value = data[f.name]
        if f.name in CHOICES[cls] and value not in CHOICES[cls][f.name]:
            continue
        if f.name in POSITIVE[cls] and value is not None and value <= 0:
            continue
        kwargs[f.name] = value
    return cls(**kwargs, **extra)


def _line(data):
    """A Line from `dump`'s data; before format 6 its cut was one range,
    `cut_from` to `cut_to`."""
    if isinstance(data, dict) and "cuts" not in data:
        data = {**data, "cuts": [[data.get("cut_from"), data.get("cut_to")]]}
    return _build(Line, data)


def load(state):
    """(rows, cols, panels, links) from `dump`'s output, links being
    {frozenset of two panel ids: Link}. Raises ValueError if it isn't one."""
    try:
        rows, cols = int(state["rows"]), int(state["cols"])
        saved = {key_cell(k): v for k, v in state["panels"].items()}
    except (KeyError, TypeError, ValueError, AttributeError) as err:
        raise ValueError(f"not a session ({err})") from None
    if not (1 <= rows <= MAX_GRID and 1 <= cols <= MAX_GRID):
        raise ValueError(f"a {rows} x {cols} layout is bigger than the plotter allows")
    grid = [(r, c) for r in range(rows) for c in range(cols)]
    fmt = state.get("format")
    if fmt not in (2, 3, 4, 5, FORMAT):
        panels, groups = _load_old(saved, grid)
        return rows, cols, _blank_is_auto(panels), _group_links(panels, groups)
    panels = {}
    for cell in grid:
        data = saved.get(cell)
        if data is None:
            panels[cell] = Panel()
            continue
        lines = [_line(l) for l in data.get("lines") or []] or [Line()]
        panels[cell] = _build(Panel, data, lines=lines, source=_source(data, grid))
    seen = set()
    for p in panels.values():  # ids must tell panels apart; a file edited by hand may not
        if p.id in seen:
            p.id = Panel().id
        seen.add(p.id)
    if fmt in (5, FORMAT):
        return rows, cols, panels, _links(state.get("links"), panels)
    if fmt == 4:
        return rows, cols, panels, _share_cut(_links(state.get("links"), panels), panels)
    groups = {cell: _group_of(saved.get(cell), old_ticks=False) for cell in panels}
    if fmt == 2:
        panels = _blank_is_auto(panels)
    return rows, cols, panels, _share_cut(_group_links(panels, groups), panels)


def _share_cut(links, panels):
    """Links saved before format 5 had no cut to share. Those that shared
    everything else (a derived panel's with its data panel, at least) share
    it too, so an FFT or derivative still follows its data when it's cut."""
    derived = {frozenset((p.id, panels[p.source].id)) for p in panels.values()
               if p.derived and p.source in panels}
    for pair, link in links.items():
        if pair in derived or set(SYNC) - {"cut"} <= link.synced:
            link.sync = " ".join(k for k in SYNC if k in link.synced | {"cut"})
    return links


def _links(saved, panels):
    """{frozenset of ids: Link} from `dump`'s list, keeping only links between
    two different panels that are there, once each."""
    ids = {p.id for p in panels.values()}
    links = {}
    for data in saved if isinstance(saved, list) else []:
        if not isinstance(data, dict):
            continue
        pair = frozenset((data.get("a"), data.get("b")))
        if len(pair) == 2 and pair <= ids and pair not in links:
            links[pair] = _build(Link, data)
    return links


def _group_of(data, old_ticks):
    """(group, ticks, frozen) of a panel as saved before format 4, when links
    were groups and each panel ticked what it shared; None if in no group.
    `old_ticks`: X and Y axis then covered their Function boxes too."""
    if not isinstance(data, dict) or not isinstance(data.get("link_group"), int) \
            or isinstance(data.get("link_group"), bool):
        return None
    words = data.get("sync") if isinstance(data.get("sync"), str) else Link().sync
    words = words.split()
    if old_ticks or not {"x_fn", "y_fn"} & set(words):
        words += [k for k, axis in (("x_fn", "x"), ("y_fn", "y")) if axis in words]
    return data["link_group"], set(words) & set(SYNC), data.get("frozen") is True


def _group_links(panels, groups):
    """Links for panels saved in groups ({cell: _group_of}): every pair in a
    group, sharing what both ticked, frozen if either was, as they behaved."""
    links = {}
    members = [(cell, g) for cell, g in groups.items() if g is not None and cell in panels]
    for i, (a, (group_a, ticks_a, frozen_a)) in enumerate(members):
        for b, (group_b, ticks_b, frozen_b) in members[i + 1:]:
            if group_a == group_b:
                shared = ticks_a & ticks_b
                links[frozenset((panels[a].id, panels[b].id))] = Link(
                    " ".join(k for k in SYNC if k in shared), frozen_a or frozen_b)
    return links


def _blank_is_auto(panels):
    """Before format 3 a blank title, label or legend name was the automatic one."""
    for p in panels.values():
        for obj in (p, *p.lines):
            for name in TEXTS[type(obj)]:
                if getattr(obj, name) == "":
                    setattr(obj, name, None)
    return panels


def _source(data, grid):
    """The cell in `data`'s "source", if it's one of the grid's."""
    try:
        source = key_cell(data["source"])
    except (TypeError, KeyError, ValueError, AttributeError):
        return None
    return source if source in grid else None


def _load_old(saved, grid):
    """(panels, groups) from a version 1 layout. There a derived panel had a
    source and no lines of its own, and all panels an operation ("fft" by
    default). Here it gets copies of its data panel's lines, in its group,
    sharing everything, as that list did."""
    panels, groups = {}, {}
    for cell in grid:  # data panels first: derived panels copy their lines
        data = saved.get(cell)
        if data is None or (isinstance(data, dict) and "source" in data):
            continue
        lines = [_line(l) for l in data.get("lines") or []] or [Line()]
        panels[cell] = _build(Panel, data, lines=lines)
        panels[cell].operation = ""
        groups[cell] = _group_of(data, old_ticks=True)
    numbers = [g[0] for g in groups.values() if g is not None]
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
        p.selected = min(data_panel.selected, len(p.lines) - 1)
        if groups[source] is None:
            numbers.append(max(numbers, default=0) + 1)
            groups[source] = numbers[-1], set(SYNC), False
        groups[source] = groups[source][0], set(SYNC), groups[source][2]  # shares everything
        groups[cell] = groups[source][0], set(SYNC), False
        panels[cell] = p
    return panels, groups
