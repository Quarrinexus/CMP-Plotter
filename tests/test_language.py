"""The window in Simplified Chinese: every text it shows has a translation,
none widens the controls column, and a language change carries on where the
window was."""

import pytest

from goose_plotter import background, i18n, smoothing, splicing
from goose_plotter.i18n import shown
from conftest import drawn, plot
from test_plotter import click


@pytest.fixture
def language():
    return "zh"


@pytest.fixture(autouse=True)
def fresh_missing():
    """Forget texts missed before, so each test counts only its own window's."""
    i18n.missing.clear()
    yield
    i18n.set_language("en")


def exercise(app, tmp_path):
    """Open everything there is to open, so every text is looked up."""
    plot(app, x_fn="1/x")
    for tab in app.tabs:
        app.tab.set(tab)
        app._show_tab()
    for key in smoothing.METHODS:
        app.smooth.set(shown(smoothing.METHODS, key))
        app.apply_controls()
    app.window_unit.set(shown(smoothing.UNITS, True))
    app.apply_controls()
    app.window_unit.set(shown(smoothing.UNITS, False))
    app.smooth.set(shown(smoothing.METHODS, ""))
    app.fit_mode.set(shown(background.MODES, "subtract"))
    app.apply_controls()
    app.cut_from.set("0.05")
    app.cut_to.set("0.1")
    app.add_cut()
    app.cut_index = 0
    app.delete_cut()
    app.cut_mode.set(shown(splicing.MODES, ""))
    app.apply_controls()
    app.pick_range("cut")
    app.stop_picking()
    app.pick_range()
    app.stop_picking()
    app.set_region((0.05, 0.1))
    app.mark_var.set(True)
    app.apply_measure()
    x, y = drawn(app)
    app.read_points()
    click(app, x[100], y[100])
    click(app, x[300], y[300])
    app.stop_picking()
    app.copy_measurements()
    app.export_measurements(tmp_path / "m.csv")
    app.in_place("fft")
    app.in_place("d1")
    app.undo_in_place()
    app.new_derived_panel("fft")
    app.in_place("d2")  # refused: a derived panel
    app.existing_derived_panel("d1")
    app.stop_picking()
    app.new_derived_panel("d1")
    app.link_panels()
    app.stop_picking()
    app.freeze()
    app.freeze()
    app.selected = (0, 0)
    app._load_controls()
    app.undo()
    app.undo()
    app.open_axes()
    app.open_style()
    app.open_save_options()
    app.save_session(tmp_path / "s.json")
    app.open_session(tmp_path / "s.json")
    app.save()
    app.update_idletasks()


def test_every_text_has_a_translation(app, tmp_path):
    exercise(app, tmp_path)
    assert not i18n.missing, sorted(i18n.missing)


def literal_keys():
    """Every English text written out in a tr() call in the source."""
    import ast
    from pathlib import Path
    import goose_plotter
    keys = set()

    def collect(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            keys.add(node.value)
        elif isinstance(node, ast.IfExp):
            collect(node.body)
            collect(node.orelse)
    for path in Path(goose_plotter.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "tr" and node.args):
                collect(node.args[0])
    return keys


def test_every_text_in_the_source_and_menus_is_translated():
    from goose_plotter import derivative, format_dialog, model, plotter, spectrum
    menus = [smoothing.METHODS, smoothing.UNITS, background.MODES, splicing.MODES,
             spectrum.WINDOWS, derivative.ORDERS, model.STYLES, model.MARKERS, model.LEGENDS,
             model.GRIDS, model.GRID_AXES, model.GRID_STYLES, plotter.Plotter.KINDS]
    wanted = literal_keys() | {v for m in menus for v in m.values()}
    wanted |= set(format_dialog.CHOICES) | {"Other", "Process", "Splicing", "Derive",
                                            "Linking", "Measure"}
    assert not wanted - set(i18n.ZH), sorted(wanted - set(i18n.ZH))
    for mapping in menus:  # key_of reads a menu back by its text, so none may repeat
        texts = [i18n.ZH[v] for v in mapping.values()]
        assert len(set(texts)) == len(texts), texts


def test_translations_keep_their_places_and_fit_tks_fonts():
    """The same {places} as the English, and only characters the X core fonts'
    Chinese (GB2312) has, with none of those plain() swaps for ASCII."""
    from string import Formatter
    from goose_plotter.plotter import PLAIN

    def places(text):
        return {name for _, name, _, _ in Formatter().parse(text) if name}
    for english, chinese in i18n.ZH.items():
        assert places(english) == places(chinese), english
        chinese.encode("gb2312")
        assert not set(chinese) & {chr(c) for c in PLAIN}, english


def test_chinese_widens_nothing(app, tmp_path):
    """Every tab, the Measure tab filled in, and the longest message fit the column."""
    plot(app)
    widths = {}
    for tab in app.tabs:
        app.tab.set(tab)
        app._show_tab()
        app.update_idletasks()
        widths[tab] = app.side_inner.winfo_reqwidth()
    app.set_region((5, 9))
    x, y = drawn(app)
    app.read_points()
    click(app, x[100], y[100])
    click(app, x[200], y[200])
    app.stop_picking()
    app.in_place("fft")
    app.update_idletasks()
    widths["Measure, filled in"] = app.side_inner.winfo_reqwidth()
    assert len(set(widths.values())) == 1, widths
    assert max(app.tab_strip.spans[t][1] for t in app.tabs) <= app.tab_strip.winfo_width()
    status = app.status.master.winfo_width()
    for english in i18n.ZH:
        if english.startswith(("Panel {target}", "Replace panel {target}")):
            continue  # asked in a dialog, not shown in the column
        app._say(i18n.tr(english))
        app.update_idletasks()
        assert app.status.winfo_reqwidth() <= status, english


def test_changing_language_carries_on(app, tmp_path):
    from goose_plotter.plotter import Plotter
    plot(app)
    app.set_region((5, 9))
    app.add_line()
    app.tab.set("Measure")
    app._show_tab()
    app.filename.set("mine.png")
    app.new_plot()  # a second plot, then back to the first
    app.switch_plot(1)
    app.set_language("en")
    state = app.relaunch
    assert state is not None and app.settings["language"] == "en"
    app.update()  # the old window closes
    again = Plotter(state)
    try:
        assert i18n.language == "en" and again.tab.get() == "Measure"
        assert again.panel.region == (5.0, 9.0) and len(again.panel.lines) == 2
        assert again.panel.selected == 1 and again.filename.get() == "mine.png"
        assert again.undo_state is not None  # the undo step came across too
        again.undo()
        assert len(again.panel.lines) == 1
        assert [p["n"] for p in again.plots] == [1, 2]  # both plots came across
        again.switch_plot(2)
        assert again.panel.line.run == ""
    finally:
        again.destroy()


def test_every_chinese_character_has_a_glyph(app):
    """On X11, Tk would take some characters from Japanese or Korean fonts
    that lack them (drawn as boxes); the window's font must have them all."""
    family = i18n.FONTS["zh"][0]
    if app.tk.call("tk", "windowingsystem") != "x11" or family not in app.tk.call(
            "font", "families"):
        pytest.skip(f"only X11's core fonts need {family}")
    chars = {c for text in i18n.ZH.values() for c in text if ord(c) > 0x2000}
    drawn_by = {c: app.tk.call("font", "actual", "TkDefaultFont", "-family", c) for c in chars}
    assert {c for c, f in drawn_by.items() if f != family} == set()
    tab_font = app.tab_strip.itemcget(app.tab_strip.find_withtag("all")[-1], "font")
    assert app.tk.call("font", "actual", tab_font, "-size") == app.tk.call(
        "font", "actual", "TkDefaultFont", "-size")  # the tabs aren't a size smaller


@pytest.mark.parametrize("language", ["en", "zh"])
def test_the_language_menu_names_each_in_a_font_that_has_it(app):
    family = i18n.FONTS["zh"][0]
    if app.tk.call("tk", "windowingsystem") != "x11" or family not in app.tk.call(
            "font", "families"):
        pytest.skip(f"only X11's core fonts need {family}")
    menu = app._language_menu()
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]
    chinese = labels.index(i18n.LANGUAGES["zh"])
    font = menu.entrycget(chinese, "font") or menu.cget("font")
    assert {app.tk.call("font", "actual", font, "-family", c)
            for c in i18n.LANGUAGES["zh"]} == {family}
