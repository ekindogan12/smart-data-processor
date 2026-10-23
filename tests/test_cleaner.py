"""Duplicate configurations, stable ordering, and independent output data."""

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from smart_data_processor import DataValidationError, remove_duplicates


@pytest.mark.parametrize(("keep", "positions"), [("first", [0, 1, 3]), ("last", [2, 3, 4]), (False, [3])])
def test_exact_duplicates_keep_options(keep, positions):
    data = pd.DataFrame({"id": [1, 2, 1, 3, 2], "name": ["Ana", "Ben", "Ana", "Cam", "Ben"]})
    original = data.copy(deep=True)
    result = remove_duplicates(data, keep=keep)
    assert_frame_equal(result, data.iloc[positions])
    assert_frame_equal(data, original)
    result.iloc[0, 1] = "Changed"
    assert_frame_equal(data, original)


def test_subset_retains_unselected_values_and_duplicate_indices():
    data = pd.DataFrame({"id": [1, 1, 2], "value": ["old", "new", "other"]}, index=[7, 7, 7])
    assert_frame_equal(remove_duplicates(data, subset=["id"], keep="last"), data.iloc[[1, 2]])


def test_multiple_key_columns():
    data = pd.DataFrame({"id": [1, 1, 1], "region": ["East", "West", "East"], "amount": [2, 3, 4]})
    assert_frame_equal(remove_duplicates(data, subset=["id", "region"]), data.iloc[:2])


def test_casefold_is_opt_in_and_preserves_original_text():
    data = pd.DataFrame({"name": ["Straße", "STRASSE", "strasse", " strasse"], "note": [1, 2, 3, 4]})
    original = data.copy(deep=True)
    assert len(remove_duplicates(data, subset=["name"])) == 4
    result = remove_duplicates(data, subset=["name"], case_insensitive_columns=["name"])
    assert_frame_equal(result, data.iloc[[0, 3]])
    assert_frame_equal(data, original)


def test_casefold_does_not_convert_numbers_to_text():
    data = pd.DataFrame({"key": [1, "1", "A", "a", None, None]})
    result = remove_duplicates(data, case_insensitive_columns=["key"])
    assert_frame_equal(result, data.iloc[[0, 1, 2, 4]])


def test_casefold_only_affects_selected_columns():
    data = pd.DataFrame({"name": ["ANA", "ana", "ana"], "region": ["East", "east", "East"]})
    assert_frame_equal(remove_duplicates(data, case_insensitive_columns=["name"]), data.iloc[[0, 1]])


def test_missing_keys_and_extension_dtypes():
    data = pd.DataFrame({"id": pd.Series([1, 1, None, None], dtype="Int64"), "group": pd.Series(["A"] * 4, dtype="category")})
    assert_frame_equal(remove_duplicates(data), data.iloc[[0, 2]])


def test_no_duplicates_and_empty_input_still_return_new_frames():
    for data in [pd.DataFrame({"id": [1, 2]}), pd.DataFrame({"id": pd.Series(dtype="Int64")})]:
        result = remove_duplicates(data)
        assert result is not data
        assert_frame_equal(result, data)


@pytest.mark.parametrize("options", [
    {"subset": []}, {"subset": "id"}, {"subset": ["missing"]},
    {"subset": ["id", "id"]}, {"subset": [1]}, {"keep": True},
    {"keep": 0}, {"keep": None}, {"keep": "all"}, {"keep": []},
    {"case_insensitive_columns": []}, {"case_insensitive_columns": "name"},
    {"subset": ["id"], "case_insensitive_columns": ["name"]},
])
def test_invalid_options_fail_without_modification(options):
    data = pd.DataFrame({"id": [1, 1], "name": ["Ana", "ana"]})
    original = data.copy(deep=True)
    with pytest.raises(DataValidationError):
        remove_duplicates(data, **options)
    assert_frame_equal(data, original)


def test_invalid_input():
    with pytest.raises(DataValidationError, match="DataFrame"):
        remove_duplicates([1, 2])
