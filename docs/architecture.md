# Phase 1 and Phase 2 architecture decisions

The proposal is the specification; its phase boundaries take precedence over the
full-product acceptance criteria. The current deliverable is a tested Python
library for imports, profiling, cleaning, transformations, ordered processing,
structured reports, and safe exports. Exports were explicitly requested for
Phase 2; the Streamlit interface remains deferred to Phase 3.

## Module boundaries

`file_handler` owns bytes, encoding, CSV records, workbook access, and resource
cleanup. `validators` defines shared header/DataFrame contracts and two public
ValueError subclasses so a future UI can display actionable validation failures.
`profiler` produces immutable dataclasses with detached dictionary conversion;
it has no file output responsibilities. `cleaner` accepts and returns DataFrames,
allowing scripts, tests, and a later UI to use the same engine.

`transformer` owns explicit text/header normalization and numeric/date conversion.
`models` contains shared operation results and diagnostics. `pipeline` orchestrates
operations and translates row provenance; `reporter` defines audit records and
byte serialization. The two additional modules keep orchestration separate from
individual operations and avoid circular imports.

`app.py` remains an empty documented entry point. The screenshot directory reserves
future interface documentation. Phase 1 loaders, profiling, and duplicate removal
remain intact; a pipeline adapter adds duplicate-removal provenance without
changing its existing DataFrame-returning API.

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

Only pandas and openpyxl are runtime dependencies. The standard library handles
encoding, CSV parsing, archive validation, paths, and profile data structures.
Pytest is the only test dependency. Editable package installation avoids runtime
path manipulation in tests. Tests use temporary files and in-memory workbooks,
plus the committed synthetic samples for end-to-end coverage. They check source
preservation, malformed inputs, encoding/worksheet selection, profile statistics,
duplicate options, all-null and typed fills, locale-configured numeric parsing,
ambiguous dates, pipeline order/provenance/error policy, JSON reports, formula
protection in headers and cells, precision preservation, and export limits.

Python 3.11+ is the declared target; the test results reported at implementation
time cover the available local interpreter, not a full cross-version matrix.
No new runtime dependencies were needed for Phase 2. No database, web framework,
plotting package, or cloud service is required.

## Phase 3 boundary

The next phase can provide upload and worksheet controls, ordered step configuration,
before/after previews, explicit application confirmation, visible diagnostics, and
download controls backed by these APIs. It should display stopped/partial execution
and export protection warnings. There is no Streamlit implementation in this phase.
