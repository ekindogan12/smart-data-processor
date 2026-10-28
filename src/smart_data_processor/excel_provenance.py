"""Small internal helpers for preserving Excel provenance through row filtering."""

from copy import deepcopy

import pandas as pd


def formula_expressions(data: pd.DataFrame) -> frozenset[str]:
    """Known source expressions, conservatively including removed formula cells.

    Ordinary formulas retain the legacy string API. Matching by expression also
    protects copies made by explicit fills and frames reordered by callers. A
    literal string identical to a known formula is protected conservatively too.
    """
    return frozenset(expression for _, expression in data.attrs.get("xlsx_source", {}).get("formulas", ())
                     if isinstance(expression, str))


def retain_source_rows(data: pd.DataFrame, positions) -> pd.DataFrame:
    """Copy selected rows and their coordinates, independent of index labels."""
    positions = tuple(positions)
    result = data.iloc[list(positions)].copy(deep=True)
    source = deepcopy(data.attrs.get("xlsx_source"))
    if source is not None:
        source["row_numbers"] = tuple(source["row_numbers"][position] for position in positions)
        result.attrs["xlsx_source"] = source
    return result
