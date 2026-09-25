"""Shared fixtures: a made-up data folder laid out like the real runs, and the
window built on it with its settings kept out of the user's own."""

import json
import tkinter as tk

import numpy as np
import pytest

from goose_plotter import settings

F = 50.0  # the oscillation's frequency in 1/B, in T
B_HIGH, B_LOW = 28.0, 4.0


def sweep(rows=6000, run=5):
    """Columns of a made-up field sweep: B from 28 T down to 4 T, and a
    capacitance with a smooth background and an oscillation of frequency F in 1/B."""
    b = np.linspace(B_HIGH, B_LOW, rows)
    return {"Timestamp": np.arange(rows) * 0.5,
            "Norminal_FIeld": b,
            "M006_AH": 0.8 + 0.001 * b + 1e-4 * np.sin(2 * np.pi * F / b),
            "M011_AH": 2.4 - 0.002 * b,
            "Source_Run": np.full(rows, float(run))}


def write_run(path, run=5, rows=6000):
    """A file like Cambridge_Sep_26.005: a preamble, tab-separated column names
    with the run's suffix, then the data."""
    columns = sweep(rows, run)
    suffix = f"_{run:03d}"
    lines = [f"{path.name} Wed, Sep 23, 2026 2:38:29 PM The Scientist",
             "Magnet: None",
             "Trigger spacing of 1.000000 on column #0",
             "Scale Factors:\t" + "\t".join(["1.000000000E+0"] * len(columns)),
             "",
             "This data's for you!",
             "\t".join(name + suffix for name in columns)]
    lines += ["\t".join(f"{v:.9E}" for v in row) for row in zip(*columns.values())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def data_dir(tmp_path):
    """A data folder with runs 005 and 003 and a profile like the real one's."""
    folder = tmp_path / "data"
    folder.mkdir()
    write_run(folder / "Cambridge_Sep_26.005.text", 5)
    write_run(folder / "Cambridge_Sep_26.003.text", 3, rows=3000)
    (folder / "goose-plotter.json").write_text(json.dumps({
        "labels": {"Norminal_FIeld": "$B$  (T)", "AH": "capacitance (bridge units)"},
        "units": {"Norminal_FIeld": "T", "AH": "bridge units"},
        "samples": {"M006": "#2a78d6", "M011": "#eb6834"},
        "defaults": {"x": "Norminal_FIeld", "y": "M006_AH"}}))
    return folder


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    """Settings kept in the test's own folder, never the user's."""
    path = tmp_path / "config" / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_FILE", path)
    return path


@pytest.fixture
def app(data_dir, settings_file, tmp_path, monkeypatch):
    """The window on the made-up data folder, with the questions it can ask
    answered yes so nothing waits. Skipped where there's no display."""
    output = tmp_path / "output"
    settings.save_settings({"data_dir": str(data_dir), "output_dir": str(output)})
    from goose_plotter import plotter
    monkeypatch.setattr(plotter.messagebox, "askyesno", lambda *a, **k: True)
    try:
        window = plotter.Plotter()
    except tk.TclError as err:  # no display
        pytest.skip(f"no display for Tk: {err}")
    window.withdraw()
    yield window
    window.destroy()


def plot(app, run="Cambridge_Sep_26.005", x_fn="x"):
    """Plot `run` on the selected line, with the x function given."""
    app.run.set(run)
    app.apply_controls()
    if x_fn != "x":
        app.x_fn.set(x_fn)
        app.apply_controls()


def drawn(app, cell=None, index=0):
    """(x, y) of line `index` as drawn in `cell` (the selected panel by default)."""
    artists = {i: a for a, i in app.artists[cell or app.selected].items()}
    artist = artists[index]
    return (np.asarray(artist.get_xdata(), dtype=float),
            np.asarray(artist.get_ydata(), dtype=float))
