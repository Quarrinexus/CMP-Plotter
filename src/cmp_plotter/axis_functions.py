"""The Function boxes under each axis: `1/x`, `exp(y)`, ... applied to a column."""

import re

import numpy as np

# Names an axis function can call; any other name stands for the quantity.
FUNCTIONS = {name: getattr(np, name) for name in (
    "exp", "log", "log10", "log2", "sqrt", "abs", "sin", "cos", "tan",
    "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "radians", "degrees",
)} | {"pi": np.pi, "e": np.e}


def quantity_name(expr):
    """The one name in `expr` that isn't a function: '1/x' -> 'x'."""
    free = set(compile(expr, "<axis function>", "eval").co_names) - FUNCTIONS.keys()
    if len(free) != 1:
        raise ValueError(f"'{expr}' should use exactly one name for the quantity, "
                         f"found {', '.join(sorted(free)) or 'none'}")
    return free.pop()


def is_identity(expr):
    """True for an empty box or a bare name like 'x': the quantity unchanged."""
    return not expr or (expr.isidentifier() and expr not in FUNCTIONS)


def apply_function(expr, values):
    """Evaluate `expr` (e.g. '1/x') on `values`; returns (result, name used)."""
    name = quantity_name(expr)
    code = compile(expr, "<axis function>", "eval")
    with np.errstate(all="ignore"):  # 1/0 etc. just give inf/nan, left unplotted
        return eval(code, {"__builtins__": {}, **FUNCTIONS}, {name: values}), name


def rename(expr, old, new):
    """Rename the quantity in `expr` from `old` to `new`: '1/y' -> '1/x'."""
    if not expr:
        return new
    return re.sub(rf"\b{old}\b", new, expr)


def file_part(expr, option):
    """Filename piece for one axis: ('1/x', 'Norminal_FIeld') -> '1-over-Norminal_FIeld'."""
    if is_identity(expr):
        return option
    name = quantity_name(expr)
    return slug(re.sub(rf"\b{name}\b", option, expr))


def slug(expr):
    """Filename-safe form of an axis function: '1/B' -> '1-over-B'."""
    for op, word in (("**", "-pow-"), ("/", "-over-"), ("*", "-times-")):
        expr = expr.replace(op, word)
    return re.sub(r"[^\w.+-]+", "_", expr).strip("_")
