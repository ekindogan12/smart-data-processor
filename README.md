# Smart Data Processor

A professional Python foundation for local CSV and Excel cleaning and automation.
**Phases 1–4 are implemented:** a local Streamlit dashboard around validated
imports, profiling, configurable cleaning, an ordered pipeline, structured reports,
and safe CSV/XLSX exports. Preview every workflow before explicitly applying it.
The main specification is [PROJECT_PROPOSAL.md](PROJECT_PROPOSAL.md).

## Install, launch, and test

Requires Python 3.11 or newer. From the repository root on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **http://127.0.0.1:8501** in your browser. Keep the terminal running; use
`Ctrl+C` to stop the application. No account, paid service, API key, database, or
cloud deployment is required. Run commands from the repository root so Streamlit
loads the supplied theme, local-only address, upload limit, and telemetry setting.

Run the complete automated suite separately:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

On macOS/Linux, use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.
`requirements.txt` installs the local package in editable mode with the `ui` and
`test` extras. The engine depends only on pandas and openpyxl; the optional UI
adds Streamlit and its dependencies. Pytest is for development. For engine-only
usage, install with `python -m pip install -e .`; the full UI test suite requires
the extras installed by `requirements.txt`.
Dependency ranges and package metadata live in `pyproject.toml` to avoid duplicate
dependency declarations. The supported ranges are bounded, not a frozen lockfile.

## Dashboard workflow

Use the sidebar links to move between five sections:

1. **Upload:** upload CSV/XLSX or choose a bundled sample. Review import settings,
   then select **Load dataset**. CSV supports Unicode detection, explicit encodings,
   and detected or configured delimiters. XLSX lists worksheets before loading,
   including when the first sheet is empty or contains instructions. Optional XLSX
   ranges and header corrections have a column-by-column review before import.
2. **Data Overview:** inspect rows, columns, missing cells, duplicate rows, column
   types, and an interactive original-data table. Loading never cleans the data.
3. **Cleaning Configuration:** add operations, select columns and settings, and
   use **Move up**, **Move down**, or **Remove step**. Execution follows the visible
   order. Header normalization changes the names offered to subsequent steps;
   obsolete selections remain visible with errors after reordering.
4. **Results:** select **Preview changes** to process the complete dataset. Review
   before/after metrics, affected rows, step summaries, warnings, and original vs.
   preview tables. Select the review checkbox, then **Apply reviewed changes**.
   Applying adopts that exact preview; it does not rerun the pipeline.
5. **Download:** select **Prepare downloads**, review export warnings, and download
   CSV, XLSX, or the JSON processing report. A failure in one export format leaves
   successful formats available. All exports contain the complete confirmed data.

Changing a file, worksheet, import option, operation, order, or error policy clears
the preview, confirmation, and prepared downloads. Import option changes require
loading again. A failed load retains the last valid original in memory, but hides
its overview tables/metrics and blocks processing until the current selection is
loaded. **Reset workspace** clears the
session's working state and upload selection; it does not modify files on disk.

Previews with errors cannot be confirmed in the dashboard. You can disable
stop-on-error to inspect further steps, then correct the errors and preview again.
Warnings alone permit confirmation. The underlying Python API continues to support
partial-result workflows for callers that explicitly need them.

### Example walkthrough: sample sales

1. Choose **Try a sample → Sales (CSV)** and **Load dataset**. The overview shows
   **10 rows, 9 columns, 4 missing cells, and 1 duplicate row**.
2. Add **Clean text**, select `customer_name`, and keep `trim`.
3. Add **Convert numbers**, select `quantity` and `unit_price`, and keep decimal
   `.` and thousands separator `None`.
4. Add **Remove duplicates** and keep all columns / first record.
5. Add **Handle missing values** for `quantity`: choose `constant`, type `Number`,
   and enter `1`. This is an explicit example choice for the fictional dataset;
   choose a suitable policy for your own data.
6. Add **Standardize dates** for `order_date`. Enter these two formats on separate
   lines: `%Y-%m-%d` and `%d/%m/%Y`.
7. Preview and inspect **9 rows, 9 columns, 3 missing cells, and 0 duplicate rows**.
   Review Priya's trimmed name and standardized date. Three other missing cells
   remain because they were not selected for filling.
8. Confirm, prepare downloads, and save the complete CSV/XLSX and JSON report.
   Decimal cells in XLSX may be stored as text to protect precision; the export
   warnings explain this. To explore worksheet selection, load **Sales workbook
   (XLSX)** and choose the `Customers` worksheet.

### Importing Excel sheets with gaps or multiple tables

Excel import is **strict by default**: blank and duplicate headers cause a
validation error. The Upload section offers explicit alternatives:

- **Excel cell range:** select one contiguous column range such as `A:B` or
  `L:M`, or a rectangle such as `L1:M20`. By default its first row is the header.
  Ranges must be within the worksheet's reported used bounds. A column-only
  range retains all worksheet rows, including blank rows below a shorter table.
- **Exclude completely empty columns:** excludes only columns whose every cell
  in the whole worksheet, including the header, is empty. Whitespace, zero,
  `False`, formulas, and named header-only columns are not empty. A column with
  data outside a selected rectangle is not classified as completely empty.
- **Generate names for missing headers:** retains the column and assigns
  `Unnamed_Column_1`, `Unnamed_Column_2`, etc., skipping existing names. Columns
  containing data are never removed merely because their headers are missing.
  Non-text headers still fail validation unless irregular-header repair is enabled.
- **Make duplicate header names unique:** keeps the first occurrence and gives
  later occurrences suffixes such as `__2`, `__3`, skipping names already present
  elsewhere. Values are selected by column position, so duplicates cannot
  overwrite one another.
- **Header selection:** use the first row, choose an absolute Excel row number,
  request header inference, or choose no header and generate names without
  consuming any row. Inference suggests the earliest row with the most non-formula
  text labels within the first 20 selected rows. It is a heuristic: inspect the
  preview, including any rows excluded before the suggested header, then approve.
- **Repair irregular headers:** explicitly trim/collapse whitespace and convert
  non-text labels to text. Generated and repaired names use the same collision
  checks. The plan identifies each affected header cell before confirmation.
- **Remove entirely blank worksheet rows:** remove only rows whose every cell
  across the whole worksheet is empty. Whitespace, formulas, zero and `False`
  remain data. Empty rows inside a selected range with data elsewhere are retained.

The worksheet view labels empty sheets before loading. **Worksheet at a glance**
shows the worksheet dimensions, table-candidate count, isolated-region count and
formula-cell count. The two largest table candidates appear first as selectable
cards with coordinates, dimensions, formula markers and short value previews.
Use a card's **Select [range]** button to open its import review without typing
coordinates. Selection does not load data or grant approval.

When at least two substantial table candidates are detected, the dashboard starts
in **Choose a table**. No range or header row is assumed and no whole-sheet header
validation runs until you make a choice. Selecting a card uses that region's first
row as its header and updates the preview; selecting a different card resets the
header policy to that new region's first row. Isolated cells retain their existing
headerless behavior. Ordinary reruns preserve your explicit settings.

**Advanced import options** contains whole-worksheet/custom-range import, separate
imports of all regions, and explicit combination. A blank custom range means the
entire worksheet: it is never silently replaced with a detected table or trimmed.
Custom range text is retained when you switch modes within the same worksheet.
Simple worksheets without multiple substantial candidates retain the existing
strict worksheet default. The backend API defaults are unchanged.

After selection, **Header settings** exposes alternate rows, inference and headerless
import. **Optional repairs for this selection** offers only relevant repairs, plus
any already-enabled choices so they remain visible and can be disabled. Nothing is
checked automatically. Invalid headers are grouped by problem with affected cells
and a specific resolution. For example, D6:H12 has non-text labels at **D6 and H6**:
choose another header row or explicitly enable irregular-header repair. The valid
K6:N9 headers need no repair controls. Every proposed change still requires review.

Cards use a display-only heuristic: a **Table candidate** has at least two rows,
two columns and four populated cells; a 1×1 region is an **Isolated cell**. Other
shapes are labeled **Small / narrow region**. These are suggestions, never a
guarantee that connected cells form a table. Size ordering uses bounding row count
× column count, including blanks and any header; ties use worksheet row/column order.
These labels and ordering do not change the engine's regions or import behavior.

Every remaining region stays available in the collapsed **Other regions — inspect
and import** section, with the same preview and Select button. Isolated cells are
never discarded. Card previews show at most three rows and four columns, with
explicit displayed/total counts; imports retain the full selected region.
**Advanced Details** keeps exact leading/trailing/internal blank ranges, source
ranges, formula coordinates and technical explanations available but collapsed.
Formula indicators use text, not color alone; native controls provide keyboard
interaction and adapt to the available width.

In **Advanced import options**, choose **Select a detected region**, **Import all regions separately**,
or explicitly approve combining regions in their original worksheet alignment.
The latter does not join keys or stack unrelated tables. Separate imports are kept
as independent originals; the **Active imported region** selector chooses the table
to clean/export. Switching tables clears derived results and export acknowledgment.
Single-cell detected regions are kept as one data value with a generated column
name, including isolated formulas, rather than consumed as headers.

Region detection is geometric, not semantic. Sparse logical tables can produce
multiple suggestions; touching tables can appear as one region. Overlapping
bounding rectangles are coalesced so detected regions do not duplicate cells.
Use custom ranges and review Before/After values when suggested boundaries do not
match your intended table. Every non-empty cell belongs to a detected region.

The import preview summarizes the selected boundary and planned change counts.
Its collapsed **Advanced Details — import plan** lists **every worksheet column**,
its original and proposed header, whether it is completely empty, and its action,
plus exact excluded row spans and validation details. For separate imports, use
**Import preview to inspect** to review each plan individually; this display-only
choice does not revoke approval or omit any region. Review the plan and check the
approval checkbox before loading
when exclusions, header inference, renames or a multi-region import are proposed.
Before/After tables are paginated, with full selected results retained. Changed
header coordinates, excluded rows/columns and table boundaries are shown separately.
Changing settings revokes approval.
Import never edits the workbook or changes selected cell values.

For a sheet with `f(Hz.)` / `dB` in A:B, empty C:K, `f(Hz.)` / `f(o)` in L:M,
and empty N, select the desired table card, or explicitly choose a custom `A:B`
or `L:M` range in Advanced import options. To retain both in worksheet alignment,
explicitly choose **Worksheet / custom range**, leave its range blank, and enable
empty-column exclusion and duplicate-header naming.
The plan excludes C:K and N and renames only L to `f(Hz.)__2`. Approve and load
four columns, preserving all selected rows and values. This does not join the
two tables by frequency; they retain their original worksheet row alignment.
Excel may omit an unformatted trailing empty N from its used range; only columns
reported in that range appear in the plan.

### Walkthrough: the actual `sayfa1.xlsx` regression workbook

The unmodified regression copy is [tests/fixtures/sayfa1.xlsx](tests/fixtures/sayfa1.xlsx).
The file actually contains `eko` and an empty **`Sayfa2`** (not `Sayfa1`). `eko`
has leading empty rows **1:5**, leading empty columns **A:C**, two main regions
**D6:H12** and **K6:N9**, and detached cells **I8, P8, O12, K13, O14 and J15**.
Its used bounds are A1:P15; the detached cells mean there are no trailing blank
rows/columns within those bounds. F8 contains an **array formula**. The fixture
hash and provenance are documented in [tests/fixtures/README.md](tests/fixtures/README.md).

1. Upload this workbook and select `eko`; the worksheet summary identifies
   `Sayfa2` as empty. The app waits for a table choice instead of treating A1:P15
   as a table with 16 missing row-1 headers.
2. Select **K6:N9** for the three-row, four-column table with valid headers on row 6.
   Alternatively, select **D6:H12** and explicitly enable **Repair irregular headers**
   to review the numeric/date labels at D6 and H6. This table has six data rows and
   five columns; F8 remains a typed array formula with its expression and reference.
3. Review **Before / After values** and **Advanced Details — import plan**, approve,
   then select **Load dataset**. No repair, removal or combination is automatic.
4. Preview/apply a cleaning workflow or an unchanged dataset. **Prepare downloads**
   produces the JSON report, but CSV/XLSX with imported formulas require explicit
   acceptance of lost formula functionality. **Download unchanged original workbook**
   returns the exact uploaded bytes, preserving the original formulas and formatting.
5. To inspect a detached cell, expand **Other regions — inspect and import** and
   select e.g. **I8:I8**. Its expression is a data value, not a header. Selecting
   another region invalidates the old preview and requires fresh import approval.

To load all eight regions independently, open **Advanced import options** and choose
**Import all regions separately**, enable irregular-header repair for D6 and H6,
and use **Import preview to inspect** to review every plan before approving. All
two tables and six isolated regions are retained; the active-region selector chooses
which original table to process.

To combine the full `eko` sheet deliberately, open **Advanced import options** and
choose **Combine regions in worksheet alignment**, choose header row **6** in
**Header settings**, enable empty-column exclusion, missing-header
generation, duplicate-header naming and irregular-header repair, then review/approve.
This retains all nine data rows (7:15) and thirteen columns (D:P), including detached
cells and blanks. It does not merge records by frequency or city.

The bundled **Sparse Excel tables (synthetic)** sample (`sample_data/sayfa1_like.xlsx`)
supplements the real fixture with trailing empty margins, additional duplicate and
unnamed headers, and mixed values. Its empty sheet is intentionally named `Sayfa1`.
Regenerate it with `python sample_data/generate_import_sample.py`.

### Limits and local state

- Default upload limit: **10 MiB per file**. The UI can lower the limit or raise it
  up to `server.maxUploadSize` from `.streamlit/config.toml`. To allow larger files,
  edit that setting, restart Streamlit, and select the desired UI limit. XLSX
  expanded archive size remains limited to **100 MiB**. These byte limits do not
  guarantee bounded DataFrame memory use; large workbooks can use much more RAM.
- Excel inspection/import also rejects worksheet grids larger than **2,000,000
  cells including blanks** (reported rows × columns). A small archive with a distant
  formatted cell can exceed this limit. Use a smaller workbook or remove unused
  rows/columns in a **copy**; the app never truncates the sheet. Selecting a small
  range does not bypass this guard because structure analysis reads the sheet.
  Worksheet-name listing remains available through the engine. The dashboard
  inspects all sheets, so an oversized sheet blocks that workbook's upload.
- Data, workflows, previews, and prepared downloads live in `st.session_state`.
  They are not shared through a global data cache, saved to a database, or sent to
  third-party processing services. Session loss, server restart, or Reset workspace
  discards this working state. Download results you want to keep.
- Tables display **100 rows per page** with explicit page/total counts. Every page
  is accessible. Cells are rendered as text to preserve mixed values and exact
  Decimals in the display; profiling still reports actual engine dtypes. Native
  table downloads and clipboard export are disabled because they bypass formula
  acknowledgment and the safe exporters. The Download section exports the entire
  confirmed result without truncation.
- XLSX exports reject unsupported sheet dimensions, oversized cell text, or invalid
  XML characters rather than truncating. Formula-injection protections remain
  mandatory. Processing and export errors leave the original dataset intact.
- This is a local, single-workspace-per-session application. It has no authentication,
  persistent projects, background jobs, or multi-file merging. The default server
  binds to `127.0.0.1`; Streamlit usage telemetry is disabled in the supplied config.

### Verification scope

Tests include the existing engine suite, state/configuration tests, and headless
dashboard interaction tests using [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing).
They cover upload widget inputs, worksheet selection, invalid imports, operation
controls/order, preview and confirmation, invalidation, error handling, and download
artifacts. Tests inspect generated bytes and download widgets; they do not exercise
an operating-system save dialog. A local server smoke check can additionally verify
the HTTP page and health endpoint.

See [Phase 4 validation](docs/phase4_validation.md) for actual test results,
performance measurements, audit findings, and remaining manual checks. Reproduce
the realistic 51,000-row CSV / 10,000-row formula-workbook benchmark with:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_phase4.py --output docs/phase4_benchmark.json
```

Manual checks remain appropriate for desktop/mobile layout, sidebar navigation,
table interaction in a real browser, the native file picker, and saving/opening
downloaded files in your preferred spreadsheet application. Automated AppTest
results are not a claim of pixel-level or browser download verification.

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
- Headers must be unique, non-blank text. Strict defaults never trim or rename
  them; XLSX supports the explicit, reviewed import options described above.
  Empty files, malformed files, missing sheets, and ragged CSV rows raise
  `FileValidationError`. Header-only tables are valid. Blank CSV records fail
  width validation instead of being silently skipped (use explicit empty fields).
  XLSX's reported worksheet range is respected, including blank rows; blank or
  merged header cells fail strict validation. Text streams and old `.xls` files are unsupported.

For programmatic XLSX import, `inspect_xlsx_import` returns an immutable plan
with `columns`, `errors`, `selected_range`, and confirmation requirements. For
example, inspect the bundled sample without changing any source bytes:

```python
from io import BytesIO
from pathlib import Path
from smart_data_processor import inspect_xlsx_import, load_dataset

payload = Path("sample_data/sample_sales.xlsx").read_bytes()
options = dict(sheet_name="Sales", exclude_empty_columns=True,
               generate_missing_headers=True, deduplicate_headers=True)
plan = inspect_xlsx_import(payload, **options)
for column in plan.columns:
    print(column.excel_column, column.original_header,
          column.imported_header, column.action)
print(plan.errors)

# Only after reviewing the exact plan and approving any header changes:
if not plan.errors:
    data = load_dataset(BytesIO(payload), filename="sample_sales.xlsx",
                        **options, confirm_header_changes=True)
```

`load_dataset` accepts the same range/header options; actual generated or suffixed
headers require `confirm_header_changes=True`. Range selection and empty-column
exclusion are explicit API arguments; the dashboard additionally requires review
of these exclusions. Excel options are rejected on CSV rather than ignored.
The import plan is separate from the processing report, which describes cleaning
steps applied after import.

Additional APIs and keyword options:

- `inspect_xlsx_layouts(payload)` returns immutable worksheet layouts, including
  exact blank ranges, suggested rectangles, formula inventory and coordinate-labeled
  raw previews. It does not require valid headers.
- `load_xlsx_regions(payload, sheet_name="eko", ranges=("D6:H12", "K6:N9"), ...)`
  returns a dictionary of independent DataFrames. Pass reviewed header options,
  including `confirm_header_changes=True` for naming repairs. A failure returns
  no partial collection. Single-cell ranges use generated names and retain the cell
  as data, requiring the same naming confirmation.
- `header_row=6`, `infer_header=True`, `headerless=True`, `remove_empty_rows=True`
  and `repair_irregular_headers=True` are opt-in. Explicit/inferred header selection
  and actual blank-row removal require `confirm_import_changes=True` in addition
  to any naming confirmation. Headerless mode requires naming confirmation.
  Headerless mode, an explicit header row and inference are mutually exclusive.
- Imported XLSX frames carry `attrs["xlsx_source"]`: source sheet/range, header
  row (`0` means no header), row numbers, column letters and formula expressions,
  kinds and references. The pipeline remaps row coordinates after filtering.
  Dashboard JSON downloads include this provenance and the source file's SHA-256.
  Standalone `export_report` keeps its existing report schema. External pandas
  operations may discard attrs; retain the source metadata when using those APIs.

The existing `load_dataset` default still reads one strict rectangular worksheet
for backward compatibility. It never auto-selects a region, infers a header or
removes blank rows/columns. The dashboard adds review gates around explicit choices.

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

Frames carrying imported formula provenance are blocked from CSV/XLSX export unless
the caller supplies **`acknowledge_formula_loss=True`**. The dashboard has a separate
revision-specific acknowledgment checkbox. Formula expressions are exported only as
protected, inert text after acknowledgment; they do not calculate. Ordinary imported
formula cells retain their existing expression-string API plus formula metadata.
Array formulas are immutable `ExcelFormula` values containing the exact expression,
formula kind and reference, not calculated values or object-representation strings.
Array formulas without a scalar expression (including data-table formulas) block
flat import; retain/download the original workbook instead. The app never evaluates,
translates, fixes references or recalculates Excel formulas.

**References retain their original workbook meaning.** For example, selecting
`eko!K6:N9` moves source `N7` to exported `D2`. Its expression `=L7+M7` is retained
as text, not rewritten to `=B2+C2` or presented as a working calculation. Referenced
cells may have moved or been omitted, including other sheets. Absolute references,
named ranges, external links and existing `#REF!` expressions are not validated.
XLSX exports attach an explanatory cell note to known formula expressions; CSV
prefixes them with an apostrophe. The dashboard's JSON report includes export
statuses, warnings and `formula_loss_acknowledged` alongside source coordinates
and the original-file hash. Download this report with CSV to retain its explanation.

Text cleaning preserves known imported formulas, including quoted text inside an
expression, and reports `formula_preserved` warnings. Case-insensitive duplicate
comparison also leaves formula expressions case-sensitive. Literal strings equal
to known source expressions are conservatively protected too; ordinary CSV text
keeps its existing cleaning behavior. Standalone row-removal operations and the
pipeline both update retained source row coordinates without changing the original.

Flat DataFrames cannot preserve workbook styles, merged-cell structure, formula
functionality or cross-sheet references. The unchanged-original download is the
preserving alternative; it contains no cleaning changes. Automatic reinsertion of
cleaned values into a formatted/formula-bearing workbook is not implemented.

Protection is mandatory. Export diagnostics belong to the returned artifact;
they do not alter the earlier processing report. Re-importing protected CSV
intentionally retains its added apostrophes.

## Architecture

```text
app.py                         # Streamlit launch entry point
.streamlit/config.toml          # Local binding, upload limit, telemetry, and theme
src/smart_data_processor/
    __init__.py                # Small public API
    file_handler.py            # Read-only imports and format-specific parsing
    excel_layout.py            # Blank margins, region discovery and typed formulas
    excel_import.py            # Reviewed range/header/blank-row import plans
    excel_provenance.py        # Formula identity and retained source-row helpers
    validators.py              # Shared contracts and public error types
    profiler.py                # Immutable descriptive statistics
    cleaner.py                 # Duplicate and missing-value handling
    transformer.py             # Text, header, numeric, and date transformations
    models.py                  # Operation results and diagnostics
    pipeline.py                # Ordered execution and original-row provenance
    reporter.py                # Reports and safe CSV/XLSX/JSON exports
    dashboard_state.py         # Testable session lifecycle and configuration adapters
    dashboard.py               # Streamlit presentation and widget wiring
tests/                         # Engine, state, AppTest, export, and integration tests
sample_data/                   # Synthetic CSV/XLSX examples and regeneration script
docs/architecture.md           # Decisions, tradeoffs, and future boundaries
docs/screenshots/              # Reserved for the future interface
```

The `src` layout makes tests exercise an installed package. File I/O, validation,
profiling, and cleaning have separate responsibilities and no UI dependencies.
Conservative parsing makes interpretation explicit; cleaning is a separate call.
See [architecture decisions](docs/architecture.md) for details and limitations.

## Remaining work

- Phase 5: publication assets, screenshots, demonstration video, and portfolio copy.
- Manual browser/spreadsheet checks and a wider Python/dependency/OS compatibility
  matrix remain follow-up validation; current measured coverage is documented.

Numeric/categorical distributions and format-inconsistency diagnostics remain
future profiling enhancements. Phase 5 has not been started. A publication license
has not yet been selected.
