"""Testable dashboard state and configuration adapters; no Streamlit imports.

All tabular processing and serialization is delegated to the existing engine.
One Workspace instance belongs to one Streamlit session, never a global cache.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
from io import BytesIO
import json

import pandas as pd
from openpyxl.utils.cell import coordinate_to_tuple, get_column_letter, range_boundaries

from .excel_layout import WorksheetLayout
from .excel_import import plan_excel_import, region_import_options
from .file_handler import DEFAULT_MAX_SIZE_BYTES, load_dataset, load_xlsx_regions
from .pipeline import ProcessingPipeline, ProcessingResult, ProcessingStep
from .profiler import DatasetProfile, profile_dataset
from .reporter import ExportResult, export_csv, export_report, export_xlsx
from .transformer import normalize_column_names
from .validators import DataValidationError


@dataclass(frozen=True)
class ImportOptions:
    """Options that participate in uploaded-source identity."""

    encoding: str | None = None
    delimiter: str | None = None
    sheet_name: str | int = 0
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES
    cell_range: str | None = None
    exclude_empty_columns: bool = False
    generate_missing_headers: bool = False
    deduplicate_headers: bool = False
    confirm_header_changes: bool = False
    header_row: int | None = None
    infer_header: bool = False
    remove_empty_rows: bool = False
    repair_irregular_headers: bool = False
    confirm_import_changes: bool = False
    region_ranges: tuple[str, ...] = ()
    headerless: bool = False


def fingerprint(value: object) -> str:
    """Stable, type-aware configuration identity (Decimal is distinct from text)."""
    encoded = json.dumps(value, sort_keys=True, default=lambda item: {
        "type": type(item).__name__, "value": str(item),
    }).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_constant(text: str, kind: str) -> object:
    """Interpret an explicitly chosen form type, without guessing column types."""
    if kind == "Text":
        return text
    if kind == "Number":
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise DataValidationError("Enter a number using a decimal point, for example 12.50.") from exc
        if not number.is_finite() or abs(number.adjusted()) > 1000:
            raise DataValidationError("Enter a finite number with an exponent between -1000 and 1000.")
        return number
    if kind == "Boolean":
        if text not in {"True", "False"}:
            raise DataValidationError("Choose True or False.")
        return text == "True"
    if kind == "Date / time":
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise DataValidationError("Enter an ISO date or datetime, for example 2026-09-01.") from exc
    raise DataValidationError("Choose a supported constant type.")


def columns_after_steps(columns: list[str], steps: list[ProcessingStep]) -> list[str]:
    """Project header changes by calling the real operation on a zero-row frame."""
    schema = pd.DataFrame(columns=columns)
    for step in steps:
        if step.operation == "normalize_column_names":
            schema = normalize_column_names(schema).data
    return list(schema.columns)


def display_page(data: pd.DataFrame, page: int = 1, page_size: int = 100) -> pd.DataFrame:
    """String-only display copy avoids Arrow coercion of mixed/Decimal cells.

    This presentation adapter is never used as pipeline or export input.
    """
    if type(page) is not int or page < 1 or type(page_size) is not int or page_size < 1:
        raise DataValidationError("Page and page size must be positive integers.")
    view = data.iloc[(page - 1) * page_size:page * page_size]
    result = pd.DataFrame(index=view.index)
    for name in view.columns:
        result[name] = pd.Series(
            [None if pd.isna(value) else str(value) for value in view[name]],
            index=view.index, dtype="string",
        )
    result.index = result.index.map(str)
    return result


@dataclass(frozen=True)
class RegionSummary:
    """Display-only description of an existing detected region, never a new boundary."""

    cell_range: str
    top: int
    left: int
    rows: int
    columns: int
    populated_cells: int
    formula_count: int
    kind: str


def summarize_regions(layout: WorksheetLayout) -> tuple[RegionSummary, ...]:
    """Rank by bounding area, then top/left coordinate; classify only for display.

    A candidate needs >=2 rows, >=2 columns and >=4 non-None cells. A 1x1
    region is isolated. Other shapes are small/narrow regions. These labels do
    not infer headers, guarantee a table, change boundaries or filter imports.
    """
    formulas = tuple(coordinate_to_tuple(coordinate) for coordinate, _ in layout.formulas)
    summaries = []
    for cell_range in layout.regions:
        left, top, right, bottom = range_boundaries(cell_range)
        rows, columns = bottom - top + 1, right - left + 1
        populated = sum(value is not None for row in layout.records[top - 1:bottom]
                        for value in row[left - 1:right])
        formula_count = sum(top <= row <= bottom and left <= col <= right for row, col in formulas)
        kind = ("Isolated cell" if rows == columns == 1 else
                "Table candidate" if rows >= 2 and columns >= 2 and populated >= 4 else
                "Small / narrow region")
        summaries.append(RegionSummary(cell_range, top, left, rows, columns, populated, formula_count, kind))
    return tuple(sorted(summaries, key=lambda item: (-item.rows * item.columns, item.top, item.left)))


def region_card_preview(layout: WorksheetLayout, region: RegionSummary) -> pd.DataFrame:
    """At most 3x4 cells for a labeled card preview; never processing/export input."""
    bottom = region.top + min(region.rows, 3) - 1
    right = region.left + min(region.columns, 4) - 1
    data = pd.DataFrame(
        [row[region.left - 1:right] for row in layout.records[region.top - 1:bottom]],
        index=range(region.top, bottom + 1),
        columns=[get_column_letter(col) for col in range(region.left, right + 1)], dtype=object,
    )
    return display_page(data)


def select_region_controls(state, cell_range: str, available: tuple[str, ...]) -> None:
    """Route a card selection through the existing detected-region import controls.

    Streamlit calls this before rerendering widgets. Source identity and approval
    invalidation remain owned by the existing upload flow, not by the cards.
    """
    if cell_range not in available:
        raise DataValidationError("Select a region from the current worksheet.")
    state["excel_region_mode"] = "Select a detected region"
    state["excel_selected_region"] = cell_range
    left, top, right, bottom = range_boundaries(cell_range)
    state["excel_header_mode"] = "No header (generate names)" if left == right and top == bottom else "First row of range"
    state["excel_header_row"] = top


def clear_import_review(state) -> None:
    """Forget an obsolete plan without touching the retained original dataset."""
    for key in ("excel_plan_key", "excel_before_preview", "excel_after_previews", "excel_controls_key"):
        state.pop(key, None)
    state["excel_plan"] = None
    state["excel_plans"] = ()


def initialize_excel_controls(state, source_key, regions: tuple[RegionSummary, ...]) -> None:
    """A new multi-table worksheet waits for selection; ordinary reruns keep choices.

    No candidate is automatically chosen and no repair is enabled. Legacy simple
    worksheets still start with their strict worksheet import settings.
    """
    if state.get("excel_ui_source") == source_key:
        return
    for key in ("excel_selected_region", "excel_range", "excel_custom_range", "excel_header_mode", "excel_header_row",
                "excel_exclude_empty", "excel_generate_headers", "excel_deduplicate_headers",
                "excel_remove_rows", "excel_repair_headers", "excel_plan_to_inspect"):
        state.pop(key, None)
    state["excel_region_mode"] = (
        "Choose a table" if sum(region.kind == "Table candidate" for region in regions) >= 2
        else "Worksheet / custom range"
    )
    state["excel_ui_source"] = source_key
    clear_import_review(state)


def relevant_import_controls(layout: WorksheetLayout, ranges, options: dict) -> dict[str, bool]:
    """Use the engine's planner to discover optional repairs, without enabling them.

    Inspect missing/duplicate headers before those repairs, including collisions
    introduced by an explicitly enabled irregular-header repair. Blank-row/column
    relevance uses the same whole-worksheet semantics as actual loading.
    """
    relevant = dict.fromkeys(("exclude_empty_columns", "generate_missing_headers", "deduplicate_headers",
                              "remove_empty_rows", "repair_irregular_headers"), False)
    for region in (ranges or (options["cell_range"],)):
        header_options = {key: options[key] for key in ("header_row", "infer_header", "headerless", "repair_irregular_headers")}
        if ranges:
            header_options = region_import_options(region, header_options)
        plan = plan_excel_import(layout.records, layout.sheet_name, cell_range=region,
                                 remove_empty_rows=True, **header_options)
        relevant["remove_empty_rows"] |= bool(plan.removed_blank_rows)
        for col in plan.columns:
            if col.action == "exclude_range":
                continue
            header = col.original_header
            missing = header is None or isinstance(header, str) and not header.strip()
            relevant["exclude_empty_columns"] |= col.completely_empty
            relevant["generate_missing_headers"] |= missing and bool(plan.header_row)
            relevant["repair_irregular_headers"] |= not missing and (not isinstance(header, str) or header != " ".join(header.split()))
            relevant["deduplicate_headers"] |= col.action == "invalid" and not missing and (
                isinstance(header, str) or header_options["repair_irregular_headers"]
            )
    return relevant


def header_problem_messages(plans, *, repaired: bool = False) -> tuple[str, ...]:
    """Translate planner failures into affected cells and explicit user actions."""
    groups = {"missing": [], "non-text": [], "duplicate": []}
    for plan in plans:
        for col in plan.columns:
            if col.action != "invalid":
                continue
            value = col.original_header
            kind = ("missing" if value is None or isinstance(value, str) and not value.strip() else
                    "non-text" if not isinstance(value, str) and not repaired else "duplicate")
            groups[kind].append(f"{col.excel_column}{plan.header_row}")
    resolutions = {
        "missing": "Choose a different header row or enable Generate names for missing headers. No data will be removed.",
        "non-text": "Choose a different header row or enable Repair irregular headers to convert these labels to text.",
        "duplicate": "Enable Make duplicate header names unique, or choose a different header row. Every column will be kept.",
    }
    return tuple(f"{len(set(cells))} {kind} header(s) at {', '.join(dict.fromkeys(cells))}. {resolutions[kind]}"
                 for kind, cells in groups.items() if cells)


@dataclass
class Workspace:
    """Upload -> configuration -> preview -> confirmation -> download state.

    Any source/settings change revokes previews, confirmation and export bytes.
    Failed imports retain the last successfully loaded original for inspection,
    but block processing until the currently selected source is loaded.
    """

    original: pd.DataFrame | None = None
    original_profile: DatasetProfile | None = None
    filename: str = ""
    active_source: str | None = None
    loaded_source: str | None = None
    steps: list[ProcessingStep] = field(default_factory=list)
    stop_on_error: bool = True
    configuration_error: str | None = None
    configuration_key: str = ""
    preview: ProcessingResult | None = None
    preview_key: tuple[str | None, str] | None = None
    applied: ProcessingResult | None = None
    exports: dict[str, ExportResult] = field(default_factory=dict)
    export_errors: dict[str, str] = field(default_factory=dict)
    revision: int = 0
    regions: dict[str, pd.DataFrame] = field(default_factory=dict)
    active_region: str | None = None
    source_bytes: bytes | None = None
    formula_loss_acknowledged: bool = False

    @property
    def source_current(self) -> bool:
        return self.original is not None and self.active_source is not None and self.active_source == self.loaded_source

    def invalidate(self) -> None:
        self.preview = self.applied = None
        self.preview_key = None
        self.exports.clear()
        self.export_errors.clear()
        self.formula_loss_acknowledged = False
        self.revision += 1

    def observe_source(self, payload: bytes | None, filename: str, options: ImportOptions) -> None:
        identity = None if payload is None else fingerprint({
            "bytes": hashlib.sha256(payload).hexdigest(), "filename": filename,
            "options": asdict(options),
        })
        if identity != self.active_source:
            self.active_source = identity
            self.invalidate()

    def load(self, payload: bytes, filename: str, options: ImportOptions) -> None:
        self.observe_source(payload, filename, options)
        self.invalidate()
        # Even a failed reload of the same selection must never appear current.
        self.loaded_source = None
        arguments = asdict(options)
        ranges = arguments.pop("region_ranges")
        if ranges:
            if not filename.lower().endswith(".xlsx"):
                raise DataValidationError("Separate regions require an XLSX workbook.")
            arguments.pop("cell_range")
            regions = load_xlsx_regions(payload, ranges=ranges, **arguments)
            loaded = next(iter(regions.values())).copy(deep=True)
        else:
            regions = {}
            loaded = load_dataset(BytesIO(payload), filename=filename, **arguments)
        profile = profile_dataset(loaded)
        self.original, self.original_profile = loaded, profile
        self.filename, self.loaded_source = filename, self.active_source
        self.regions, self.active_region = regions, next(iter(regions), None)
        self.source_bytes = payload if filename.lower().endswith(".xlsx") else None

    def select_region(self, region: str) -> None:
        """Activate a separately imported original; discard derived work on switch."""
        if not self.source_current or region not in self.regions:
            raise DataValidationError("Load the selected regions before switching tables.")
        if region != self.active_region:
            self.invalidate()
            self.original = self.regions[region].copy(deep=True)
            self.original_profile = profile_dataset(self.original)
            self.active_region = region

    def acknowledge_formula_loss(self, acknowledged: bool) -> None:
        if type(acknowledged) is not bool:
            raise DataValidationError("Formula acknowledgment must be boolean.")
        if acknowledged != self.formula_loss_acknowledged:
            self.exports.clear()
            self.export_errors.clear()
        self.formula_loss_acknowledged = acknowledged

    def configure(
        self, steps: list[ProcessingStep], *, stop_on_error: bool = True,
        error: str | None = None,
    ) -> None:
        identity = fingerprint({
            "steps": [asdict(step) for step in steps], "stop_on_error": stop_on_error,
            "error": error,
        })
        if identity != self.configuration_key:
            self.invalidate()
            self.configuration_key = identity
        self.steps, self.stop_on_error = deepcopy(steps), stop_on_error
        self.configuration_error = error

    def make_preview(self) -> None:
        if not self.source_current:
            raise DataValidationError("Load the currently selected file and import settings first.")
        if self.configuration_error:
            raise DataValidationError(self.configuration_error)
        self.invalidate()
        self.preview = ProcessingPipeline(self.steps, stop_on_error=self.stop_on_error).run(self.original)
        self.preview_key = (self.active_source, self.configuration_key)

    def apply_preview(self) -> None:
        if not self.source_current or self.preview is None or self.preview_key != (self.active_source, self.configuration_key):
            raise DataValidationError("Generate a current preview before applying changes.")
        if self.preview.report.errors:
            raise DataValidationError("Resolve the preview errors before applying changes.")
        self.applied = ProcessingResult(self.preview.data.copy(deep=True), deepcopy(self.preview.report))
        self.exports.clear()
        self.export_errors.clear()

    def prepare_downloads(self) -> None:
        if self.applied is None or not self.source_current:
            raise DataValidationError("Confirm a current preview before preparing downloads.")
        for kind, exporter in {"csv": export_csv, "xlsx": export_xlsx, "json": None}.items():
            if kind in self.exports or kind in self.export_errors:
                continue
            try:
                if exporter:
                    self.exports[kind] = exporter(
                        self.applied.data,
                        **({"acknowledge_formula_loss": True} if self.formula_loss_acknowledged else {}),
                    )
                else:
                    report = json.loads(export_report(self.applied.report))
                    # Export diagnostics describe these artifacts, separately from
                    # the unchanged processing report schema. JSON runs last.
                    report["exports"] = {
                        kind: ({"status": "ready", "protected_cell_count": self.exports[kind].protected_cell_count,
                                "warnings": [asdict(issue) for issue in self.exports[kind].warnings]}
                               if kind in self.exports else {"status": "failed", "error": self.export_errors[kind]})
                        for kind in ("csv", "xlsx")
                    }
                    report["formula_loss_acknowledged"] = self.formula_loss_acknowledged
                    if self.applied.data.attrs.get("xlsx_source"):
                        report["xlsx_source"] = deepcopy(self.applied.data.attrs["xlsx_source"])
                        report["source_sha256"] = hashlib.sha256(self.source_bytes).hexdigest()
                    self.exports[kind] = ExportResult(
                        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"),
                        "application/json",
                    )
            except (DataValidationError, ValueError, OverflowError) as exc:
                self.export_errors[kind] = str(exc)
