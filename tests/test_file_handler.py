"""Import behavior, invalid inputs, and source preservation."""

from datetime import datetime
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from smart_data_processor import FileValidationError, load_dataset


def csv_stream(text, **options):
    return load_dataset(BytesIO(text.encode("utf-8")), filename="input.csv", **options)


def test_csv_preserves_values_and_original_file(tmp_path):
    path = tmp_path / "input.CSV"
    payload = b'id,code,name,empty\n0012,NA, Ana ,\n0013,NULL,Ben,""\n'
    path.write_bytes(payload)
    result = load_dataset(path)
    assert result["id"].tolist() == ["0012", "0013"]
    assert result["code"].tolist() == ["NA", "NULL"]
    assert result["name"].tolist() == [" Ana ", "Ben"]
    assert result["empty"].isna().all()
    assert path.read_bytes() == payload


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-32"])
def test_detects_unicode_encodings(encoding):
    payload = "name,city\nAna García,Málaga\n".encode(encoding)
    result = load_dataset(BytesIO(payload), filename="input.csv")
    assert result.iloc[0].tolist() == ["Ana García", "Málaga"]


def test_legacy_encoding_requires_explicit_choice():
    stream = BytesIO("name;city\nAna;Málaga\n".encode("cp1252"))
    with pytest.raises(FileValidationError, match="encoding"):
        load_dataset(stream, filename="input.csv")
    result = load_dataset(stream, filename="input.csv", encoding="cp1252")
    assert result.loc[0, "city"] == "Málaga"


@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_common_delimiter_detection(delimiter):
    result = csv_stream(f"id{delimiter}name\n01{delimiter}Ana\n02{delimiter}Ben\n")
    assert result.columns.tolist() == ["id", "name"]
    assert result["id"].tolist() == ["01", "02"]


def test_custom_delimiter_and_quoted_multiline_fields():
    result = csv_stream('id:name\n01:"Ana: García\nSales"\n', delimiter=":")
    assert result.loc[0, "name"] == "Ana: García\nSales"


def test_single_column_and_header_only_tables():
    assert csv_stream("name\nAna\nBen\n")["name"].tolist() == ["Ana", "Ben"]
    assert csv_stream("id,name\n").shape == (0, 2)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("\n", "at least one column"),
        ("id,id\n1,2\n", "unique"),
        ("id, \n1,2\n", "non-empty"),
        ("id,name\n1,Ana,extra\n", "fields"),
        ("id,name\n1\n", "fields"),
        ("id,name\n\n", "fields"),
        ('id,name\n1,"unclosed\n', "Malformed CSV"),
        ("id,name\n1,\x00\n", "NUL"),
    ],
)
def test_rejects_invalid_csv(text, message):
    with pytest.raises(FileValidationError, match=message):
        csv_stream(text)


@pytest.mark.parametrize("delimiter", ["", "::", "\n", "\x00", '"', 1])
def test_rejects_invalid_delimiter(delimiter):
    with pytest.raises(FileValidationError, match="delimiter"):
        csv_stream("id\n1\n", delimiter=delimiter)


def test_unknown_encoding():
    with pytest.raises(FileValidationError, match="decode"):
        csv_stream("id\n1\n", encoding="not-an-encoding")


@pytest.mark.parametrize("filename", ["input.xls", "input.json", "input", "input.csv.exe"])
def test_unsupported_extensions(filename):
    with pytest.raises(FileValidationError, match="extension"):
        load_dataset(BytesIO(b"id\n1\n"), filename=filename)


def test_missing_file_and_directory(tmp_path):
    with pytest.raises(FileValidationError, match="Cannot read"):
        load_dataset(tmp_path / "missing.csv")
    directory = tmp_path / "directory.csv"
    directory.mkdir()
    with pytest.raises(FileValidationError, match="Cannot read"):
        load_dataset(directory)


def test_stream_position_and_content_preserved_on_success_and_failure():
    stream = BytesIO(b"id,name\n1,Ana\n")
    original = stream.getvalue()
    stream.seek(4)
    assert load_dataset(stream, filename="input.csv").shape == (1, 2)
    assert stream.tell() == 4
    with pytest.raises(FileValidationError, match="size limit"):
        load_dataset(stream, filename="input.csv", max_size_bytes=2)
    assert stream.tell() == 4
    assert stream.getvalue() == original
    assert not stream.closed


def test_exact_size_limit_is_accepted():
    payload = b"id\n1\n"
    assert load_dataset(BytesIO(payload), filename="input.csv", max_size_bytes=len(payload)).shape == (1, 1)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "10"])
@pytest.mark.parametrize("option", ["max_size_bytes", "max_uncompressed_bytes"])
def test_invalid_size_configuration(limit, option):
    with pytest.raises(FileValidationError, match="positive integer"):
        csv_stream("id\n1\n", **{option: limit})


def test_text_and_unnamed_streams_rejected():
    with pytest.raises(FileValidationError, match="bytes"):
        load_dataset(StringIO("id\n1\n"), filename="input.csv")
    with pytest.raises(FileValidationError, match="filename"):
        load_dataset(BytesIO(b"id\n1\n"))


def test_named_binary_stream():
    stream = BytesIO(b"id\n1\n")
    stream.name = "upload.csv"
    assert load_dataset(stream).loc[0, "id"] == "1"


def test_nonseekable_stream_rejected():
    class Nonseekable(BytesIO):
        def seek(self, *args):
            raise OSError("Not seekable")
    with pytest.raises(FileValidationError, match="seekable"):
        load_dataset(Nonseekable(b"id\n1\n"), filename="input.csv")


def test_xlsx_native_values_formulas_blanks_and_source_preserved(workbook_bytes):
    timestamp = datetime(2026, 9, 1)
    stream = workbook_bytes({"Sales": [
        ["id", "quantity", "date", "formula", "active"],
        ["001", 2, timestamp, "=B2*3", True],
        ["002", None, None, None, False],
    ]})
    payload = stream.getvalue()
    result = load_dataset(stream, filename="sales.XLSX")
    assert result.loc[0, "id"] == "001"
    assert type(result.loc[0, "quantity"]) is int
    assert result.loc[0, "date"] == timestamp
    assert result.loc[0, "formula"] == "=B2*3"
    assert result.loc[0, "active"] is True
    assert pd.isna(result.loc[1, "quantity"])
    assert stream.getvalue() == payload
    assert stream.tell() == 0


@pytest.mark.parametrize("selector", ["Customers", 1])
def test_worksheet_selection(workbook_bytes, selector):
    stream = workbook_bytes({"Sales": [["id"], [1]], "Customers": [["name"], ["Ana"]]})
    assert load_dataset(stream, filename="input.xlsx", sheet_name=selector).loc[0, "name"] == "Ana"


@pytest.mark.parametrize("selector", ["missing", -1, 2, True, None, 1.5])
def test_invalid_worksheet_selection(workbook_bytes, selector):
    stream = workbook_bytes({"Sales": [["id"], [1]]})
    with pytest.raises(FileValidationError, match="worksheet|Worksheet|sheet_name"):
        load_dataset(stream, filename="input.xlsx", sheet_name=selector)


@pytest.mark.parametrize("records", [[], [["id", "id"], [1, 2]], [["id", None], [1, 2]], [[123], [1]]])
def test_invalid_xlsx_headers(workbook_bytes, records):
    with pytest.raises(FileValidationError):
        load_dataset(workbook_bytes({"Sheet": records}), filename="input.xlsx")


def test_header_only_xlsx_and_internal_blank_rows(workbook_bytes):
    stream = workbook_bytes({"Empty": [["id"]], "Gaps": [["id"], [1], [None], [2]]})
    assert load_dataset(stream, filename="input.xlsx").shape == (0, 1)
    result = load_dataset(stream, filename="input.xlsx", sheet_name="Gaps")
    assert len(result) == 3
    assert pd.isna(result.iloc[1, 0])


@pytest.mark.parametrize("payload", [b"not a workbook", b"PK\x03\x04broken"])
def test_corrupt_xlsx(payload):
    with pytest.raises(FileValidationError, match="Cannot read XLSX"):
        load_dataset(BytesIO(payload), filename="input.xlsx")


def test_zip_that_is_not_xlsx():
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("notes.txt", "not an Excel workbook")
    with pytest.raises(FileValidationError, match="Cannot read XLSX"):
        load_dataset(stream, filename="input.xlsx")


def test_xlsx_uncompressed_limit(workbook_bytes):
    stream = workbook_bytes({"Sales": [["id"], [1]]})
    with pytest.raises(FileValidationError, match="uncompressed"):
        load_dataset(stream, filename="input.xlsx", max_uncompressed_bytes=1)


def test_format_specific_options_are_not_ignored(workbook_bytes):
    with pytest.raises(FileValidationError, match="only supported for XLSX"):
        csv_stream("id\n1\n", sheet_name="Sales")
    with pytest.raises(FileValidationError, match="only supported for CSV"):
        load_dataset(workbook_bytes({"Sales": [["id"]]}), filename="input.xlsx", delimiter=";")
