"""Ordered, repeatable execution and accurate audit/provenance reporting."""

from decimal import Decimal

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from smart_data_processor import (
    DataValidationError, ProcessingPipeline, ProcessingStep, load_dataset,
)


def test_full_pipeline_order_statistics_and_nonmutation():
    data = pd.DataFrame({
        " Order ID ": ["001", "001", "002", "003"],
        " Name ": [" ANA ", " ANA ", " BEN ", " CAM "],
        " Amount ": ["1,50", "1,50", None, "4,50"],
        " Date ": ["01/09/2026", "01/09/2026", "02/09/2026", "03/09/2026"],
    }, index=[7, 7, 7, 9])
    original = data.copy(deep=True)
    steps = [
        ProcessingStep("normalize_column_names"),
        ProcessingStep("clean_text", {"columns": ["name"], "operation": "trim"}),
        ProcessingStep("clean_text", {"columns": ["name"], "operation": "title"}),
        ProcessingStep("convert_numeric", {"columns": ["amount"], "decimal_separator": ","}),
        ProcessingStep("remove_duplicates", {"subset": ["order_id"]}),
        ProcessingStep("handle_missing", {"columns": ["amount"], "strategy": "mean"}),
        ProcessingStep("standardize_dates", {"columns": ["date"], "input_formats": ["%d/%m/%Y"]}),
    ]
    pipeline = ProcessingPipeline(steps)
    result = pipeline.run(data)
    assert result.data["order_id"].tolist() == ["001", "002", "003"]
    assert result.data["name"].tolist() == ["Ana", "Ben", "Cam"]
    assert result.data["amount"].tolist() == [Decimal("1.50"), 3, Decimal("4.50")]
    assert result.data["date"].tolist() == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert result.data.index.tolist() == [7, 7, 9]
    report = result.report
    assert report.status == "completed"
    assert report.before.row_count == 4 and report.after.row_count == 3
    assert report.before.missing_value_count == 1 and report.after.missing_value_count == 0
    assert report.before.duplicate_row_count == 1 and report.after.duplicate_row_count == 0
    assert report.affected_rows == 4
    assert [step.operation for step in report.steps] == [step.operation for step in steps]
    assert report.steps[0].affected_rows == 0
    assert len(report.steps[0].renamed_columns) == 4
    assert report.steps[4].affected_row_positions == (1,)
    assert report.steps[5].affected_row_positions == (2,)
    assert_frame_equal(data, original)
    assert_frame_equal(pipeline.run(data).data, result.data)
    assert pipeline.run(data).report.to_dict() == report.to_dict()
    result.data.iloc[0, 1] = "Changed"
    assert_frame_equal(data, original)


def test_errors_keep_original_values_and_stop_by_default():
    data = pd.DataFrame({"amount": ["1", "bad"], "name": [" ANA ", " BEN "]})
    result = ProcessingPipeline([
        ProcessingStep("convert_numeric", {"columns": ["amount"]}),
        ProcessingStep("clean_text", {"columns": ["name"]}),
    ]).run(data)
    assert result.data["amount"].tolist() == [1, "bad"]
    assert result.data["name"].tolist() == [" ANA ", " BEN "]
    assert result.report.status == "stopped_on_error"
    assert len(result.report.steps) == 1 and result.report.planned_steps == 2
    assert result.report.steps[0].status == "partial"
    assert result.report.errors[0].row_position == 1


def test_continue_on_error_and_original_positions_after_drop():
    data = pd.DataFrame({"key": [None, "a", "b"], "amount": ["x", "1", "bad"], "name": [" A ", " B ", " C "]}, index=[8, 8, 8])
    result = ProcessingPipeline([
        ProcessingStep("handle_missing", {"columns": ["key"], "strategy": "drop"}),
        ProcessingStep("convert_numeric", {"columns": ["amount"]}),
        ProcessingStep("clean_text", {"columns": ["name"]}),
    ], stop_on_error=False).run(data)
    assert result.report.status == "completed_with_errors"
    assert result.report.errors[0].row_position == 2
    assert result.report.steps[1].affected_row_positions == (1,)
    assert result.report.steps[2].affected_row_positions == (1, 2)
    assert result.report.affected_rows == 3
    assert result.data["name"].tolist() == ["B", "C"]


@pytest.mark.parametrize("step", [
    ProcessingStep("unknown"),
    ProcessingStep("convert_numeric", {"columns": ["missing"]}),
    ProcessingStep("clean_text", {"columns": ["name"], "unknown": True}),
    ProcessingStep("handle_missing", {"columns": ["number", "name"], "strategy": "mean"}),
    ProcessingStep("remove_duplicates", {"unknown": True}),
])
def test_failed_configuration_is_atomic_and_reported(step):
    data = pd.DataFrame({"name": ["a", None], "number": [1, None]})
    original = data.copy(deep=True)
    result = ProcessingPipeline([step]).run(data)
    assert_frame_equal(result.data, original)
    assert_frame_equal(data, original)
    assert result.report.steps[0].status == "failed"
    assert result.report.affected_rows == 0
    assert result.report.errors[0].code == "invalid_operation"


def test_configuration_snapshot_and_detached_report():
    parameters = {"columns": ["name"], "operation": "trim"}
    pipeline = ProcessingPipeline([ProcessingStep("clean_text", parameters)])
    parameters["columns"].append("missing")
    parameters["operation"] = "upper"
    data = pd.DataFrame({"name": [" ana "]})
    result = pipeline.run(data)
    assert result.data.loc[0, "name"] == "ana"
    result.report.steps[0].parameters["columns"].append("other")
    assert pipeline.run(data).data.loc[0, "name"] == "ana"


def test_empty_pipeline_returns_independent_data_and_complete_report():
    data = pd.DataFrame({"name": ["Ana"]})
    result = ProcessingPipeline([]).run(data)
    assert result.data is not data
    assert_frame_equal(result.data, data)
    assert result.report.before == result.report.after
    assert result.report.status == "completed"
    assert result.report.steps == ()


def test_step_order_and_current_column_names_are_respected():
    data = pd.DataFrame({" Amount ": ["1", None]})
    result = ProcessingPipeline([
        ProcessingStep("normalize_column_names"),
        ProcessingStep("handle_missing", {"columns": ["amount"], "strategy": "mean"}),
        ProcessingStep("convert_numeric", {"columns": ["amount"]}),
    ]).run(data)
    assert result.report.steps[1].status == "failed"
    assert result.data.loc[0, "amount"] == "1"
    assert len(result.report.steps) == 2


def test_all_null_warnings_do_not_stop_execution():
    data = pd.DataFrame({"amount": [None], "name": [" Ana "]}, dtype=object)
    result = ProcessingPipeline([
        ProcessingStep("handle_missing", {"columns": ["amount"], "strategy": "mean"}),
        ProcessingStep("clean_text", {"columns": ["name"]}),
    ]).run(data)
    assert result.report.status == "completed"
    assert result.report.warnings[0].code == "all_null"
    assert result.data.loc[0, "name"] == "Ana"


@pytest.mark.parametrize("steps,kwargs", [
    ("not steps", {}), (["step"], {}), ([ProcessingStep(1)], {}),
    ([ProcessingStep("clean_text", [])], {}),
    ([ProcessingStep("clean_text", {1: "value"})], {}), ([], {"stop_on_error": "yes"}),
])
def test_pipeline_configuration_validation(steps, kwargs):
    with pytest.raises(DataValidationError):
        ProcessingPipeline(steps, **kwargs)


def test_sample_sales_phase_two_workflow(sample_directory):
    data = load_dataset(sample_directory / "sample_sales.csv")
    original = data.copy(deep=True)
    result = ProcessingPipeline([
        ProcessingStep("clean_text", {"columns": ["customer_name"], "operation": "trim"}),
        ProcessingStep("convert_numeric", {"columns": ["quantity", "unit_price"]}),
        ProcessingStep("handle_missing", {"columns": ["quantity"], "strategy": "median"}),
        ProcessingStep("standardize_dates", {"columns": ["order_date"], "input_formats": ["%Y-%m-%d", "%d/%m/%Y"]}),
        ProcessingStep("remove_duplicates"),
    ]).run(data)
    assert result.report.status == "completed"
    assert result.report.after.row_count == 9
    assert result.report.after.missing_value_count == 3
    assert result.data.loc[8, "customer_name"] == "Priya Shah"
    assert result.data.loc[8, "order_date"] == "2026-09-05"
    assert_frame_equal(data, original)
