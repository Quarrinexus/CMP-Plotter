# QCM Plotter

Interactive Tk window for plotting columns from `*.NNN.text` run files.

```bash
uv run qcm-plotter
```

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
- **Swap axes**: swaps x and y for every line in the panel.
- **Save figure**: writes to the output folder, named after the plot (e.g.
  `run_005_M006_AH_vs_1-over-Norminal_FIeld.png`) unless you type a name in
  Save as. No extension means `.png`; `.pdf`, `.svg` etc. also work.
