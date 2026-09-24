"""Locate and load run files from `data/` by their run id ('003', '005', ...).

Every analysis script takes the run id as an optional command-line argument,
so the same script can be pointed at any dataset without editing it:

    python squiggle-finder.py 006
    python squiggle-finder.py 005+006     # a file written by merge-runs.py
"""

import argparse
from pathlib import Path

import pandas as pd

# The package lives at <repo>/src/huairou_cmp, so the repo root is two up.
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

# Lines of instrument preamble above the column header in every .text file.
HEADER_LINES = 6

# Column written by merge-runs.py recording which input run each row came from,
# so analyses can tell a seam between files from a feature in the data.
SOURCE_COL = "Source_Run"

# Samples on the AH bridge -> plot colour. Each has a `<name>_AH` capacitance
# column and a `<name>_AH_Loss` loss column.
SAMPLES = {"M006": "#2a78d6", "M011": "#eb6834"}
DEFAULT_SAMPLE = "M006"

# How a sample can be wired up, tried in order: the AH bridge gives one
# capacitance column; torque (from run 009 for M006) gives two raw channels.
# Each entry is column suffix -> axis label. The file header gives no units
# for the torque channels.
SAMPLE_CHANNELS = (
    {"AH": "capacitance\n(bridge units)"},
    {"Tau_X": "torque X\n(raw)", "Tau_Y": "torque Y\n(raw)"},
)


def sample_channels(df, sample):
    """Columns measuring `sample` in this run -> y label.

    E.g. {'M006_AH': ...} for a bridge run, or {'M006_Tau_X': ...,
    'M006_Tau_Y': ...} for a torque run.
    """
    for channels in SAMPLE_CHANNELS:
        cols = {f"{sample}_{suffix}": f"{sample} {label}"
                for suffix, label in channels.items()}
        if all(c in df.columns for c in cols):
            return cols
    raise KeyError(f"no {sample} measurement in this run; columns: {', '.join(df.columns)}")


def available_runs():
    """Run ids present in DATA_DIR, e.g. ['001', '003', '005']."""
    return sorted(p.suffixes[-2].lstrip(".") for p in DATA_DIR.glob("*.*.text"))


def run_path(run):
    """Return the data file for run id `run`, e.g. '005' -> data/*.005.text."""
    matches = sorted(DATA_DIR.glob(f"*.{run}.text"))
    if len(matches) != 1:
        found = "no" if not matches else f"{len(matches)}"
        raise FileNotFoundError(
            f"{found} files match run '{run}' in {DATA_DIR}; "
            f"available runs: {', '.join(available_runs()) or 'none'}"
        )
    return matches[0]


def load_run(run):
    """Read one run into a DataFrame with the run suffix stripped.

    The header is six lines of instrument preamble; every column carries a
    `_NNN` run suffix which we drop so the same frame layout works for any run.
    """
    df = pd.read_csv(run_path(run), sep="\t", skiprows=HEADER_LINES)
    df.columns = [c.strip().rsplit("_", 1)[0] for c in df.columns]
    return df


def _run_parser(default, description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "run", nargs="?", default=default,
        help=f"run id as a string, e.g. '005' or '005+006' (default: {default})",
    )
    return parser


def parse_run(default, description=None):
    """Read the run id from the command line, falling back to `default`."""
    return _run_parser(default, description).parse_args().run


def parse_run_and_sample(default, description=None):
    """Read the run id and `--sample` (M006 unless given) from the command line.

    Returns (run, sample), e.g. ('005', 'M011') for `script.py 005 --sample M011`.
    """
    parser = _run_parser(default, description)
    parser.add_argument(
        "--sample", choices=list(SAMPLES), default=DEFAULT_SAMPLE,
        help=f"sample to plot (default: {DEFAULT_SAMPLE})",
    )
    args = parser.parse_args()
    return args.run, args.sample
