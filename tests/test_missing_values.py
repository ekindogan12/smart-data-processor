"""Missing-value strategies, dtype compatibility, and non-mutation."""

from datetime import datetime
from decimal import Decimal

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from smart_data_processor import DataValidationError, handle_missing


def test_keep_and_drop_are_independent_and_respect_selected_columns():
    data = pd.DataFrame({"a": [1, None, 3], "b": [None, "x", "y"]}, index=[7, 7, 7])
    original = data.copy(deep=True)
    kept = handle_missing(data, columns=["a"], strategy="keep")
    assert kept.data is not data
    assert_frame_equal(kept.data, data)
    dropped = handle_missing(data, columns=["a"], strategy="drop")
    assert_frame_equal(dropped.data, data.iloc[[0, 2]])
    assert dropped.affected_positions == (1,)
    assert dropped.retained_positions == (0, 2)
    assert len(handle_missing(data, columns=["a", "b"], strategy="drop").data) == 1
    assert_frame_equal(data, original)


@pytest.mark.parametrize(("strategy", "expected"), [
    ("mean", Decimal("4")), ("median", Decimal("2")), ("mode", 1),
])
def test_statistical_fills(strategy, expected):
    data = pd.DataFrame({"value": [1, 2, 9, None], "other": [None] * 4}, dtype=object)
    original = data.copy(deep=True)
    result = handle_missing(data, columns=["value"], strategy=strategy)
    assert result.data.loc[3, "value"] == expected
    assert result.affected_positions == (3,)
    assert_frame_equal(result.data[["other"]], data[["other"]])
    assert_frame_equal(data, original)
    if strategy == "mode":
        assert result.warnings[0].code == "mode_tie"


@pytest.mark.parametrize("strategy", ["mean", "median"])
def test_fractional_integer_fill_preserves_large_integer_values(strategy):
    data = pd.DataFrame({"value": pd.Series([9007199254740992, 9007199254740993, None], dtype="Int64")})
    result = handle_missing(data, columns=["value"], strategy=strategy)
    assert result.data["value"].tolist() == [9007199254740992, 9007199254740993, Decimal("9007199254740992.5")]
    assert result.warnings[0].code == "dtype_changed"


def test_constant_fill_and_nullable_types():
    data = pd.DataFrame({"count": pd.Series([1, None], dtype="Int64"), "name": pd.Series(["Ana", None], dtype="string")})
    result = handle_missing(data, columns=["count"], strategy="constant", value=2)
    assert str(result.data["count"].dtype) == "Int64"
    assert result.data["count"].tolist() == [1, 2]
    result = handle_missing(data, columns=["name"], strategy="constant", value="Unknown")
    assert result.data["name"].tolist() == ["Ana", "Unknown"]
    result.data.loc[0, "name"] = "Changed"
    assert data.loc[0, "name"] == "Ana"


def test_constant_can_extend_categories_without_mutating_original():
    data = pd.DataFrame({"region": pd.Series(["East", None], dtype="category")})
    result = handle_missing(data, columns=["region"], strategy="constant", value="Unknown")
    assert result.data["region"].tolist() == ["East", "Unknown"]
    assert data["region"].cat.categories.tolist() == ["East"]


@pytest.mark.parametrize("strategy", ["mean", "median", "mode"])
def test_all_null_object_and_numeric_columns_are_unchanged_with_warning(strategy):
    for dtype in [object, "Float64"]:
        data = pd.DataFrame({"value": pd.Series([None, None], dtype=dtype)})
        result = handle_missing(data, columns=["value"], strategy=strategy)
        assert_frame_equal(result.data, data)
        assert result.affected_positions == ()
        assert result.warnings[0].code == "all_null"


def test_all_null_object_constant_and_empty_input():
    data = pd.DataFrame({"value": [None, None]}, dtype=object)
    result = handle_missing(data, columns=["value"], strategy="constant", value="New")
    assert result.data["value"].tolist() == ["New", "New"]
    empty = data.iloc[:0]
    assert_frame_equal(handle_missing(empty, columns=["value"], strategy="mean").data, empty)


def test_mode_tie_uses_first_observation_and_skips_nulls():
    data = pd.DataFrame({"value": [None, "z", "a", "a", "z"]})
    result = handle_missing(data, columns=["value"], strategy="mode")
    assert result.data.loc[0, "value"] == "z"
    assert result.warnings[0].code == "mode_tie"


@pytest.mark.parametrize("strategy", ["mean", "median"])
@pytest.mark.parametrize("series", [
    pd.Series(["1", None]), pd.Series([True, None], dtype="boolean"),
    pd.Series([None], dtype="string"), pd.Series([datetime(2026, 1, 1), None]),
    pd.Series([1, "2", None], dtype=object),
])
def test_statistical_fill_rejects_non_numeric_columns(strategy, series):
    data = pd.DataFrame({"value": series})
    original = data.copy(deep=True)
    with pytest.raises(DataValidationError, match="numeric"):
        handle_missing(data, columns=["value"], strategy=strategy)
    assert_frame_equal(data, original)


@pytest.mark.parametrize(("series", "value"), [
    (pd.Series([1, None], dtype="Int64"), "2"),
    (pd.Series([True, None], dtype="boolean"), 1),
    (pd.Series(["a", None], dtype="string"), 2),
    (pd.Series([1, "a", None], dtype=object), "unknown"),
])
def test_constant_type_validation(series, value):
    with pytest.raises(DataValidationError, match="incompatible"):
        handle_missing(pd.DataFrame({"value": series}), columns=["value"], strategy="constant", value=value)


@pytest.mark.parametrize("value", [None, pd.NA, float("nan"), float("inf"), [], {}, complex(1, 2)])
def test_invalid_constant(value):
    with pytest.raises(DataValidationError):
        handle_missing(pd.DataFrame({"value": [None]}), columns=["value"], strategy="constant", value=value)


@pytest.mark.parametrize("parameters", [
    {"columns": []}, {"columns": ["missing"]}, {"columns": "value"},
    {"columns": ["value"], "strategy": "unknown"},
    {"columns": ["value"], "strategy": "keep", "value": 1},
])
def test_invalid_missing_configuration(parameters):
    with pytest.raises(DataValidationError):
        handle_missing(pd.DataFrame({"value": [None]}), **parameters)


def test_nonfinite_statistic_is_rejected():
    with pytest.raises(DataValidationError, match="finite"):
        handle_missing(pd.DataFrame({"value": [float("inf"), None]}), columns=["value"], strategy="mean")
