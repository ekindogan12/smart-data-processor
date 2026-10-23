"""Shared in-memory and committed sample fixtures."""

from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
import pytest


@pytest.fixture
def sample_directory() -> Path:
    return Path(__file__).resolve().parents[1] / "sample_data"


@pytest.fixture
def workbook_bytes():
    """Build a fresh binary workbook with named worksheets for each test."""
    def build(sheets):
        workbook = Workbook()
        workbook.remove(workbook.active)
        for name, records in sheets.items():
            sheet = workbook.create_sheet(name)
            for record in records:
                sheet.append(record)
        stream = BytesIO()
        workbook.save(stream)
        workbook.close()
        stream.seek(0)
        return stream
    return build
