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


def buttons(widget):
    """The texts of the ttk buttons shown in `widget`, top to bottom."""
    found = []
    for child in widget.winfo_children():
        if child.winfo_manager() and child.winfo_class() == "TButton":
            found.append(child["text"])
        elif child.winfo_manager():
            found += buttons(child)
    return found


def test_this_panel_turns_into_its_fft_and_undo_turns_it_back(app):
    plot(app, x_fn="1/x")
    app.fit_mode.set("Subtract")
    app.apply_controls()
    panel = app.panel
    panel.x_min, panel.title = 0.05, "My data"
    app.in_place("fft")
    assert len(app.panels) == 1 and app.panel is panel and panel.operation == "fft"
    assert panel.x_min is None and panel.title is None  # in T, not frequency
    frequency, amplitude = drawn(app)
    assert frequency[np.argmax(amplitude)] == pytest.approx(F, rel=0.05)
    derive = buttons(app.tabs["Derive"])
    assert derive.count("Undo") == 1 and "Back to data" not in derive
    # The Derivative section's This panel swaps it for a derivative; Undo still
    # goes back to the data.
    app.in_place("d1")
    assert panel.operation == "d1" and buttons(app.tabs["Derive"]).count("Undo") == 1
    app.undo_in_place()
    assert panel.operation == "" and panel.data_view is None
    assert (panel.x_min, panel.title) == (0.05, "My data")
    assert "Undo" not in buttons(app.tabs["Derive"])


def test_this_panel_is_only_for_data_panels(app):
    plot(app)
    app.new_derived_panel("fft")
    app.in_place("d1")
    assert app.panel.operation == "fft" and app.panel.data_view is None
    assert "Back to data" in buttons(app.tabs["Derive"])


def test_this_panel_survives_undo_and_sessions(app, tmp_path):
    plot(app)
    app.panel.y_max = 3.0
    app.in_place("d2")
    app.derivative_window.set("101")
    app.apply_derivative()
    app.undo()  # the window change, not the turning
    assert app.panel.operation == "d2" and app.panel.derivative_window == 51
    assert buttons(app.tabs["Derive"]).count("Undo") == 1
    path = tmp_path / "s.json"
    app.save_session(path)
    app.open_session(path)
    assert app.panel.data_view == (None, None, None, 3.0, None, None, None)
    app.undo_in_place()
    assert app.panel.y_max == 3.0 and not app.panel.derived


def test_undo_forgets_ranges_in_an_x_that_changed(app):
    plot(app)
    app.panel.x_min, app.panel.y_max, app.panel.x_label = 5.0, 3.0, "B"
    app.in_place("fft")
    app.x_fn.set("1/x")  # F needs 1/B; 5 T means nothing there
    app.apply_controls()
    app.undo_in_place()
    assert (app.panel.x_min, app.panel.y_max) == (None, 3.0)
    app.panel.x_min = 0.1
    app.in_place("d1")
    app.swap()
    app.undo_in_place()
    assert (app.panel.x_max, app.panel.y_min, app.panel.y_max) == (3.0, 0.1, None)
    assert app.panel.y_label == "B"


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
    # The Derive tab's This panel row, on panels it has turned.
    app.tab.set("Derive")
    app._show_tab()
    for operation in ("fft", "d2"):
        app.in_place(operation)
        app.update_idletasks()
        widths[f"Derive, {operation} here"] = app.side_inner.winfo_reqwidth()
    assert len(set(widths.values())) == 1, widths
