# Synthetic sample data

All datasets in this directory are fictional examples for demonstrations and
tests. Names are invented, email addresses in older samples use example.com, and
no file represents a customer engagement or measured business results.

| File | Purpose |
| --- | --- |
| `portfolio_sales_raw.csv` | Main portfolio demo: 12 rows, 8 columns, 3 missing cells, 2 exact duplicate rows, inconsistent casing/whitespace and ISO/day-first dates. |
| `portfolio_sales_expected.csv` | Actual cleaned CSV from the documented seven-step demo; 10 rows, 8 columns, no missing cells or exact duplicates. |
| `sample_sales.csv`, `sample_sales.xlsx` | Existing sales/import examples; the workbook also has a Customers worksheet. |
| `sample_inventory.csv` | Semicolon-delimited inventory with missing stock and a duplicate. |
| `sayfa1_like.xlsx` | Synthetic sparse worksheet with separate regions, blank margins, problematic headers and formulas. This is not the user-supplied regression workbook. |

For the main demo, `/` dates explicitly mean **day/month/year**. Quantity and price
are strings on CSV import. Median fills and the `unknown` region value are deliberate
demo choices, not claims that missing real-world values can be recovered. Missing
price in order 000108 becomes 14.50; missing quantity in order 000106 becomes 2.
Leading zeros in order IDs stay intact. Product spelling/case is not changed.

Run `python scripts/run_portfolio_demo.py` from the repository root after installing
requirements. This reads the raw fixture without modifying it and writes complete
CSV, XLSX, JSON and export diagnostics under ignored `.demo-output/`. Re-running
overwrites only the named generated artifacts in the chosen output directory.
The JSON step configuration is in `docs/portfolio/demo_steps.json`.

Existing sample generators remain available:

```text
python sample_data/generate_samples.py
python sample_data/generate_import_sample.py
```

Those generators explicitly replace their respective synthetic XLSX samples.
The raw portfolio CSV is hand-authored; do not use private data for public images.
