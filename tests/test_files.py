"""Reading data files and profiles, and turning columns into axis text."""

import json

import numpy as np
import pytest

from goose_plotter import axis_functions, columns, datasets, profile
from conftest import write_run


# --- data files -------------------------------------------------------------

def test_detects_a_run_file_past_its_preamble(tmp_path):
    path = write_run(tmp_path / "Cambridge_Sep_26.005.text", rows=50)
    fmt = datasets.detect_format(datasets.read_lines(path))
    assert fmt == {"delimiter": "tab", "header_line": 7, "data_line": 8}


def test_loads_columns_without_the_run_suffix(tmp_path):
    df = datasets.load_dataset(write_run(tmp_path / "run.005.text", rows=50))
    assert list(df.columns) == ["Timestamp", "Norminal_FIeld", "M006_AH", "M011_AH",
                                "Source_Run"]
    assert len(df) == 50
    assert df["Norminal_FIeld"].iloc[0] == pytest.approx(28)


def test_other_delimiters_and_no_header(tmp_path):
    path = tmp_path / "plain.csv"
    path.write_text("a,b\n1,2\n3,4\n5,6\n")
    assert list(datasets.load_dataset(path).columns) == ["a", "b"]
    path = tmp_path / "bare.dat"
    path.write_text("1 2 3\n4 5 6\n7 8 9\n")
    df = datasets.load_dataset(path)
    assert list(df.columns) == ["column_1", "column_2", "column_3"]


def test_a_saved_format_that_no_longer_fits_falls_back_to_detection(tmp_path):
    path = write_run(tmp_path / "run.005.text", rows=20)
    df = datasets.load_dataset(path, {"delimiter": "tab", "header_line": 2, "data_line": 3})
    assert "M006_AH" in df


def test_unreadable_files():
    with pytest.raises(datasets.FormatError):
        datasets.detect_format(["no numbers", "here at all"])
    lines = ["a\tb", "1\t2", "3\t4", "5\t6"]
    with pytest.raises(datasets.FormatError, match="before the data"):
        datasets.parse(lines, {"delimiter": "tab", "header_line": 3, "data_line": 2})
    with pytest.raises(datasets.FormatError, match="past the end"):
        datasets.parse(lines, {"delimiter": "tab", "header_line": 0, "data_line": 9})


def test_finds_data_files_and_names_runs(tmp_path):
    for name in ("x.005.text", "notes.md", "y.csv", "y.txt"):
        (tmp_path / name).write_text("")
    assert set(datasets.find_datasets(tmp_path)) == {"x.005", "y.csv", "y.txt"}
    assert datasets.find_datasets(None) == {}
    assert datasets.run_number("Cambridge_Sep_26.005") == "005"
    assert datasets.describe("Cambridge_Sep_26.005") == "run 005"
    assert datasets.describe("sweep") == "sweep"


# --- profiles ---------------------------------------------------------------

def test_profile_reads_and_rejects(tmp_path):
    assert profile.load_profile(None) == (profile.Profile(), "")
    (tmp_path / profile.PROFILE_NAME).write_text(json.dumps(
        {"units": {"AH": "bridge units"}, "format": {"delimiter": ""}}))
    loaded, error = profile.load_profile(tmp_path)
    assert loaded.units == {"AH": "bridge units"} and loaded.format is None
    assert "'format' ignored" in error
    (tmp_path / profile.PROFILE_NAME).write_text("{not json")
    assert "ignored" in profile.load_profile(tmp_path)[1]


def test_save_format_keeps_the_rest_of_the_profile(tmp_path):
    (tmp_path / profile.PROFILE_NAME).write_text(json.dumps({"units": {"B": "T"}}))
    fmt = {"delimiter": "tab", "header_line": 1, "data_line": 2}
    profile.save_format(tmp_path, fmt)
    assert profile.load_profile(tmp_path)[0].format == fmt
    profile.save_format(tmp_path, None)
    loaded = profile.load_profile(tmp_path)[0]
    assert loaded.format is None and loaded.units == {"B": "T"}


# --- column names and axis functions ----------------------------------------

def test_sample_columns_match_their_profile_keys():
    labels = {"AH": "capacitance", "AH_Loss": "loss"}
    assert columns.label("M006_AH", labels) == "M006 capacitance"
    assert columns.label("M006_AH", labels, with_sample=False) == "capacitance"
    assert columns.label("M006_AH_Loss", labels) == "M006 loss"  # the longest key wins
    assert columns.label("Other", labels) == "Other"
    assert columns.without_unit(columns.with_unit("M006_AH", {"AH": "u"})) == "M006_AH"
    assert columns.sample_of({"M006": "#fff"}, "Norminal_FIeld", "M006_AH") == "M006"


def test_axis_functions():
    values = np.array([1.0, 2.0, 4.0])
    result, name = axis_functions.apply_function("1/B", values)
    assert name == "B" and np.allclose(result, [1, 0.5, 0.25])
    assert np.allclose(axis_functions.apply_function("log10(x)", values)[0], np.log10(values))
    assert np.isinf(axis_functions.apply_function("1/x", np.array([0.0]))[0][0])
    assert axis_functions.is_identity("") and axis_functions.is_identity("x")
    assert not axis_functions.is_identity("exp")
    assert axis_functions.rename("1/y", "y", "x") == "1/x"
    assert axis_functions.file_part("1/x", "Norminal_FIeld") == "1-over-Norminal_FIeld"


def test_axis_functions_refuse_what_they_cant_use():
    with pytest.raises(ValueError, match="exactly one name"):
        axis_functions.apply_function("x*y", np.ones(2))
    with pytest.raises(ValueError, match="none"):
        axis_functions.apply_function("2*pi", np.ones(2))
    with pytest.raises(ValueError, match="open, x"):  # any other name is a second quantity
        axis_functions.apply_function("open(x)", np.ones(2))
