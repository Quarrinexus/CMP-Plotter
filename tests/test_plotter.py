"""The window, driven as a user would, on the made-up data in conftest."""

import json

import numpy as np
import pytest

from goose_plotter import smoothing, splicing
from conftest import B_HIGH, B_LOW, F, drawn, plot

def test_plots_the_profile_default_axes(app):
    plot(app)
    line = app.panel.line
    assert (line.x, line.y) == ("Norminal_FIeld", "M006_AH")
    x, _ = drawn(app)
    assert x.max() == pytest.approx(B_HIGH) and x.min() == pytest.approx(B_LOW)
    assert app.axes[(0, 0)].get_title() == "run 005"
    assert app.filename.get() == "run_005_M006_AH_vs_Norminal_FIeld.png"
    assert app.error_label["text"] == ""


def test_a_bad_function_is_reported_under_the_axes(app):
    plot(app)
    app.y_fn.set("y +")
    app.apply_controls()
    assert app.error_label["text"].startswith("Function error")
    assert not app.axes[(0, 0)].lines


def test_fft_panel_finds_the_oscillation(app):
    plot(app, x_fn="1/x")
    app.fit_mode.set("Subtract")  # degree 10, the default
    app.apply_controls()
    app.new_derived_panel("fft")
    frequency, amplitude = drawn(app, (1, 0))
    assert frequency[np.argmax(amplitude)] == pytest.approx(F, rel=0.05)
    assert app.panels[(1, 0)].source == (0, 0)


def test_splicing_keeps_and_removes_several_ranges(app):
    plot(app)
    app.cut_mode.set(splicing.MODES["remove"])
    app.apply_controls()
    for start, end in (("10", "12"), ("20", "22")):
        app.cut_from.set(start)
        app.cut_to.set(end)
        app.add_cut()
    x, _ = drawn(app)
    finite = x[np.isfinite(x)]
    assert not np.any((finite >= 10) & (finite <= 12) | (finite >= 20) & (finite <= 22))
    assert np.isnan(x).any()  # gaps, not joins
    assert app.cut_list.get(0, "end") == ("x 10 to 12", "x 20 to 22")
    # One mode for every range.
    app.cut_mode.set(splicing.MODES["keep"])
    app.apply_controls()
    x, _ = drawn(app)
    assert np.all((x >= 10) & (x <= 12) | (x >= 20) & (x <= 22))
    assert app.filename.get().endswith("_x10-12_20-22.png")


def test_a_kept_range_sets_the_fft_resolution(app):
    plot(app, x_fn="1/x")
    app.cut_from.set("0.05")
    app.cut_to.set("0.15")
    app.add_cut()  # off, so it switches to keeping the range
    assert app.panel.line.cutting == ("keep", ((0.05, 0.15),))
    app.new_derived_panel("fft")
    assert app.axes[(1, 0)].get_title().endswith("ΔF 10")


def test_editing_picking_and_deleting_ranges(app):
    plot(app)
    app.cut_from.set("5")
    app.cut_to.set("6")
    app.add_cut()
    app.cut_from.set("5.5")
    app.add_cut(replace=True)  # Enter changes the chosen range
    assert app.panel.line.cuts == ((5.5, 6.0),)
    app.pick_range("cut")
    app._use_range(20.0, 25.0)
    assert app.panel.line.cuts == ((5.5, 6.0), (20.0, 25.0))
    app.cut_index = 0
    app.delete_cut()
    assert app.panel.line.cuts == ((20.0, 25.0),)
    app.cut_from.set("")
    app.cut_to.set("")
    app.add_cut()
    assert "at least one end" in app.status["text"]


def test_a_cut_in_the_old_x_is_cleared(app):
    plot(app)
    app.cut_from.set("5")
    app.cut_to.set("9")
    app.add_cut()
    app.x_fn.set("1/x")
    app.apply_controls()
    assert app.panel.line.cuts == ()
    app.cut_from.set("0.1")
    app.cut_to.set("0.2")
    app.add_cut()
    app.swap()
    assert app.panel.line.cuts == ()


def test_a_cut_range_with_no_points_explains_itself(app):
    plot(app, x_fn="1/x")
    app.cut_from.set("5")
    app.cut_to.set("9")  # in T, while x is 1/B
    app.add_cut()
    assert app.error_label["text"].startswith("Splicing error: there are no points")


def test_links_share_what_they_tick(app):
    plot(app)
    app.set_layout(1, 2)
    app.selected = (0, 0)
    app._link((0, 0), (0, 1))
    app.selected = (0, 0)
    app._load_controls()
    app.smooth.set(smoothing.METHODS["mean"])
    app.apply_controls()
    other = app.panels[(0, 1)].lines[0]
    assert other.smooth == ""  # Smoothing isn't ticked to start with
    app.sync_vars["cut"].set(True)
    app.set_sync("cut")
    app.cut_from.set("5")
    app.cut_to.set("9")
    app.add_cut()
    assert other.cutting == ("keep", ((5.0, 9.0),))
    app.add_line()
    assert len(app.panels[(0, 1)].lines) == 2  # lines stay paired


def test_derived_panels_follow_every_setting(app):
    plot(app)
    app.new_derived_panel("d1")
    app.selected = (0, 0)
    app._load_controls()
    app.cut_from.set("5")
    app.cut_to.set("9")
    app.add_cut()
    app.smooth.set(smoothing.METHODS["median"])
    app.apply_controls()
    derived = app.panels[(1, 0)].lines[0]
    assert derived.cutting == ("keep", ((5.0, 9.0),)) and derived.smooth == "median"
    x, _ = drawn(app, (1, 0))
    assert x.min() >= 5 and x.max() <= 9


def test_undo_one_step(app):
    plot(app)
    app.cut_from.set("5")
    app.cut_to.set("9")
    app.add_cut()
    app.cut_index = 0
    app.delete_cut()
    app.undo()
    assert app.panel.line.cuts == ((5.0, 9.0),)
    app.undo()
    assert app.status["text"] == "Nothing to undo."


def test_session_save_and_open(app, tmp_path):
    plot(app)
    app.cut_from.set("5")
    app.cut_to.set("9")
    app.add_cut()
    app.set_layout(1, 2)
    path = tmp_path / "s.json"
    app.save_session(path)
    saved = json.loads(path.read_text())
    assert saved["format"] == 6 and saved["cols"] == 2
    app.set_layout(1, 1)
    app.cut_mode.set(splicing.MODES[""])
    app.apply_controls()
    app.open_session(path)
    assert app.cols == 2
    assert app.panels[(0, 0)].lines[0].cutting == ("keep", ((5.0, 9.0),))


def test_save_figure(app, tmp_path):
    plot(app)
    app.save()
    assert (tmp_path / "output" / "run_005_M006_AH_vs_Norminal_FIeld.png").is_file()


def test_no_tab_widens_the_controls_column(app):
    """Every tab leaves the column as wide as the controls above the tabs make
    it, so switching tabs never pushes the plot over."""
    plot(app)
    app.cut_from.set("5")
    app.cut_to.set("9")
    app.add_cut()  # a range in the Splicing list
    widths = {}
    for tab in app.tabs:
        app.tab.set(tab)
        app._show_tab()
        app.update_idletasks()
        widths[tab] = app.side_inner.winfo_reqwidth()
    assert len(set(widths.values())) == 1, widths
