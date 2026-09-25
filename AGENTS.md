# Notes for agents working on GOOSE Plotter

GOOSE (Graphical Oscillation Observation Software Environment), formerly
CMP Plotter: a Tk + matplotlib window for plotting columns of
capacitance-bridge (CMP) data files against each other. README.md describes it from the user's side;
this file is what isn't obvious from the code.

## Running

```bash
uv run goose-plotter
```

Python 3.13, managed by uv; dependencies are in `pyproject.toml`. There's no
test suite. Check changes by driving the real window from a script (below)
and by looking at a saved figure or a screenshot.

No data ships with the repo. On the author's machine it sits inside a
Huairou-CMP folder whose `Analysis/data` holds real runs
(`Cambridge_Sep_26.00N.text`) with a `goose-plotter.json` profile; run
005 (a 28 T → 1 T sweep, 13k rows) and run 003 (24k rows, ~10k of them
parked at 28 T) are the useful ones, and `Analysis/squiggle-finder.py` is
the offline oscillation analysis the Smoothing, Background and FFT features
mirror. If that folder isn't around this repo, use whatever data folder
`~/.config/goose-plotter/settings.json` points at, or ask for some.

## Layout

| File | What's in it |
|---|---|
| `plotter.py` | the window: controls, drawing, zoom, saving |
| `model.py` | `Line` and `Panel`, colours, legend text, shared axis labels |
| `smoothing.py` | moving average, median, Savitzky–Golay; windows in points or x |
| `background.py` | polynomial fit in x, shown or subtracted |
| `spectrum.py` | FFT of a line against its plotted x, for FFT panels; `even_grid`, the binning it shares |
| `derivative.py` | first and second derivatives on `even_grid`, for derivative panels |
| `axis_functions.py` | the Function boxes (`1/x`, `exp(y)`, ...) |
| `datasets.py`, `format_dialog.py`, `profile.py`, `columns.py` | reading files and per-folder profiles |
| `widgets.py` | the line and axes editors, colour picker, layout grid, overwrite question |
| `session.py` | panels and lines to and from JSON-ready data, for session files and undo |
| `theme.py` | the window's colours and ttk styling; use its names, not hex codes, in Tk widgets |

## How a line is drawn

`Plotter._draw_panel`, per `Line`, via `_line_data`:

1. read the columns, apply the axis functions (`_axis`)
2. background (`background.apply`): fit on the unsmoothed data
3. smoothing (`smoothing.smooth`), on what's left
4. in a derived panel only, `spectrum.spectrum` or `derivative.derivative` of
   that against x
5. one `ax.plot` call

`_line_data` caches steps 1–3 per line, keyed on the line's settings, so a
data panel and its derived panels do the work once; `_reload_folder` clears it.

Keep that order. Things that depend on it:

- **One artist per `Line`.** The legend labels and `_show_colour` zip
  `ax.lines` against the panel's lines, and `self.artists` maps each artist to
  a line index. A second artist per line breaks all three; that's why "show
  the fit" is a mode on a copied line, not an overlay.
- **`Line.shown`** is the tuple of what was last drawn:
  `(run, x, x_fn, y, y_fn, smoothing, fitting)`. `parts()`, `legend_labels`,
  `_default_name` and the zoom logic in `apply_controls` all index into it, so
  a new per-line setting means updating each of them.
- **Style isn't in `shown`**, on purpose: `Line.style`, `width`, `marker`,
  `marker_size` and `label` go through `Line.plot_style()` and the legend only, so they
  don't touch the `_line_data` cache, the filename or the zoom logic. A
  width of None means `auto_width` (heavier for a shown fit), and a
  `marker_size` of None `AUTO_MARKER_SIZE`; `apply_controls` only stores the
  box's number if it differs from the auto one it showed.
- **Settings in x units** (`Line.span`, `fit_from`, `fit_to`) are in the
  *plotted* x, after its function. They're cleared whenever x or its function
  changes, or on ⇅, since a value in T means nothing in 1/B.
- Errors are stored in `Line.error` as `"<Stage> error: message"`.
  `_show_error` shows the selected line's under the axes boxes; it runs from
  `_load_controls`, which every redraw path ends in, so there's no popup.

## Derived panels are linked panels

`Panel.operation` makes a derived panel: "fft", "d1" or "d2" ("" is a data
panel; `Panel.derived`). It draws that of its own lines. `_derived` makes
one with copies of its data panel's lines, in that panel's link group, with
every SYNC key ticked on both, so it follows every change through the link
(see below) and can be frozen or partly synced like any linked panel.
`source` is only the cell it was made from, for "FFT of panel N";
`_tidy_link_groups` clears it once the panel no longer shares a group with
that one (unlinked, deleted, removed by the layout). So:

- Check `derived` / `operation`, never `source`, for whether a panel is
  derived. `operation` only matters where FFTs and derivatives differ
  (drawing, the Operations boxes, `_default_name`).
- Derived panels are only made from data panels (no FFT of a derivative),
  and there's no fit-range picking on them. Putting one on a panel already
  derived from the same data just changes its `operation`. **Back to data**
  (`back_to_data`) sets it to "".
- `_line_data` caches by `_data_key` (the settings through smoothing), not
  by line, so a data panel and its derived panels do the work once; a hit
  also fills in an x-unit span the line hasn't got yet. `_changed` prunes it
  to the lines still in the panels.
- `spectrum.even_grid` bins at bin centres for FFTs; derivatives pass
  `at_mean_x`, since the half-step error there becomes noise once
  differentiated. Keep the FFT's binning as it is unless you mean to change
  its output.

## Linked data

`Panel.link_group` puts panels in a group whose lines match line by line:
the panels have the same number of lines, and share the settings they sync.
`model.SYNC` maps each Sync tick box's key to the `Line` fields it covers;
`Panel.sync` is the space-separated keys a panel ticks (a string, so sessions
save it as they are), read through `Panel.synced`. A key syncs between two
panels only if both tick it. Each panel has its own `Line` objects, and
axis ranges and zoom are each panel's own. So:

- After changing a line's settings, call `_sync_inputs(cell)`, which copies
  the ones both sides sync to the group (clearing a member's x-unit settings
  if its x changes, and never copying `X_UNITS` between different x);
  `apply_controls`, `swap`, the line editor and the colour picker do. Keep
  `SYNC`'s "x" before the keys holding x-unit settings: that clearing runs
  after x is copied. Add and remove lines through `add_line` /
  `remove_line`, which do it in every list in `_group_lists`.
- `Panel.frozen` makes `_sync_inputs`
  skip it both ways; `freeze` sends its settings on unfreezing. Lines are
  still added and removed across frozen panels, so pairs stay matched.
  Leaving a group (`unlink_panel`, `_tidy_link_groups`) unfreezes it.
- `_tied(cell)` is every panel a change shows in: the group plus each
  member's FFT or data panel. `_redraw_selected` redraws those.
- A group's FFT panel shares one member's list, so `_group_lists`
  deduplicates by identity: never replace a list, only change it in place.

## Typed axis ranges

`Panel.x_min` ... `y_max` (`model.RANGES`) are in the plotted units, like
the x-unit line settings, so they're cleared the same way: `_clear_ranges`
when a line's x or y changes, including a linked member's in
`_sync_inputs`; ⇅ swaps a data panel's (a derived panel's are cleared);
changing a derived panel's operation, or `back_to_data`, clears them. `_draw_panel`
applies them after drawing, which turns autoscaling off, so the zoom-keeping
in `_redraw_selected` treats them as user-set: after changing them, redraw
with `keep=""` (as `apply_axes` does) or the old range comes back.

The title, labels and legend names (`Panel.title`, `x_label`, `y_label`,
`Line.label`) are None for the automatic text and "" for none. `_draw_panel`
keeps what it drew in `auto_text` / `auto_names` for the editors to show;
Enter on a box still showing that text leaves it None. Sessions before
format 3 used "" for automatic, and `load` converts them. Typed texts are
checked with `text_problem` before they're stored: bad mathtext only fails when the
canvas draws, and on the real figure that would break every redraw after.

## Sessions

`session.dump` / `session.load` turn `self.panels` into plain data and back;
`Plotter._restore` swaps it in. `dump` marks its output with `FORMAT`;
without it `load` reads the version 1 layout (`_load_old`), where a derived
panel had no lines of its own and every panel an "fft" operation. `load` drops unknown or mistyped fields and menu values that
aren't keys, and raises ValueError for anything that isn't a session, before
anything changes. A new `Line` or `Panel` field is saved automatically unless
it's in `session.SKIP`; one whose value must be a menu key goes in
`session.CHOICES` too.

## Undo

One step, built on the session snapshot: `_changed()` runs after every redraw
(`_build_axes`, `_redraw_selected`) and colour change, and when the panels'
`session.dump` differs from the last one, that last one becomes
`undo_state`. So a new action needs no undo code of its own as long as it
ends in one of those redraws. The colour picker calls it with `merge=True`,
making a drag one step. `undo` restores with `restoring` set, so the restore
isn't recorded as a change. Selection isn't in the snapshot, so selecting
isn't a step. Opening a session is undoable, but not its data-folder switch.

## Things that look odd but are deliberate

- **Row order, not sorted x.** The field record jitters (hundreds of direction
  reversals per run) and parks at the ends of sweeps, so smoothing windows
  and x-unit windows follow the rows in the order they were taken.
  `smoothing.stretches` finds, per row, the unbroken run of rows within the
  window in x.
- **No scipy.** Savitzky–Golay is done in numpy (it matches
  `scipy.signal.savgol_filter` to rounding error); `background.fit` uses
  `numpy.polynomial.Chebyshev.fit` so high degrees stay well conditioned.
- **Drawn icons and triangles**, not Unicode arrows: Tk's X core fonts can
  show them as '®'. The same goes for text: in Tk widgets − (minus), – (en
  dash) and → show as '®' and Δ as '∈'. matplotlib draws them fine, so plot
  text keeps them and anything Tk shows goes through `plain()` in
  `plotter.py`, or is written in ASCII (the "Savitzky-Golay" method name).
  `·` and `×` are fine.
- **Zoom survives redraws** only for limits the user set (zooming turns
  matplotlib's autoscale off). `_redraw_selected(keep)` restores those and
  pushes the full view first so the toolbar's Home still works.
- **Tabs aren't a `ttk.Notebook`**: a Notebook is as tall as its tallest
  tab, which would keep the column long. `_show_tab` packs one frame of
  `self.tabs` and hides the others, so the column fits the tab shown.
- **The controls column is a scrolling canvas** (`self.side`) with the Save
  area pinned below it; the scrollbar shows only when the column is taller
  than the window, in a slot that keeps its width either way so the plot
  doesn't shift.

## Testing by script

Build the window, patch the popups so they can't block, drive the controls,
then read the state:

```python
from goose_plotter import plotter as P
P.messagebox.askyesno = lambda *a, **k: True  # the only popup questions left
app = P.Plotter()                      # uses ~/.config/goose-plotter/settings.json
app.run.set(next(n for n in app.datasets if "005" in n)); app.apply_controls()
app.smooth.set("Savitzky-Golay"); app.apply_controls()
print(app.panel.line.shown, app.error_label["text"])
app.fig.savefig("/some/scratch/dir/check.png")
app.destroy()
```

`askyesno` comes up when making FFT or derivative panels or linking. Wrap runs in
`timeout`: an unpatched popup waits forever. Don't call
`choose_folder`, which rewrites the user's settings file.

## Style

- Match the surrounding code: short docstrings that say why, plain names,
  comments only where the reason isn't visible.
- UI text is plain and short; the left column is ~330 px wide, so check that
  a new control doesn't widen it (`app.side_inner.winfo_reqwidth()`).
- Update README.md's **Use** section when behaviour changes.
- Commits: an imperative subject line, then a body saying what changed and
  why, ending with the `Co-Authored-By` line the earlier commits use.
