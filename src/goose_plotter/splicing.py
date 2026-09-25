"""The Splicing tab: cut a line to part of its x range, or cut a range out of it."""

import numpy as np

# Mode stored on a Line -> name shown in the Splicing box. "" is off.
MODES = {"": "Off", "keep": "Keep range", "remove": "Remove range"}


def span_text(start, end):
    """'x 0.036–0.067', 'x 0.036–' for an open end."""
    return f"x {'' if start is None else f'{start:.4g}'}–{'' if end is None else f'{end:.4g}'}"


def describe(mode, start, end):
    """Short text for the legend and line list: 'x 0.036–0.067', 'without x 0.04–0.05'."""
    return span_text(start, end) if mode == "keep" else f"without {span_text(start, end)}"


def file_part(mode, start, end):
    """Filename piece: 'x0.036-0.067' for a kept range, 'no0.04-0.05' for one cut out."""
    ends = f"{'' if start is None else f'{start:.4g}'}-{'' if end is None else f'{end:.4g}'}"
    return f"{'x' if mode == 'keep' else 'no'}{ends}"


def cut(x, y, mode, start, end):
    """(x, y) cut to the rows with x from `start` to `end` (None: no limit), for
    mode 'keep', or with those rows cut out, for 'remove'.

    Kept, the rows outside are dropped, so what follows (fits, smoothing,
    spectra) only ever sees the range. Removed, the rows inside become NaN in
    both x and y rather than being dropped: the plot shows a gap, and
    smoothing and fits treat it as one instead of joining its two sides."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if start is not None and end is not None and start > end:
        start, end = end, start
    inside = np.isfinite(x)
    if start is not None:
        inside &= x >= start
    if end is not None:
        inside &= x <= end
    if mode == "keep":
        if not inside.any():
            # Most likely a range typed in other units, e.g. T while x is 1/B.
            finite = x[np.isfinite(x)]
            extent = (f"; this line's x runs from {finite.min():.4g} to {finite.max():.4g}"
                      if len(finite) else "")
            raise ValueError(f"there are no points in {span_text(start, end)}{extent}. "
                             f"The range is in the plotted x, after its function")
        return x[inside], y[inside]
    if inside.all():
        raise ValueError(f"removing {span_text(start, end)} leaves no points")
    return np.where(inside, np.nan, x), np.where(inside, np.nan, y)
