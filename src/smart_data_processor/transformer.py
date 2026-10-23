"""Explicit text, numeric, and date transformations with per-cell diagnostics."""

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata

import pandas as pd

from .models import Issue, OperationResult
from .validators import (
    DataValidationError, scalar_kind, validate_columns, validate_dataframe, validate_headers,
)


def clean_text(
    data: pd.DataFrame, *, columns: Sequence[str], operation: str = "trim"
) -> OperationResult:
    """Apply one text operation, preserving nulls and reporting non-text cells."""
    validate_dataframe(data)
    selected = validate_columns(columns, list(data.columns), option="columns")
    methods = {"trim": str.strip, "lower": str.lower, "upper": str.upper, "title": str.title}
    if not isinstance(operation, str) or operation not in methods:
        raise DataValidationError("Text operation must be trim, lower, upper, or title.")
    result = data.copy(deep=True)
    affected, warnings = set(), []
    for name in selected:
        values = data[name].tolist()
        changed = False
        for position, value in enumerate(values):
            if pd.isna(value):
                continue
            if not isinstance(value, str):
                warnings.append(Issue("non_text", "Non-text value left unchanged.", name, position))
                continue
            transformed = methods[operation](value)
            if transformed != value:
                values[position] = transformed
                affected.add(position)
                changed = True
        if changed:
            # Text categories may merge after normalization; do not mutate category metadata.
            dtype = data[name].dtype if isinstance(data[name].dtype, pd.StringDtype) else object
            result[name] = pd.Series(values, index=data.index, dtype=dtype)
            if str(result[name].dtype) != str(data[name].dtype):
                warnings.append(Issue("dtype_changed", "Text transformation uses object dtype.", name))
    return OperationResult(result, tuple(sorted(affected)), tuple(warnings))


def normalize_column_names(data: pd.DataFrame) -> OperationResult:
    """Opt-in NFKC/casefold snake_case names; reject empty names and collisions."""
    validate_dataframe(data)
    names = [
        re.sub(r"[\W_]+", "_", unicodedata.normalize("NFKC", name).casefold()).strip("_")
        for name in data.columns
    ]
    validate_headers(names)
    changes = tuple((old, new) for old, new in zip(data.columns, names) if old != new)
    result = data.copy(deep=True)
    result.columns = names
    return OperationResult(result, renamed_columns=changes)


def convert_numeric(
    data: pd.DataFrame,
    *,
    columns: Sequence[str],
    decimal_separator: str = ".",
    thousands_separator: str | None = None,
) -> OperationResult:
    """Parse strict numeric strings into exact int/Decimal values (object dtype).

    Grouped integer parts require groups of three. Exponents and signs are
    supported; surrounding whitespace must be trimmed explicitly beforehand.
    Invalid/non-finite values are preserved with errors; nulls remain null.
    Native finite numbers are retained. Booleans are not numeric inputs.
    """
    validate_dataframe(data)
    selected = validate_columns(columns, list(data.columns), option="columns")
    if decimal_separator not in (".", ","):
        raise DataValidationError("decimal_separator must be '.' or ','.")
    if thousands_separator not in (None, ".", ",", " ", "\u00a0", "'"):
        raise DataValidationError("Unsupported thousands_separator.")
    if decimal_separator == thousands_separator:
        raise DataValidationError("Decimal and thousands separators must differ.")
    integer = r"[0-9]+"
    if thousands_separator is not None:
        group = re.escape(thousands_separator)
        integer = rf"(?:[0-9]+|[0-9]{{1,3}}(?:{group}[0-9]{{3}})+)"
    decimal = re.escape(decimal_separator)
    pattern = re.compile(rf"[+-]?(?:{integer}(?:{decimal}[0-9]+)?|{decimal}[0-9]+)(?:[eE][+-]?[0-9]+)?")
    result, affected, errors = data.copy(deep=True), set(), []
    for name in selected:
        values = data[name].tolist()
        changed = False
        for position, value in enumerate(values):
            if pd.isna(value):
                continue
            try:
                if isinstance(value, str):
                    if not pattern.fullmatch(value):
                        raise ValueError("Value does not match the configured numeric syntax.")
                    normalized = value.replace(thousands_separator, "") if thousands_separator else value
                    number = Decimal(normalized.replace(decimal_separator, "."))
                    # Prevent tiny input exponents from producing enormous Python integers.
                    if not number.is_finite() or abs(number.adjusted()) > 1000:
                        raise ValueError("Numeric exponent exceeds the supported range (-1000..1000).")
                    values[position] = int(number) if number == number.to_integral_value() else number
                    affected.add(position)
                    changed = True
                elif scalar_kind(value) != "numeric" or not Decimal(str(value)).is_finite():
                    raise ValueError("Expected a finite number or numeric string.")
            except (ValueError, InvalidOperation) as exc:
                errors.append(Issue("invalid_numeric", str(exc), name, position))
        if changed:
            result[name] = pd.Series(values, index=data.index, dtype=object)
    return OperationResult(result, tuple(sorted(affected)), errors=tuple(errors))


def standardize_dates(
    data: pd.DataFrame, *, columns: Sequence[str], input_formats: Sequence[str]
) -> OperationResult:
    """Convert dates to ISO 8601 using only explicit numeric strptime formats.

    Every format must include %Y, %m, and %d. Time directives %H, %M, %S,
    %f, %z and literal %% are supported. All matching formats are considered;
    conflicting interpretations remain unchanged with a warning and an error.
    Native dates/datetimes retain time and timezone information via isoformat.
    """
    validate_dataframe(data)
    selected = validate_columns(columns, list(data.columns), option="columns")
    if isinstance(input_formats, (str, bytes)) or not isinstance(input_formats, Sequence) or not input_formats:
        raise DataValidationError("input_formats must be a non-empty sequence of explicit formats.")
    formats = list(input_formats)
    for fmt in formats:
        if not isinstance(fmt, str) or not fmt:
            raise DataValidationError("Every input format must be a non-empty string.")
        tokens = re.findall(r"%(.)", fmt)
        if re.search(r"%(?:[^%YmdHMSfz]|$)", fmt.replace("%%", "")) or not {"Y", "m", "d"}.issubset(tokens):
            raise DataValidationError("Formats require %Y, %m, %d and supported numeric directives only.")
        try:
            # Validate directive syntax even when there are no non-null cells.
            datetime.strptime("", fmt)
        except re.error as exc:
            raise DataValidationError(f"Invalid input format: {fmt!r}.") from exc
        except ValueError:
            pass  # Empty input does not match a valid format.
    result, affected, warnings, errors = data.copy(deep=True), set(), [], []
    for name in selected:
        values = data[name].tolist()
        changed = False
        for position, value in enumerate(values):
            if pd.isna(value):
                continue
            if isinstance(value, (datetime, date)):
                converted = value.isoformat()
            else:
                matches = set()
                if isinstance(value, str):
                    for fmt in formats:
                        try:
                            parsed = datetime.strptime(value, fmt)
                            with_time = any(token in fmt for token in ("%H", "%M", "%S", "%f", "%z"))
                            matches.add(parsed.isoformat() if with_time else parsed.date().isoformat())
                        except ValueError:
                            continue
                if len(matches) != 1:
                    if len(matches) > 1:
                        message = "Multiple input formats give different dates; original retained."
                        warnings.append(Issue("ambiguous_date", message, name, position))
                        errors.append(Issue("ambiguous_date", message, name, position))
                    else:
                        errors.append(Issue("invalid_date", "No input format matched; original retained.", name, position))
                    continue
                converted = matches.pop()
            if converted != value:
                affected.add(position)
                values[position] = converted
                changed = True
        if changed:
            result[name] = pd.Series(values, index=data.index, dtype=object)
    return OperationResult(result, tuple(sorted(affected)), tuple(warnings), tuple(errors))
