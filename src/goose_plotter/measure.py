"""Reading numbers off a drawn line, for the Measure tab: its extremes in an x
region, the point nearest a click, and the peaks of a spectrum.

Everything here works on the line as drawn (x, y in the plotted units, NaN
for gaps) and in row order, which jitters in x, so a region is a mask on x
values, never a slice of rows."""

import numpy as np


def tidy_region(saved):
    """`Panel.region` as it's kept: () for the whole line, else a (start, end)
    pair of finite numbers or None (no limit), start below end."""
    if not isinstance(saved, (list, tuple)) or len(saved) != 2:
        return ()
    if not all(e is None or (isinstance(e, (int, float)) and not isinstance(e, bool)
                             and np.isfinite(e)) for e in saved):
        return ()
    start, end = (None if e is None else float(e) for e in saved)
    if start is None and end is None:
        return ()
    if start is not None and end is not None and start > end:
        start, end = end, start
    return start, end


def tidy_points(saved):
    """`Panel.points` as it's kept: up to two (x, y) pairs of finite numbers."""
    kept = []
    for pair in saved if isinstance(saved, (list, tuple)) else ():
        if (isinstance(pair, (list, tuple)) and len(pair) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        and np.isfinite(v) for v in pair)):
            kept.append((float(pair[0]), float(pair[1])))
    return tuple(kept[-2:])


def in_region(x, region):
    """Whether each x is in `region` (a tidy_region; () is everything) and finite."""
    x = np.asarray(x, dtype=float)
    hit = np.isfinite(x)
    if region:
        start, end = region
        if start is not None:
            hit &= x >= start
        if end is not None:
            hit &= x <= end
    return hit


def refine(x, y, i):
    """The top of the parabola through points i-1, i, i+1, as (x, y), for a peak
    on an even grid (an FFT's), finer than one bin; the point itself at an edge."""
    if i <= 0 or i >= len(y) - 1:
        return float(x[i]), float(y[i])
    a, b, c = y[i - 1], y[i], y[i + 1]
    bend = a - 2 * b + c
    if not np.isfinite(bend) or bend >= 0:  # flat, or not a peak after all
        return float(x[i]), float(y[i])
    shift = 0.5 * (a - c) / bend  # in bins, within ±0.5
    step = x[i + 1] - x[i]
    return float(x[i] + shift * step), float(b - 0.25 * (a - c) * shift)


def extremes(x, y, region=(), even=False):
    """The line's numbers in `region`: its highest and lowest point, peak to
    peak, mean and number of points, or None if no drawn point is in it.
    With `even` (an FFT's grid) the highest point is refined by `refine`."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    hit = in_region(x, region) & np.isfinite(y)
    if not hit.any():
        return None
    rows = np.flatnonzero(hit)
    top, bottom = rows[np.argmax(y[rows])], rows[np.argmin(y[rows])]
    high = refine(x, y, top) if even else (float(x[top]), float(y[top]))
    low = (float(x[bottom]), float(y[bottom]))
    return {"max": high, "min": low, "range": float(y[top] - y[bottom]),
            "mean": float(np.mean(y[rows])), "points": int(len(rows))}


def peaks(x, y, region=(), count=5, floor=10.0):
    """Up to `count` peaks of a spectrum in `region`, highest first, as (x, y)
    refined by `refine`: points above both neighbours (so not the ends, nor
    the DC bin) and at least `floor` percent of the tallest of those. Not of
    the highest point, which is often the low-frequency end left by drift."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(y) < 3:
        return []
    hit = in_region(x, region) & np.isfinite(y)
    if not hit.any():
        return []
    middle = y[1:-1]
    local = (middle > y[:-2]) & (middle >= y[2:]) & hit[1:-1]
    rows = np.flatnonzero(local) + 1
    if not len(rows):
        return []
    rows = rows[y[rows] >= floor / 100 * np.max(y[rows])]
    rows = rows[np.argsort(y[rows])[::-1]][:count]
    return [refine(x, y, i) for i in rows]


def nearest(xy, point, to_pixels):
    """The row of `xy` (N x 2, as drawn) nearest `point` on screen, where
    `to_pixels` maps (N x 2) data to pixels; NaN rows are skipped. None if
    there are none."""
    xy = np.asarray(xy, dtype=float)
    finite = np.flatnonzero(np.isfinite(xy).all(axis=1))
    if not len(finite):
        return None
    pixels = to_pixels(xy[finite])
    target = to_pixels(np.asarray([point], dtype=float))[0]
    return int(finite[np.argmin(np.hypot(*(pixels - target).T))])


def snap(xy, point, to_pixels):
    """`point` moved onto the nearest drawn point of `xy`, as (x, y) floats;
    itself if it's one already, and None if nothing is drawn."""
    xy = np.asarray(xy, dtype=float)
    exact = np.flatnonzero((xy[:, 0] == point[0]) & (xy[:, 1] == point[1])) if len(xy) else []
    row = exact[0] if len(exact) else nearest(xy, point, to_pixels)
    return None if row is None else (float(xy[row, 0]), float(xy[row, 1]))
