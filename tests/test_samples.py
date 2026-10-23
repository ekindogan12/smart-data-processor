"""End-to-end checks against the realistic, committed sample datasets."""

import pytest
from pandas.testing import assert_frame_equal

from smart_data_processor import load_dataset, profile_dataset, remove_duplicates


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_sales_import_profile_cleaning(sample_directory, extension):
    path = sample_directory / f"sample_sales.{extension}"
    source = path.read_bytes()
    data = load_dataset(path)
    original = data.copy(deep=True)
    profile = profile_dataset(data)
    assert (profile.row_count, profile.column_count) == (10, 9)
    assert profile.duplicate_row_count == 1
    assert profile.missing_value_count == 4
    assert data.loc[0, "order_id"] == "001001"
    cleaned = remove_duplicates(data)
    assert len(cleaned) == 9
    assert profile_dataset(cleaned).duplicate_row_count == 0
    assert_frame_equal(data, original)
    assert path.read_bytes() == source


def test_inventory_delimiter_and_missing_stock(sample_directory):
    data = load_dataset(sample_directory / "sample_inventory.csv")
    profile = profile_dataset(data)
    assert (profile.row_count, profile.column_count) == (5, 5)
    assert profile.missing_value_count == profile.duplicate_row_count == 1
    assert data.loc[0, "sku"] == "000041"


def test_customers_case_insensitive_email_matching(sample_directory):
    data = load_dataset(sample_directory / "sample_sales.xlsx", sheet_name="Customers")
    cleaned = remove_duplicates(data, subset=["email"], keep="last", case_insensitive_columns=["email"])
    assert len(cleaned) == 4
    assert cleaned["customer_id"].tolist() == ["C001", "C003", "C004", "C005"]
