"""The Splicing tab: cut a line to some x ranges, or cut those ranges out of it.

A line's ranges share one mode: kept, the line is what's in any of them;
removed, it's what's in none."""

import math

import numpy as np

# Mode stored on a Line -> name shown in the Splicing box. "" is off.
MODES = {"": "Off", "keep": "Keep ranges", "remove": "Remove ranges"}

MAX_NAMED = 2  # ranges named in the legend and filename; more are counted


def _end(value):
    return "" if value is None else f"{value:.4g}"


def range_text(start, end):
    """'0.036–0.067', '0.036–' for an open end."""
    return f"{_end(start)}–{_end(end)}"


def tidy(ranges):
    """`ranges` as Line.cuts holds them: a tuple of (start, end) pairs, each
    end a finite number or None (no limit), start below end, in order of
    start. Pairs that aren't, or with neither end, are left out."""
    kept = []
    for pair in ranges if isinstance(ranges, (list, tuple)) else ():
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        if not all(e is None or (isinstance(e, (int, float)) and not isinstance(e, bool)
                                 and math.isfinite(e)) for e in pair):
            continue
        start, end = (None if e is None else float(e) for e in pair)
        if start is None and end is None:
            continue
        if start is not None and end is not None and start > end:
            start, end = end, start
        if (start, end) not in kept:
            kept.append((start, end))
    return tuple(sorted(kept, key=lambda p: -math.inf if p[0] is None else p[0]))


def describe(mode, ranges):
    """Short text for the legend and line list: 'x 0.036–0.067',
    'without x 1–2, 3–4', 'without 3 x ranges'."""
    if len(ranges) > MAX_NAMED:
        text = f"{len(ranges)} x ranges"
        return text if mode == "keep" else f"without {text}"
    text = "x " + ", ".join(range_text(*r) for r in ranges)
    return text if mode == "keep" else f"without {text}"


def file_part(mode, ranges):
    """Filename piece: 'x0.036-0.067' for a kept range, 'no1-2_3-4' for two
    cut out, 'no3ranges' for more."""
    prefix = "x" if mode == "keep" else "no"
    if len(ranges) > MAX_NAMED:
        return f"{prefix}{len(ranges)}ranges"
    return prefix + "_".join(f"{_end(a)}-{_end(b)}" for a, b in ranges)


def inside(x, ranges):
    """Whether each x is in any of the ranges (NaN x is in none)."""
    x = np.asarray(x, dtype=float)
    hit = np.zeros(len(x), dtype=bool)
    finite = np.isfinite(x)
    for start, end in ranges:
        this = finite.copy()
        if start is not None:
            this &= x >= start
        if end is not None:
            this &= x <= end
        hit |= this
    return hit


def cut(x, y, mode, ranges):
    """(x, y) cut to the rows with x in any of `ranges`, for mode 'keep', or
    with those rows cut out, for 'remove'.

    Kept, the rows outside are dropped, so what follows (fits, smoothing,
    spectra) only ever sees the ranges. Removed, the rows inside become NaN
    in both x and y rather than being dropped: the plot shows a gap, and
    fits and x-unit windows leave it out instead of joining its two sides."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    hit = inside(x, ranges)
    named = ", ".join(range_text(*r) for r in ranges)
    if mode == "keep":
        if not hit.any():
            # Most likely ranges typed in other units, e.g. T while x is 1/B.
            finite = x[np.isfinite(x)]
            extent = (f"; this line's x runs from {finite.min():.4g} to {finite.max():.4g}"
                      if len(finite) else "")
            raise ValueError(f"there are no points in x {named}{extent}. "
                             f"Ranges are in the plotted x, after its function")
        return x[hit], y[hit]
    if hit[np.isfinite(x)].all():
        raise ValueError(f"removing x {named} leaves no points")
    return np.where(hit, np.nan, x), np.where(hit, np.nan, y)
