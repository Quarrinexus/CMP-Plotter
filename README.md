# QCM Plotter

Interactive Tk window for plotting columns from delimited text data files
(`.txt`, `.text`, `.csv`, `.tsv`, `.dat`). The preamble, header line and
delimiter are detected automatically.

## Install

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Get the code:
   ```bash
   git clone https://github.com/<user>/QCM-Plotter.git
   cd QCM-Plotter
   ```
3. Run it. The first run downloads Python 3.13 and the dependencies into
   `.venv`; later runs start straight away.
   ```bash
   uv run qcm-plotter
   ```

To get a `qcm-plotter` command that works from any folder instead:

```bash
uv tool install .
```

After pulling changes, update it with `uv tool install --reinstall .`;
`uv tool uninstall qcm-plotter` removes it.

## Use

- **Data / Output folder** (under Folders): choose with Browse...; both are
  remembered in `~/.config/qcm-plotter/settings.json`.
- **Data format...** (under Folders): set the delimiter, column-name line and
  first data line by hand, with a preview. Opens by itself when a file's layout
  can't be detected. Saved for the whole data folder in its profile.
- **Dataset, X axis, Y axis**: any column against any other, sample columns
  (`M006_AH`, `M011_AH_Loss`, ...) included. Changing a control redraws.
- **Function**: under each axis, e.g. `1/x`, `exp(y)`, `log10(x)`; numpy's usual
  functions plus `pi` and `e`. Enter applies.
- **Lines**: + copies the selected line, - removes it. Each line has its own
  dataset, axes and functions; click a line in the list or on the plot to edit
  it. The swatch beside the list picks its colour.
- **Layout...**: hover to size the grid, click to apply. Click a panel to select it.
- **⇅** (beside the X and Y axis boxes): swaps x and y, functions included, for
  every line in the panel.
- **Save figure**: writes to the output folder, named after the plot (e.g.
  `run_005_M006_AH_vs_1-over-Norminal_FIeld.png`) unless you type a name in
  Save as. No extension means `.png`; `.pdf`, `.svg` etc. also work.

## Profiles

A `qcm-plotter.json` in the data folder tells the plotter about that folder's
columns. Everything in it is optional; without one, columns show under their
raw names. See [examples/qcm-plotter.json](examples/qcm-plotter.json).

```json
{
  "labels":   {"Norminal_FIeld": "$B$  (T)", "AH": "capacitance (bridge units)"},
  "units":    {"Norminal_FIeld": "T", "AH": "bridge units"},
  "samples":  {"M006": "#2a78d6", "M011": "#eb6834"},
  "defaults": {"x": "Norminal_FIeld", "y": "M006_AH"},
  "format":   {"delimiter": "tab", "header_line": 8, "data_line": 9}
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
