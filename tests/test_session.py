"""Sessions and undo snapshots: the panels to plain data and back, old formats included."""

import json

import pytest

from goose_plotter import session
from goose_plotter.model import (SYNC, Line, Link, Panel, legend_labels, line_colours)


def state(**panel_kw):
    """A 2 x 1 layout: a data panel with a cut line, and its FFT linked to it."""
    line = Line(run="r.005", x="B", x_fn="1/x", y="M006_AH", smooth="savgol", window=31,
                background="subtract", degree=4, cut="remove", cuts=((0.1, 0.2), (0.3, None)),
                colour="#123456", label="mine")
    data = Panel([line, Line(run="r.003")], **panel_kw)
    fft = Panel([l.copy() for l in data.lines], source=(0, 0), operation="fft", pad=4)
    links = {frozenset((data.id, fft.id)): Link(" ".join(SYNC))}
    return {(0, 0): data, (1, 0): fft}, links


def test_round_trip_through_json():
    panels, links = state(title="$B$ sweep", x_min=0.1)
    dumped = session.dump(panels, 2, 1, links)
    rows, cols, loaded, loaded_links = session.load(json.loads(json.dumps(dumped)))
    assert (rows, cols) == (2, 1)
    assert loaded[(0, 0)].lines[0].cuts == ((0.1, 0.2), (0.3, None))
    assert loaded[(0, 0)].title == "$B$ sweep" and loaded[(0, 0)].x_min == 0.1
    assert loaded[(1, 0)].operation == "fft" and loaded[(1, 0)].source == (0, 0)
    assert loaded_links == links
    # Undo compares dumps, so a loaded state must dump the same as the original.
    assert session.dump(loaded, rows, cols, loaded_links) == dumped


def test_bad_values_are_dropped_not_fatal():
    panels, links = state()
    dumped = json.loads(json.dumps(session.dump(panels, 2, 1, links)))
    line = dumped["panels"]["0,0"]["lines"][0]
    line.update(smooth="wobble", window=-3, width="thick", cut="sometimes", colour=None)
    dumped["panels"]["0,0"]["legend"] = "centre stage"
    loaded = session.load(dumped)[2][(0, 0)]
    assert (loaded.lines[0].smooth, loaded.lines[0].window, loaded.lines[0].cut) == ("", 21, "")
    assert loaded.legend == "auto"


def test_not_a_session():
    for bad in ({}, {"rows": 1}, {"rows": "x", "cols": 1, "panels": {}}, [1, 2]):
        with pytest.raises(ValueError):
            session.load(bad)
    with pytest.raises(ValueError, match="bigger"):
        session.load({"rows": 99, "cols": 1, "panels": {}})


def test_duplicate_ids_are_made_distinct():
    panels, links = state()
    dumped = session.dump(panels, 2, 1, links)
    dumped["panels"]["1,0"]["id"] = dumped["panels"]["0,0"]["id"]
    loaded = session.load(dumped)[2]
    assert loaded[(0, 0)].id != loaded[(1, 0)].id


def test_format_5_single_cut_becomes_one_range():
    panels, links = state()
    dumped = json.loads(json.dumps(session.dump(panels, 2, 1, links)))
    dumped["format"] = 5
    line = dumped["panels"]["0,0"]["lines"][0]
    del line["cuts"]
    line.update(cut="keep", cut_from=0.5, cut_to=0.2)
    assert session.load(dumped)[2][(0, 0)].lines[0].cuts == ((0.2, 0.5),)


def test_before_format_5_derived_links_share_the_cut():
    panels, links = state()
    dumped = json.loads(json.dumps(session.dump(panels, 2, 1, links)))
    dumped["format"] = 4
    for link in dumped["links"]:
        link["sync"] = " ".join(k for k in link["sync"].split() if k != "cut")
    loaded_links = session.load(dumped)[3]
    assert all("cut" in link.synced for link in loaded_links.values())


def test_before_format_5_partial_links_between_data_panels_stay_partial():
    a, b = Panel([Line(run="r")]), Panel([Line(run="r")])
    dumped = session.dump({(0, 0): a, (0, 1): b}, 1, 2,
                          {frozenset((a.id, b.id)): Link("run x y")})
    dumped["format"] = 4
    (link,) = session.load(dumped)[3].values()
    assert link.synced == {"run", "x", "y"}


def test_version_1_layout():
    """Derived panels had a source and no lines; they get copies, linked."""
    old = {"rows": 2, "cols": 1, "panels": {
        "0,0": {"lines": [{"run": "r.005", "y": "M006_AH"}], "link_group": None},
        "1,0": {"source": "0,0"}}}
    rows, cols, panels, links = session.load(old)
    fft = panels[(1, 0)]
    assert fft.operation == "fft" and fft.lines[0].y == "M006_AH"
    (link,) = links.values()
    assert link.synced == set(SYNC)


def test_format_2_blank_text_was_automatic():
    old = {"format": 2, "rows": 1, "cols": 1,
           "panels": {"0,0": {"title": "", "lines": [{"label": ""}]}}}
    panel = session.load(old)[2][(0, 0)]
    assert panel.title is None and panel.lines[0].label is None


# --- model ------------------------------------------------------------------

def test_legend_names_only_what_differs():
    base = dict(run="r.005", x="B", x_fn="x", y="M006_AH", y_fn="y", smoothing=None,
                fitting=None, cutting=None)
    lines = [Line(shown=tuple(base.values())),
             Line(shown=tuple({**base, "cutting": ("keep", ((1.0, 2.0),))}.values()))]
    assert legend_labels(lines) == ["M006_AH", "M006_AH · x 1–2"]
    lines[1].shown = tuple({**base, "run": "r.003"}.values())
    assert legend_labels(lines) == ["run 005", "run 003"]


def test_line_colours_avoid_clashes():
    panel = Panel([Line(y="M006_AH"), Line(y="M006_AH"), Line(y="M011_AH", colour="#000000")])
    colours = line_colours(panel, {"M006": "#2a78d6", "M011": "#eb6834"})
    assert colours[0] == "#2a78d6" and colours[2] == "#000000"
    assert len(set(colours)) == 3


def test_changing_x_clears_every_x_unit_setting():
    line = Line(span=0.1, fit_from=1.0, fit_to=2.0, cut="keep", cuts=((1.0, 2.0),))
    line.clear_x_units()
    assert (line.span, line.fit_from, line.fit_to, line.cuts) == (None, None, None, ())
    assert line.cutting is None and line.cut == "keep"  # the mode stays for new ranges
