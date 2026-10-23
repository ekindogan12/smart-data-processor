# Smart Data Processor

A professional Python foundation for local CSV and Excel cleaning and automation.
**Phase 1 is implemented:** validated imports, dataset profiling, missing-value
detection, and configurable duplicate removal. There is no graphical interface yet.
The main specification is [PROJECT_PROPOSAL.md](PROJECT_PROPOSAL.md).

## Install and test

Requires Python 3.11 or newer. From the repository root on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

On macOS/Linux, use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.
`requirements.txt` installs the local package in editable mode with the test extra.
Runtime dependencies are only pandas and openpyxl; pytest is for development.
Dependency ranges and package metadata live in `pyproject.toml` to avoid duplicate
dependency declarations. The supported ranges are bounded, not a frozen lockfile.

## Use the engine

After installation, run this in Python from the repository root:

```python
from smart_data_processor import load_dataset, profile_dataset, remove_duplicates

original = load_dataset("sample_data/sample_sales.csv")
profile = profile_dataset(original)
print(profile.to_dict())

# Apply an explicit operation; original remains available unchanged.
cleaned = remove_duplicates(original, subset=["order_id"], keep="first")
print(f"Removed {len(original) - len(cleaned)} rows")

sales = load_dataset("sample_data/sample_sales.xlsx", sheet_name="Sales")
customers = load_dataset("sample_data/sample_sales.xlsx", sheet_name="Customers")
unique_customers = remove_duplicates(
    customers,
    subset=["email"],
    keep="last",
    case_insensitive_columns=["email"],
)
```

The sample sales data has 10 rows, 9 columns, 4 missing cells, and 1 exact
duplicate row. The Customers worksheet demonstrates case-insensitive email matching.
All sample records are fictional.

### Import contract

- Accepts local paths or seekable binary streams; streams need a `filename`
  argument or a `.name` attribute. The stream position is restored even on failure.
- Supports `.csv` and `.xlsx` (case-insensitive extensions). Source files are only
  opened for reading. Data stays local; the engine makes no network calls.
- Defaults to a 10 MiB input limit, configurable with `max_size_bytes`. XLSX also
  has a 100 MiB expanded archive limit (`max_uncompressed_bytes`). These byte
  limits are not a guarantee of bounded DataFrame memory usage.
- CSV detects UTF-8 (including BOM) and BOM-marked UTF-16/32. For ambiguous legacy
  encodings, explicitly pass `encoding="cp1252"`, for example. It never replaces
  undecodable bytes or guesses a potentially destructive legacy encoding.
- CSV sniffs comma, semicolon, tab, and pipe; falls back to comma if inconclusive.
  Pass `delimiter=";"` to resolve ambiguity. CSV must have a header and consistent
  record widths. Quoted delimiters and multiline fields are supported.
- CSV preserves strings, leading zeros, whitespace, and literal `NA`/`NULL`.
  **Only empty CSV fields become `pd.NA`**, including quoted empty fields. Pandas
  dtype is deliberately `object`; numeric/date inference belongs to later phases.
- XLSX selects a worksheet by name or zero-based index (`sheet_name=0` by default).
  Native Excel values, dates, and formula text are preserved as object columns.
  Formulas are never evaluated. Excel display formatting is not imported; a numeric
  cell displayed as `0012` is still the stored number `12`.
- Headers must be unique, non-blank text. They are never trimmed or renamed.
  Empty files, malformed files, missing sheets, and ragged CSV rows raise
  `FileValidationError`. Header-only tables are valid. Blank CSV records fail
  width validation instead of being silently skipped (use explicit empty fields).
  XLSX's reported worksheet range is respected, including blank rows; blank or
  merged header cells fail validation. Text streams and old `.xls` files are unsupported.

### Profiling and duplicate semantics

`profile_dataset` returns frozen dataclasses containing row/column counts, column
names and pandas dtypes, per-column missing counts and percentages, total missing
cells, and exact duplicate counts. A duplicate count means repeated rows after
the first occurrence, excluding the index. Empty tables have zero percentages.
Missing detection uses pandas `isna`; whitespace and literal strings are values.

`remove_duplicates` compares all columns unless `subset` is supplied. `keep` can
be `"first"`, `"last"`, or `False` (remove every member of a duplicate group).
`case_insensitive_columns` applies Unicode casefold only to string comparison
keys and must be contained in `subset` when supplied. It does not trim spaces
or change retained values. Missing-key matching follows pandas duplicate semantics.
The result is a separate DataFrame with original dtypes, ordering, and index labels.
These APIs target scalar spreadsheet cells, not nested mutable Python objects.
Invalid dataset/configuration arguments raise `DataValidationError`.

## Architecture

```text
app.py                         # Reserved Phase 3 entry point; no UI implementation
src/smart_data_processor/
    __init__.py                # Small public API
    file_handler.py            # Read-only imports and format-specific parsing
    validators.py              # Shared contracts and public error types
    profiler.py                # Immutable descriptive statistics
    cleaner.py                 # Explicit duplicate removal
    transformer.py             # Phase 2 placeholder
    reporter.py                # Later-phase placeholder
tests/                         # Import, profiling, cleaning, and integration tests
sample_data/                   # Synthetic CSV/XLSX examples and regeneration script
docs/architecture.md           # Decisions, tradeoffs, and future boundaries
docs/screenshots/              # Reserved for the future interface
```

The `src` layout makes tests exercise an installed package. File I/O, validation,
profiling, and cleaning have separate responsibilities and no UI dependencies.
Conservative parsing makes interpretation explicit; cleaning is a separate call.
See [architecture decisions](docs/architecture.md) for details and limitations.

## Remaining phases

- Phase 2: missing-value treatment, text normalization, validated numeric/date
  conversion, a configurable processing pipeline, and operation summaries.
- Phase 3: Streamlit upload/configuration/preview interface, CSV/XLSX exports and
  formula-injection protection at the export boundary.
- Phase 4: broader compatibility, performance, usability, and reliability refinement.
- Phase 5: publication assets, screenshots, demonstration video, and portfolio copy.

Numeric/categorical distributions and format-inconsistency diagnostics remain
future profiling enhancements. No transformations, export features, or UI are
implemented in Phase 1. A publication license has not yet been selected.
