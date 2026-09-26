import numpy as np
import pytest

from goose_plotter import measure


def test_a_region_masks_by_x_not_by_row():
    x = np.array([1.0, 5.0, 2.0, np.nan, 6.0, 1.5])  # jittered, with a gap
    assert measure.in_region(x, (1.2, 5.5)).tolist() == [False, True, True, False,
                                                         False, True]
    assert measure.in_region(x, ()).sum() == 5  # the whole line, less the gap
    assert measure.in_region(x, (None, 1.5)).tolist() == [True, False, False, False,
                                                          False, True]


def test_extremes_in_a_region_skip_gaps():
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([9.0, 2.0, np.nan, 7.0, -1.0, 8.0])
    found = measure.extremes(x, y, (0.5, 4.5))
    assert found["max"] == (3.0, 7.0) and found["min"] == (4.0, -1.0)
    assert found["range"] == 8.0 and found["points"] == 3
    assert found["mean"] == pytest.approx(8 / 3)
    assert measure.extremes(x, y, (10.0, 11.0)) is None


def test_refine_finds_a_peak_between_bins():
    x = np.arange(0.0, 20.0)
    centre = 7.3
    y = 5 - (x - centre) ** 2  # a parabola: refined exactly
    top_x, top_y = measure.refine(x, y, int(np.argmax(y)))
    assert top_x == pytest.approx(centre) and top_y == pytest.approx(5.0)
    assert measure.refine(x, y, 0) == (0.0, y[0])  # at an edge: the point itself


def test_peaks_highest_first_above_the_floor():
    x = np.linspace(0, 100, 1001)
    y = (3 * np.exp(-(x - 20) ** 2) + 1 * np.exp(-(x - 50) ** 2)
         + 0.2 * np.exp(-(x - 80) ** 2) + np.exp(-x))  # DC at x = 0 is an edge
    found = measure.peaks(x, y, count=5, floor=10)
    assert [round(f) for f, _ in found] == [20, 50]  # 0.2 is under 10 % of 3
    assert found[0][1] == pytest.approx(3, rel=1e-3)
    assert len(measure.peaks(x, y, count=1, floor=1)) == 1
    assert [round(f) for f, _ in measure.peaks(x, y, (40, None), floor=1)] == [50, 80]


def test_the_floor_is_of_the_tallest_peak_not_the_low_end():
    x = np.linspace(0, 100, 1001)
    y = 30 * np.exp(-x / 2) + 3 * np.exp(-(x - 50) ** 2) + 0.2 * np.exp(-(x - 80) ** 2)
    assert [round(f) for f, _ in measure.peaks(x, y, floor=10)] == [50]


def test_snap_goes_to_the_nearest_drawn_point_on_screen():
    xy = np.array([[0.0, 0.0], [1.0, 10.0], [np.nan, np.nan], [2.0, 0.0]])
    # x counts a hundred times y on screen here, so (1.8, 1) is nearest (2, 0)...
    wide = lambda d: d * np.array([100.0, 1.0])
    assert measure.snap(xy, (1.8, 1.0), wide) == (2.0, 0.0)
    # ...but with y stretched instead, the point at y = 10 is nearer.
    tall = lambda d: d * np.array([1.0, 0.1])
    assert measure.snap(xy, (1.4, 8.0), tall) == (1.0, 10.0)
    assert measure.snap(xy[[2]], (0, 0), tall) is None


def test_saved_regions_and_points_are_tidied():
    assert measure.tidy_region([5, 2]) == (2.0, 5.0)
    assert measure.tidy_region([None, None]) == ()
    assert measure.tidy_region(["a", 1]) == ()
    assert measure.tidy_region([None, 3]) == (None, 3.0)
    assert measure.tidy_points([[1, 2], [3, "x"], [4, 5], [6, 7]]) == ((4.0, 5.0), (6.0, 7.0))
    assert measure.tidy_points("nonsense") == ()
