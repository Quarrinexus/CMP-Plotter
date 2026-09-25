"""FFT panels: the spectrum of a line's y against its plotted x."""

import re

import numpy as np

# Window stored on a Panel -> name shown in the FFT box. "" is none.
WINDOWS = {"hann": "Hann", "": "None"}
PADDING = (1, 2, 4, 8)  # zero-padding factors offered


def even_grid(x, y, least, what, at_mean_x=False):
    """(grid, values, step): `y` against `x` averaged into bins on an even grid.

    x is uneven (a steady sweep in B is uneven in 1/B) and jitters, parks and
    can double back, so the finite points are averaged into bins on an even
    grid of as many points as there are, with empty bins interpolated. Needs
    at least `least` points; `what` names the operation in the error.

    `at_mean_x`: interpolate from each bin's mean x rather than its centre,
    which is up to half a step off; that matters for derivatives, which
    magnify it, and not for spectra."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    used = np.isfinite(x) & np.isfinite(y)
    x, y = x[used], y[used]
    n = len(x)
    if n < least:
        raise ValueError(f"{what} needs at least {least} points; this line has {n}")
    lo, hi = x.min(), x.max()
    if hi == lo:
        raise ValueError("all the x values are the same")
    step = (hi - lo) / (n - 1)
    bins = np.rint((x - lo) / step).astype(int)
    counts = np.bincount(bins, minlength=n)
    sums = np.bincount(bins, weights=y, minlength=n)
    grid = lo + step * np.arange(n)
    filled = counts > 0
    at = np.bincount(bins, weights=x, minlength=n)[filled] / counts[filled] if at_mean_x \
        else grid[filled]
    return grid, np.interp(grid, at, sums[filled] / counts[filled]), step


def spectrum(x, y, window="hann", pad=1):
    """(frequency, amplitude) of `y` against `x`, the zero-frequency bin left out.

    Taken on `even_grid`. Amplitude is in y's units: a sine of amplitude A
    gives a peak of about A. `pad` zero-pads to that many times the length,
    which draws peaks more smoothly without adding resolution."""
    _, values, step = even_grid(x, y, 8, "an FFT")
    n = len(values)
    values = values - values.mean()
    weights = np.hanning(n) if window == "hann" else np.ones(n)
    transform = np.fft.rfft(values * weights, n * pad)
    amplitude = 2 * np.abs(transform) / weights.sum()
    frequency = np.fft.rfftfreq(n * pad, step)
    return frequency[1:], amplitude[1:]


def resolution(x):
    """The spectrum's frequency resolution, 1 / (x range), over finite x."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return 1 / (x.max() - x.min()) if len(x) and x.max() > x.min() else np.nan


def frequency_label(x_fn, unit):
    """'F  (T)' for x = 1/B with B in T; else 'frequency  (1/…)' in x's units."""
    expr = (x_fn or "x").replace(" ", "")
    if unit and re.fullmatch(r"1/\(?[A-Za-z_]\w*\)?", expr):
        return f"$F$  ({unit})"  # a period in 1/B is a frequency in B's units
    if unit and (expr.isidentifier()):
        return f"frequency  (1/{unit})"
    return "frequency  (1 / x units)"
