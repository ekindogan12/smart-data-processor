# Smart Data Processor

A professional Python foundation for local CSV and Excel cleaning and automation.
**Phases 1 and 2 are implemented:** validated imports, profiling, configurable
cleaning and transformations, an ordered pipeline, reports, and safe CSV/XLSX
exports. There is no graphical interface yet.
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
  dtype is deliberately `object`; numeric/date conversion is an explicit Phase 2 step.
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

## Clean and transform with a pipeline

Steps execute **exactly in the listed order**, referencing the column names that
exist at that point. There is no implicit preprocessing. Trim before parsing
numbers; convert numeric strings before mean/median. Deduplicate before computing
statistics if repeated records should not contribute to them.

```python
from smart_data_processor import (
    ProcessingPipeline, ProcessingStep, load_dataset,
    export_csv, export_xlsx, export_report,
)

original = load_dataset("sample_data/sample_sales.csv")
pipeline = ProcessingPipeline([
    ProcessingStep("clean_text", {
        "columns": ["customer_name"], "operation": "trim",
    }),
    ProcessingStep("convert_numeric", {
        "columns": ["quantity", "unit_price"],
        "decimal_separator": ".", "thousands_separator": None,
    }),
    ProcessingStep("remove_duplicates"),
    ProcessingStep("handle_missing", {
        "columns": ["quantity"], "strategy": "median",
    }),
    ProcessingStep("standardize_dates", {
        "columns": ["order_date"],
        "input_formats": ["%Y-%m-%d", "%d/%m/%Y"],
    }),
])
result = pipeline.run(original)
print(result.report.status)
print(result.report.to_dict())

# Inspect diagnostics before choosing to export partially processed data.
if not result.report.errors:
    csv_artifact = export_csv(result.data)
    xlsx_artifact = export_xlsx(result.data, sheet_name="Sales")
    report_bytes = export_report(result.report)
    print(csv_artifact.warnings, xlsx_artifact.warnings)
    # Bytes can be downloaded or saved to an explicitly chosen NEW path:
    # with open("cleaned_sales.csv", "xb") as handle:
    #     handle.write(csv_artifact.content)
```

The pipeline copies configuration at construction and can be reused across runs.
Parameters are the same as the standalone functions. JSON step definitions can
be loaded with `ProcessingPipeline([ProcessingStep(**item) for item in definitions])`.

| Operation | Supported parameters and behavior |
|---|---|
| `handle_missing` | Required `columns`; `strategy="keep"`, `"drop"`, `"constant"`, `"mean"`, `"median"`, or `"mode"`; `value` only for a constant fill. Drop removes rows missing **any** selected value. |
| `clean_text` | Required `columns`; `operation="trim"`, `"lower"`, `"upper"`, or `"title"`. Combine operations as consecutive steps. |
| `normalize_column_names` | Optional step with no parameters. Unicode NFKC/casefold snake_case names; empty names or collisions fail the step. |
| `convert_numeric` | Required `columns`; `decimal_separator="."` or `","`; optional `thousands_separator` of `.`, `,`, space, nonbreaking space, or apostrophe. Separators must differ. |
| `standardize_dates` | Required `columns` and a non-empty list of explicit `input_formats`; outputs ISO 8601 text. |
| `remove_duplicates` | Existing Phase 1 `subset`, `keep`, and `case_insensitive_columns` options. |

New standalone operations return `OperationResult` with `.data`,
`.affected_positions`, `.warnings`, and `.errors`. For example:

```python
from smart_data_processor import handle_missing, convert_numeric

converted = convert_numeric(original, columns=["quantity"])
if not converted.errors:
    filled = handle_missing(
        converted.data, columns=["quantity"], strategy="constant", value=1,
    )
```

The existing standalone `remove_duplicates` still returns a DataFrame; its
pipeline adapter adds audit information without changing that API.

### Missing values and text

Missing detection uses pandas `isna`. Existing `""`, whitespace, `"NA"`, and
`"NULL"` are ordinary strings; trimming to `""` does not automatically create a null.
Text operations preserve nulls and leave non-text cells unchanged with warnings.
Column normalization replaces runs of punctuation/whitespace with underscores and
removes leading/trailing underscores; later steps must use the new names.

Mean/median accept actual numbers, including object columns containing native
numbers or `Decimal`, never numeric strings or booleans. Constant fills require
a non-missing scalar compatible with the column's text/numeric/boolean/date type.
Mixed-type columns reject constant fills. Compatible categorical constants can
extend categories on the returned data only. Fractional fills may use object dtype
to preserve existing integers exactly; dtype changes produce warnings.

All-null object/numeric columns remain unchanged with warnings for mean/median.
Mode does the same for any all-null column. Typed text/date/boolean columns still
reject mean/median when all-null. An untyped all-null object column accepts any
supported constant. Mode ignores nulls and resolves ties by first occurrence,
with a warning. Unsupported strategies and incompatible fills fail explicitly.

### Numeric and date conversion

Numeric parsing supports signs, scientific notation, strict three-digit grouping,
and the configured decimal separator. Trim surrounding whitespace explicitly.
Malformed groups, currency symbols, non-finite values, and booleans produce
per-cell errors. Adjusted decimal exponents outside -1000..1000 are rejected.
Successful strings become exact Python `int` or `Decimal` values in object
columns. Native finite numbers, missing cells, and invalid original values are
preserved. There is no coercion of invalid values into nulls. Decimal means use
at least 28 significant digits plus input precision; recurring fractions are
rounded within that decimal context.

Date formats require `%Y`, `%m`, `%d`; optional directives are `%H`, `%M`, `%S`,
`%f`, `%z`, and literal `%%`. Locale-dependent names and two-digit years are
unsupported. Every supplied format is tried. If `%d/%m/%Y` and `%m/%d/%Y` give
different interpretations of `01/02/2026`, the original remains with an ambiguity
warning **and** an error. A single explicit format establishes the intended order.
Invalid dates and unmatched values remain unchanged with errors. Native dates
and datetimes become ISO text, retaining times and timezone offsets; no timezone
is invented. String fractional seconds support up to six digits; native pandas
timestamps retain their available precision.

### Reports and error policy

By default, execution stops after a step reports errors. Earlier successful
steps and valid cells from partial conversions remain applied; invalid cells are
retained. A configuration failure changes nothing in that step. This is stepwise
processing, not a transaction over the whole pipeline. Explicitly set
`stop_on_error=False` to continue. Warnings alone do not stop execution.
Standalone configuration failures raise `DataValidationError`; the pipeline
captures them as failed-step diagnostics.

Reports contain before/after profiles, per-step dimensions and parameters, statuses,
affected rows, renamed columns, warnings, and errors. Overall status is `completed`,
`completed_with_errors`, or `stopped_on_error`; `planned_steps` identifies skipped
work. Step statuses are `applied`, `partial` (conversion errors, possibly no valid
changes), or `failed` (configuration error).

Pipeline row positions are zero-based positions in the **original input**, even
after deletions or with repeated index labels. Standalone positions refer to that
operation's input. Changed/removed rows count once per step and once overall;
header-only changes count zero rows and have separate rename metadata.
Diagnostics identify columns/positions without copying cell contents.

`export_report` returns UTF-8 JSON with `schema_version=1`. Dates/Decimals in
parameters become strings, missing markers become null, and non-finite numeric
configuration values become strings so failed-step reports can serialize.
Unsupported arbitrary Python parameter objects are rejected.

### Safe spreadsheet exports

`export_csv` and `export_xlsx` return `ExportResult` with `.content` bytes,
`.media_type`, `.protected_cell_count`, and `.warnings`. They never write paths
or mutate input. The index is excluded; dates use ISO text and missing cells are
empty. Empty strings and missing cells may be indistinguishable after roundtrips.

- CSV uses UTF-8 and quotes every field. Formula-like text beginning with `=`,
  `+`, `-`, `@` (including whitespace/control-prefixed and fullwidth variants)
  receives an apostrophe. Headers are protected too. Native negative numbers
  remain numeric. The changed export representation is reported. CSV cannot
  control other spreadsheet type inference; prefer XLSX for text identifiers.
- XLSX stores **all text as explicit string cells**, including imported formulas.
  No executable formulas are emitted. Decimals and integers longer than 15 digits
  are stored as text with precision warnings. Standard floats retain spreadsheet
  floating-point limits. Invalid sheet names, Excel dimension limits, oversized
  strings, and illegal XML characters are rejected instead of silently removed.

Protection is mandatory. Export diagnostics belong to the returned artifact;
they do not alter the earlier processing report. Re-importing protected CSV
intentionally retains its added apostrophes.

## Architecture

```text
app.py                         # Reserved Phase 3 entry point; no UI implementation
src/smart_data_processor/
    __init__.py                # Small public API
    file_handler.py            # Read-only imports and format-specific parsing
    validators.py              # Shared contracts and public error types
    profiler.py                # Immutable descriptive statistics
    cleaner.py                 # Duplicate and missing-value handling
    transformer.py             # Text, header, numeric, and date transformations
    models.py                  # Operation results and diagnostics
    pipeline.py                # Ordered execution and original-row provenance
    reporter.py                # Reports and safe CSV/XLSX/JSON exports
tests/                         # Unit, export-security, and integration tests
sample_data/                   # Synthetic CSV/XLSX examples and regeneration script
docs/architecture.md           # Decisions, tradeoffs, and future boundaries
docs/screenshots/              # Reserved for the future interface
```

The `src` layout makes tests exercise an installed package. File I/O, validation,
profiling, and cleaning have separate responsibilities and no UI dependencies.
Conservative parsing makes interpretation explicit; cleaning is a separate call.
See [architecture decisions](docs/architecture.md) for details and limitations.

## Remaining phases

- Phase 3: Streamlit upload/configuration/preview interface, operation confirmation,
  visible diagnostics, and download controls wired to the existing export functions.
- Phase 4: broader compatibility, performance, usability, and reliability refinement.
- Phase 5: publication assets, screenshots, demonstration video, and portfolio copy.

Numeric/categorical distributions and format-inconsistency diagnostics remain
future profiling enhancements. The UI is not implemented. Exports were included
in Phase 2 as explicitly requested, ahead of the original interface milestone.
A publication license has not yet been selected.
