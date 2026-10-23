"""Structured processing reports and spreadsheet-safe, in-memory exports."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
import csv
import json
import math
from numbers import Integral, Real
import re
from typing import Any

import pandas as pd
from openpyxl import Workbook

from .models import Issue
from .profiler import DatasetProfile
from .validators import DataValidationError, validate_dataframe

_INVALID_XML_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


@dataclass(frozen=True)
class Dimensions:
    """Row and column counts at a processing boundary."""

    rows: int
    columns: int


@dataclass(frozen=True)
class StepReport:
    """Audit of a requested step, including failed and partially applied steps."""

    operation: str
    parameters: dict[str, Any]
    status: str
    before: Dimensions
    after: Dimensions
    affected_rows: int
    affected_row_positions: tuple[int, ...]
    warnings: tuple[Issue, ...] = ()
    errors: tuple[Issue, ...] = ()
    renamed_columns: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ProcessingReport:
    """Input/output statistics and an ordered audit, independent of UI or files."""

    before: DatasetProfile
    after: DatasetProfile
    steps: tuple[StepReport, ...]
    status: str
    planned_steps: int
    affected_rows: int

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(issue for step in self.steps for issue in step.warnings)

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(issue for step in self.steps for issue in step.errors)

    def to_dict(self) -> dict[str, Any]:
        """Return detached, JSON-safe values with schema and diagnostic summaries."""
        result = asdict(self)
        result["schema_version"] = 1
        result["warnings"] = [asdict(issue) for issue in self.warnings]
        result["errors"] = [asdict(issue) for issue in self.errors]
        return _json_value(result)


@dataclass(frozen=True)
class ExportResult:
    """Downloadable bytes plus explicit export-only protection diagnostics."""

    content: bytes
    media_type: str
    protected_cell_count: int = 0
    warnings: tuple[Issue, ...] = ()


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (datetime, date, Decimal)):
        return str(value) if isinstance(value, Decimal) else value.isoformat()
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return None
    if isinstance(value, Real):
        if not math.isfinite(value):
            # Invalid operation parameters still need an exportable error report.
            return str(value)
        return int(value) if isinstance(value, Integral) else float(value)
    if hasattr(value, "item"):
        return _json_value(value.item())
    raise DataValidationError(f"Unsupported report parameter type: {type(value).__name__}.")


def export_report(report: ProcessingReport) -> bytes:
    """Serialize a processing report as UTF-8 JSON, without writing any file."""
    if not isinstance(report, ProcessingReport):
        raise DataValidationError("Expected a ProcessingReport.")
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def _formula_like(text: str) -> bool:
    candidate = re.sub(r"^[\s\x00-\x1f\u200b\ufeff]+", "", text)
    return candidate.startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")) or text.startswith(("\t", "\r", "\n"))


def _export_scalar(value: Any) -> Any:
    """Represent supported scalar cells explicitly; never stringify containers."""
    if not pd.api.types.is_scalar(value):
        raise DataValidationError("Exports require scalar spreadsheet cell values.")
    if pd.isna(value):
        return None
    if isinstance(value, (str, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise DataValidationError("Exports do not support infinite numeric values.")
        return value
    if isinstance(value, Real):
        if not math.isfinite(value):
            raise DataValidationError("Exports do not support infinite numeric values.")
        return float(value)
    if hasattr(value, "item"):
        return _export_scalar(value.item())
    raise DataValidationError(f"Unsupported export cell type: {type(value).__name__}.")


def export_csv(data: pd.DataFrame, *, delimiter: str = ",") -> ExportResult:
    """Return UTF-8 CSV; quote every field and prefix formula-like text with '.

    Protection includes headers and leading whitespace/control characters. Native
    negative numbers stay numeric. The index is excluded and missing cells are
    empty. Protection is mandatory and changes only the exported representation.
    """
    validate_dataframe(data)
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\r\n\x00"':
        raise DataValidationError("delimiter must be one character other than newline, NUL, or quote.")
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, delimiter=delimiter, quoting=csv.QUOTE_ALL, lineterminator="\n")
    protected = 0

    def safe_row(row):
        nonlocal protected
        result = []
        for value in row:
            value = _export_scalar(value)
            if isinstance(value, str) and _formula_like(value):
                value = "'" + value
                protected += 1
            result.append(value)
        return result

    writer.writerow(safe_row(data.columns))
    for row in data.itertuples(index=False, name=None):
        writer.writerow(safe_row(row))
    warnings = (Issue(
        "formula_protection", f"Prefixed {protected} formula-like CSV text cells/headers with an apostrophe."
    ),) if protected else ()
    try:
        content = buffer.getvalue().encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DataValidationError("CSV text contains invalid Unicode characters.") from exc
    return ExportResult(content, "text/csv", protected, warnings)


def export_xlsx(data: pd.DataFrame, *, sheet_name: str = "Processed Data") -> ExportResult:
    """Return XLSX bytes with all text explicitly stored as strings, never formulas.

    Dates use ISO text. Decimal and >15-digit integer values use text to preserve
    precision. Reject Excel limits/illegal XML controls instead of truncating.
    """
    validate_dataframe(data)
    if (
        not isinstance(sheet_name, str) or not sheet_name.strip() or len(sheet_name) > 31
        or re.search(r"[\\/*?:\[\]]", sheet_name) or _INVALID_XML_TEXT.search(sheet_name)
        or sheet_name.startswith("'") or sheet_name.endswith("'")
    ):
        raise DataValidationError(
            "sheet_name must be non-blank, at most 31 characters, without \\/*?:[], "
            "illegal XML characters, or leading/trailing apostrophes."
        )
    if len(data) + 1 > 1_048_576 or len(data.columns) > 16_384:
        raise DataValidationError("Dataset exceeds XLSX row or column limits.")
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    protected, precision = 0, 0

    def write_row(row_number, values):
        nonlocal protected, precision
        for column_number, raw in enumerate(values, 1):
            value = _export_scalar(raw)
            if isinstance(value, str) and _formula_like(value):
                protected += 1
            if isinstance(value, Decimal) or (
                isinstance(value, int) and not isinstance(value, bool) and len(str(abs(value))) > 15
            ):
                value = str(value)
                precision += 1
            if isinstance(value, str):
                if len(value) > 32_767 or _INVALID_XML_TEXT.search(value):
                    raise DataValidationError(
                        f"XLSX cell at row {row_number}, column {column_number} exceeds text limits or contains illegal controls."
                    )
            cell = worksheet.cell(row_number, column_number, value)
            if isinstance(value, str):
                cell.data_type = "s"  # Also protects headers, formulas, and Excel error-looking text.

    try:
        write_row(1, data.columns)
        for row_number, values in enumerate(data.itertuples(index=False, name=None), 2):
            write_row(row_number, values)
        buffer = BytesIO()
        workbook.save(buffer)
    finally:
        workbook.close()
    warnings = []
    if protected:
        warnings.append(Issue("formula_protection", f"Stored {protected} formula-like XLSX text cells/headers as literal strings."))
    if precision:
        warnings.append(Issue("precision_protection", f"Stored {precision} Decimal/large integer cells as text to preserve precision."))
    return ExportResult(
        buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        protected, tuple(warnings),
    )
