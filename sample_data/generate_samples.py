"""Regenerate the synthetic XLSX fixture: python sample_data/generate_samples.py.

The Sales sheet mirrors the CSV, with explicit native numeric cells. Customer
records demonstrate missing fields and case-insensitive duplicates. Running this
script explicitly overwrites sample_sales.xlsx; the processing engine never does.
"""

import csv
from pathlib import Path

from openpyxl import Workbook


def main() -> None:
    directory = Path(__file__).resolve().parent
    workbook = Workbook()
    sales = workbook.active
    sales.title = "Sales"
    with (directory / "sample_sales.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        sales.append(next(reader))
        for record in reader:
            values = [value if value else None for value in record]
            if values[6] is not None:
                values[6] = int(values[6])
            if values[7] is not None:
                values[7] = float(values[7])
            sales.append(values)
    customers = workbook.create_sheet("Customers")
    for record in [
        ["customer_id", "name", "email", "city"],
        ["C001", "Ana García", "ana@example.com", "Valencia"],
        ["C002", "Alex Morgan", "Alex@example.com", "London"],
        ["C003", "Alex Morgan", "alex@example.com", "London"],
        ["C004", "Leila Haddad", "leila@example.com", None],
        ["C005", "Noah Chen", None, "Berlin"],
    ]:
        customers.append(record)
    for sheet in workbook:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    workbook.save(directory / "sample_sales.xlsx")
    workbook.close()


if __name__ == "__main__":
    main()
