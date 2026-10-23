"""Shared operation results and diagnostics, with no I/O dependencies."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Issue:
    """A diagnostic; row_position is zero-based, never an index label.

    Standalone operations use their input positions. Pipeline reports translate
    positions back to the original input, even after rows have been removed.
    """

    code: str
    message: str
    column: str | None = None
    row_position: int | None = None


@dataclass(frozen=True)
class OperationResult:
    """Independent output plus changes and diagnostics for one operation."""

    data: pd.DataFrame
    affected_positions: tuple[int, ...] = ()
    warnings: tuple[Issue, ...] = ()
    errors: tuple[Issue, ...] = ()
    retained_positions: tuple[int, ...] | None = None
    renamed_columns: tuple[tuple[str, str], ...] = ()
