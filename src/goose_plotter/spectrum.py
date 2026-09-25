"""FFT panels: the spectrum of a line's y against its plotted x."""

import re

import numpy as np

# Window stored on a Panel -> name shown in the FFT box. "" is none.
WINDOWS = {"hann": "Hann", "": "None"}
PADDING = (1, 2, 4, 8)  # zero-padding factors offered


def spectrum(x, y, window="hann", pad=1):
    """(frequency, amplitude) of `y` against `x`, the zero-frequency bin left out.

    x is uneven (a steady sweep in B is uneven in 1/B) and jitters, parks and
    can double back, so the finite points are first averaged into bins on an
    even grid of as many points as there are, with empty bins interpolated.
    Amplitude is in y's units: a sine of amplitude A gives a peak of about A.
    `pad` zero-pads to that many times the length, which draws peaks more
    smoothly without adding resolution."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    used = np.isfinite(x) & np.isfinite(y)
    x, y = x[used], y[used]
    n = len(x)
    if n < 8:
        raise ValueError(f"an FFT needs at least 8 points; this line has {n}")
    lo, hi = x.min(), x.max()
    if hi == lo:
        raise ValueError("all the x values are the same")
    step = (hi - lo) / (n - 1)
    bins = np.rint((x - lo) / step).astype(int)
    counts = np.bincount(bins, minlength=n)
    sums = np.bincount(bins, weights=y, minlength=n)
    grid = lo + step * np.arange(n)
    filled = counts > 0
    values = np.interp(grid, grid[filled], sums[filled] / counts[filled])
    values -= values.mean()
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
