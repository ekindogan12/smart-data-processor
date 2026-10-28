"""Explicit, non-mutating duplicate handling for tabular datasets."""

from collections.abc import Sequence
from collections import Counter
from decimal import Decimal, localcontext
from typing import Literal

import pandas as pd

from .validators import (
    DataValidationError, scalar_kind, series_kind, validate_columns, validate_dataframe,
)
from .models import Issue, OperationResult
from .excel_provenance import formula_expressions, retain_source_rows


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
    Known Excel formula expressions remain case-sensitive during comparison.
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
    formulas = formula_expressions(data)
    for name in insensitive:
        comparison[name] = comparison[name].map(
            lambda value: value.casefold() if isinstance(value, str) and value not in formulas else value
        )
    try:
        duplicates = comparison.duplicated(keep=keep)
    except TypeError as exc:
        raise DataValidationError("Duplicate comparison requires scalar, hashable cell values.") from exc
    # Positional selection also handles repeated index labels correctly.
    return retain_source_rows(data, (position for position, duplicate in enumerate(duplicates) if not duplicate))


def handle_missing(
    data: pd.DataFrame,
    *,
    columns: Sequence[str],
    strategy: str = "keep",
    value: object = None,
) -> OperationResult:
    """Keep/drop/fill missing cells in selected columns without mutating input.

    Strategies: keep, drop, constant, mean, median, mode. Drop removes rows
    missing ANY selected value. Statistical fills never infer numeric strings.
    All-null columns without a computable statistic remain intact with a warning.
    Mode ties choose the first observed value and report the tie. Configuration
    errors raise DataValidationError before any result is returned.
    """
    validate_dataframe(data)
    selected = validate_columns(columns, list(data.columns), option="columns")
    strategies = {"keep", "drop", "constant", "mean", "median", "mode"}
    if not isinstance(strategy, str) or strategy not in strategies:
        raise DataValidationError(f"strategy must be one of {sorted(strategies)}.")
    if strategy != "constant" and value is not None:
        raise DataValidationError("value is only valid with strategy='constant'.")
    result = data.copy(deep=True)
    if strategy == "keep":
        return OperationResult(result)
    if strategy == "drop":
        missing = data[selected].isna().any(axis=1).to_numpy()
        removed = tuple(i for i, flag in enumerate(missing) if flag)
        retained = tuple(i for i, flag in enumerate(missing) if not flag)
        return OperationResult(
            retain_source_rows(data, retained), removed,
            retained_positions=retained,
        )

    warnings = []
    affected = set()
    if strategy == "constant" and (not pd.api.types.is_scalar(value) or pd.isna(value)):
        raise DataValidationError("A constant fill requires a non-missing scalar value.")
    if strategy == "constant" and scalar_kind(value) == "numeric" and not Decimal(str(value)).is_finite():
        raise DataValidationError("A numeric constant must be finite.")
    for name in selected:
        series = data[name]
        kind = series_kind(series)
        if strategy in {"mean", "median"} and kind not in {"numeric", "empty"}:
            raise DataValidationError(f"{strategy} requires a numeric column: {name!r}.")
        if strategy == "constant":
            constant_kind = scalar_kind(value)
            if constant_kind == "unsupported" or kind not in {constant_kind, "empty"}:
                raise DataValidationError(
                    f"Constant type {constant_kind!r} is incompatible with column {name!r} ({kind})."
                )
        missing = series.isna().to_numpy()
        if not missing.any():
            continue
        observed = series[~series.isna()].tolist()
        fill = value
        if strategy != "constant" and not observed:
            warnings.append(Issue("all_null", "No observed value; column left unchanged.", name))
            continue
        if strategy in {"mean", "median"}:
            numbers = [Decimal(str(item)) for item in observed]
            if not all(item.is_finite() for item in numbers):
                raise DataValidationError(f"{strategy} requires finite numbers in {name!r}.")
            # Extra precision preserves long integer parts while allowing fractions.
            precision = max(len(n.as_tuple().digits) + abs(n.as_tuple().exponent) for n in numbers)
            with localcontext() as context:
                context.prec = max(28, precision + len(str(len(numbers))) + 28)
                if strategy == "mean":
                    fill = sum(numbers) / len(numbers)
                else:
                    ordered = sorted(numbers)
                    middle = len(ordered) // 2
                    fill = ordered[middle] if len(ordered) % 2 else (
                        ordered[middle - 1] + ordered[middle]
                    ) / 2
            if fill == fill.to_integral_value():
                fill = int(fill)
        elif strategy == "mode":
            try:
                counts = Counter(observed)
            except TypeError as exc:
                raise DataValidationError("Mode requires scalar, hashable values.") from exc
            maximum = max(counts.values())
            candidates = [item for item, count in counts.items() if count == maximum]
            fill = candidates[0]
            if len(candidates) > 1:
                warnings.append(Issue("mode_tie", "Mode tie resolved by first occurrence.", name))
        target = series.copy(deep=True)
        if isinstance(target.dtype, pd.CategoricalDtype) and fill not in target.cat.categories:
            target = target.cat.add_categories([fill])
        try:
            target = target.fillna(fill)
        except (TypeError, ValueError):
            # Compatible fills may require fractional values in an integer column.
            target = series.astype(object)
            target.iloc[[i for i, flag in enumerate(missing) if flag]] = fill
        if str(target.dtype) != str(series.dtype):
            warnings.append(Issue(
                "dtype_changed", f"Fill changed dtype from {series.dtype} to {target.dtype}.", name
            ))
        result[name] = target
        affected.update(i for i, flag in enumerate(missing) if flag)
    return OperationResult(result, tuple(sorted(affected)), tuple(warnings))
