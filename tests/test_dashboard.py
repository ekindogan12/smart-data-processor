"""Headless Streamlit interactions, including real upload widget input.

AppTest checks rendering/state and generated download bytes. It does not inspect
browser pixel layout, the operating-system file picker, or saved download files.
"""

from io import BytesIO
import json
from pathlib import Path

from pandas.testing import assert_frame_equal
import pytest
from streamlit.testing.v1 import AppTest

from smart_data_processor import load_dataset


@pytest.fixture
def app():
    return AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20).run()


def upload(app, payload=b"id,amount,name\n001,1, Ana \n001,1, Ana \n002,2,Ben\n", filename="input.csv"):
    app.file_uploader[0].upload(filename, payload).run()
    app.button(key="load_dataset").click().run()
    assert not app.exception
    return app


def add_step(app, label, columns=None):
    app.selectbox(key="new_operation").select(label).run()
    app.button(key="add_operation").click().run()
    key = f"step_{app.session_state['queue'][-1]['id']}"
    if columns is not None:
        app.multiselect(key=f"{key}_columns").set_value(columns).run()
    return key


def preview_and_apply(app):
    app.button(key="preview_changes").click().run()
    assert not app.session_state["workspace"].preview.report.errors
    revision = app.session_state["workspace"].revision
    assert app.button(key="apply_changes").disabled
    app.checkbox(key=f"confirm_{revision}").check().run()
    app.button(key="apply_changes").click().run()


def test_empty_states_and_navigation(app):
    assert not app.exception
    assert app.title[0].value == "Smart Data Processor"
    assert len(app.header) == 5
    assert len(app.file_uploader) == 1
    assert app.button(key="load_dataset").disabled
    assert not app.get("download_button")
    assert app.session_state["workspace"].original is None


def test_csv_upload_profile_preview_confirm_and_downloads(app):
    upload(app)
    original = app.session_state["workspace"].original.copy(deep=True)
    assert [(metric.label, metric.value) for metric in app.metric] == [
        ("Rows", "3"), ("Columns", "3"), ("Missing cells", "0"), ("Duplicate rows", "1"),
    ]
    add_step(app, "Remove duplicates")
    app.button(key="preview_changes").click().run()
    assert len(app.session_state["workspace"].preview.data) == 2
    assert app.session_state["workspace"].applied is None
    assert not app.get("download_button")
    revision = app.session_state["workspace"].revision
    app.checkbox(key=f"confirm_{revision}").check().run()
    app.button(key="apply_changes").click().run()
    app.button(key="prepare_downloads").click().run()
    assert len(app.get("download_button")) == 3
    workspace = app.session_state["workspace"]
    assert_frame_equal(workspace.original, original)
    assert json.loads(workspace.exports["json"].content)["after"]["row_count"] == 2
    for kind in ["csv", "xlsx"]:
        data = load_dataset(BytesIO(workspace.exports[kind].content), filename=f"result.{kind}")
        assert len(data) == 2
    for button in app.get("download_button"):
        assert button.proto.url
    app.get("download_button")[0].click().run()
    assert not app.exception
    assert len(app.session_state["workspace"].applied.data) == 2


def test_legacy_csv_options_and_failed_load_preserve_original(app):
    upload(app)
    original = app.session_state["workspace"].original.copy(deep=True)
    app.file_uploader[0].upload("legacy.csv", "id;name\n01;Málaga\n".encode("cp1252")).run()
    app.button(key="load_dataset").click().run()
    assert any("decode" in error.value for error in app.error)
    assert_frame_equal(app.session_state["workspace"].original, original)
    app.selectbox(key="csv_encoding").select("cp1252").run()
    app.selectbox(key="csv_delimiter").select("Semicolon (;)").run()
    app.button(key="load_dataset").click().run()
    assert app.session_state["workspace"].original.iloc[0].tolist() == ["01", "Málaga"]
    assert not app.exception


def test_xlsx_sheet_selection_and_changes_invalidate_results(app, workbook_bytes):
    payload = workbook_bytes({"Instructions": [], "Sales": [["id"], [1]], "Customers": [["name"], ["Ana"]]}).getvalue()
    app.file_uploader[0].upload("book.xlsx", payload).run()
    sheet = next(widget for widget in app.selectbox if widget.label == "Excel worksheet")
    assert sheet.options == ["Instructions", "Sales", "Customers"]
    sheet.select("Sales").run()
    app.button(key="load_dataset").click().run()
    preview_and_apply(app)
    next(widget for widget in app.selectbox if widget.label == "Excel worksheet").select("Customers").run()
    assert app.session_state["workspace"].applied is None
    assert app.session_state["workspace"].preview is None
    assert app.button(key="preview_changes").disabled
    app.button(key="load_dataset").click().run()
    assert app.session_state["workspace"].original.iloc[0, 0] == "Ana"
    assert not app.exception


def test_invalid_workbook_and_import_limit_are_visible(app):
    app.file_uploader[0].upload("broken.xlsx", b"not a workbook").run()
    assert app.error
    assert app.button(key="load_dataset").disabled
    app.file_uploader[0].upload("large.csv", b"id\n" + b"x" * (1024**2)).run()
    app.number_input(key="import_limit").set_value(1).run()
    assert any("exceeds" in error.value for error in app.error)
    assert app.button(key="load_dataset").disabled


def test_upload_clear_invalidates_confirmation_without_losing_original(app):
    upload(app)
    preview_and_apply(app)
    app.file_uploader[0].clear().run()
    assert app.session_state["workspace"].original is not None
    assert app.session_state["workspace"].applied is None
    assert app.button(key="preview_changes").disabled


def test_step_edits_reorder_and_remove_require_new_preview(app):
    upload(app)
    text_key = add_step(app, "Clean text", ["name"])
    duplicate_key = add_step(app, "Remove duplicates")
    preview_and_apply(app)
    app.selectbox(key=f"{text_key}_text").select("upper").run()
    assert app.session_state["workspace"].preview is None
    app.button(key=f"{duplicate_key}_up").click().run()
    assert [step.operation for step in app.session_state["workspace"].steps] == ["remove_duplicates", "clean_text"]
    app.button(key=f"{duplicate_key}_remove").click().run()
    assert len(app.session_state["workspace"].steps) == 1
    preview_and_apply(app)
    assert app.session_state["workspace"].applied.data.loc[0, "name"] == " ANA "
    assert not app.exception


def test_configuration_persists_while_import_settings_are_pending(app):
    upload(app)
    key = add_step(app, "Clean text", ["name"])
    app.selectbox(key=f"{key}_text").select("upper").run()
    app.selectbox(key="csv_encoding").select("utf-8-sig").run()
    assert app.button(key="preview_changes").disabled
    app.button(key="load_dataset").click().run()
    assert app.multiselect(key=f"{key}_columns").value == ["name"]
    assert app.selectbox(key=f"{key}_text").value == "upper"


def test_numeric_conversion_errors_block_confirmation_and_preserve_original(app):
    upload(app, b"amount\n1\nbad\n")
    add_step(app, "Convert numbers", ["amount"])
    app.button(key="preview_changes").click().run()
    state = app.session_state["workspace"]
    assert state.preview.data["amount"].tolist() == [1, "bad"]
    assert state.original["amount"].tolist() == ["1", "bad"]
    assert state.preview.report.errors[0].code == "invalid_numeric"
    assert any("preview contains errors" in error.value for error in app.error)
    assert not any(button.key == "apply_changes" for button in app.button)
    assert not app.get("download_button")


def test_numeric_then_missing_constant_and_explicit_date_controls(app):
    upload(app, b"amount,date\n\"1.234,50\",01/02/2026\n,13/02/2026\n")
    number = add_step(app, "Convert numbers", ["amount"])
    app.selectbox(key=f"{number}_decimal").select(",").run()
    app.selectbox(key=f"{number}_thousands").select("Dot (.)").run()
    missing = add_step(app, "Handle missing values", ["amount"])
    app.selectbox(key=f"{missing}_strategy").select("constant").run()
    app.selectbox(key=f"{missing}_constant_type").select("Number").run()
    app.text_input(key=f"{missing}_value").set_value("9.50").run()
    dates = add_step(app, "Standardize dates", ["date"])
    app.text_area(key=f"{dates}_formats").set_value("%d/%m/%Y").run()
    preview_and_apply(app)
    assert app.session_state["workspace"].applied.data["date"].tolist() == ["2026-02-01", "2026-02-13"]
    assert str(app.session_state["workspace"].applied.data.loc[1, "amount"]) == "9.50"
    assert not app.exception


def test_ambiguous_dates_are_visible(app):
    upload(app, b"date\n01/02/2026\n")
    key = add_step(app, "Standardize dates", ["date"])
    app.text_area(key=f"{key}_formats").set_value("%d/%m/%Y\n%m/%d/%Y").run()
    app.button(key="preview_changes").click().run()
    report = app.session_state["workspace"].preview.report
    assert report.errors[0].code == report.warnings[0].code == "ambiguous_date"
    assert not app.exception


def test_normalized_columns_are_available_and_reorder_does_not_drop_stale_selection(app):
    upload(app, b" Amount \n1\n")
    add_step(app, "Normalize column names")
    key = add_step(app, "Convert numbers", ["amount"])
    preview_and_apply(app)
    app.button(key=f"{key}_up").click().run()
    assert app.multiselect(key=f"{key}_columns").value == ["amount"]
    assert app.button(key="preview_changes").disabled
    assert app.session_state["workspace"].applied is None
    assert app.error


def test_unrelated_reruns_do_not_reprocess_or_reexport(app, monkeypatch):
    from smart_data_processor import dashboard_state
    upload(app)
    preview_and_apply(app)
    app.button(key="prepare_downloads").click().run()
    monkeypatch.setattr(dashboard_state.ProcessingPipeline, "run", lambda *args: pytest.fail("Reprocessed"))
    monkeypatch.setattr(dashboard_state, "export_csv", lambda *args: pytest.fail("Reexported"))
    app.checkbox(key="side_by_side").check().run()
    assert not app.exception
    assert len(app.get("download_button")) == 3


def test_sample_mode_and_reset(app):
    app.radio(key="source_mode").set_value("Try a sample").run()
    app.button(key="load_dataset").click().run()
    assert len(app.session_state["workspace"].original) == 10
    app.button(key="reset_workspace").click().run()
    assert app.session_state["workspace"].original is None
    assert not app.session_state["queue"]
    assert app.radio(key="source_mode").value == "Upload a file"


def test_unexpected_processing_failure_is_visible_and_retains_original(app, monkeypatch):
    from smart_data_processor import dashboard_state
    upload(app)
    original = app.session_state["workspace"].original.copy(deep=True)

    def fail(*args):
        raise RuntimeError("Simulated unexpected failure")

    monkeypatch.setattr(dashboard_state.ProcessingPipeline, "run", fail)
    app.button(key="preview_changes").click().run()
    assert any("original dataset is preserved" in error.value for error in app.error)
    assert_frame_equal(app.session_state["workspace"].original, original)
    assert app.session_state["workspace"].preview is None
    assert not app.exception


def approve_excel_import(app):
    key = f"excel_approve_{app.session_state['excel_review_revision']}"
    app.checkbox(key=key).check().run()


def test_two_table_workbook_plan_requires_approval_and_preserves_all_data(app, two_tables_workbook):
    app.file_uploader[0].upload("measurements.xlsx", two_tables_workbook).run()
    assert app.button(key="load_dataset").disabled
    assert not app.error  # No whole-sheet plan is built before a choice.
    app.selectbox(key="excel_region_mode").select("Worksheet / custom range").run()
    assert any("missing header(s)" in item.value for item in app.warning)
    app.checkbox(key="excel_exclude_empty").check().run()
    assert any("duplicate header(s)" in item.value for item in app.warning)
    app.checkbox(key="excel_deduplicate_headers").check().run()
    assert app.button(key="load_dataset").disabled
    plan_table = next(table.value for table in app.dataframe if "Excel column" in table.value.columns)
    assert plan_table.loc[plan_table["Action"] == "Exclude: completely empty", "Excel column"].tolist() == list("CDEFGHIJK") + ["N"]
    assert plan_table.loc[plan_table["Excel column"] == "L", "Import header"].iloc[0] == "f(Hz.)__2"
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    assert app.session_state["workspace"].source_current
    assert app.session_state["workspace"].original.shape == (3, 4)
    assert app.session_state["workspace"].original.iloc[0].tolist() == [10, -3, 1000, 1.5]
    assert not app.exception


def test_range_selection_reapproval_and_revocation_invalidate_old_results(app, two_tables_workbook):
    app.file_uploader[0].upload("measurements.xlsx", two_tables_workbook).run()
    app.selectbox(key="excel_region_mode").select("Worksheet / custom range").run()
    app.text_input(key="excel_range").set_value("A:B").run()
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    preview_and_apply(app)
    app.button(key="prepare_downloads").click().run()
    app.text_input(key="excel_range").set_value("L:M").run()
    assert app.button(key="load_dataset").disabled
    assert not app.session_state["workspace"].exports
    assert not app.metric
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    assert app.session_state["workspace"].original.columns.tolist() == ["f(Hz.)", "f(o)"]
    approval_key = f"excel_approve_{app.session_state['excel_review_revision']}"
    app.checkbox(key=approval_key).uncheck().run()
    assert not app.session_state["workspace"].source_current
    assert not app.metric
    assert app.button(key="preview_changes").disabled
    assert not app.exception


def test_missing_headers_with_data_need_generation_and_approval(app, workbook_bytes):
    payload = workbook_bytes({"Sheet": [["id", None, None], [1, 7, None]]}).getvalue()
    app.file_uploader[0].upload("missing.xlsx", payload).run()
    app.checkbox(key="excel_exclude_empty").check().run()
    assert app.button(key="load_dataset").disabled
    plan = app.session_state["excel_plan"]
    assert plan.columns[1].action == "invalid"
    assert plan.columns[2].action == "exclude_empty"
    app.checkbox(key="excel_generate_headers").check().run()
    assert app.button(key="load_dataset").disabled
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    assert app.session_state["workspace"].original.columns.tolist() == ["id", "Unnamed_Column_1"]
    assert app.session_state["workspace"].original.iloc[0].tolist() == [1, 7]


def test_failed_new_upload_hides_stale_statistics_and_original_table(app, two_tables_workbook):
    upload(app)
    original = app.session_state["workspace"].original.copy(deep=True)
    preview_and_apply(app)
    app.file_uploader[0].upload("measurements.xlsx", two_tables_workbook).run()
    app.selectbox(key="excel_region_mode").select("Worksheet / custom range").run()
    assert app.error
    assert not app.metric
    assert not any(heading.value == "Original dataset" for heading in app.subheader)
    assert not app.get("download_button")
    assert any("not current" in message.value for message in app.warning)
    assert_frame_equal(app.session_state["workspace"].original, original)
    assert not app.session_state["workspace"].source_current


def test_import_plan_is_not_rescanned_on_unrelated_reruns(app, two_tables_workbook, monkeypatch):
    from smart_data_processor import dashboard
    app.file_uploader[0].upload("measurements.xlsx", two_tables_workbook).run()
    app.selectbox(key="excel_region_mode").select("Worksheet / custom range").run()
    app.text_input(key="excel_range").set_value("A:B").run()
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    monkeypatch.setattr(dashboard, "inspect_xlsx_import", lambda *args, **kwargs: pytest.fail("Rescanned workbook"))
    preview_and_apply(app)
    assert not app.exception


def open_sparse_workbook(app, payload):
    app.file_uploader[0].upload("sayfa1_like.xlsx", payload).run()
    assert any("Sayfa1 (empty)" in item.value for item in app.caption)
    assert app.button(key="load_dataset").disabled
    next(widget for widget in app.selectbox if widget.label == "Excel worksheet").select("eko").run()


def configure_sparse_headers(app):
    for key in ("excel_generate_headers", "excel_deduplicate_headers", "excel_repair_headers"):
        app.checkbox(key=key).check().run()


def test_sparse_workbook_separate_import_and_region_switch(app, sayfa1_like_workbook):
    open_sparse_workbook(app, sayfa1_like_workbook)
    app.selectbox(key="excel_region_mode").select("Import all regions separately").run()
    configure_sparse_headers(app)
    assert len(app.session_state["excel_plans"]) == 2
    assert any("D4:H8" in caption.value for caption in app.caption)
    assert any("K4:N7" in caption.value for caption in app.caption)
    assert app.button(key="load_dataset").disabled
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    workspace = app.session_state["workspace"]
    assert workspace.original.shape == (4, 5)
    assert len(workspace.regions) == 2
    preview_and_apply(app)
    next(widget for widget in app.selectbox if widget.label == "Active imported region").select("K4:N7").run()
    workspace = app.session_state["workspace"]
    assert workspace.original.shape == (3, 4)
    assert workspace.original.iloc[0, 2] == "=K5/1000"
    assert workspace.applied is None and not workspace.exports
    assert not app.exception


def test_sparse_header_inference_before_after_and_invalidation(app, sayfa1_like_workbook):
    open_sparse_workbook(app, sayfa1_like_workbook)
    app.selectbox(key="excel_region_mode").select("Worksheet / custom range").run()
    app.text_input(key="excel_range").set_value("D:H").run()
    app.selectbox(key="excel_header_mode").select("Infer header (review required)").run()
    configure_sparse_headers(app)
    app.checkbox(key="excel_remove_rows").check().run()
    plan = app.session_state["excel_plan"]
    assert plan.header_row == 4 and plan.removed_blank_rows == (9, 10, 11, 12)
    assert any("Before / After" in expander.label for expander in app.expander)
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    preview_and_apply(app)
    app.selectbox(key="excel_header_mode").select("Choose worksheet row").run()
    app.number_input(key="excel_header_row").set_value(5).run()
    assert not app.session_state["workspace"].source_current
    assert app.session_state["workspace"].preview is None
    assert app.button(key="load_dataset").disabled
    assert not app.metric
    assert not app.exception


def test_formula_export_gate_and_original_download_are_explicit(app, sayfa1_like_workbook):
    open_sparse_workbook(app, sayfa1_like_workbook)
    app.button(key="region_card_D4:H8").click().run()
    configure_sparse_headers(app)
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    workspace = app.session_state["workspace"]
    assert workspace.source_bytes == sayfa1_like_workbook
    assert any(button.key == "download_original" for button in app.get("download_button"))
    preview_and_apply(app)
    app.button(key="prepare_downloads").click().run()
    assert set(workspace.export_errors) == {"csv", "xlsx"}
    assert set(workspace.exports) == {"json"}
    app.checkbox(key=f"formula_ack_{workspace.revision}").check().run()
    app.button(key="prepare_downloads").click().run()
    assert set(workspace.exports) == {"csv", "xlsx", "json"}
    app.checkbox(key=f"formula_ack_{workspace.revision}").uncheck().run()
    assert not workspace.exports
    assert not any(button.key in {"download_csv", "download_xlsx"} for button in app.get("download_button"))
    assert not app.exception


def test_switch_to_empty_sheet_revokes_current_data(app, sayfa1_like_workbook):
    open_sparse_workbook(app, sayfa1_like_workbook)
    app.button(key="region_card_D4:H8").click().run()
    configure_sparse_headers(app)
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    preview_and_apply(app)
    next(widget for widget in app.selectbox if widget.label == "Excel worksheet").select("Sayfa1").run()
    assert not app.session_state["workspace"].source_current
    assert not app.metric and not app.get("download_button")
    assert app.button(key="load_dataset").disabled
    assert not app.exception


def test_real_sayfa1_import_all_regions_and_array_formula_download_gate(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    assert any("Sayfa2 (empty)" in item.value for item in app.caption)
    app.selectbox(key="excel_region_mode").select("Import all regions separately").run()
    app.checkbox(key="excel_repair_headers").check().run()
    assert len(app.session_state["excel_plans"]) == 8
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    workspace = app.session_state["workspace"]
    assert len(workspace.regions) == 8
    assert workspace.original.shape == (6, 5)
    from smart_data_processor.excel_layout import ExcelFormula
    assert isinstance(workspace.original.iloc[1, 2], ExcelFormula)
    preview_and_apply(app)
    app.button(key="prepare_downloads").click().run()
    assert set(workspace.export_errors) == {"csv", "xlsx"}
    app.checkbox(key=f"formula_ack_{workspace.revision}").check().run()
    app.button(key="prepare_downloads").click().run()
    assert set(workspace.exports) == {"csv", "xlsx", "json"}
    report = json.loads(workspace.exports["json"].content)
    assert ["F8", "ArrayFormula", "F8"] in report["xlsx_source"]["formula_details"]
    assert workspace.source_bytes == sayfa1_workbook
    next(widget for widget in app.selectbox if widget.label == "Active imported region").select("I8:I8").run()
    assert workspace.original.iloc[0, 0] == "=D9+D8"
    assert not workspace.exports and not workspace.formula_loss_acknowledged
    assert not app.exception


def test_table_exports_cannot_bypass_formula_acknowledgment(app):
    import streamlit as st
    assert st.get_option("client.disableDataExport") is True


def test_structure_summary_two_largest_cards_and_collapsed_details(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    cards = [button for button in app.button if button.key.startswith("region_card_")]
    assert [button.label for button in cards[:2]] == ["Select D6:H12", "Select K6:N9"]
    assert len(cards) == 8
    assert {"Worksheet size", "Table candidates", "Isolated regions", "Formula cells"} <= {item.value for item in app.caption}
    assert "**15 rows × 16 columns**" in [item.value for item in app.markdown]
    others = next(item for item in app.expander if item.label.startswith("Other regions (6)"))
    assert not others.proto.expanded
    assert len(others.button) == 6
    assert {button.key for button in others.button} == {"region_card_" + coordinate for coordinate in ("I8:I8", "P8:P8", "O12:O12", "K13:K13", "O14:O14", "J15:J15")}
    advanced = next(item for item in app.expander if item.label == "Advanced Details")
    assert not advanced.proto.expanded
    assert any("Leading blank rows: 1:5" in item.value for item in advanced.markdown)
    assert any("Leading blank columns: A:C" in item.value for item in advanced.markdown)
    assert len(advanced.dataframe[0].value) == 9
    assert all(not item.proto.expanded for item in app.expander if item.label.startswith("Advanced Details"))
    assert any("Contains 1 formula cell" == item.value for item in app.markdown)
    assert any("Contains 3 formula cells" == item.value for item in app.markdown)
    assert not app.exception


def test_card_selects_table_and_isolated_region_with_new_approval_and_export_guards(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.button(key="region_card_K6:N9").click().run()
    assert app.selectbox(key="excel_region_mode").value == "Select a detected region"
    assert app.selectbox(key="excel_selected_region").value == "K6:N9"
    assert app.button(key="region_card_K6:N9").label == "Selected K6:N9"
    assert not any(widget.key == "excel_range" for widget in app.text_input)
    assert app.button(key="load_dataset").disabled
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    preview_and_apply(app)
    workspace = app.session_state["workspace"]
    app.checkbox(key=f"formula_ack_{workspace.revision}").check().run()
    app.button(key="prepare_downloads").click().run()
    assert set(workspace.exports) == {"csv", "xlsx", "json"}
    app.button(key="region_card_I8:I8").click().run()
    assert app.session_state["excel_plan"].header_row == 0
    assert not workspace.source_current and workspace.preview is None and not workspace.exports
    assert not workspace.formula_loss_acknowledged
    assert app.button(key="load_dataset").disabled
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    assert workspace.original.shape == (1, 1)
    assert workspace.original.iloc[0, 0] == "=D9+D8"
    assert workspace.source_bytes == sayfa1_workbook
    preview_and_apply(app)
    app.button(key="prepare_downloads").click().run()
    assert set(workspace.export_errors) == {"csv", "xlsx"}
    assert not app.exception


def test_inspecting_another_import_plan_does_not_reprocess_or_invalidate(app, sayfa1_workbook, monkeypatch):
    from smart_data_processor import dashboard
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.selectbox(key="excel_region_mode").select("Import all regions separately").run()
    app.checkbox(key="excel_repair_headers").check().run()
    assert len(app.session_state["excel_plans"]) == 8
    assert len([item for item in app.expander if item.label.startswith("Before / After")]) == 1
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    preview_and_apply(app)
    workspace = app.session_state["workspace"]
    preview, applied, revision = workspace.preview, workspace.applied, workspace.revision
    monkeypatch.setattr(dashboard, "inspect_xlsx_import", lambda *args, **kwargs: pytest.fail("Rescanned workbook"))
    monkeypatch.setattr(dashboard, "summarize_regions", lambda *args: pytest.fail("Recomputed structure summary"))
    app.selectbox(key="excel_plan_to_inspect").select(7).run()
    assert workspace.preview is preview and workspace.applied is applied
    assert workspace.revision == revision and workspace.source_current
    assert any("J15:J15" in item.value for item in app.caption)
    assert len(workspace.regions) == 8
    assert not app.exception


def test_small_narrow_regions_are_not_labeled_as_tables(app, workbook_bytes):
    payload = workbook_bytes({"Sheet": [["a", None, None, "b"], [1, None, None, None], [2, None, None, None]]}).getvalue()
    app.file_uploader[0].upload("narrow.xlsx", payload).run()
    assert any("Small / narrow region" in item.value for item in app.caption)
    assert any("Isolated cell" in item.value for item in app.caption)
    others = next(item for item in app.expander if item.label.startswith("Other regions"))
    assert not others.proto.expanded  # Non-candidates are always progressively disclosed.
    assert len([item for item in app.button if item.key.startswith("region_card_")]) == 2
    assert not app.exception


def test_all_import_modes_remain_available_after_card_selection(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.button(key="region_card_K6:N9").click().run()
    assert app.selectbox(key="excel_region_mode").options == [
        "Choose a table", "Worksheet / custom range", "Select a detected region", "Import all regions separately",
        "Combine regions in worksheet alignment",
    ]
    app.selectbox(key="excel_region_mode").select("Worksheet / custom range").run()
    assert not app.text_input(key="excel_range").disabled
    app.text_input(key="excel_range").set_value("K6:N9").run()
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    assert app.session_state["workspace"].original.shape == (3, 4)
    app.selectbox(key="excel_region_mode").select("Combine regions in worksheet alignment").run()
    assert not app.session_state["workspace"].source_current
    assert app.button(key="load_dataset").disabled
    assert not app.exception


def test_changed_workbook_replaces_cards_and_invalidates_selected_region(app, sayfa1_workbook, workbook_bytes):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.button(key="region_card_K6:N9").click().run()
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    preview_and_apply(app)
    replacement = workbook_bytes({"eko": [["x", "y"], [1, 2]]}).getvalue()
    app.file_uploader[0].upload("sayfa1.xlsx", replacement).run()
    assert [item.key for item in app.button if item.key.startswith("region_card_")] == ["region_card_A1:B2"]
    assert not app.session_state["workspace"].source_current
    assert app.session_state["workspace"].preview is None
    assert len(app.session_state["region_summaries"]) == 1
    app.button(key="region_card_A1:B2").click().run()
    app.button(key="load_dataset").click().run()
    assert app.session_state["workspace"].original.shape == (1, 2)
    assert not app.exception


def test_multi_table_workbook_has_no_whole_sheet_plan_until_user_chooses(app, sayfa1_workbook, monkeypatch):
    from smart_data_processor import dashboard
    monkeypatch.setattr(dashboard, "inspect_xlsx_import", lambda *args, **kwargs: pytest.fail("Planned an unselected worksheet"))
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    assert app.selectbox(key="excel_region_mode").value == "Choose a table"
    assert app.session_state["excel_plan"] is None and app.session_state["excel_plans"] == ()
    assert not app.error
    assert not any(widget.key == "excel_header_mode" for widget in app.selectbox)
    assert not any(widget.key == "excel_range" for widget in app.text_input)
    assert not app.checkbox
    assert app.button(key="load_dataset").disabled
    assert not next(item for item in app.expander if item.label == "Advanced import options").proto.expanded
    assert [item.label for item in app.button if item.key.startswith("region_card_")][:2] == ["Select D6:H12", "Select K6:N9"]
    app.run()
    assert app.session_state["excel_plan"] is None and not app.exception


def test_selected_table_header_cells_offer_only_explicit_repair_and_keep_original(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.button(key="region_card_D6:H12").click().run()
    plan = app.session_state["excel_plan"]
    assert plan.selected_range == "D6:H12" and plan.header_row == 6
    assert app.selectbox(key="excel_header_mode").value == "First row of range"
    assert any("2 non-text header(s) at D6, H6" in item.value for item in app.warning)
    assert {widget.key for widget in app.checkbox} == {"excel_repair_headers"}
    assert not app.checkbox(key="excel_repair_headers").value
    assert app.button(key="load_dataset").disabled
    app.checkbox(key="excel_repair_headers").check().run()
    assert not app.session_state["excel_plan"].errors
    assert app.button(key="load_dataset").disabled
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    workspace = app.session_state["workspace"]
    assert workspace.original.shape == (6, 5)
    assert workspace.original.attrs["xlsx_source"]["header_row"] == 6
    assert workspace.source_bytes == sayfa1_workbook
    assert not app.exception


def test_valid_table_has_no_irrelevant_repairs_and_survives_reruns(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.button(key="region_card_K6:N9").click().run()
    assert not any(item.label == "Optional repairs for this selection" for item in app.expander)
    assert not app.error
    assert app.session_state["excel_plan"].header_row == 6
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    preview_and_apply(app)
    workspace = app.session_state["workspace"]
    preview, revision = workspace.preview, workspace.revision
    app.run()
    assert workspace.source_current and workspace.preview is preview and workspace.revision == revision
    assert app.session_state["excel_plan"].selected_range == "K6:N9"
    assert not app.exception


def test_card_and_dropdown_reset_previous_header_row_only_on_explicit_selection(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.button(key="region_card_D6:H12").click().run()
    app.selectbox(key="excel_header_mode").select("Choose worksheet row").run()
    assert app.number_input(key="excel_header_row").value == 6
    app.number_input(key="excel_header_row").set_value(8).run()
    app.run()
    assert app.session_state["excel_plan"].header_row == 8
    app.selectbox(key="excel_selected_region").select("K6:N9").run()
    assert app.selectbox(key="excel_header_mode").value == "First row of range"
    assert app.session_state["excel_plan"].selected_range == "K6:N9"
    assert app.session_state["excel_plan"].header_row == 6
    app.selectbox(key="excel_header_mode").select("Choose worksheet row").run()
    assert app.number_input(key="excel_header_row").value == 6
    app.number_input(key="excel_header_row").set_value(7).run()
    app.button(key="region_card_D6:H12").click().run()
    assert app.session_state["excel_plan"].header_row == 6
    assert app.button(key="load_dataset").disabled
    assert not app.exception


def test_explicit_whole_sheet_range_is_not_replaced_or_auto_trimmed(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.selectbox(key="excel_region_mode").select("Worksheet / custom range").run()
    plan = app.session_state["excel_plan"]
    assert plan.selected_range == "A1:P15" and plan.header_row == 1
    assert len(plan.errors) == 16
    assert any("16 missing header(s)" in item.value and "A1" in item.value and "P1" in item.value for item in app.warning)
    assert not app.checkbox(key="excel_generate_headers").value
    assert not app.checkbox(key="excel_exclude_empty").value
    app.run()
    assert app.session_state["excel_plan"].selected_range == "A1:P15"
    app.text_input(key="excel_range").set_value("D6:H12").run()
    assert app.text_input(key="excel_range").value == "D6:H12"
    assert app.session_state["excel_plan"].header_row == 6
    assert not app.exception


def test_cancel_selection_revokes_preview_and_does_not_choose_another_table(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.button(key="region_card_K6:N9").click().run()
    approve_excel_import(app)
    app.button(key="load_dataset").click().run()
    preview_and_apply(app)
    workspace = app.session_state["workspace"]
    original = workspace.original.copy(deep=True)
    app.selectbox(key="excel_region_mode").select("Choose a table").run()
    assert not workspace.source_current and workspace.preview is None and workspace.applied is None
    assert app.session_state["excel_plan"] is None and not workspace.exports
    assert_frame_equal(workspace.original, original)
    assert app.button(key="load_dataset").disabled
    app.button(key="region_card_K6:N9").click().run()
    assert app.button(key="load_dataset").disabled  # Approval must be renewed.
    assert not app.exception


def test_region_dropdown_does_not_implicitly_select_first_table(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.selectbox(key="excel_region_mode").select("Select a detected region").run()
    assert app.selectbox(key="excel_selected_region").value is None
    assert app.session_state["excel_plan"] is None
    assert app.button(key="load_dataset").disabled
    app.selectbox(key="excel_selected_region").select("K6:N9").run()
    assert app.session_state["excel_plan"].selected_range == "K6:N9"
    assert not app.exception


def test_progressive_disclosure_does_not_forget_an_explicit_custom_range(app, sayfa1_workbook):
    app.file_uploader[0].upload("sayfa1.xlsx", sayfa1_workbook).run()
    app.selectbox(key="excel_region_mode").select("Worksheet / custom range").run()
    app.text_input(key="excel_range").set_value("D6:H12").run()
    app.button(key="region_card_K6:N9").click().run()
    assert app.session_state["excel_plan"].selected_range == "K6:N9"
    assert not any(widget.key == "excel_range" for widget in app.text_input)
    app.selectbox(key="excel_region_mode").select("Worksheet / custom range").run()
    assert app.text_input(key="excel_range").value == "D6:H12"
    assert app.session_state["excel_plan"].selected_range == "D6:H12"
    assert not app.exception
