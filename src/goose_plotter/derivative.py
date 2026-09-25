"""Derivative panels: the first or second derivative of a line's y against its plotted x."""

from math import factorial

import numpy as np

from goose_plotter.spectrum import even_grid

# Operation stored on a Panel with a source -> name shown in the Tk controls
# (ASCII: Tk's core fonts can garble superscripts). "fft" is spectrum's.
ORDERS = {"d1": "First", "d2": "Second"}
LABELS = {"d1": "$dy/dx$", "d2": "$d^2y/dx^2$"}  # for the plot, in mathtext
HEADINGS = {"d1": "d/dx", "d2": "d²/dx²"}


def derivative(x, y, order, window):
    """(x, the `order`-th derivative of y) on `spectrum.even_grid`.

    Rows jitter and double back in x, so differences between neighbouring
    rows would divide by next to nothing; binning onto an even grid first
    gives a steady step. Each point's derivative is then read off a
    Savitzky–Golay fit of degree `order` + 1 to the `window` grid points
    around it (the ends off the first and last full window's fit), so the
    window sets how much noise is smoothed out."""
    if window % 2 == 0:
        raise ValueError(f"the window must be odd, not {window}")
    if window < order + 3:
        raise ValueError(f"the window must be at least {order + 3} points")
    grid, values, step = even_grid(x, y, window, "a derivative with this window",
                                   at_mean_x=True)
    degree = order + 1
    half = window // 2
    offsets = np.arange(-half, half + 1)
    # Row k of `fit` turns a window of values into the polynomial's k-th coefficient.
    fit = np.linalg.pinv(np.vander(offsets, degree + 1, increasing=True))
    scale = factorial(order) / step ** order
    result = np.empty_like(values)
    result[half:-half] = np.correlate(values, fit[order], mode="valid") * scale
    # The ends: the edge window's polynomial, differentiated `order` times, at each offset.
    for window_values, ends, at in ((values[:window], offsets[:half], slice(None, half)),
                                     (values[-window:], offsets[half + 1:], slice(-half, None))):
        coefficients = np.polynomial.polynomial.polyder(fit @ window_values, order)
        result[at] = np.polynomial.polynomial.polyval(ends, coefficients) / step ** order
    return grid, result
