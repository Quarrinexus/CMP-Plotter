"""Column names on screen, from the profile's labels and units ('AH' also matches 'M006_AH')."""


def lookup(table, column):
    """(entry, sample prefix) for `column` in `table`: 'M006_AH_Loss' -> (..., 'M006')."""
    # Longest key first, so 'M006_AH_Loss' finds 'AH_Loss' rather than 'AH'.
    if column in table:
        return table[column], ""
    for key in sorted(table, key=len, reverse=True):
        if column.endswith(f"_{key}"):
            return table[key], column.removesuffix(f"_{key}")
    return None, ""


def label(column, labels, with_sample=True):
    """Axis label: 'M006_AH' -> 'M006 capacitance (bridge units)'."""
    text, prefix = lookup(labels, column)
    if text is None:
        return column
    return f"{prefix} {text}" if prefix and with_sample else text


def with_unit(column, units):
    """Dropdown text for a column: 'Norminal_FIeld' -> 'Norminal_FIeld  (T)'."""
    unit, _ = lookup(units, column)
    return f"{column}  ({unit})" if unit else column


def without_unit(text):
    """Inverse of with_unit: the option name back from its dropdown text."""
    return text.partition("  (")[0]


def sample_of(samples, *columns):
    """The sample in `samples` the first matching column belongs to, else ''."""
    for col in columns:
        for sample in samples:
            if col.startswith(f"{sample}_"):
                return sample
    return ""
