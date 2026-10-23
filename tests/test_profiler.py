"""Exact profile statistics and read-only behavior."""

from dataclasses import FrozenInstanceError
import json

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from smart_data_processor import DataValidationError, profile_dataset


def test_profile_counts_types_missing_values_duplicates_without_mutation():
    data = pd.DataFrame({
        "id": pd.Series([1, 2, 2, 3], dtype="Int64"),
        "name": pd.Series(["Ana", "Ben", "Ben", pd.NA], dtype="string"),
        "amount": [10.5, None, None, 20.0],
    })
    original = data.copy(deep=True)
    profile = profile_dataset(data)
    assert (profile.row_count, profile.column_count) == (4, 3)
    assert profile.duplicate_row_count == 1
    assert profile.missing_value_count == 3
    assert [column.name for column in profile.columns] == ["id", "name", "amount"]
    assert [column.dtype for column in profile.columns] == ["Int64", "string", "float64"]
    assert [column.missing_count for column in profile.columns] == [0, 1, 2]
    assert [column.missing_percentage for column in profile.columns] == [0.0, 25.0, 50.0]
    assert_frame_equal(data, original)
    assert json.loads(json.dumps(profile.to_dict()))["row_count"] == 4
    with pytest.raises(FrozenInstanceError):
        profile.row_count = 9
    detached = profile.to_dict()
    detached["columns"][0]["name"] = "changed"
    assert profile.columns[0].name == "id"


def test_missing_markers_and_literal_text_are_distinct():
    data = pd.DataFrame({"value": [None, float("nan"), pd.NaT, pd.NA, "", " ", "NA"]})
    profile = profile_dataset(data)
    assert profile.missing_value_count == 4
    assert profile.columns[0].missing_percentage == pytest.approx(4 / 7 * 100)


def test_empty_dataframe_with_headers():
    profile = profile_dataset(pd.DataFrame({"id": pd.Series(dtype="Int64")}))
    assert profile.row_count == profile.duplicate_row_count == profile.missing_value_count == 0
    assert profile.columns[0].missing_percentage == 0.0
    assert profile.columns[0].dtype == "Int64"


def test_duplicate_counts_exclude_index_and_count_only_excess_rows():
    profile = profile_dataset(pd.DataFrame({"id": [1, 1, 1]}, index=[10, 20, 30]))
    assert profile.duplicate_row_count == 2


@pytest.mark.parametrize("data", [None, [], pd.DataFrame(), pd.DataFrame([[1, 2]], columns=["id", "id"]), pd.DataFrame({" ": [1]})])
def test_invalid_datasets(data):
    with pytest.raises(DataValidationError):
        profile_dataset(data)
