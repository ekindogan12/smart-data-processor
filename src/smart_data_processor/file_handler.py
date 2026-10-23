"""Validated, read-only CSV/XLSX imports with conservative value handling."""

import codecs
import csv
from io import BytesIO, StringIO
from os import PathLike
from pathlib import Path
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from xml.etree.ElementTree import ParseError

from .validators import DataValidationError, FileValidationError, validate_headers

DEFAULT_MAX_SIZE_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024


def load_dataset(
    source: str | PathLike[str] | BinaryIO,
    *,
    filename: str | None = None,
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
    encoding: str | None = None,
    delimiter: str | None = None,
    sheet_name: str | int = 0,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> pd.DataFrame:
    """Load a local path or seekable binary stream without changing the source.

    Streams require ``filename`` (or a ``name`` attribute) and their position is
    restored. CSV fields remain strings; only empty fields become ``pd.NA``.
    UTF-8/BOM and BOM-marked UTF-16/32 are detected; ambiguous legacy encodings
    require an explicit override. Delimiters are sniffed from comma, semicolon,
    tab, and pipe. XLSX preserves formulas and native cell values, without
    evaluating formulas. The first worksheet is selected by default.

    Header-only datasets are valid; empty files, ragged rows, and duplicate or
    blank headers are rejected. Limits apply to input bytes and XLSX expanded
    archive bytes. All failures in input validation raise FileValidationError.
    """
    for label, value in (
        ("max_size_bytes", max_size_bytes),
        ("max_uncompressed_bytes", max_uncompressed_bytes),
    ):
        if type(value) is not int or value <= 0:
            raise FileValidationError(f"{label} must be a positive integer.")

    is_path = isinstance(source, (str, PathLike))
    name = str(source) if is_path else filename or getattr(source, "name", "")
    if not isinstance(name, str) or Path(name).suffix.lower() not in {".csv", ".xlsx"}:
        raise FileValidationError("Provide a filename with a .csv or .xlsx extension.")
    suffix = Path(name).suffix.lower()
    if suffix == ".csv" and (type(sheet_name) is not int or sheet_name != 0):
        raise FileValidationError("sheet_name is only supported for XLSX files.")
    if suffix == ".xlsx" and (encoding is not None or delimiter is not None):
        raise FileValidationError("encoding and delimiter are only supported for CSV files.")

    try:
        if is_path:
            with Path(source).open("rb") as handle:
                payload = handle.read(max_size_bytes + 1)
        else:
            position = source.tell()
            try:
                source.seek(0)
                payload = source.read(max_size_bytes + 1)
            finally:
                source.seek(position)
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        raise FileValidationError(
            "Cannot read input; provide a readable file or seekable binary stream."
        ) from exc
    if not isinstance(payload, bytes):
        raise FileValidationError("Input streams must return bytes, not text.")
    if len(payload) > max_size_bytes:
        raise FileValidationError(f"Input exceeds the {max_size_bytes}-byte size limit.")
    if not payload:
        raise FileValidationError("The input file is empty.")

    try:
        if suffix == ".csv":
            return _load_csv(payload, encoding, delimiter)
        return _load_xlsx(payload, sheet_name, max_uncompressed_bytes)
    except DataValidationError as exc:
        raise FileValidationError(str(exc)) from exc


def _decode_csv(payload: bytes, encoding: str | None) -> str:
    if encoding is None:
        if payload.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
            encoding = "utf-32"
        elif payload.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            encoding = "utf-16"
        else:
            encoding = "utf-8-sig"
    try:
        text = payload.decode(encoding)
    except (UnicodeError, LookupError, TypeError) as exc:
        raise FileValidationError(
            "Cannot decode CSV. Supply its encoding explicitly, e.g. encoding='cp1252'."
        ) from exc
    if "\x00" in text:
        raise FileValidationError("CSV contains NUL characters; check the file and encoding.")
    return text


def _load_csv(payload: bytes, encoding: str | None, delimiter: str | None) -> pd.DataFrame:
    text = _decode_csv(payload, encoding)
    if delimiter is not None and (
        not isinstance(delimiter, str)
        or len(delimiter) != 1
        or delimiter in '\r\n\x00"'
    ):
        raise FileValidationError("delimiter must be one character other than newline, NUL, or quote.")
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
        except csv.Error:
            # Comma is the documented fallback, including single-column inputs.
            delimiter = ","
    try:
        reader = csv.reader(StringIO(text, newline=""), delimiter=delimiter, strict=True)
        headers = next(reader, [])
        validate_headers(headers)
        rows = []
        for row in reader:
            if len(row) != len(headers):
                raise FileValidationError(
                    f"CSV record ending at line {reader.line_num} has {len(row)} fields; "
                    f"expected {len(headers)}. Check the delimiter or malformed rows."
                )
            rows.append([pd.NA if value == "" else value for value in row])
    except csv.Error as exc:
        raise FileValidationError(f"Malformed CSV: {exc}.") from exc
    return pd.DataFrame(rows, columns=headers, dtype=object)


def _load_xlsx(payload: bytes, sheet_name: str | int, max_uncompressed_bytes: int) -> pd.DataFrame:
    if not isinstance(sheet_name, str) and type(sheet_name) is not int:
        raise FileValidationError("sheet_name must be a worksheet name or zero-based index.")
    workbook = None
    try:
        with ZipFile(BytesIO(payload)) as archive:
            if sum(info.file_size for info in archive.infolist()) > max_uncompressed_bytes:
                raise FileValidationError("XLSX exceeds the uncompressed archive size limit.")
        workbook = load_workbook(BytesIO(payload), read_only=True, data_only=False)
        names = workbook.sheetnames
        if isinstance(sheet_name, str):
            if sheet_name not in names:
                raise FileValidationError(f"Unknown worksheet {sheet_name!r}. Available: {names}.")
            worksheet = workbook[sheet_name]
        else:
            if not 0 <= sheet_name < len(names):
                raise FileValidationError(f"Worksheet index out of range. Available: {names}.")
            worksheet = workbook[names[sheet_name]]
        records = worksheet.iter_rows(values_only=True)
        headers = list(next(records, ()))
        validate_headers(headers)
        # Object dtype avoids coercing integers with blanks into floats, for example.
        return pd.DataFrame(list(records), columns=headers, dtype=object)
    except FileValidationError:
        raise
    except (BadZipFile, InvalidFileException, ParseError, KeyError, OSError, ValueError, TypeError, EOFError) as exc:
        raise FileValidationError(f"Cannot read XLSX workbook: {exc}.") from exc
    finally:
        if workbook is not None:
            workbook.close()
