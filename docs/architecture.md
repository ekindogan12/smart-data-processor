# Phase 1 architecture decisions

The proposal is the specification; its phase boundaries take precedence over the
full-product acceptance criteria. The current deliverable is a tested Python
library for imports, basic profiling, missing detection, and duplicate handling.

## Module boundaries

`file_handler` owns bytes, encoding, CSV records, workbook access, and resource
cleanup. `validators` defines shared header/DataFrame contracts and two public
ValueError subclasses so a future UI can display actionable validation failures.
`profiler` produces immutable dataclasses with detached dictionary conversion;
it has no file output responsibilities. `cleaner` accepts and returns DataFrames,
allowing scripts, tests, and a later UI to use the same engine.

The proposed `transformer`, `reporter`, and `app.py` files are documented empty
modules. Implementations and tests for those later-phase features are intentionally
deferred. The screenshot directory reserves the proposal's documentation layout.

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
per column. No whitespace, date, or numeric normalization occurs. pandas determines
duplicate and missing-key equivalence; the index is excluded from comparison.
Positional filtering keeps repeated index labels correct. A deep DataFrame copy
ensures edits to returned scalar cells cannot affect the original. pandas deep
copies do not recursively clone nested Python objects; those are outside the
spreadsheet cell contract.

## Dependency and verification choices

Only pandas and openpyxl are runtime dependencies. The standard library handles
encoding, CSV parsing, archive validation, paths, and profile data structures.
Pytest is the only test dependency. Editable package installation avoids runtime
path manipulation in tests. Tests use temporary files and in-memory workbooks,
plus the committed synthetic samples for end-to-end coverage. They check source
preservation, malformed inputs, encoding/worksheet selection, profile statistics,
duplicate options, Unicode behavior, and repeated index labels.

Python 3.11+ is the declared target; the test results reported at implementation
time cover the available local interpreter, not a full cross-version matrix.
No database, web framework, plotting package, cloud service, or export code is
needed in Phase 1.
