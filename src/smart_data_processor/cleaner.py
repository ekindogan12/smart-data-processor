"""Explicit, non-mutating duplicate handling for tabular datasets."""

from collections.abc import Sequence
from typing import Literal

import pandas as pd

from .validators import DataValidationError, validate_columns, validate_dataframe


def remove_duplicates(
    data: pd.DataFrame,
    *,
    subset: Sequence[str] | None = None,
    keep: Literal["first", "last", False] = "first",
    case_insensitive_columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Return an independent frame after the caller explicitly requests removal.

    Compare all columns by default, or only ``subset``. Keep the first or last
    member of each duplicate group; ``False`` removes every member. Selected
    text columns can use Unicode casefold for comparison only. Non-string
    values remain unchanged; whitespace is significant. Case-insensitive
    columns must participate in the duplicate key. Output retains original
    values, dtypes, row order, and index labels. Missing-value equivalence
    follows pandas ``DataFrame.duplicated`` semantics.
    """
    validate_dataframe(data)
    if not (keep is False or isinstance(keep, str) and keep in {"first", "last"}):
        raise DataValidationError("keep must be 'first', 'last', or False.")
    selected = list(data.columns) if subset is None else validate_columns(
        subset, list(data.columns), option="subset"
    )
    insensitive = [] if case_insensitive_columns is None else validate_columns(
        case_insensitive_columns, selected, option="case_insensitive_columns"
    )
    comparison = data.loc[:, selected].copy(deep=True)
    for name in insensitive:
        comparison[name] = comparison[name].map(
            lambda value: value.casefold() if isinstance(value, str) else value
        )
    try:
        duplicates = comparison.duplicated(keep=keep)
    except TypeError as exc:
        raise DataValidationError("Duplicate comparison requires scalar, hashable cell values.") from exc
    # Positional selection also handles repeated index labels correctly.
    return data.iloc[~duplicates.to_numpy()].copy(deep=True)
