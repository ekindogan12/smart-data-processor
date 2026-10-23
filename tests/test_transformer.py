"""Explicit parsing, rejected interpretations, and unchanged source values."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from smart_data_processor import (
    DataValidationError, clean_text, convert_numeric, normalize_column_names, standardize_dates,
)


@pytest.mark.parametrize(("operation", "expected"), [
    ("trim", "ana GARCÍA"), ("lower", " ana garcía "),
    ("upper", " ANA GARCÍA "), ("title", " Ana García "),
])
def test_text_operations_preserve_nontext_and_unselected_columns(operation, expected):
    data = pd.DataFrame({"name": [" ana GARCÍA ", None, 12], "other": [" X "] * 3}, dtype=object)
    original = data.copy(deep=True)
    result = clean_text(data, columns=["name"], operation=operation)
    assert result.data.loc[0, "name"] == expected
    assert result.data.loc[1, "name"] is None
    assert result.data.loc[2, "name"] == 12
    assert result.warnings[0].code == "non_text"
    assert result.warnings[0].row_position == 2
    assert result.affected_positions == (0,)
    assert_frame_equal(result.data[["other"]], data[["other"]])
    assert_frame_equal(data, original)


def test_text_string_dtype_categories_and_no_op():
    data = pd.DataFrame({"name": pd.Series(["a", None], dtype="string")})
    assert_frame_equal(clean_text(data, columns=["name"]).data, data)
    result = clean_text(data, columns=["name"], operation="upper")
    assert str(result.data["name"].dtype) == "string"
    categorical = pd.DataFrame({"name": pd.Series(["A", "a"], dtype="category")})
    result = clean_text(categorical, columns=["name"], operation="lower")
    assert result.data["name"].tolist() == ["a", "a"]
    assert result.warnings[0].code == "dtype_changed"


def test_column_normalization_is_explicit_unicode_aware_and_non_mutating():
    data = pd.DataFrame([[1, 2]], columns=[" Order ID ", "Total (€)"])
    result = normalize_column_names(data)
    assert result.data.columns.tolist() == ["order_id", "total"]
    assert result.renamed_columns == ((" Order ID ", "order_id"), ("Total (€)", "total"))
    assert result.affected_positions == ()
    assert data.columns.tolist() == [" Order ID ", "Total (€)"]


@pytest.mark.parametrize("headers", [["Name", " name "], ["!!!"], ["a-b", "a_b"]])
def test_header_collision_or_empty_name_rejected(headers):
    with pytest.raises(DataValidationError):
        normalize_column_names(pd.DataFrame([[1] * len(headers)], columns=headers))


def test_numeric_separators_exact_precision_and_invalid_values():
    data = pd.DataFrame({"amount": ["1.234,50", "9007199254740993", "0,12345678901234567890123456789", "12.34,5", "bad", None, " 1 ", True], "other": ["001"] * 8}, dtype=object)
    original = data.copy(deep=True)
    result = convert_numeric(data, columns=["amount"], decimal_separator=",", thousands_separator=".")
    assert result.data["amount"].tolist()[:3] == [Decimal("1234.50"), 9007199254740993, Decimal("0.12345678901234567890123456789")]
    assert [issue.row_position for issue in result.errors] == [3, 4, 6, 7]
    for position in [3, 4, 5, 6, 7]:
        assert result.data.iloc[position, 0] == data.iloc[position, 0]
    assert result.affected_positions == (0, 1, 2)
    assert_frame_equal(result.data[["other"]], data[["other"]])
    assert_frame_equal(data, original)


@pytest.mark.parametrize(("value", "expected"), [
    ("-12", -12), ("+1.5", Decimal("1.5")), (".25", Decimal(".25")),
    ("1e3", 1000), ("-2.5e-3", Decimal("-.0025")), ("00012", 12),
])
def test_numeric_signs_exponents_and_fractional_parts(value, expected):
    result = convert_numeric(pd.DataFrame({"n": [value]}), columns=["n"])
    assert result.data.loc[0, "n"] == expected
    assert not result.errors


@pytest.mark.parametrize("separator", [",", " ", "\u00a0", "'"])
def test_numeric_group_separators(separator):
    result = convert_numeric(pd.DataFrame({"n": [f"1{separator}234.50"]}), columns=["n"], thousands_separator=separator)
    assert result.data.loc[0, "n"] == Decimal("1234.50")


@pytest.mark.parametrize("value", ["1,23", "1,234,56", "--1", "NaN", "Infinity", "", "1e1001", "1e-1001", "1.2.3", "1,234.5,6"])
def test_invalid_numeric_values_are_retained(value):
    result = convert_numeric(pd.DataFrame({"n": [value]}), columns=["n"], thousands_separator=",")
    assert result.data.loc[0, "n"] == value
    assert result.errors[0].code == "invalid_numeric"
    assert result.affected_positions == ()


def test_native_numeric_cells_and_missing_values():
    data = pd.DataFrame({"n": [1, 2.5, Decimal("3.2"), pd.NA, float("inf")]}, dtype=object)
    result = convert_numeric(data, columns=["n"])
    assert_frame_equal(result.data, data)
    assert len(result.errors) == 1
    assert result.errors[0].row_position == 4


@pytest.mark.parametrize("parameters", [
    {"decimal_separator": ":"}, {"decimal_separator": ".", "thousands_separator": "."},
    {"thousands_separator": "xx"},
])
def test_numeric_configuration_validation(parameters):
    with pytest.raises(DataValidationError):
        convert_numeric(pd.DataFrame({"n": ["1"]}), columns=["n"], **parameters)


def test_explicit_date_order_invalid_dates_and_source_preservation():
    data = pd.DataFrame({"date": ["01/02/2026", "31/02/2026", None, "2026-03-04"], "other": [" x "] * 4}, dtype=object)
    original = data.copy(deep=True)
    result = standardize_dates(data, columns=["date"], input_formats=["%d/%m/%Y", "%Y-%m-%d"])
    assert result.data["date"].tolist() == ["2026-02-01", "31/02/2026", None, "2026-03-04"]
    assert result.errors[0].row_position == 1
    assert result.affected_positions == (0,)
    assert_frame_equal(data, original)
    assert_frame_equal(result.data[["other"]], data[["other"]])


def test_ambiguous_date_is_retained_with_warning_and_error():
    data = pd.DataFrame({"date": ["01/02/2026", "13/02/2026", "02/02/2026"]})
    result = standardize_dates(data, columns=["date"], input_formats=["%d/%m/%Y", "%m/%d/%Y"])
    assert result.data["date"].tolist() == ["01/02/2026", "2026-02-13", "2026-02-02"]
    assert result.errors[0].code == result.warnings[0].code == "ambiguous_date"
    assert result.errors[0].row_position == 0


def test_native_dates_timestamps_and_timezones_are_preserved_as_iso():
    timestamp = pd.Timestamp("2026-03-04T15:06:07.123456789+02:00")
    data = pd.DataFrame({"date": [date(2026, 3, 4), datetime(2026, 3, 4, 15, 6, tzinfo=timezone(timedelta(hours=2))), timestamp, pd.NaT]}, dtype=object)
    result = standardize_dates(data, columns=["date"], input_formats=["%Y-%m-%d"])
    assert result.data["date"].iloc[:3].tolist() == ["2026-03-04", "2026-03-04T15:06:00+02:00", "2026-03-04T15:06:07.123456789+02:00"]
    assert pd.isna(result.data.loc[3, "date"])


def test_explicit_time_format_keeps_time_and_offset():
    result = standardize_dates(pd.DataFrame({"date": ["2026-03-04 15:06:07.123456+0200"]}), columns=["date"], input_formats=["%Y-%m-%d %H:%M:%S.%f%z"])
    assert result.data.loc[0, "date"] == "2026-03-04T15:06:07.123456+02:00"


@pytest.mark.parametrize("formats", [[], "%d/%m/%Y", ["%m/%d"], ["%d/%m/%y"], ["%Y-%b-%d"], ["%Y-%m-%d%Q"], ["%Y-%m-%d%"], ["%Y-%Y-%m-%d"], [None]])
def test_date_format_validation_even_for_empty_data(formats):
    with pytest.raises(DataValidationError):
        standardize_dates(pd.DataFrame({"date": []}), columns=["date"], input_formats=formats)


@pytest.mark.parametrize("function,parameters", [
    (clean_text, {"operation": "invalid"}), (convert_numeric, {}),
    (standardize_dates, {"input_formats": ["%Y-%m-%d"]}),
])
def test_column_selection_validation(function, parameters):
    with pytest.raises(DataValidationError):
        function(pd.DataFrame({"value": [1]}), columns=["missing"], **parameters)


def test_empty_transformations_and_independent_no_op_output():
    data = pd.DataFrame({"value": pd.Series(dtype=object)})
    for result in [clean_text(data, columns=["value"]), convert_numeric(data, columns=["value"]), standardize_dates(data, columns=["value"], input_formats=["%Y-%m-%d"])]:
        assert_frame_equal(result.data, data)
        assert result.data is not data
