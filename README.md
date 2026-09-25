# GOOSE Plotter

GOOSE, the **G**raphical **O**scillation **O**bservation **S**oftware
**E**nvironment: an interactive Tk window for plotting columns from delimited text data files
(`.txt`, `.text`, `.csv`, `.tsv`, `.dat`). The preamble, header line and
delimiter are detected automatically.

## Install

### Linux and macOS

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Get the code:
   ```bash
   git clone https://github.com/Quarrinexus/GOOSE-Plotter.git
   cd GOOSE-Plotter
   ```
3. Run it. The first run downloads Python 3.13 and the dependencies into
   `.venv`; later runs start straight away.
   ```bash
   uv run goose-plotter
   ```

### Windows

In PowerShell:

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/),
   then close and reopen PowerShell so the `uv` command is found:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
2. Get the code, either with [Git for Windows](https://git-scm.com/download/win):
   ```powershell
   git clone https://github.com/Quarrinexus/GOOSE-Plotter.git
   cd GOOSE-Plotter
   ```
   or by downloading the ZIP from GitHub (Code > Download ZIP), extracting
   it, and running `cd` into the extracted folder.
3. Run it. As on Linux, the first run downloads Python 3.13 (Tk included)
   and the dependencies; later runs start straight away.
   ```powershell
   uv run goose-plotter
   ```

Settings are kept in `C:\Users\<you>\.config\goose-plotter\settings.json`.

### A command that works from any folder

On any system, instead of `uv run` from the project folder:

```bash
uv tool install .
```

`uv tool uninstall goose-plotter` removes it. If the `goose-plotter` command
isn't found afterwards, run `uv tool update-shell` and open a new terminal.

## Update

From the project folder, get the latest code:

```bash
git pull
```

If you downloaded the ZIP instead, download it again and extract it over the
old folder (or somewhere new).

With `uv run goose-plotter` there's nothing more to do: the next run picks up
the new code, and any new dependencies, by itself. If you installed the
command with `uv tool install .`, reinstall it from the project folder:

```bash
uv tool install --reinstall .
```

Your settings (`~/.config/goose-plotter/settings.json`) and each data folder's
`goose-plotter.json` profile live outside the project folder, so updating
keeps them.

## Use

At the top of the controls column, **Files** opens to the folders, Data
format and sessions (it starts closed once both folders are chosen). Under
it Dataset, the Lines list and the axes are always shown, and the rest is in
three tabs: **Process** (Smoothing, Background), **Operations** (FFT,
Derivative) and **Linking** (Linked data); their sections start open. If
the selected line can't be drawn (a bad function, a
file that won't load, a smoothing window that's too big), the reason shows
in red under the Y axis until it's fixed or another line is selected.
Other messages show above the buttons at the bottom of the column: green
ones (Saved ..., Undone) clear after 10 seconds, red ones stay until the
next message, and instructions for a pick under way (Click the panel ...)
stay until it's done or cancelled.

- **Data / Output folder** (under Files): choose with Browse...; both are
  remembered in `~/.config/goose-plotter/settings.json` (see Windows above).
- **Data format...** (under Files): set the delimiter, column-name line and
  first data line by hand, with a preview. Opens by itself when a file's layout
  can't be detected. Saved for the whole data folder in its profile.
- **Dataset, X axis, Y axis**: any column against any other, sample columns
  (`M006_AH`, `M011_AH_Loss`, ...) included. Changing a control redraws.
- **Function**: under each axis, e.g. `1/x`, `exp(y)`, `log10(x)`; numpy's usual
  functions plus `pi` and `e`. Enter applies.
- **Smoothing**: per line, under the axes. Moving average, median or
  Savitzky–Golay (with its polynomial order) over a window of points, taken in
  the order they were recorded; SG needs an odd window. Or set the window in
  **x units**: the plotted x, so with a `1/x` function on the field the window
  is in 1/B. Each point then uses the unbroken run of rows around it whose x is
  within half the window of its own, so separate sweeps aren't mixed, and SG
  becomes a polynomial fit in x, right for unevenly spaced points. It applies
  to the plotted y, after its function. To see raw and smoothed together, copy the
  line with + and smooth the copy; the legend tells them apart.
- **Background**: per line, under Smoothing. Fits a polynomial of the chosen
  degree to the plotted y against the plotted x (so in 1/B with a `1/x`
  function) and either **Subtract**s it, leaving the oscillations, or
  **Show fit**, which draws the fit dashed in place of the data; copy a line
  with + to lay its fit over it. **Fit x ... to** limits the fit to part
  of the line (leave out the parked ends of a sweep); outside it the line
  isn't drawn. **Pick** sets the range by dragging across the plot.
  The fit comes before smoothing.
- **Line editor**: the box under + and -, which shows the selected line's
  look, opens it. **Colour** (drag in the field and the brightness strip;
  **Automatic** goes back to the sample's colour or a free one), **Line**
  (Auto is solid, or dashed for a shown fit; None leaves only the markers),
  **Width** (**Auto** undoes a set width), **Marker** with its **Size**
  (for any marker but None; **Auto** is 3), and **Name in the
  legend**, also shown in the Lines list (blank: automatic; mathtext works;
  Enter applies). Everything else applies as you click, keeps the zoom, and
  follows whichever line is selected.
- **Axes editor**: the small plot button right of ⇅ opens it, for the selected
  panel (it follows the selection). Type an x or y range (**from** /
  **to**, Enter applies) in the plotted units, so in 1/B with a `1/x`
  function; leave an end blank to let it follow the data. **Use current
  view** fills the boxes from what the panel shows, e.g. after zooming, to
  pin it. A range is cleared when what's on its axis changes (another column
  or function), and ⇅ swaps the x and y ranges. **Title**, **x label** and
  **y label** replace the panel's own (blank: automatic; matplotlib mathtext
  like `$B$ (T)` works); they stay when the data changes, so update them
  with it. **Legend**: Auto shows one for two or more lines, Off hides it,
  and a position (a corner, or Outside right of the panel) shows it there
  even for one line. **Grid**: **show** Off, Major (the default) or Major +
  minor (fainter lines between the major ones), on **axis** Both, x only or
  y only, in **style** Solid, Dashed or Dotted. Legend and Grid apply as you
  click. **Ticks**: **Point inward** turns every panel's tick marks to point
  into the plot instead of out (off to start with); it's a preference for
  all panels, kept in `settings.json` until you untick it.
- **FFT** (Operations tab): **New panel** adds a row with the selected panel's spectrum
  under it; **Existing panel...** puts it in the panel you click next
  (asking first if that panel has lines of its own). The new panel is linked
  to the data panel (see Linked data below, and the Linking tab) with every
  Sync box ticked on both, so changing a line's axes, fit, smoothing or
  colour in either redraws both, and adding or removing a line does too; untick
  a box on it to keep that setting its own (e.g. untick Smoothing to take the
  FFT of the unsmoothed data), or **Freeze** it. The spectrum is of each line as plotted (after its function,
  background and smoothing) against its plotted x, so with `1/x` on the field
  it's in F (T); amplitude is in y's units. Select the FFT panel for its
  settings: Window (Hann or none), Padding (zero-padding, for smoother
  peaks), F max, and **Back to data**, which turns it back into an ordinary
  panel plotting its lines (still linked). Its title gives the frequency resolution,
  ΔF = 1 / (x range).
- **Derivative** (Operations tab): works like FFT. Choose the **Order**
  (First or Second), then **New panel** or **Existing panel...** (clicking
  an FFT panel of the same data turns it into the derivative). The panel shows dy/dx or d²y/dx² of each line as plotted,
  against its plotted x, linked to its data panel the same way. As the rows
  jitter and double back in x, each line is first averaged onto an even grid
  in x, and each point's derivative is read off a Savitzky–Golay fit over
  **Window** grid points around it (odd; 51 to start). Select the derivative
  panel to change its order or window, or go **Back to data**. Derivatives magnify
  noise, the second much more than the first, so widen the window until
  the curve is steady; a jump in the data shows as a spike.
- **Linked data** (Linking tab): **Link...** then click another
  panel, and the two share their lines' settings, line by line (the selected
  panel takes the other's number of lines, asking first if some of its own
  would go). From then on adding or removing a line in one does the same in
  all of them, and changing a synced setting does too. **Sync** chooses, per
  panel, what it shares: **Dataset**, **X axis**, **X function**, **Y
  axis**, **Y function**, **Colour** and **Line style** (line, width, marker
  and its size) are ticked to start with; **Smoothing** and **Background**
  aren't. A
  setting syncs between two panels only if both tick it, so e.g. one panel
  shows the raw data, a linked one the same data with the background
  subtracted, and another that smoothed; or untick Y axis to plot another
  column against the same x. Ticking a box sends the selected panel's
  setting to the others that tick it. Fit ranges and x-unit windows only
  sync between panels with the same x. FFT and derivative panels are linked
  panels too, so all of this works on them. Axis ranges and zoom stay each panel's own. Any number of panels
  can join (linking two groups merges them); the selected panel's linked
  partners get a dashed frame. **Unlink** takes the selected one out,
  keeping what it plots. **Freeze** pauses the selected panel's link without
  leaving the group: nothing it syncs crosses to or from it (adding or
  removing a line still happens in all of them, so lines stay paired), and
  the rest of the group keeps syncing among themselves. **Unfreeze** sends
  its synced settings to the others, so what you changed while it was
  frozen is carried across.
- The controls column scrolls (mouse wheel or its scrollbar) when it's taller
  than the window.
- **Lines**: + copies the selected line, - removes it. Each line has its own
  dataset, axes and functions; click a line in the list or on the plot to edit
  it.
- **Layout...**: hover to size the grid, click to apply. Click a panel to select it.
- **Delete panel** (beside Layout..., at the bottom of the column): deletes the selected panel. The
  panels after it, across then down, move back one place, and the grid loses
  the row or column that leaves empty (a 3 x 1 stack becomes 2 x 1); in a
  grid of both rows and columns the last cell gets an empty panel instead.
  An FFT or derivative panel of the deleted one keeps its lines, unlinked. Ctrl+Z brings
  it back. There's always at least one panel.
- **⇅** (beside the X and Y axis boxes): swaps x and y, functions included, for
  every line in the panel.
- **Save figure**: writes to the output folder, named after the plot (e.g.
  `run_005_M006_AH_vs_1-over-Norminal_FIeld.png`) unless you type a name in
  Save as. No extension means `.png`; `.pdf`, `.svg` etc. also work. If a
  file of that name is already there, it asks before replacing it. Ticking
  **Don't ask me again** there stops the question; to bring it back, delete
  the `"overwrite_without_asking"` line from `settings.json`.
- **Options...** (beside Save figure): how Save figure writes the file. **Size**
  is **As on screen** (the default) or **Custom**, a **Width** and
  **Height** in inches or cm, e.g. a journal's column width; text keeps its
  point size, so a small figure has relatively larger labels. **DPI** (200
  to start) sets the resolution of PNGs and the like, with the size in
  pixels shown beside it (PDF and SVG stay sharp at any DPI). **Transparent**
  leaves out the white background. They're kept in `settings.json`, for
  every figure until changed.
- **Open session... / Save session...** (under Files): a session
  is a `.json` file holding the layout and every panel and line, with its
  settings, FFT and derivative panels, links, ranges, labels and styles, plus the data
  folder and a typed Save as name. Opening one switches to its data folder if
  that's still there. The data itself isn't in it, only which files to read.

### Keyboard

| Key | Does |
|---|---|
| Ctrl+S | Save figure (Enter in Save as does too) |
| Ctrl+Z | undo the last change (one step, for now) |
| Ctrl+D | copy the selected line (+) |
| Delete | remove the selected line (-) |
| Up / Down | select the previous / next line |
| Ctrl+arrow keys | select the panel beside the selected one |
| Esc | stop picking a fit range or a panel |

Delete and the arrow keys are left alone while you type in a box; click
the plot to get out of it.

## Profiles

A `goose-plotter.json` in the data folder tells the plotter about that folder's
columns. Everything in it is optional; without one, columns show under their
raw names. See [examples/goose-plotter.json](examples/goose-plotter.json).

```json
{
  "labels":   {"Norminal_FIeld": "$B$  (T)", "AH": "capacitance (bridge units)"},
  "units":    {"Norminal_FIeld": "T", "AH": "bridge units"},
  "samples":  {"M006": "#2a78d6", "M011": "#eb6834"},
  "defaults": {"x": "Norminal_FIeld", "y": "M006_AH"}
}
```

- **labels**: axis label per column (matplotlib mathtext like `$B$` works).
- **units**: shown beside the column in the X and Y lists.
- A key in labels or units also matches sample columns: `AH` covers `M006_AH`
  and `M011_AH`, labelled "M006 capacitance ...".
- **samples**: colour for each sample's lines; a column belongs to a sample if
  it starts with its name and `_`.
- **defaults**: the axes a new line starts on.
- **format**: written by Data format...; lines count from 1, `header_line` 0
  means no column names, `delimiter` is `tab`, `comma`, `semicolon`,
  `whitespace` or the character itself. Leave it out to detect automatically.

## License

MIT; see [LICENSE](LICENSE).
