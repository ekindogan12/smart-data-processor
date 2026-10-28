"""Session lifecycle, configuration identity, and complete export artifacts."""

from datetime import datetime
from decimal import Decimal
from io import BytesIO
import json

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from smart_data_processor import DataValidationError, FileValidationError, ProcessingStep, list_worksheets, load_dataset
from smart_data_processor.dashboard_state import (
    ImportOptions, Workspace, columns_after_steps, display_page, parse_constant,
)


@pytest.fixture
def workspace():
    state = Workspace()
    state.load(b"id,amount\n001,1\n001,1\n002,2\n", "sales.csv", ImportOptions())
    state.configure([ProcessingStep("remove_duplicates")])
    return state


def test_preview_confirm_and_download_preserve_original_and_do_not_reprocess(workspace, monkeypatch):
    original = workspace.original.copy(deep=True)
    workspace.make_preview()
    assert len(workspace.preview.data) == 2
    assert workspace.applied is None
    assert not workspace.exports
    from smart_data_processor import dashboard_state
    monkeypatch.setattr(dashboard_state.ProcessingPipeline, "run", lambda *args: pytest.fail("Unnecessary processing"))
    workspace.apply_preview()
    workspace.prepare_downloads()
    assert set(workspace.exports) == {"csv", "xlsx", "json"}
    assert json.loads(workspace.exports["json"].content)["after"]["row_count"] == 2
    for kind in ["csv", "xlsx"]:
        loaded = load_dataset(BytesIO(workspace.exports[kind].content), filename=f"cleaned.{kind}")
        assert loaded["id"].tolist() == ["001", "002"]
    workspace.applied.data.iloc[0, 0] = "changed"
    assert workspace.preview.data.iloc[0, 0] == "001"
    assert_frame_equal(workspace.original, original)


@pytest.mark.parametrize("change", ["bytes", "filename", "encoding", "delimiter", "sheet", "limit", "remove"])
def test_source_and_import_setting_changes_revoke_preview_confirmation_and_exports(workspace, change):
    workspace.make_preview()
    workspace.apply_preview()
    workspace.prepare_downloads()
    payload, filename, options = b"id,amount\n001,1\n001,1\n002,2\n", "sales.csv", ImportOptions()
    if change == "bytes":
        payload += b"003,3\n"
    elif change == "filename":
        filename = "other.csv"
    elif change == "encoding":
        options = ImportOptions(encoding="cp1252")
    elif change == "delimiter":
        options = ImportOptions(delimiter=";")
    elif change == "sheet":
        options = ImportOptions(sheet_name="Other")
    elif change == "limit":
        options = ImportOptions(max_size_bytes=100)
    else:
        payload = None
    workspace.observe_source(payload, filename, options)
    assert workspace.preview is workspace.applied is None
    assert not workspace.exports
    assert not workspace.source_current
    assert len(workspace.original) == 3
    with pytest.raises(DataValidationError, match="Load"):
        workspace.make_preview()


@pytest.mark.parametrize("change", ["parameters", "order", "policy", "error"])
def test_configuration_changes_revoke_confirmation(workspace, change):
    steps = [ProcessingStep("convert_numeric", {"columns": ["amount"]}), ProcessingStep("remove_duplicates")]
    workspace.configure(steps)
    workspace.make_preview()
    workspace.apply_preview()
    if change == "parameters":
        steps[1] = ProcessingStep("remove_duplicates", {"keep": "last"})
    elif change == "order":
        steps.reverse()
    workspace.configure(steps, stop_on_error=change != "policy", error="Invalid constant" if change == "error" else None)
    assert workspace.preview is workspace.applied is None


def test_identical_configuration_and_source_do_not_invalidate(workspace):
    workspace.make_preview()
    preview = workspace.preview
    revision = workspace.revision
    workspace.configure([ProcessingStep("remove_duplicates")])
    workspace.observe_source(b"id,amount\n001,1\n001,1\n002,2\n", "sales.csv", ImportOptions())
    assert workspace.preview is preview
    assert workspace.revision == revision


def test_failed_import_preserves_last_original_and_blocks_actions(workspace):
    original = workspace.original.copy(deep=True)
    with pytest.raises(FileValidationError):
        workspace.load(b"id,id\n1,2\n", "bad.csv", ImportOptions())
    assert_frame_equal(workspace.original, original)
    assert not workspace.source_current
    with pytest.raises(DataValidationError):
        workspace.apply_preview()
    with pytest.raises(DataValidationError):
        workspace.prepare_downloads()


def test_conversion_errors_can_be_inspected_but_not_confirmed():
    state = Workspace()
    state.load(b"amount\n1\nbad\n", "input.csv", ImportOptions())
    state.configure([ProcessingStep("convert_numeric", {"columns": ["amount"]})])
    state.make_preview()
    assert state.preview.report.errors[0].row_position == 1
    assert state.preview.data["amount"].tolist() == [1, "bad"]
    with pytest.raises(DataValidationError, match="Resolve"):
        state.apply_preview()
    assert state.original["amount"].tolist() == ["1", "bad"]


def test_error_in_one_export_does_not_hide_other_formats(workspace, monkeypatch):
    from smart_data_processor import dashboard_state
    workspace.make_preview()
    workspace.apply_preview()

    def fail(data):
        raise DataValidationError("XLSX text limit exceeded")

    monkeypatch.setattr(dashboard_state, "export_xlsx", fail)
    workspace.prepare_downloads()
    assert set(workspace.exports) == {"csv", "json"}
    assert workspace.export_errors == {"xlsx": "XLSX text limit exceeded"}
    monkeypatch.setattr(dashboard_state, "export_csv", lambda *args: pytest.fail("Re-exported cached file"))
    workspace.prepare_downloads()


def test_paginated_display_cannot_truncate_the_export():
    payload = ("id\n" + "\n".join(f"{i:05}" for i in range(251))).encode()
    state = Workspace()
    state.load(payload, "long.csv", ImportOptions())
    state.configure([])
    assert len(display_page(state.original)) == 100
    assert len(display_page(state.original, page=3)) == 51
    state.make_preview()
    state.apply_preview()
    state.prepare_downloads()
    for kind in ["csv", "xlsx"]:
        frame = load_dataset(BytesIO(state.exports[kind].content), filename=f"result.{kind}")
        assert len(frame) == 251
        assert frame.iloc[-1, 0] == "00250"


def test_display_adapter_preserves_exact_mixed_values_and_original_index():
    data = pd.DataFrame({"n": [Decimal("0.123456789012345678901"), 10**100, "bad", None]}, index=[7, 7, 8, 9])
    original = data.copy(deep=True)
    view = display_page(data)
    assert view.iloc[0, 0] == "0.123456789012345678901"
    assert view.iloc[1, 0] == str(10**100)
    assert pd.isna(view.iloc[3, 0])
    assert view.index.tolist() == ["7", "7", "8", "9"]
    assert_frame_equal(data, original)


def test_header_projection_reuses_engine_and_rejects_collisions():
    assert columns_after_steps([" Order ID "], [ProcessingStep("normalize_column_names")]) == ["order_id"]
    with pytest.raises(DataValidationError, match="unique"):
        columns_after_steps(["Name", " name "], [ProcessingStep("normalize_column_names")])


@pytest.mark.parametrize("text,kind,expected", [
    ("001", "Text", "001"), ("12.50", "Number", Decimal("12.50")),
    ("False", "Boolean", False), ("True", "Boolean", True),
    ("2026-09-01", "Date / time", datetime(2026, 9, 1)),
])
def test_typed_constant_adapter(text, kind, expected):
    assert parse_constant(text, kind) == expected


@pytest.mark.parametrize("text,kind", [
    ("bad", "Number"), ("inf", "Number"), ("1e1001", "Number"),
    ("yes", "Boolean"), ("01/02/2026", "Date / time"), ("x", "Unknown"),
])
def test_invalid_constant_adapter(text, kind):
    with pytest.raises(DataValidationError):
        parse_constant(text, kind)


def test_worksheet_discovery_handles_empty_first_sheet(workbook_bytes):
    payload = workbook_bytes({"Instructions": [], "Sales": [["id"], [1]]}).getvalue()
    assert list_worksheets(payload) == ("Instructions", "Sales")
    state = Workspace()
    state.load(payload, "sales.xlsx", ImportOptions(sheet_name="Sales"))
    assert state.original.iloc[0, 0] == 1


@pytest.mark.parametrize("payload,options", [
    (b"", {}), (b"bad", {}), ("not bytes", {}),
    (b"bad", {"max_size_bytes": 0}), (b"bad", {"max_uncompressed_bytes": True}),
])
def test_worksheet_discovery_validation(payload, options):
    with pytest.raises(FileValidationError):
        list_worksheets(payload, **options)


def test_worksheet_discovery_respects_both_limits(workbook_bytes):
    payload = workbook_bytes({"Sheet": [["id"], [1]]}).getvalue()
    for options in [{"max_size_bytes": 1}, {"max_uncompressed_bytes": 1}]:
        with pytest.raises(FileValidationError, match="limit"):
            list_worksheets(payload, **options)


def test_failed_reload_of_identical_source_is_not_current(workspace, monkeypatch):
    from smart_data_processor import dashboard_state
    original = workspace.original.copy(deep=True)
    payload = b"id,amount\n001,1\n001,1\n002,2\n"

    def fail(*args, **kwargs):
        raise FileValidationError("Read failed")

    monkeypatch.setattr(dashboard_state, "load_dataset", fail)
    with pytest.raises(FileValidationError):
        workspace.load(payload, "sales.csv", ImportOptions())
    assert not workspace.source_current
    assert_frame_equal(workspace.original, original)


@pytest.mark.parametrize("options", [
    ImportOptions(cell_range="A:B"), ImportOptions(exclude_empty_columns=True),
    ImportOptions(generate_missing_headers=True), ImportOptions(deduplicate_headers=True),
    ImportOptions(confirm_header_changes=True),
])
def test_excel_import_options_participate_in_source_identity(workspace, options):
    workspace.make_preview()
    workspace.observe_source(b"id,amount\n001,1\n001,1\n002,2\n", "sales.csv", options)
    assert workspace.preview is None
    assert not workspace.source_current


@pytest.mark.parametrize("options", [
    ImportOptions(header_row=4), ImportOptions(infer_header=True), ImportOptions(remove_empty_rows=True),
    ImportOptions(repair_irregular_headers=True), ImportOptions(confirm_import_changes=True),
    ImportOptions(region_ranges=("D4:H8", "K4:N7")),
])
def test_layout_options_invalidate_pending_results(workspace, options):
    workspace.make_preview()
    workspace.observe_source(b"id,amount\n001,1\n001,1\n002,2\n", "sales.csv", options)
    assert workspace.preview is None
    assert not workspace.source_current


def test_separate_import_failure_does_not_adopt_partial_tables(workspace, sayfa1_like_workbook):
    original = workspace.original.copy(deep=True)
    with pytest.raises(FileValidationError):
        workspace.load(sayfa1_like_workbook, "sayfa1.xlsx", ImportOptions(
            sheet_name="eko", region_ranges=("K4:N7", "A1:Z2"),
            generate_missing_headers=True, confirm_header_changes=True,
        ))
    assert_frame_equal(workspace.original, original)
    assert not workspace.source_current
    assert not workspace.regions


def test_formula_acknowledgment_resets_on_configuration_change(sayfa1_like_workbook):
    state = Workspace()
    state.load(sayfa1_like_workbook, "sayfa1_like.xlsx", ImportOptions(
        sheet_name="eko", cell_range="K4:N7", generate_missing_headers=True, confirm_header_changes=True,
    ))
    state.configure([])
    state.make_preview()
    state.apply_preview()
    state.acknowledge_formula_loss(True)
    state.prepare_downloads()
    assert set(state.exports) == {"csv", "xlsx", "json"}
    assert state.source_bytes == sayfa1_like_workbook
    state.configure([ProcessingStep("remove_duplicates")])
    assert not state.formula_loss_acknowledged and not state.exports


def test_region_summary_ranks_actual_tables_and_retains_isolated_formulas(sayfa1_workbook):
    from smart_data_processor import inspect_xlsx_layouts
    from smart_data_processor.dashboard_state import summarize_regions
    layout = inspect_xlsx_layouts(sayfa1_workbook)[0]
    regions = summarize_regions(layout)
    assert [region.cell_range for region in regions[:2]] == ["D6:H12", "K6:N9"]
    assert [(region.rows, region.columns, region.formula_count) for region in regions[:2]] == [(7, 5, 1), (4, 4, 3)]
    assert sum(region.kind == "Table candidate" for region in regions) == 2
    assert sum(region.kind == "Isolated cell" for region in regions) == 6
    assert sum(region.formula_count for region in regions) == 9
    assert set(region.cell_range for region in regions) == set(layout.regions)


@pytest.mark.parametrize("records,kind,populated", [
    ([[1]], "Isolated cell", 1),
    ([["a", "b"]], "Small / narrow region", 2),
    ([["a"], [1], [2]], "Small / narrow region", 3),
    ([[1, 2], [None, 3]], "Small / narrow region", 3),
    ([[0, False], [" ", "=1+1"]], "Table candidate", 4),
    ([["x", "y"], [1, 2], [3, None]], "Table candidate", 5),
])
def test_display_candidate_heuristic_is_explicit_and_keeps_nonempty_values(records, kind, populated):
    from smart_data_processor.excel_layout import analyze_worksheet
    from smart_data_processor.dashboard_state import summarize_regions
    layout = analyze_worksheet(records, "Sheet")
    summary, = summarize_regions(layout)
    assert summary.kind == kind and summary.populated_cells == populated
    assert summary.cell_range == layout.regions[0]


def test_region_card_preview_is_bounded_and_does_not_mutate_array_formula(sayfa1_workbook):
    from copy import deepcopy
    from smart_data_processor import inspect_xlsx_layouts
    from smart_data_processor.dashboard_state import summarize_regions, region_card_preview
    from smart_data_processor.excel_layout import ExcelFormula
    layout = inspect_xlsx_layouts(sayfa1_workbook)[0]
    original = deepcopy(layout.records)
    preview = region_card_preview(layout, summarize_regions(layout)[0])
    assert preview.shape == (3, 4)
    assert preview.columns.tolist() == list("DEFG")
    assert preview.index.tolist() == ["6", "7", "8"]
    assert preview.loc["8", "F"] == "=F11(D6:D9,7)"
    preview.loc["8", "F"] = "display edit"
    assert layout.records == original
    assert isinstance(layout.records[7][5], ExcelFormula)


def test_display_sort_ties_use_coordinates_and_do_not_reorder_engine_regions():
    from dataclasses import replace
    from smart_data_processor.excel_layout import analyze_worksheet
    from smart_data_processor.dashboard_state import summarize_regions
    layout = analyze_worksheet([["a", None, "b"], [None, None, None], ["c", None, "d"]], "Sheet")
    layout = replace(layout, regions=tuple(reversed(layout.regions)))
    assert [region.cell_range for region in summarize_regions(layout)] == ["A1:A1", "C1:C1", "A3:A3", "C3:C3"]
    assert layout.regions == ("C3:C3", "A3:A3", "C1:C1", "A1:A1")


def test_empty_layout_has_no_region_cards():
    from smart_data_processor.excel_layout import analyze_worksheet
    from smart_data_processor.dashboard_state import summarize_regions
    assert summarize_regions(analyze_worksheet([], "Empty")) == ()


def test_card_selection_updates_only_existing_import_controls_and_rejects_stale_regions():
    from smart_data_processor.dashboard_state import select_region_controls
    state = {"excel_range": "A:B", "excel_region_mode": "Worksheet / custom range", "untouched": 7}
    select_region_controls(state, "D6:H12", ("D6:H12", "K6:N9"))
    assert state == {"excel_range": "A:B", "excel_region_mode": "Select a detected region",
                     "excel_selected_region": "D6:H12", "excel_header_mode": "First row of range",
                     "excel_header_row": 6, "untouched": 7}
    original = state.copy()
    with pytest.raises(DataValidationError, match="current worksheet"):
        select_region_controls(state, "A1:A2", ("D6:H12", "K6:N9"))
    assert state == original


def test_new_multi_table_source_waits_without_choosing_a_range_and_reruns_preserve_choices(sayfa1_workbook):
    from smart_data_processor import inspect_xlsx_layouts
    from smart_data_processor.dashboard_state import initialize_excel_controls, summarize_regions, select_region_controls
    regions = summarize_regions(inspect_xlsx_layouts(sayfa1_workbook)[0])
    state = {"excel_range": "A1:P15", "excel_header_row": 14, "excel_repair_headers": True}
    initialize_excel_controls(state, ("file", "eko"), regions)
    assert state["excel_region_mode"] == "Choose a table"
    assert "excel_selected_region" not in state and "excel_range" not in state
    assert "excel_repair_headers" not in state
    assert state["excel_plan"] is None and state["excel_plans"] == ()
    select_region_controls(state, "K6:N9", tuple(region.cell_range for region in regions))
    state["excel_header_mode"], state["excel_header_row"] = "Choose worksheet row", 7
    before = state.copy()
    initialize_excel_controls(state, ("file", "eko"), regions)
    assert state == before
    initialize_excel_controls(state, ("different file", "eko"), regions)
    assert state["excel_region_mode"] == "Choose a table" and "excel_selected_region" not in state


def test_region_selection_resets_only_header_policy_and_retains_explicit_custom_range():
    from smart_data_processor.dashboard_state import select_region_controls
    state = {"excel_header_mode": "Choose worksheet row", "excel_header_row": 14, "excel_range": "A1:P15"}
    select_region_controls(state, "D6:H12", ("D6:H12", "I8:I8"))
    assert state["excel_header_mode"] == "First row of range" and state["excel_header_row"] == 6
    assert state["excel_range"] == "A1:P15"
    select_region_controls(state, "I8:I8", ("D6:H12", "I8:I8"))
    assert state["excel_header_mode"] == "No header (generate names)" and state["excel_header_row"] == 8


@pytest.mark.parametrize("cell_range,expected", [
    ("D6:H12", {"repair_irregular_headers"}), ("K6:N9", set()),
    (None, {"generate_missing_headers", "exclude_empty_columns", "remove_empty_rows"}),
])
def test_only_relevant_import_repairs_are_offered(sayfa1_workbook, cell_range, expected):
    from smart_data_processor import inspect_xlsx_layouts
    from smart_data_processor.dashboard_state import relevant_import_controls
    layout = inspect_xlsx_layouts(sayfa1_workbook)[0]
    flags = relevant_import_controls(layout, (), dict(cell_range=cell_range, header_row=None,
                infer_header=False, headerless=False, repair_irregular_headers=False))
    assert {key for key, value in flags.items() if value} == expected


def test_header_problems_identify_affected_cells_and_actions(sayfa1_workbook):
    from smart_data_processor import inspect_xlsx_import
    from smart_data_processor.dashboard_state import header_problem_messages
    left = inspect_xlsx_import(sayfa1_workbook, sheet_name="eko", cell_range="D6:H12")
    messages = header_problem_messages((left,))
    assert len(messages) == 1
    assert "2 non-text header(s) at D6, H6" in messages[0]
    assert "Choose a different header row" in messages[0] and "Repair irregular headers" in messages[0]
    fixed = inspect_xlsx_import(sayfa1_workbook, sheet_name="eko", cell_range="D6:H12", repair_irregular_headers=True)
    assert header_problem_messages((fixed,), repaired=True) == ()


def test_repair_collisions_offer_deduplication_instead_of_losing_a_column(workbook_bytes):
    from smart_data_processor import inspect_xlsx_layouts, inspect_xlsx_import
    from smart_data_processor.dashboard_state import relevant_import_controls, header_problem_messages
    payload = workbook_bytes({"Sheet": [[1, "1", None], [10, 20, 30]]}).getvalue()
    layout = inspect_xlsx_layouts(payload)[0]
    options = dict(cell_range=None, header_row=None, infer_header=False, headerless=False, repair_irregular_headers=True)
    flags = relevant_import_controls(layout, (), options)
    assert flags["deduplicate_headers"] and flags["generate_missing_headers"]
    messages = header_problem_messages((inspect_xlsx_import(payload, repair_irregular_headers=True),), repaired=True)
    assert any("duplicate header(s) at B1" in message and "unique" in message for message in messages)
    assert any("missing header(s) at C1" in message and "Generate names" in message for message in messages)
