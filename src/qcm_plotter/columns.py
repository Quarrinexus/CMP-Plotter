"""What the data columns are called on screen: axis labels and units."""

from qcm_plotter.runs import SAMPLES

# Column -> axis label; anything missing is labelled with its column name.
# 'AH' and 'AH_Loss' also match per-sample columns ('M006_AH' ->
# 'M006 capacitance (bridge units)').
LABELS = {
    "Timestamp": "time  (s)",
    "T_Probe": "probe temperature  (K)",
    "T_VTI": "VTI temperature  (K)",
    "Norminal_FIeld": r"$B$  (T)",
    "AH": "capacitance (bridge units)",
    "AH_Loss": "loss (bridge units)",
}

# Column -> unit shown beside it in the dropdowns, matched like LABELS. The
# Hall channels are raw instrument readings; the file header gives no units.
UNITS = {
    "Timestamp": "s",
    "T_Probe": "K",
    "T_VTI": "K",
    "Norminal_FIeld": "T",
    "AngleHall_x": "raw",
    "AngleHall_y": "raw",
    "AH": "bridge units",
    "AH_Loss": "bridge units",
}


def lookup(table, column):
    """(entry, sample prefix) for `column` in `table`: 'M006_AH_Loss' -> (..., 'M006')."""
    if column in table:
        return table[column], ""
    for key in sorted(table, key=len, reverse=True):
        if column.endswith(f"_{key}"):
            return table[key], column.removesuffix(f"_{key}")
    return None, ""


def label(column, with_sample=True):
    """Axis label: 'M006_AH' -> 'M006 capacitance (bridge units)'."""
    text, prefix = lookup(LABELS, column)
    if text is None:
        return column
    return f"{prefix} {text}" if prefix and with_sample else text


def with_unit(column):
    """Dropdown text for a column: 'Norminal_FIeld' -> 'Norminal_FIeld  (T)'."""
    unit, _ = lookup(UNITS, column)
    return f"{column}  ({unit})" if unit else column


def without_unit(text):
    """Inverse of with_unit: the option name back from its dropdown text."""
    return text.partition("  (")[0]


def sample_of(*columns):
    """The runs.SAMPLES sample the first matching column belongs to, else ''."""
    for col in columns:
        for sample in SAMPLES:
            if col.startswith(f"{sample}_"):
                return sample
    return ""
