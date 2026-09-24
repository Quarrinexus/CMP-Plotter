"""Find and load delimited text data files, detecting their layout."""

from io import StringIO
from pathlib import Path
import re

import pandas as pd

# File types listed as datasets; anything else in the data folder is ignored.
DATA_EXTENSIONS = {".txt", ".text", ".csv", ".tsv", ".dat"}

# Delimiter names as saved in a format, tried in this order when detecting;
# None means runs of whitespace. Any other string is used as it is.
DELIMITERS = {"tab": "\t", "comma": ",", "semicolon": ";", "whitespace": None}

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


class FormatError(ValueError):
    """The file's layout couldn't be detected, or doesn't fit the format given."""


def read_lines(path):
    return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()


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


def detect_format(lines):
    """The format of a file's `lines`, e.g. {'delimiter': 'tab', 'header_line': 10,
    'data_line': 11}. Lines count from 1; header_line 0 means no column names."""
    found = [(name, *start) for name, d in DELIMITERS.items()
             if (start := _data_start(lines, d))]
    if not found:
        raise FormatError("no block of numeric columns found")
    name, start, width = max(found, key=lambda f: f[2])  # max keeps the first of equals
    # Column names: the non-blank line just above the numbers, if it fits.
    header = next((i for i in range(start - 1, -1, -1) if lines[i].strip()), None)
    names = _fields(lines[header], DELIMITERS[name]) if header is not None else []
    fits = len(names) == width and len(set(names)) == width
    return {"delimiter": name, "header_line": header + 1 if fits else 0,
            "data_line": start + 1}


def _strip_suffix(columns):
    """Drop a `_NNN` suffix every column shares: 'T_Probe_005' -> 'T_Probe'."""
    suffixes = {m[1] if (m := re.search(r"(_\d+)$", c)) else None for c in columns}
    if len(suffixes) != 1 or None in suffixes:
        return columns
    suffix = suffixes.pop()
    stripped = [c.removesuffix(suffix) for c in columns]
    return stripped if len(set(stripped)) == len(stripped) else columns


def parse(lines, fmt):
    """A file's `lines` as a DataFrame, read with `fmt` (see detect_format)."""
    delimiter = DELIMITERS.get(fmt["delimiter"], fmt["delimiter"])
    start, header = fmt["data_line"] - 1, fmt["header_line"] - 1
    if not 0 <= start < len(lines):
        raise FormatError(f"data line {start + 1} is past the end of the file")
    if header >= start:
        raise FormatError("the column names must come before the data")
    width = len(_fields(lines[start], delimiter))
    if width < 1:
        raise FormatError(f"line {start + 1} is empty")
    if header >= 0:
        names = _fields(lines[header], delimiter)
        if len(names) != width:
            raise FormatError(f"line {header + 1} has {len(names)} names but "
                              f"line {start + 1} has {width} values")
        if len(set(names)) != width:
            raise FormatError(f"line {header + 1} repeats a column name")
        if all(map(_is_number, names)):
            raise FormatError(f"line {header + 1} is data, not column names")
    else:
        names = [f"column_{i + 1}" for i in range(width)]
    try:
        df = pd.read_csv(StringIO("\n".join(lines[start:])), sep=delimiter or r"\s+",
                         header=None, names=names, usecols=range(width), index_col=False)
    except ValueError as err:  # pandas' parser errors are ValueErrors
        raise FormatError(str(err).strip()) from err
    if df.empty or not any(t.kind in "fiu" for t in df.dtypes):
        raise FormatError("no numeric columns with this format")
    df.columns = _strip_suffix(names)
    return df


def load_dataset(path, fmt=None):
    """Read a data file into a DataFrame with `fmt`, detecting the format if that fails."""
    lines = read_lines(path)
    if fmt:
        try:
            return parse(lines, fmt)
        except FormatError as err:  # e.g. a file with a longer preamble
            saved_error = err
    try:
        return parse(lines, detect_format(lines))
    except FormatError:
        if fmt:
            raise saved_error from None
        raise
