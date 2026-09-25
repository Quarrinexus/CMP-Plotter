import numpy as np
import pytest

from goose_plotter import splicing

X = np.linspace(0, 10, 101)  # steps of 0.1
Y = X ** 2


def test_keep_drops_rows_outside_every_range():
    x, y = splicing.cut(X, Y, "keep", ((1, 2), (5, 6)))
    assert len(x) == len(y) == 22
    assert np.all(((x >= 1) & (x <= 2)) | ((x >= 5) & (x <= 6)))
    assert np.array_equal(y, x ** 2)


def test_remove_leaves_gaps_rather_than_joining():
    x, y = splicing.cut(X, Y, "remove", ((1, 2), (5, 6)))
    assert len(x) == len(X)  # rows kept, as NaN, so the plot shows gaps
    gone = np.isnan(x)
    assert np.array_equal(gone, np.isnan(y))
    assert gone.sum() == 22
    assert not np.any((x[~gone] >= 1) & (x[~gone] <= 2))


def test_open_ends_have_no_limit():
    x, _ = splicing.cut(X, Y, "keep", ((None, 1),))
    assert x.min() == 0 and x.max() == 1
    x, _ = splicing.cut(X, Y, "keep", ((9, None),))
    assert x.min() == 9 and x.max() == 10


def test_nan_x_is_in_no_range():
    x = X.copy()
    x[3] = np.nan
    kept, _ = splicing.cut(x, Y, "keep", ((None, 10),))
    assert len(kept) == len(X) - 1


def test_keep_with_nothing_in_range_says_where_x_is():
    with pytest.raises(ValueError, match="runs from 0 to 10"):
        splicing.cut(X, Y, "keep", ((20, 30),))


def test_removing_everything_is_an_error():
    with pytest.raises(ValueError, match="leaves no points"):
        splicing.cut(X, Y, "remove", ((None, 5), (5, None)))


def test_tidy_orders_swaps_and_drops_bad_ranges():
    ranges = [[4, 3], [1, 2], "junk", [None, None], [5, float("nan")], [True, 3],
              [1, 2], [None, 0.5], (7,)]
    assert splicing.tidy(ranges) == ((None, 0.5), (1.0, 2.0), (3.0, 4.0))
    assert splicing.tidy("not a list") == ()


def test_describe_and_file_part_count_many_ranges():
    two = ((1.0, 2.0), (3.0, 4.0))
    assert splicing.describe("remove", two) == "without x 1–2, 3–4"
    assert splicing.describe("keep", two[:1]) == "x 1–2"
    assert splicing.file_part("remove", two) == "no1-2_3-4"
    three = two + ((5.0, None),)
    assert splicing.describe("keep", three) == "3 x ranges"
    assert splicing.file_part("remove", three) == "no3ranges"
