"""The Smoothing section: moving average, median or Savitzky–Golay over a line's y."""

import warnings

import numpy as np
import pandas as pd

# Method stored on a Line -> name shown in the Smoothing box. "" is no smoothing.
METHODS = {"": "None", "mean": "Moving average", "median": "Median",
           "savgol": "Savitzky-Golay"}  # ASCII: Tk's core fonts garble an en dash

# What the window is counted in: points (rows) or units of the plotted x.
UNITS = {False: "points", True: "x units"}

# Most window cells gathered at once when smoothing in x; bounds memory use.
CHUNK = 2_000_000


def describe(method, size, order, in_x):
    """Short text for the legend and toggle: 'avg 21', 'SG Δx 0.05, order 2'."""
    if in_x:
        size = f"Δx {size:g}" if size is not None else "Δx"
    return {"mean": f"avg {size}", "median": f"median {size}",
            "savgol": f"SG {size}, order {order}"}[method]


def file_part(method, size, order, in_x):
    """Filename piece: 'avg21', 'median-dx0.05', 'sg51-o2'."""
    size = f"-dx{size:g}" if in_x else size
    return {"mean": f"avg{size}", "median": f"median{size}",
            "savgol": f"sg{size}-o{order}"}[method]


def nice(value):
    """`value` rounded to 1, 2 or 5 times a power of ten: 0.0374 -> 0.05."""
    if not np.isfinite(value) or value <= 0:
        return 1.0
    power = 10.0 ** np.floor(np.log10(value))
    return next(float(f"{m * power:.3g}") for m in (1, 2, 5, 10) if m * power >= value)


def step_nice(value, direction):
    """The next 1-2-5 value above (direction 1) or below (-1) `value`."""
    power = 10.0 ** np.floor(np.log10(value))
    steps = [float(f"{m * power:.3g}") for m in (0.5, 1, 2, 5, 10, 20)]
    if direction > 0:
        return next(s for s in steps if s > value * (1 + 1e-9))
    return next(s for s in reversed(steps) if s < value * (1 - 1e-9))


def span_for(x, window):
    """An x window about as wide as `window` points: a starting value for x units."""
    with warnings.catch_warnings(action="ignore"):
        step = np.nanmedian(np.abs(np.diff(np.asarray(x, dtype=float))))
    return nice(window * step)


def smooth(x, y, method, size, order, in_x=False):
    """`y` smoothed over a window of `size` points, or of `size` in x if `in_x`.

    Windows follow row order rather than x sorted: a field record isn't
    monotonic (it jitters and sits parked at the ends of a sweep), so sorting
    would mix separate stretches of the sweep. Points that aren't finite (1/0
    from an axis function, say) are left out of their neighbours' windows and
    stay gaps in the result."""
    if not method:
        return y
    y = np.asarray(y, dtype=float)
    finite = np.isfinite(y)
    if in_x:
        if not size > 0:
            raise ValueError("the window in x must be more than 0")
        if order < 0:
            raise ValueError("the order can't be negative")
        result = smooth_in_x(np.asarray(x, dtype=float), np.where(finite, y, np.nan),
                             method, size / 2, order)
        return np.where(finite, result, np.nan)
    window = size
    if window < 3:
        raise ValueError("the window must be at least 3 points")
    if window > len(y):
        raise ValueError(f"the window of {window} points is longer than the "
                         f"line's {len(y)} points")
    if method == "savgol":
        if window % 2 == 0:
            raise ValueError(f"Savitzky–Golay needs an odd window, not {window}")
        if not 0 <= order < window - 1:
            raise ValueError(f"the order must be from 0 to {window - 2} "
                             f"for a window of {window}")
        if not finite.any():
            return y
        # The fit needs evenly spaced points, so bridge gaps by interpolation.
        index = np.arange(len(y))
        filled = np.interp(index, index[finite], y[finite])
        result = savgol(filled, window, order)
    else:
        rolling = pd.Series(np.where(finite, y, np.nan)).rolling(
            window, center=True, min_periods=1)
        result = getattr(rolling, method)().to_numpy()
    return np.where(finite, result, np.nan)


def savgol(values, window, order):
    """Savitzky–Golay filter: each point from a degree-`order` polynomial
    least-squares fitted to the `window` points around it. The first and last
    half-windows are read off the fit to the first and last full window."""
    half = window // 2
    offsets = np.arange(-half, half + 1)
    # Row k of `fit` turns a window of values into the polynomial's k-th coefficient.
    fit = np.linalg.pinv(np.vander(offsets, order + 1, increasing=True))
    result = np.empty_like(values)
    result[half:-half] = np.correlate(values, fit[0], mode="valid")
    ends = np.vander(offsets, order + 1, increasing=True)
    result[:half] = ends[:half] @ (fit @ values[:window])
    result[-half:] = ends[half + 1:] @ (fit @ values[-window:])
    return result


def smooth_in_x(x, y, method, half, order):
    """Each point from the rows in its stretch (see `stretches`): their mean,
    median, or for Savitzky–Golay a degree-`order` polynomial fitted in x and
    read off at the point's own x. NaN in `y` marks points to leave out."""
    first, stop = stretches(x, half)
    # Rows sharing a stretch (a parked field gives thousands) share one
    # calculation: windows[w] is a distinct stretch, rows[w] a row that has it.
    windows, rows, member = np.unique(np.stack([first, stop], axis=1), axis=0,
                                      return_index=True, return_inverse=True)
    widths = windows[:, 1] - windows[:, 0]
    fits = np.full((len(windows), order + 1 if method == "savgol" else 1), np.nan)
    # Pad each window to the next power of two, in chunks of about CHUNK cells.
    buckets = np.frexp(widths - 1)[1]
    for b in np.unique(buckets):
        width = 2 ** int(b)
        chosen = np.flatnonzero(buckets == b)
        for c in range(0, len(chosen), max(1, CHUNK // width)):
            w = chosen[c:c + max(1, CHUNK // width)]
            cells = windows[w, :1] + np.arange(width)
            inside = cells < windows[w, 1:]
            cells = np.minimum(cells, len(y) - 1)
            values = np.where(inside, y[cells], np.nan)
            with warnings.catch_warnings(action="ignore"):  # all-NaN windows give NaN
                if method == "mean":
                    fits[w, 0] = np.nanmean(values, axis=1)
                elif method == "median":
                    fits[w, 0] = np.nanmedian(values, axis=1)
                else:
                    u = (x[cells] - x[rows[w], None]) / half
                    fits[w] = local_fit(u, values, order)
    fits = fits[member]
    if method != "savgol":
        return fits[:, 0]
    # Each row reads its window's polynomial off at its own x.
    u = (x - x[rows[member]]) / half
    return np.polynomial.polynomial.polyval(u, fits.T, tensor=False)


def local_fit(u, values, order):
    """Per row, the coefficients (constant first) of a degree-`order`
    polynomial least-squares fitted to (u, values); NaN values are left out.
    With fewer distinct u than the order needs (a parked field, say), it falls
    back to a lower degree. Rows with no values give NaN."""
    used = np.isfinite(values)
    u = np.where(used, u, 0.0)
    values = np.where(used, values, 0.0)
    # Normal equations from the moments sum(u^k) and sum(u^k y). u is within
    # [-1, 1], so they stay well conditioned for the orders offered.
    powers = [used.astype(float)]
    for _ in range(2 * order):
        powers.append(powers[-1] * u)
    moments = np.stack([p.sum(axis=1) for p in powers], axis=1)
    k = np.arange(order + 1)
    matrix = moments[:, k[:, None] + k[None, :]]
    rhs = np.stack([(powers[j] * values).sum(axis=1) for j in k], axis=1)
    coefficients = (np.linalg.pinv(matrix, rcond=1e-10) @ rhs[:, :, None])[:, :, 0]
    return np.where(used.any(axis=1)[:, None], coefficients, np.nan)


def stretches(x, half):
    """For each row, (first, stop): the unbroken run of rows around it whose x
    are all within `half` of its own. A row with a far-off or NaN x ends a run."""
    n = len(x)
    # Sparse tables: low[k, i] and high[k, i] are the min and max of
    # x[i : i + 2**k]; the tail of each row, past the data, is never read.
    levels = n.bit_length()
    low, high = np.full((levels, n), np.nan), np.full((levels, n), np.nan)
    low[0] = high[0] = x
    for k in range(1, levels):
        s = 2 ** (k - 1)
        low[k, :n - s] = np.minimum(low[k - 1, :n - s], low[k - 1, s:])
        high[k, :n - s] = np.maximum(high[k - 1, :n - s], high[k - 1, s:])

    def fits(a, b, i):
        """Whether x[a..b] (inclusive) all lie within `half` of x[i]."""
        k = np.frexp(b - a + 1)[1] - 1  # floor(log2(length))
        other = b - 2 ** k + 1
        lo = np.minimum(low[k, a], low[k, other])
        hi = np.maximum(high[k, a], high[k, other])
        return (lo >= x[i] - half) & (hi <= x[i] + half)

    rows = np.arange(n)
    # Binary searches, all rows at once: the furthest back and forward that fit.
    lo, hi = np.zeros(n, dtype=int), rows.copy()
    while (lo < hi).any():
        mid = (lo + hi) // 2
        ok = fits(mid, rows, rows)
        hi, lo = np.where(ok, mid, hi), np.where(ok, lo, mid + 1)
    first = hi
    lo, hi = rows.copy(), np.full(n, n - 1)
    while (lo < hi).any():
        mid = (lo + hi + 1) // 2
        ok = fits(rows, mid, rows)
        lo, hi = np.where(ok, mid, lo), np.where(ok, hi, mid - 1)
    return first, lo + 1
