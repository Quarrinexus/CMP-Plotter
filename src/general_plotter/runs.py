"""Load run files like `Cambridge_Sep_26.005.text` by their run id ('005')."""

from pathlib import Path

import pandas as pd

# Lines of instrument preamble above the column header in every .text file.
HEADER_LINES = 6

# Samples on the AH bridge -> plot colour. Each has a `<name>_AH` capacitance
# column and a `<name>_AH_Loss` loss column.
SAMPLES = {"M006": "#2a78d6", "M011": "#eb6834"}


def available_runs(data_dir):
    """Run ids present in `data_dir`, e.g. ['001', '003', '005']."""
    if not data_dir or not Path(data_dir).is_dir():
        return []
    return sorted(p.suffixes[-2].lstrip(".") for p in Path(data_dir).glob("*.*.text"))


def run_path(data_dir, run):
    """Return the data file for run id `run`, e.g. '005' -> <data_dir>/*.005.text."""
    matches = sorted(Path(data_dir).glob(f"*.{run}.text"))
    if len(matches) != 1:
        found = "no" if not matches else f"{len(matches)}"
        raise FileNotFoundError(
            f"{found} files match run '{run}' in {data_dir}; "
            f"available runs: {', '.join(available_runs(data_dir)) or 'none'}"
        )
    return matches[0]


def load_run(data_dir, run):
    """Read one run into a DataFrame, dropping the `_NNN` suffix from column names."""
    df = pd.read_csv(run_path(data_dir, run), sep="\t", skiprows=HEADER_LINES)
    df.columns = [c.strip().rsplit("_", 1)[0] for c in df.columns]
    return df
