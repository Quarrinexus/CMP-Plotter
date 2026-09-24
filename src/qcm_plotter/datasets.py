"""Find and load delimited text data files, detecting their layout."""

from io import StringIO
from pathlib import Path
import re

import pandas as pd

# File types listed as datasets; anything else in the data folder is ignored.
DATA_EXTENSIONS = {".txt", ".text", ".csv", ".tsv", ".dat"}

# Tried in order; None means runs of whitespace.
DELIMITERS = ("\t", ",", ";", None)

# Consecutive numeric rows needed before a block counts as the data.
MIN_ROWS = 3


def find_datasets(data_dir):
    """Dataset name -> file for the data files in `data_dir`, e.g. 'Cambridge_Sep_26.005'."""
    if not data_dir or not Path(data_dir).is_dir():
        return {}
    files = sorted(p for p in Path(data_dir).iterdir()
                   if p.is_file() and p.suffix.lower() in DATA_EXTENSIONS)
    stems = [p.stem for p in files]
    # Two files differing only by extension keep it, so names stay unique.
    return {p.stem if stems.count(p.stem) == 1 else p.name: p for p in files}


def run_number(name):
    """'Cambridge_Sep_26.005' -> '005'; None for names without a trailing .NNN."""
    match = re.search(r"\.(\d+)$", name)
    return match[1] if match else None


def describe(name):
    """How a dataset is named on the plot: 'run 005', or its full name."""
    number = run_number(name)
    return f"run {number}" if number else name


def _fields(line, delimiter):
    fields = line.split(delimiter) if delimiter else line.split()
    fields = [f.strip() for f in fields]
    while fields and not fields[-1]:  # trailing delimiters
        fields.pop()
    return fields


def _is_number(text):
    try:
        float(text)
    except ValueError:
        return False
    return True


def _data_start(lines, delimiter):
    """(first data line, fields per row) for `delimiter`, or None if no data block."""
    run_start, run_width, run_length = 0, 0, 0
    for i, line in enumerate(lines):
        fields = _fields(line, delimiter)
        if len(fields) >= 2 and all(map(_is_number, fields)):
            if len(fields) == run_width:
                run_length += 1
            else:
                run_start, run_width, run_length = i, len(fields), 1
            if run_length == MIN_ROWS:
                return run_start, run_width
        else:
            run_width = run_length = 0
    return None


def _layout(lines):
    """(delimiter, first data line, fields per row), preferring the widest split."""
    found = [(d, *start) for d in DELIMITERS if (start := _data_start(lines, d))]
    if not found:
        raise ValueError("no block of numeric columns found")
    return max(found, key=lambda f: f[2])  # max keeps the first of equals


def _strip_suffix(columns):
    """Drop a `_NNN` suffix every column shares: 'T_Probe_005' -> 'T_Probe'."""
    suffixes = {m[1] if (m := re.search(r"(_\d+)$", c)) else None for c in columns}
    if len(suffixes) != 1 or None in suffixes:
        return columns
    suffix = suffixes.pop()
    stripped = [c.removesuffix(suffix) for c in columns]
    return stripped if len(set(stripped)) == len(stripped) else columns


def load_dataset(path):
    """Read a data file into a DataFrame, whatever its preamble and delimiter.

    The column names come from the non-blank line just above the numbers."""
    lines = Path(path).read_text(errors="replace").splitlines()
    delimiter, start, width = _layout(lines)
    header = next((lines[i] for i in range(start - 1, -1, -1) if lines[i].strip()), "")
    names = _fields(header, delimiter)
    if len(names) != width or len(set(names)) != width:
        names = [f"column_{i + 1}" for i in range(width)]
    # Hand pandas the same lines scanned above, so line counting can't disagree.
    df = pd.read_csv(StringIO("\n".join(lines[start:])), sep=delimiter or r"\s+",
                     header=None, names=names, usecols=range(width), index_col=False)
    df.columns = _strip_suffix(names)
    return df
