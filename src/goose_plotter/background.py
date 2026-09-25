"""The Background section: a polynomial in x fitted to a line, shown or subtracted."""

import warnings

import numpy as np
from numpy.polynomial import Chebyshev

# Mode stored on a Line -> name shown in the Background box. "" is off.
MODES = {"": "Off", "fit": "Show fit", "subtract": "Subtract"}


def span_text(start, end):
    """', x 0.036–0.067' for a fit range; '' for the whole line."""
    if start is None and end is None:
        return ""
    return f", x {'' if start is None else f'{start:.4g}'}–{'' if end is None else f'{end:.4g}'}"


def describe(mode, degree, start, end):
    """Short text for the legend and toggle: '− deg 10', 'fit deg 10, x 0.036–0.067'."""
    return f"{'fit' if mode == 'fit' else '−'} deg {degree}{span_text(start, end)}"


def file_part(mode, degree, start, end):
    """Filename piece: 'bg10' for a subtracted fit, 'fit10' for the fit itself."""
    return f"{'fit' if mode == 'fit' else 'bg'}{degree}"


def apply(x, y, mode, degree, start, end):
    """`y` with the fit subtracted, or the fit itself, for mode 'subtract' or 'fit'.

    The fit is a degree-`degree` least-squares polynomial in x over the rows
    with x from `start` to `end` (None: no limit). Outside that range the line
    is left out, as the polynomial runs off wildly there. Points that aren't
    finite are left out of the fit and stay gaps."""
    fitted = fit(np.asarray(x, dtype=float), np.asarray(y, dtype=float), degree, start, end)
    return fitted if mode == "fit" else y - fitted


def fit(x, y, degree, start, end):
    """The fitted polynomial at each x in the range, NaN elsewhere."""
    if degree < 0:
        raise ValueError("the degree can't be negative")
    if start is not None and end is not None and start > end:
        start, end = end, start
    inside = np.isfinite(x)
    if start is not None:
        inside &= x >= start
    if end is not None:
        inside &= x <= end
    used = inside & np.isfinite(y)
    if not used.any():
        # Most likely a range typed in other units, e.g. T while x is 1/B.
        finite = x[np.isfinite(x)]
        extent = f"; this line's x runs from {finite.min():.4g} to {finite.max():.4g}" if len(finite) else ""
        raise ValueError(f"there are no points in the fit range{span_text(start, end)}"
                         f"{extent}. The range is in the plotted x, after its function")
    distinct = len(np.unique(x[used]))
    if distinct <= degree:
        raise ValueError(f"a degree-{degree} fit needs more than {degree} different "
                         f"x values in the fit range; it has {distinct}")
    if distinct == 1:  # degree 0 on a single x (a parked field): just the mean
        return np.where(inside, y[used].mean(), np.nan)
    # Chebyshev.fit maps x onto [-1, 1] first, so high degrees stay well
    # conditioned even over a narrow range like 1/B = 0.036-0.067.
    with warnings.catch_warnings():
        warnings.simplefilter("error", np.exceptions.RankWarning)
        try:
            polynomial = Chebyshev.fit(x[used], y[used], degree)
        except np.exceptions.RankWarning:
            raise ValueError(f"degree {degree} is too high for the points in "
                             f"the fit range; try a lower one") from None
    return np.where(inside, polynomial(np.where(inside, x, 0.0)), np.nan)
