"""Read-only dataset profiling, independent of presentation and export."""

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from .validators import DataValidationError, validate_dataframe


@dataclass(frozen=True)
class ColumnProfile:
    """A column's actual pandas dtype and missing-value statistics."""

    name: str
    dtype: str
    missing_count: int
    missing_percentage: float


@dataclass(frozen=True)
class DatasetProfile:
    """Immutable statistics; duplicates count repeats after their first occurrence."""

    row_count: int
    column_count: int
    columns: tuple[ColumnProfile, ...]
    missing_value_count: int
    duplicate_row_count: int

    def to_dict(self) -> dict[str, Any]:
        """Return detached built-in values suitable for downstream presentation."""
        return asdict(self)


def profile_dataset(data: pd.DataFrame) -> DatasetProfile:
    """Describe data without inferring types, normalizing text, or filling blanks.

    Missing values follow pandas ``isna`` semantics (None, NaN, NaT, pd.NA).
    Empty strings and whitespace in caller-supplied frames are ordinary values.
    An empty dataset has zero missing percentages and zero duplicate rows.
    """
    validate_dataframe(data)
    rows = len(data)
    columns = tuple(
        ColumnProfile(
            name=name,
            dtype=str(data[name].dtype),
            missing_count=int(data[name].isna().sum()),
            missing_percentage=float(data[name].isna().sum() / rows * 100) if rows else 0.0,
        )
        for name in data.columns
    )
    try:
        duplicates = int(data.duplicated().sum())
    except TypeError as exc:
        raise DataValidationError("Profiling requires scalar, hashable cell values.") from exc
    return DatasetProfile(
        row_count=rows,
        column_count=len(columns),
        columns=columns,
        missing_value_count=sum(column.missing_count for column in columns),
        duplicate_row_count=duplicates,
    )
