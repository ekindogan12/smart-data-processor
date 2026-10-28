# Phase 1–4 architecture decisions

The proposal is the specification; its phase boundaries take precedence over the
full-product acceptance criteria. The current deliverable is a tested Python
library for imports, profiling, cleaning, transformations, ordered processing,
structured reports, and safe exports, with a local Streamlit dashboard in Phase 3.
Exports were explicitly requested and implemented in Phase 2.

## Module boundaries

`file_handler` owns bytes, encoding, CSV records, workbook access, and resource
cleanup. `validators` defines shared header/DataFrame contracts and two public
ValueError subclasses so a future UI can display actionable validation failures.
`profiler` produces immutable dataclasses with detached dictionary conversion;
it has no file output responsibilities. `cleaner` accepts and returns DataFrames,
allowing scripts, tests, and a later UI to use the same engine.

`excel_import` builds an immutable range/header import plan from worksheet records.
It owns empty-column classification and deterministic header naming, with no I/O
or Streamlit dependency. Inspection and loading use the same planner so their
exclusion and naming decisions agree; columns are selected by position to prevent
duplicate names from overwriting data.

`excel_layout` owns geometric region detection, exact empty margins/ranges and
coordinate-labeled worksheet previews. Eight-neighbor occupied-cell components
produce rectangular suggestions; overlapping boxes are coalesced to prevent
duplicate coverage. This handles the actual workbook's detached formulas, which
invalidate a whole-sheet blank-separator-only algorithm. It is not semantic table
recognition: sparse tables may split and touching tables may share a suggestion.

`transformer` owns explicit text/header normalization and numeric/date conversion.
`models` contains shared operation results and diagnostics. `pipeline` orchestrates
operations and translates row provenance; `reporter` defines audit records and
byte serialization. The two additional modules keep orchestration separate from
individual operations and avoid circular imports.

`app.py` calls the dashboard's `main` function. `dashboard` owns widgets and
presentation, while `dashboard_state` owns testable session transitions and input
adapters without importing Streamlit. No engine module depends on either UI module.
Phase 1 loaders, profiling, and duplicate removal remain intact; a pipeline adapter
adds duplicate-removal provenance without changing its existing DataFrame API.

## Preservation over inference

Automatic pandas CSV inference can erase identifiers' leading zeros or treat
literal business codes such as `NA` as nulls. CSV parsing therefore uses Python's
standard-library `csv` reader, validates row widths before DataFrame construction,
preserves text, and maps only empty fields to missing values. Unicode BOMs are
unambiguous encoding signals. Legacy encodings must be selected explicitly because
several encodings can decode the same bytes into different valid text. Delimiter
sniffing is heuristic and has an explicit override.

XLSX parsing uses openpyxl in read-only mode and closes workbooks in a finally
block. `data_only=False` retains formula expressions instead of possibly absent
or stale cached results. Object dtype preserves native cell types without pandas
coercion, so profiling reports `object` for imported columns even when their cells
are numeric. Excel dates are decoded according to openpyxl's cell metadata. This
is a value import, not a lossless workbook editor: styles, comments, charts, and
merged-cell structure are not represented by DataFrames.

Paths are opened read-only; binary stream positions are restored. Size-limited
reads avoid loading oversized input files. The XLSX expanded archive limit guards
against highly compressed inputs, but no hard process memory/CPU limit is claimed.
The loader materializes the dataset; streaming large datasets is future work.

## Explicit cleaning

Duplicate comparison uses a temporary copy of selected columns. Unicode casefold
supports comparisons such as `Straße` and `STRASSE` without rewriting stored text.
Casefold can deliberately group more spellings than lowercase; users opt into it
per column. Deduplication performs no whitespace, date, or numeric normalization.
pandas determines
duplicate and missing-key equivalence; the index is excluded from comparison.
Positional filtering keeps repeated index labels correct. A deep DataFrame copy
ensures edits to returned scalar cells cannot affect the original. pandas deep
copies do not recursively clone nested Python objects; those are outside the
spreadsheet cell contract.

## Transformation contracts

New operations return `OperationResult`, containing an independent DataFrame,
affected positions, diagnostics, and (when applicable) retained positions or
column-name changes. A malformed operation raises `DataValidationError` without
modifying its input. Valid numeric/date conversions may coexist with invalid
cells; invalid values remain intact and errors identify their column/row.

Missing-value filling inspects dtype and actual non-null values because Phase 1
imports intentionally use object columns. Numeric strings are not numbers until
the caller selects conversion. Booleans are a separate type. Mean/median only
operate on numeric columns; constants must match the column's type. Unobserved
object columns can accept an explicit typed constant. Statistics without any
observations leave cells untouched with warnings. Mode ties are deterministic:
the first observed tied value wins, with a warning. Category constants may add
categories on the copy. Fractional fills use object dtype when necessary to avoid
rounding existing large integers, and dtype changes are reported.

Text operations transform only strings and report skipped non-text cells. Empty
strings do not automatically become missing values. Optional header normalization
uses Unicode NFKC, casefold, and underscore separation; collisions and names that
would become empty are rejected rather than disambiguated automatically.

Numeric parsing uses a strict separator-aware grammar and standard-library
`Decimal`. For example, `1.234,50` requires decimal `,` and thousands `.`. Grouping
must contain triples; signs and scientific notation are allowed. Integer strings
become exact Python integers and fractions become exact Decimals in object columns.
This trades pandas vectorization speed for preservation of identifiers selected
for conversion, large integers, and decimal precision. Native numeric values are
retained. Adjusted exponents outside -1000..1000 are rejected rather than expanding
extreme inputs. Mean/median use a local decimal context with at least 28 digits plus
input precision; nonterminating means necessarily round in that context.

Date parsing uses only explicit numeric `strptime` formats with year, month, and
day. It never guesses locale, day-first order, timezone, or a missing year. All
formats are evaluated: conflicting results preserve the original and produce both
an ambiguity warning and an error. A single user-selected format resolves order.
Output is ISO 8601 text, preserving explicit times and offsets. Native date and
datetime values use `isoformat`; numeric Excel serial dates in ordinary numeric
cells are not interpreted as dates. String fractions follow `strptime`'s six-digit
precision, while native timestamps preserve their available precision.

## Ordered pipeline and provenance

`ProcessingPipeline` snapshots `ProcessingStep` configurations and runs them in
exactly the given order. There is no fixed global order or implicit operation.
Callers choose whether duplicates contribute to statistics and whether trimmed
text contributes to duplicate comparison. Later steps refer to the current schema
after any explicit header normalization. A typical sequence is:

```python
pipeline = ProcessingPipeline([
    ProcessingStep("normalize_column_names"),
    ProcessingStep("clean_text", {"columns": ["amount"], "operation": "trim"}),
    ProcessingStep("convert_numeric", {"columns": ["amount"]}),
    ProcessingStep("remove_duplicates", {"subset": ["order_id"]}),
    ProcessingStep("handle_missing", {"columns": ["amount"], "strategy": "mean"}),
])
```

Step signatures and values are validated before their output is adopted. A
configuration failure is atomic for that step and recorded as `failed`. Conversion
errors yield `partial` (including when every cell fails). Successful steps are
`applied`. By default any error stops subsequent steps; warnings do not. Explicit
`stop_on_error=False` continues. Prior successful steps and valid cells in a partial
conversion remain applied; this is not whole-pipeline rollback. The input always
remains unchanged and an empty pipeline still returns a copy.

Internal positional row IDs track original rows across filtering without relying
on index uniqueness. Duplicate-removal provenance uses a temporary positional
index and restores original index labels. Missing-row removal returns retained
positions directly. Reports remap diagnostic and affected positions to the original
input; standalone results use positions in their own input. Affected-row counts
include removed rows, count each row once per step, and use the union across steps
for the overall count. Header-only operations report rename pairs and zero changed
rows. No temporary columns or index values leak into output.

## Reports and export boundaries

Reports include full input/output profiles, ordered steps and their parameters,
per-step dimensions, statuses, affected rows, warnings, errors, and planned-step
counts. Frozen dataclass envelopes have detached parameter snapshots; their nested
parameter dictionaries are caller-editable without affecting the reusable pipeline.
`to_dict` produces detached JSON-safe values. JSON has `schema_version=1`; Decimal
and datetime parameters become strings, missing markers become null, and non-finite
numeric configuration values become strings so failed configurations can still be
reported. Arbitrary unsupported Python objects are explicitly rejected.

Exports return artifacts in memory so command-line tools and a future UI can decide
where to save or download. The engine never overwrites paths. CSV/XLSX artifacts
carry protection counts and warnings separately from the immutable processing
history; JSON serialization does not mutate that history. The DataFrame index is
not exported. Native dates use ISO text, including offsets. Missing values use
empty cells; empty strings and missing cells can converge on spreadsheet roundtrip.

CSV quotes every field and prefixes formula-like text with an apostrophe, including
headers, whitespace/control-prefixed markers, and fullwidth variants. Literal
numeric values are not escaped. Re-imported CSV retains protection apostrophes.
This is an intentional, reported export representation change. CSV has no type
metadata, so spreadsheet consumers may still infer numeric/date types on import.

XLSX explicitly assigns string cell types for all text, including imported formulas
and strings that resemble Excel errors. There is no formula-writing mode. Decimals
and integers exceeding 15 digits are stored as text with precision warnings.
Existing floating-point values retain spreadsheet floating-point limitations.
Dimension limits, illegal XML characters, and oversized strings fail explicitly
instead of triggering openpyxl's string truncation. These measures operate only
on serialized output and cannot modify the processing result.

## Dependency and verification choices

Only pandas and openpyxl are engine runtime dependencies. The optional `ui` extra
adds Streamlit; `requirements.txt` includes the UI and test extras. The standard library handles
encoding, CSV parsing, archive validation, paths, and profile data structures.
Pytest runs the suite, with AppTest supplied by Streamlit. Editable installation avoids runtime
path manipulation in tests. Tests use temporary files and in-memory workbooks,
plus the committed synthetic samples for end-to-end coverage. They check source
preservation, malformed inputs, encoding/worksheet selection, profile statistics,
duplicate options, all-null and typed fills, locale-configured numeric parsing,
ambiguous dates, pipeline order/provenance/error policy, JSON reports, formula
protection in headers and cells, precision preservation, and export limits.

Python 3.11+ is the declared target; the test results reported at implementation
time cover the available local interpreter, not a full cross-version matrix.
No new runtime dependencies were needed for Phase 2. Phase 3 adds Streamlit and its
transitive dependencies, with no separate plotting library, database, or cloud service.

## Phase 3: local dashboard

The UI is a single page with sidebar links to Upload, Data Overview, Cleaning
Configuration, Results, and Download. Native Streamlit controls, bordered metrics,
clear primary actions, a light theme, and responsive columns keep the presentation
minimal. Static CSS never interpolates uploaded content. Uploaded cell values are
rendered in tables, not passed to HTML or evaluated as formulas.

### Compatible backend additions

The existing loader could select a known worksheet but could not list worksheet
names without first loading a table. `list_worksheets(payload, ...)` now exposes
that metadata using the existing XLSX archive validation, byte limits, and workbook
cleanup. It does not read worksheet rows or require valid headers in the first
sheet. All previous signatures remain compatible. Worksheet metadata is cached only for
the current session and bytes/size-limit combination.

The targeted XLSX import fix adds `inspect_xlsx_import` and optional keyword
arguments to `load_dataset`. Strict validation remains the default. The planner
distinguishes a missing header from a completely empty whole worksheet column;
only the latter can be excluded by `exclude_empty_columns`. Explicit contiguous
ranges select columns or a rectangle with its own header row. Selected values and
blank rows are retained unchanged unless explicit blank-row removal is confirmed.
Missing-name generation and duplicate suffixes
reserve all existing selected names and require explicit header confirmation.

`inspect_xlsx_layouts` reads worksheets without requiring valid table headers and
labels empty worksheets. `load_xlsx_regions` returns separate DataFrames atomically,
never concatenates them, and reuses the same range/header planner as single-table
loading. Isolated one-cell detected regions use a shared UI/API headerless policy
so formula/value cells do not disappear into column labels. Naming confirmation
still applies. Combination is an explicit, reviewed worksheet-aligned import.

Header selection is absolute, inferred, first-row-of-range, or headerless. Inference
selects the earliest row with the most non-formula text labels among the first 20
selected rows, with a mandatory review gate. Exact excluded rows and changed header
coordinates are exposed. Optional irregular-header repair trims/collapses whitespace
and converts labels to text; all naming collisions use deterministic reserved names.
Blank-row/column removal considers the whole worksheet and only `None` cells;
whitespace, zero, booleans and formulas are never classified as blank.

The dashboard displays every column's action plus excluded row spans before
import. Exclusions and renames require a revision-specific approval checkbox.
The plan is cached in session state by file digest, sheet, limits, and import
options; unrelated reruns do not scan the workbook again. Loading recalculates
the same plan from the same bytes instead of trusting UI-supplied header mappings.
The source workbook is never written. Import planning is separate from the
post-import cleaning pipeline and its processing report.

Formula cells are read with `data_only=False`. Ordinary formula strings retain the
previous public API and are distinguished from literal equals-prefixed text through
Excel cell-type metadata. Array formulas use an immutable `ExcelFormula` object
containing their expression, kind and reference. Unsupported formula forms lacking
an expression block flat import instead of invoking `str` on an openpyxl object.
The untouched workbook remains the preserving alternative.

XLSX DataFrame attrs hold source row/column coordinates and the original formula
inventory. The pipeline updates retained row coordinates after filtering; the formula
inventory remains conservatively attached even if some formula rows are removed.
Exporters reject imported formulas unless `acknowledge_formula_loss=True`; typed
formula cells also trigger the guard if attrs were lost. After acknowledgment,
expressions become protected literal text in the export only. The dashboard retains
the uploaded bytes and offers an exact original download. It does not patch a
formatted workbook or claim that reference semantics survive flat export.

The dashboard JSON download adds source provenance and file hash to the existing
processing report; standalone `export_report` is unchanged. Source attrs are part
of the controlled pipeline contract, not a guarantee for arbitrary external pandas
operations that drop metadata or rearrange columns.

### Session lifecycle and invalidation

One `Workspace` instance is held in `st.session_state` per browser session. It owns
the last valid original/profile, active and loaded source identities, copied
pipeline configuration, preview, confirmed result, and prepared export artifacts.
Widget state holds the ordered operation cards and their editable parameters.
Data is never placed in a global Streamlit data cache or written to persistent storage.

Source identity includes a SHA-256 content digest, filename, encoding, delimiter,
worksheet, size limit, range, header/exclusion options, and header confirmation.
Separate-region selections, headerless mode and row-removal approval also participate.
Configuration identity includes ordered steps and typed
parameters, stop-on-error policy, and validation errors. Changing either identity
revokes the preview, confirmed result, and download artifacts immediately on the
corresponding widget rerun. A revision-specific review checkbox prevents an earlier
confirmation from carrying over. Reordering and deleting cards also invalidate
immediately. Failed imports retain the last valid original in memory but hide its
overview tables/metrics and block processing until the active selection is loaded.
The loaded-source marker is cleared before each load attempt, including retries
of an identical source. Revoking import approval also blocks use of retained data.
Configuration remains visible during pending
imports to avoid Streamlit discarding hidden widgets' selected values.

Separate imports retain independent original tables. Selecting another active table
revokes derived results and formula-export acknowledgment. A failed collection load
cannot adopt a partially loaded table set. Before/After import previews are cached
with the exact plan; table pagination does not reconstruct the imported dataset.
Results show compact metrics and meaningful table previews, with diagnostics, source
coordinates and formula details collapsed by default.

Worksheet structure presentation is deliberately independent of region detection.
The `dashboard_state` display adapter ranks existing rectangles by bounding area
(descending), then top/left coordinates, and labels a region as a table candidate
only when it has at least two rows, two columns and four non-None cells. A single
cell is isolated; remaining shapes are small/narrow regions. This is a transparent
display heuristic, not semantic classification or a new detection algorithm.
The two largest table candidates are shown first; every other region remains selectable
in a collapsed section. Formula counts come from the engine's formula inventory,
including array formulas, even when they lie outside the small card preview.

Card previews slice at most 3×4 original cells into an explicitly labeled display
copy. They never feed imports or exports. Summary metadata is cached by source
bytes/name/sheet. Card and dropdown selection callbacks update the existing
mode/region controls and reset the header policy to the selected region's first
row (or headerless for a singleton) before the widget rerun. Existing source
identity and revision-based confirmation then
invalidate stale previews. No independent import or approval path is introduced.
The import-plan inspection selector changes presentation only; all separate-region
plans remain loaded and validated. Exact blank ranges, coordinates and diagnostics
live in collapsed Advanced Details sections. Native buttons have unique coordinate
labels; selection and formula status use text rather than color alone.

For a new worksheet with multiple substantial candidates, UI state starts in
`Choose a table`, with no import plan. It never substitutes a candidate for a
previously selected custom range. Whole-worksheet, custom-range, separate-region
and combined imports are explicit controls in a collapsed Advanced import options
section. The original strict default remains for simple worksheets and the Python
APIs. Selecting `Choose a table` again cancels the pending selection, clears the
import review, and revokes readiness without deleting the retained original.

The initialization identity uses file bytes/name/sheet, so ordinary reruns do not
reset a selected range or manually chosen header. New source identities reset UI
choices and require a fresh review. Custom-range text has a non-widget backing key
to survive Streamlit's cleanup of progressively hidden widgets. Choosing a table
resets the header policy only in the explicit selection callback, never during a
normal rerun. The region dropdown starts with no selection instead of choosing the
first candidate implicitly.

The UI discovers relevant optional controls through the existing import planner,
using already-read worksheet records and cached header-policy context. No parallel
header validation or data-cleaning algorithm is introduced. Missing, non-text and
duplicate header failures are grouped for display with exact cell coordinates and
actionable repair guidance. Relevant or already-enabled controls remain visible;
repairs are never automatically checked. The source DataFrame, formula guards,
coordinate metadata, exporters, processing pipeline and backend APIs are unchanged.

The lifecycle is explicit:

```text
Select source/settings -> Load dataset -> Configure ordered steps
    -> Preview changes -> Review + Apply -> Prepare downloads -> Download

Source or configuration change -> clear preview, confirmation, and exports
Import failure                 -> retain original in memory, hide overview, block preview
Preview errors                 -> display partial result, block confirmation
```

Preview calls `ProcessingPipeline.run` once on the full original dataset. Apply
copies the reviewed result and report rather than recomputing. Export preparation
calls existing exporters once per format and retains bytes/errors for subsequent
reruns. Unrelated interactions such as table pagination and comparison layout do
not re-run processing or export. Download buttons use `on_click="ignore"` to avoid
an unnecessary processing rerun. Profiles are computed on load and supplied by the
pipeline for results; the UI does not implement its own statistics.

### Configuration and display adapters

Each card builds the existing `ProcessingStep` with typed widget parameters.
Constant input types are explicit; decimal constants use Decimal, booleans are
selected, and dates require ISO input. The backend still validates column/type
compatibility. The projected schema calls the existing header-normalization
operation on a zero-row DataFrame, allowing later selectors to show actual renamed
columns without performing row processing. If reordering makes a selection invalid,
it remains visible with a validation error instead of silently disappearing.

The pipeline's default stepwise error behavior remains unchanged. The dashboard
shows partial previews and original-row diagnostics, but deliberately disallows
confirming previews with errors. Disabling stop-on-error helps inspect more steps;
it does not override the confirmation gate. Warnings may be reviewed and confirmed.
The Python API remains available for explicitly managed partial-result workflows.

Tables use a display-only string copy of 100-row pages. This avoids Arrow coercion
of mixed numeric/text columns, exact Decimals, and large integers. Missing cells
stay null in the display. Page counts and total rows are visible; all pages are
accessible. This adapter is never input to processing or export. Streamlit's
`client.disableDataExport` is enforced in both configuration and application startup
to disable native table downloads/copy, which would bypass formula acknowledgment
and safe serialization. The Download section always exports the full confirmed
DataFrame. Full row/column counts are shown there explicitly.

Processing errors retain original values and are displayed with step summaries
and diagnostics. UI diagnostics use one-based original row ordinals (excluding
the header); the underlying JSON report retains zero-based positions. Expected
export failures are isolated by format so other downloads remain available. A
final UI exception boundary reports unexpected failures, logs details locally,
and invalidates derived results while preserving the original.

### Local operation and limits

`.streamlit/config.toml` sets the light theme, loopback binding, default 10 MiB
upload cap, and disabled usage telemetry. The user can tighten the per-file limit
in the UI. Raising the cap requires changing the server configuration/restarting,
then selecting a larger UI limit. XLSX expanded archive validation remains at
100 MiB. Uploaded data, full processing copies, and exports consume memory;
byte limits are not a guarantee of peak RAM usage. Sessions are transient and
workspaces are lost on reset/session loss/server restart. There is no database,
authentication layer, external processing API, or cloud deployment.

### Automated and manual verification boundaries

State tests exercise source/settings identity, invalidation, configuration order,
confirmation guards, non-mutation, complete exports despite display pagination,
typed constants, and worksheet discovery. Streamlit AppTest exercises actual
upload widget values and controls, worksheet selection, import failures, operation
editing/reordering, preview/apply, errors, reset, and download widgets/artifacts.
Original Phase 1/2 tests remain intact. Server smoke checks verify loopback HTTP
startup, the root page, and the health endpoint, then stop the owned server.

The targeted regression fixture `tests/fixtures/sayfa1.xlsx` is a byte-identical
copy of the supplied workbook, with an accompanying SHA-256. It actually contains
`eko` and empty `Sayfa2`; tests verify leading rows 1:5, columns A:C, both main
tables, detached cells and the F8 array formula. A separately labeled synthetic
sample adds trailing blanks, extra duplicate headers and additional mixed types.
AppTest verifies both import flows, separate-table switching, source/preview
invalidation, explicit formula export gates and original-byte preservation.

AppTest is headless: it does not establish pixel-level layout quality, native file
picker behavior, browser save dialogs, or spreadsheet application behavior. Those
remain explicit manual checks. Phase 4 adds the focused reliability work below;
Phase 5 publication work has not begun.

## Phase 4: formula and workflow reliability

### Formula references and export semantics

A flat export creates a new coordinate system and usually omits other sheets,
names, tables and external-workbook context. Relative-reference translation alone
cannot prove that a formula is valid: removing a blank column or filtering a row
can change references nonuniformly, and INDIRECT, structured references and array
formulas need workbook-level semantics. Consequently this engine deliberately has
**no executable-formula export mode**. Original definitions remain in memory;
the byte-for-byte original download is the preservation path. It does not repair
already broken source formulas or include cleaning changes.

After explicit acknowledgment, XLSX stores expressions as string cells and adds
cell comments explaining that references describe the source workbook and are
neither translated nor validated. CSV uses protected literal text. These notes and
export warnings cover omitted/moved cells without claiming a formula dependency
analysis. They do not change data values, coordinates, worksheet dimensions or the
processing report. No formula engine, workbook rewriting, or dependency was added.

The dashboard JSON report now adds `exports` (per-format success/failure,
protection counts and warnings) and `formula_loss_acknowledged`. These are artifact
diagnostics, separate from `ProcessingReport` and its unchanged schema/API. JSON
is prepared after CSV/XLSX; changing acknowledgment clears all cached artifacts,
so the report records the current decision. Existing source coordinates and source
SHA-256 remain present. Source selection/configuration changes revoke approval,
the preview, applied data and downloads as before.

### Preserving definitions during cleaning

Ordinary Excel formulas retain their existing string API. `excel_provenance`
derives a set of known source expressions from metadata; text cleaning skips
these and typed `ExcelFormula` values with per-cell warnings. Case-insensitive
duplicate comparison also preserves expression case, including quoted literals.
Expression-based protection intentionally includes literal strings matching known
formulas and copies introduced by explicit fills. It remains conservative after
formula rows are removed. External callers that drop metadata cannot recover
ordinary formula identity, but exporters still write all strings inertly.

The same helper module keeps source row numbers aligned for **standalone**
duplicate removal and missing-row removal, including repeated DataFrame index
labels. Pipeline provenance remains positional and compatible. Arbitrary external
pandas reshaping/reordering is outside this provenance contract.

### Resource and performance boundaries

Worksheet values are collected directly from the read-only iterator without first
retaining a second collection of openpyxl cell objects. Declared grids over
2,000,000 cells (including blanks) fail before materialization; a running cell
count also bounds workbooks without declared dimensions. There is no truncation.
The guard also applies to selected ranges because the current importer analyzes
the complete worksheet. Names-only discovery does not materialize cells. The UI
inspects every worksheet and rejects a workbook if any sheet exceeds the limit.
Existing upload/expanded-archive limits remain in force. These limits are not a
guarantee of peak RAM: multiple sheets, copies, comments and output buffers also
consume memory. No region-detection algorithm or public function signature changed.

The reproducible benchmark measures load, worksheet analysis, ordered processing
and both exports, with data-generation time excluded. It checks full output sizes,
non-mutation and absence of executable formulas. Formula comments add output size
and serialization time intentionally. Timings are observations rather than brittle
test thresholds. See [Phase 4 validation](phase4_validation.md) and the recorded
JSON results for the tested environment, exact outcomes and limitations.
