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

- **Data / Output folder**: choose with Browse...; both are remembered in
  `~/.config/qcm-plotter/settings.json`.
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
