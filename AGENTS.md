# Notes for agents working on CMP Plotter

A Tk + matplotlib window for plotting columns of capacitance-bridge (CMP)
data files against each other. README.md describes it from the user's side;
this file is what isn't obvious from the code.

## Running

```bash
uv run cmp-plotter
```

Python 3.13, managed by uv; dependencies are in `pyproject.toml`. There's no
test suite. Check changes by driving the real window from a script (below)
and by looking at a saved figure or a screenshot.

The folder above this repo (`../Analysis/data`) holds real runs
(`Cambridge_Sep_26.00N.text`) with a `cmp-plotter.json` profile; run 005
(a 28 T → 1 T sweep, 13k rows) and run 003 (24k rows, ~10k of them parked
at 28 T) are the useful ones. `../Analysis/squiggle-finder.py` is the
offline oscillation analysis the Smoothing and Background sections mirror.

## Layout

| File | What's in it |
|---|---|
| `plotter.py` | the window: controls, drawing, zoom, saving |
| `model.py` | `Line` and `Panel`, colours, legend text, shared axis labels |
| `smoothing.py` | moving average, median, Savitzky–Golay; windows in points or x |
| `background.py` | polynomial fit in x, shown or subtracted |
| `axis_functions.py` | the Function boxes (`1/x`, `exp(y)`, ...) |
| `datasets.py`, `format_dialog.py`, `profile.py`, `columns.py` | reading files and per-folder profiles |
| `widgets.py` | colour picker, layout grid |

## How a line is drawn

`Plotter._draw_panel`, per `Line`:

1. read the columns, apply the axis functions (`_axis`)
2. background (`background.apply`): fit on the unsmoothed data
3. smoothing (`smoothing.smooth`), on what's left
4. one `ax.plot` call

Keep that order. Things that depend on it:

- **One artist per `Line`.** The legend labels and `_show_colour` zip
  `ax.lines` against the panel's lines, and `self.artists` maps each artist to
  a line index. A second artist per line breaks all three; that's why "show
  the fit" is a mode on a copied line, not an overlay.
- **`Line.shown`** is the tuple of what was last drawn:
  `(run, x, x_fn, y, y_fn, smoothing, fitting)`. `parts()`, `legend_labels`,
  `_default_name` and the zoom logic in `apply_controls` all index into it, so
  a new per-line setting means updating each of them.
- **Settings in x units** (`Line.span`, `fit_from`, `fit_to`) are in the
  *plotted* x, after its function. They're cleared whenever x or its function
  changes, or on ⇅, since a value in T means nothing in 1/B.
- Errors are stored in `Line.error` as `"<Stage> error: message"`; the text
  before the first `": "` becomes the popup title.

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
- **The controls column is a scrolling canvas** (`self.side`) with the Save
  area pinned below it; the scrollbar shows only when the column is taller
  than the window.

## Testing by script

Build the window, patch the popups so they can't block, drive the controls,
then read the state:

```python
from cmp_plotter import plotter as P
P.messagebox.showerror = lambda title, message, parent=None: print(title, message)
app = P.Plotter()                      # uses ~/.config/cmp-plotter/settings.json
app.run.set(next(n for n in app.datasets if "005" in n)); app.apply_controls()
app.smooth.set("Savitzky-Golay"); app.apply_controls()
print(app.panel.line.shown, app.panel.line.error)
app.fig.savefig("/some/scratch/dir/check.png")
app.destroy()
```

Wrap runs in `timeout`: an unpatched popup waits forever. Don't call
`choose_folder`, which rewrites the user's settings file.

## Style

- Match the surrounding code: short docstrings that say why, plain names,
  comments only where the reason isn't visible.
- UI text is plain and short; the left column is ~330 px wide, so check that
  a new control doesn't widen it (`app.side_inner.winfo_reqwidth()`).
- Update README.md's **Use** section when behaviour changes.
- Commits: an imperative subject line, then a body saying what changed and
  why, ending with the `Co-Authored-By` line the earlier commits use.
