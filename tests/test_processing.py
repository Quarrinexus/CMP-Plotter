"""Background, smoothing, spectra and derivatives: the numbers behind each line."""

import numpy as np
import pytest

from goose_plotter import background, derivative, smoothing, spectrum


# --- background -------------------------------------------------------------

def test_background_subtract_removes_a_polynomial_exactly():
    x = np.linspace(0.03, 0.07, 500)
    y = 3 - 20 * x + 150 * x ** 2
    assert np.allclose(background.apply(x, y, "subtract", 2, None, None), 0, atol=1e-9)
    assert np.allclose(background.apply(x, y, "fit", 2, None, None), y)


def test_background_range_limits_the_fit_and_the_line():
    x = np.linspace(0, 10, 101)
    fitted = background.apply(x, x ** 2, "fit", 2, 2, 5)
    inside = (x >= 2) & (x <= 5)
    assert np.all(np.isnan(fitted[~inside]))
    assert np.allclose(fitted[inside], x[inside] ** 2)


def test_background_errors():
    x = np.linspace(0, 1, 50)
    with pytest.raises(ValueError, match="no points in the fit range"):
        background.apply(x, x, "fit", 2, 5, 6)
    with pytest.raises(ValueError, match="more than 3 different"):
        background.apply(np.repeat([1.0, 2.0, 3.0], 5), np.ones(15), "fit", 3, None, None)
    with pytest.raises(ValueError, match="negative"):
        background.apply(x, x, "fit", -1, None, None)


def test_background_skips_nan():
    x = np.linspace(0, 1, 50)
    y = 2 * x + 1
    y[10] = np.nan
    result = background.apply(x, y, "subtract", 1, None, None)
    assert np.isnan(result[10])
    assert np.allclose(np.delete(result, 10), 0, atol=1e-9)


# --- smoothing --------------------------------------------------------------

def test_savgol_keeps_a_polynomial_of_its_order():
    x = np.arange(200.0)
    y = 0.5 * x ** 2 - 3 * x + 7
    assert np.allclose(smoothing.smooth(x, y, "savgol", 11, 2), y)


def test_moving_average_and_median_of_a_constant():
    x = np.arange(100.0)
    y = np.full(100, 4.0)
    for method in ("mean", "median"):
        assert np.allclose(smoothing.smooth(x, y, method, 9, 0), 4)


def test_median_removes_a_spike():
    y = np.zeros(50)
    y[25] = 100
    assert smoothing.smooth(np.arange(50.0), y, "median", 5, 0)[25] == 0


def test_smoothing_keeps_gaps():
    y = np.sin(np.arange(100) / 10)
    y[40:45] = np.nan
    for method in ("mean", "median", "savgol"):
        result = smoothing.smooth(np.arange(100.0), y, method, 7, 2)
        assert np.all(np.isnan(result[40:45]))
        assert np.all(np.isfinite(np.delete(result, range(40, 45))))


def test_smoothing_in_x_units_is_a_fit_in_x():
    x = np.sort(np.random.default_rng(1).uniform(0, 10, 400))  # uneven steps
    y = 2 * x - 1
    assert np.allclose(smoothing.smooth(x, y, "savgol", 1.0, 1, in_x=True), y)
    assert np.allclose(smoothing.smooth(x, np.full(400, 3.0), "mean", 1.0, 0, in_x=True), 3)


def test_stretches_break_where_x_jumps():
    x = np.array([0.0, 0.1, 0.2, 5.0, 5.1, 0.3])
    first, stop = smoothing.stretches(x, 0.5)
    # Row 5 is close to rows 0-2 in x, but not in an unbroken run with them.
    assert (first[5], stop[5]) == (5, 6)
    assert (first[1], stop[1]) == (0, 3)


def test_smoothing_errors():
    x = np.arange(20.0)
    with pytest.raises(ValueError, match="odd window"):
        smoothing.smooth(x, x, "savgol", 10, 2)
    with pytest.raises(ValueError, match="longer than"):
        smoothing.smooth(x, x, "mean", 21, 0)
    with pytest.raises(ValueError, match="at least 3"):
        smoothing.smooth(x, x, "mean", 2, 0)
    with pytest.raises(ValueError, match="order must be"):
        smoothing.smooth(x, x, "savgol", 5, 4)


def test_nice_steps():
    assert smoothing.nice(0.0374) == 0.05
    assert smoothing.step_nice(0.05, 1) == 0.1
    assert smoothing.step_nice(0.05, -1) == 0.02


# --- spectrum ---------------------------------------------------------------

def test_spectrum_peak_at_the_frequency_with_its_amplitude():
    x = np.linspace(0, 2, 4000)
    y = 0.3 * np.sin(2 * np.pi * 25 * x)
    frequency, amplitude = spectrum.spectrum(x, y, "hann", 4)
    peak = np.argmax(amplitude)
    assert frequency[peak] == pytest.approx(25, abs=0.5)
    assert amplitude[peak] == pytest.approx(0.3, rel=0.05)


def test_spectrum_of_uneven_jittering_x():
    rng = np.random.default_rng(0)
    x = np.linspace(0, 1, 3000) + rng.normal(0, 1e-4, 3000)  # jitter, reversals
    frequency, amplitude = spectrum.spectrum(x, np.cos(2 * np.pi * 40 * x))
    assert frequency[np.argmax(amplitude)] == pytest.approx(40, abs=1)


def test_spectrum_errors_and_resolution():
    with pytest.raises(ValueError, match="at least 8"):
        spectrum.spectrum(np.arange(5.0), np.arange(5.0))
    with pytest.raises(ValueError, match="same"):
        spectrum.spectrum(np.ones(20), np.arange(20.0))
    assert spectrum.resolution(np.array([0.1, np.nan, 0.2])) == pytest.approx(10)


def test_frequency_label():
    assert spectrum.frequency_label("1/x", "T") == "$F$  (T)"
    assert spectrum.frequency_label("x", "T") == "frequency  (1/T)"
    assert spectrum.frequency_label("x**2", "T") == "frequency  (1 / x units)"


# --- derivative -------------------------------------------------------------

def test_derivatives_of_a_cubic():
    x = np.linspace(-2, 2, 2001)
    y = x ** 3
    grid, d1 = derivative.derivative(x, y, 1, 21)
    assert np.allclose(d1, 3 * grid ** 2, atol=1e-3)
    grid, d2 = derivative.derivative(x, y, 2, 21)
    assert np.allclose(d2, 6 * grid, atol=1e-2)


def test_derivative_errors():
    x = np.linspace(0, 1, 100)
    with pytest.raises(ValueError, match="odd"):
        derivative.derivative(x, x, 1, 20)
    with pytest.raises(ValueError, match="at least 5"):
        derivative.derivative(x, x, 2, 3)
