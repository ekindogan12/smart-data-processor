"""Shared validation rules and actionable public exceptions."""

from collections.abc import Sequence

import pandas as pd


class FileValidationError(ValueError):
    """An input file cannot be safely interpreted with the supplied settings."""


class DataValidationError(ValueError):
    """A dataset or cleaning configuration is invalid."""


def validate_headers(headers: Sequence[object]) -> None:
    """Reject absent, blank, non-text, or duplicate column names; never rename."""
    if not headers:
        raise DataValidationError("The dataset must contain at least one column.")
    if any(not isinstance(name, str) or not name.strip() for name in headers):
        raise DataValidationError("Column names must be non-empty strings.")
    if len(set(headers)) != len(headers):
        raise DataValidationError("Column names must be unique; duplicate headers found.")


def validate_dataframe(data: pd.DataFrame) -> None:
    """Validate the tabular contract shared by profiling and cleaning."""
    if not isinstance(data, pd.DataFrame):
        raise DataValidationError("Expected a pandas DataFrame.")
    validate_headers(list(data.columns))


def validate_columns(
    columns: Sequence[str], available: Sequence[str], *, option: str
) -> list[str]:
    """Return a validated, non-empty column selection in the caller's order."""
    if isinstance(columns, (str, bytes)) or not isinstance(columns, Sequence):
        raise DataValidationError(f"{option} must be a sequence of column names.")
    selected = list(columns)
    if not selected or any(not isinstance(name, str) for name in selected):
        raise DataValidationError(f"{option} must contain one or more column names.")
    if len(set(selected)) != len(selected):
        raise DataValidationError(f"{option} contains repeated column names.")
    unknown = [name for name in selected if name not in available]
    if unknown:
        raise DataValidationError(f"Unknown columns in {option}: {unknown}.")
    return selected
