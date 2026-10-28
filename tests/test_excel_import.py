"""Regression coverage for disjoint Excel tables and explicit import repairs."""

from io import BytesIO

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from smart_data_processor import FileValidationError, inspect_xlsx_import, load_dataset


def test_two_tables_reproduce_strict_missing_header_error(two_tables_workbook):
    with pytest.raises(FileValidationError, match="Column names must be non-empty strings"):
        load_dataset(BytesIO(two_tables_workbook), filename="measurements.xlsx")


def test_exact_plan_and_explicit_combined_import(two_tables_workbook):
    options = {"exclude_empty_columns": True, "deduplicate_headers": True}
    plan = inspect_xlsx_import(two_tables_workbook, **options)
    assert not plan.errors
    assert plan.selected_range == "A1:N4"
    assert plan.row_count == 3
    assert [c.excel_column for c in plan.columns if c.action == "exclude_empty"] == list("CDEFGHIJK") + ["N"]
    renamed = [c for c in plan.columns if c.action.startswith("rename_")]
    assert [(c.excel_column, c.original_header, c.imported_header) for c in renamed] == [("L", "f(Hz.)", "f(Hz.)__2")]
    assert plan.requires_header_confirmation
    with pytest.raises(FileValidationError, match="confirm_header_changes"):
        load_dataset(BytesIO(two_tables_workbook), filename="input.xlsx", **options)
    result = load_dataset(BytesIO(two_tables_workbook), filename="input.xlsx", confirm_header_changes=True, **options)
    expected = pd.DataFrame({
        "f(Hz.)": [10, 20, 40], "dB": [-3, -6, None],
        "f(Hz.)__2": [1000, 2000, None], "f(o)": [1.5, 2.5, None],
    }, dtype=object)
    assert_frame_equal(result, expected)
    assert inspect_xlsx_import(two_tables_workbook, **options) == plan


def test_excluding_empty_columns_alone_still_rejects_duplicate_headers(two_tables_workbook):
    with pytest.raises(FileValidationError, match="must be unique"):
        load_dataset(BytesIO(two_tables_workbook), filename="input.xlsx", exclude_empty_columns=True)


@pytest.mark.parametrize("cell_range,headers,first_row", [
    ("A:B", ["f(Hz.)", "dB"], [10, -3]),
    ("L:M", ["f(Hz.)", "f(o)"], [1000, 1.5]),
    (" l:m ", ["f(Hz.)", "f(o)"], [1000, 1.5]),
])
def test_selecting_each_table_preserves_all_selected_rows(two_tables_workbook, cell_range, headers, first_row):
    plan = inspect_xlsx_import(two_tables_workbook, cell_range=cell_range)
    assert not plan.errors and not plan.requires_header_confirmation
    assert plan.requires_confirmation  # The UI explicitly confirms out-of-range exclusions.
    result = load_dataset(BytesIO(two_tables_workbook), filename="input.xlsx", cell_range=cell_range)
    assert result.columns.tolist() == headers
    assert result.iloc[0].tolist() == first_row
    assert len(result) == 3  # Includes the final blank row in the right-hand table.


def test_explicit_rectangle_selects_its_first_row_as_header(workbook_bytes):
    payload = workbook_bytes({"Sheet": [["Instructions", None], ["x", "y"], [1, 2], [3, 4], [5, 6]]}).getvalue()
    plan = inspect_xlsx_import(payload, cell_range="A2:B4")
    assert (plan.header_row, plan.last_row, plan.worksheet_rows, plan.row_count) == (2, 4, 5, 2)
    result = load_dataset(BytesIO(payload), filename="input.xlsx", cell_range="A2:B4")
    assert_frame_equal(result, pd.DataFrame({"x": [1, 3], "y": [2, 4]}, dtype=object))


def test_blank_headers_with_data_are_never_excluded_as_empty(workbook_bytes):
    payload = workbook_bytes({"Sheet": [
        ["id", None, None, None, None, None, "  "],
        ["001", 0, False, " ", "=A2", None, None],
    ]}).getvalue()
    options = {"exclude_empty_columns": True, "generate_missing_headers": True}
    plan = inspect_xlsx_import(payload, **options)
    assert [c.excel_column for c in plan.columns if c.completely_empty] == ["F"]
    assert [c.excel_column for c in plan.columns if c.action == "rename_missing"] == ["B", "C", "D", "E", "G"]
    with pytest.raises(FileValidationError, match="confirm_header_changes"):
        load_dataset(BytesIO(payload), filename="input.xlsx", **options)
    result = load_dataset(BytesIO(payload), filename="input.xlsx", confirm_header_changes=True, **options)
    assert result.iloc[0].tolist() == ["001", 0, False, " ", "=A2", None]
    assert result.columns.tolist() == ["id"] + [f"Unnamed_Column_{i}" for i in range(1, 6)]


def test_empty_check_covers_entire_column_including_cells_outside_range(workbook_bytes):
    payload = workbook_bytes({"Sheet": [["notes", "metadata"], ["x", None], [1, None]]}).getvalue()
    plan = inspect_xlsx_import(payload, cell_range="A2:B3", exclude_empty_columns=True, generate_missing_headers=True)
    assert not plan.columns[1].completely_empty
    assert plan.columns[1].has_data
    assert plan.columns[1].action == "rename_missing"


def test_named_columns_without_data_are_not_excluded(workbook_bytes):
    payload = workbook_bytes({"Sheet": [["id", "unused"], [1, None]]}).getvalue()
    result = load_dataset(BytesIO(payload), filename="input.xlsx", exclude_empty_columns=True)
    assert result.columns.tolist() == ["id", "unused"]


def test_keep_empty_columns_when_user_only_approves_generated_names(two_tables_workbook):
    result = load_dataset(BytesIO(two_tables_workbook), filename="input.xlsx", generate_missing_headers=True,
                          deduplicate_headers=True, confirm_header_changes=True)
    assert result.shape == (3, 14)
    assert result.columns.is_unique
    assert result.iloc[:, 2:11].isna().all().all()
    assert result.iloc[:, 13].isna().all()


def test_generated_names_reserve_all_existing_headers_and_keep_column_order(workbook_bytes):
    payload = workbook_bytes({"Sheet": [
        ["a", "a", "a__2", None, "Unnamed_Column_1", None, "a"], list(range(7)),
    ]}).getvalue()
    options = {"generate_missing_headers": True, "deduplicate_headers": True}
    plan = inspect_xlsx_import(payload, **options)
    names = [c.imported_header for c in plan.columns]
    assert names == ["a", "a__3", "a__2", "Unnamed_Column_2", "Unnamed_Column_1", "Unnamed_Column_3", "a__4"]
    result = load_dataset(BytesIO(payload), filename="input.xlsx", confirm_header_changes=True, **options)
    assert result.columns.tolist() == names
    assert result.iloc[0].tolist() == list(range(7))


def test_missing_generation_does_not_convert_nontext_headers(workbook_bytes):
    payload = workbook_bytes({"Sheet": [[123], [4]]}).getvalue()
    with pytest.raises(FileValidationError, match="non-text header"):
        load_dataset(BytesIO(payload), filename="input.xlsx", generate_missing_headers=True, confirm_header_changes=True)


@pytest.mark.parametrize("cell_range", ["B:A", "A0:B2", "1:3", "A:B3", "A1:B", "A:Z", "A1:B100", "A:B,L:M", "XFE:XFE", False, 1])
def test_invalid_or_out_of_bounds_ranges_fail_explicitly(two_tables_workbook, cell_range):
    with pytest.raises(FileValidationError):
        inspect_xlsx_import(two_tables_workbook, cell_range=cell_range)
    with pytest.raises(FileValidationError):
        load_dataset(BytesIO(two_tables_workbook), filename="input.xlsx", cell_range=cell_range)


def test_excluding_an_entirely_empty_selection_fails(two_tables_workbook):
    plan = inspect_xlsx_import(two_tables_workbook, cell_range="C:K", exclude_empty_columns=True)
    assert "at least one column" in plan.errors[0]
    with pytest.raises(FileValidationError, match="at least one column"):
        load_dataset(BytesIO(two_tables_workbook), filename="input.xlsx", cell_range="C:K", exclude_empty_columns=True)


def test_workbook_bytes_paths_and_stream_positions_are_preserved(two_tables_workbook, tmp_path):
    path = tmp_path / "measurement.xlsx"
    path.write_bytes(two_tables_workbook)
    stream = BytesIO(two_tables_workbook)
    stream.seek(23)
    load_dataset(stream, filename="input.xlsx", cell_range="A:B")
    assert stream.tell() == 23
    assert stream.getvalue() == two_tables_workbook
    load_dataset(path, exclude_empty_columns=True, deduplicate_headers=True, confirm_header_changes=True)
    assert path.read_bytes() == two_tables_workbook


@pytest.mark.parametrize("options", [
    {"cell_range": "A:B"}, {"exclude_empty_columns": True}, {"generate_missing_headers": True},
    {"deduplicate_headers": True}, {"confirm_header_changes": True},
])
def test_excel_options_are_not_silently_ignored_for_csv(options):
    with pytest.raises(FileValidationError, match="only supported for XLSX"):
        load_dataset(BytesIO(b"id\n1\n"), filename="input.csv", **options)


@pytest.mark.parametrize("options", [
    {"exclude_empty_columns": "yes"}, {"generate_missing_headers": 1},
    {"deduplicate_headers": None}, {"max_size_bytes": 1}, {"max_uncompressed_bytes": 1},
])
def test_inspection_validates_options_and_size_limits(two_tables_workbook, options):
    with pytest.raises(FileValidationError):
        inspect_xlsx_import(two_tables_workbook, **options)
