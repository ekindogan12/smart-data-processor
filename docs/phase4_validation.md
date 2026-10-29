# Phase 4 validation and readiness

Validated locally on 2026-10-28. This is the historical Phase 4 record, from before
Phase 5 preparation. See the [current release checklist](portfolio/release_checklist.md)
for subsequent tests, screenshot captures and publication status.

## Findings and fixes

The existing exporters already prevented executable formulas and required explicit
acknowledgment for imported formula data. The audit found additional reliability
gaps and fixed them without changing public function signatures or region detection:

- Text normalization could change ordinary formula strings, including quoted
  literals. Known expressions and typed array formulas now stay unchanged, with
  `formula_preserved` diagnostics. Case-insensitive duplicate comparison also keeps
  known formula expressions case-sensitive.
- Direct duplicate/missing-row removal retained outdated source row coordinates.
  Both standalone operations now keep coordinates aligned, including when index
  labels repeat. Original data and metadata remain independent.
- Export warnings did not explain relocated references concretely. Warnings now
  state that references describe the original workbook, may point to omitted/moved
  cells and are not translated or validated. Exported XLSX formula-text cells carry
  explanatory notes. The dashboard JSON download records per-format export status,
  protection counts, warnings and acknowledgment, including failed exports.
- Archive size limits did not bound a sparse worksheet's addressed grid. Inspection
  now rejects grids over 2,000,000 cells including blanks, before materialization
  when dimensions are declared, and checks a running count otherwise. It never
  truncates. The loader also avoids retaining an extra full list of openpyxl cells.

The real `sayfa1.xlsx` fixture demonstrates why executable formula relocation is
unsafe: importing `eko!K6:N9` moves `N7` to `D2`, while its original expression is
`=L7+M7`. The exported sheet contains only A:D and rows 1:4. That expression is
preserved as a string with a warning note, never an executable formula or a claimed
valid `=B2+C2` rewrite. The exact original workbook remains the preservation option.
No formulas are calculated, dependency-resolved, repaired or translated.

## Workflow audit

| Stage | Automated coverage and outcome |
| --- | --- |
| Upload | Valid CSV/XLSX, encoding/delimiter settings, empty/corrupt/oversized files, worksheet changes, and non-mutation pass. Oversized-grid failure hides previous results and downloads while retaining the original internally. |
| Table selection | Real D6:H12/K6:N9 candidates, detached cells, explicit full-sheet/custom ranges, separate/combine modes, blank rows/columns and deterministic header repair remain covered. No default merge or removal added. |
| Cleaning | Ordered operations, original-value retention on conversion errors, formula-safe text operations, duplicate comparison and source-coordinate filtering pass. |
| Preview/confirmation | Source/settings changes invalidate previews; confirmation gates remain mandatory. Reruns preserve current artifacts; changing operations or formula acknowledgment clears stale downloads. |
| Download | CSV escaping, XLSX literal string cell types, raw worksheet XML without executable formula nodes, complete dimensions, JSON diagnostics, original bytes, and format-specific errors pass. |
| Local server | Streamlit startup on loopback, root HTML HTTP 200 and health endpoint HTTP 200 (`ok`) passed. The test-owned server was stopped. This is not a browser test. |

Formula regressions include relative, absolute and mixed references; ranges;
omitted/blank cells; other worksheets; external workbooks; named and structured
references; INDIRECT; existing `#REF!`; quoted literals; dynamic expressions; and
typed array formulas. They verify literal preservation and safe exports, not
Excel expression validity. Existing strict-header and repair tests remain intact.

## Exact test results

Environment: Windows 11 (10.0.26200), Python 3.13.9, pytest 9.1.1, pandas 3.1.0,
openpyxl 3.1.5, Streamlit 1.66.1, using the repository's installed virtual environment.

```text
Before changes: .\.venv\Scripts\python.exe -m pytest -q
440 passed in 25.69s

Final full suite: .\.venv\Scripts\python.exe -m pytest -q
468 passed in 56.12s
```

All 440 existing tests were preserved; 28 new regressions were added. The final
suite had no failures or skips. Streamlit AppTest executed the actual widget and
session-state workflows; it did not drive a browser. `git diff --check` also passed.

## Performance observations

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_phase4.py --output docs/phase4_benchmark.json
```

The deterministic datasets contain realistic IDs, text, numeric fields, dates,
blanks and duplicates. The XLSX table starts at D6 and contains 10,000 source
formulas. The pipeline trims customer names and explicitly removes duplicates.
Input generation and output verification are excluded from individual stage
timings. All dimensions/non-mutation/no-executable-formula assertions passed.

| Dataset | Input → output rows | Columns | Analysis | Load | Pipeline | CSV export | XLSX export |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV, 2,652,050 bytes | 51,000 → 50,000 | 8 | N/A | 0.1221 s | 0.3914 s | 0.6827 s | 10.5282 s |
| XLSX, 307,800 bytes | 10,000 → 10,000 | 8 | 1.5631 s | 1.4566 s | 7.3010 s | 1.1431 s | 4.4281 s |

[Final measurements](phase4_benchmark.json) and the
[pre-change baseline](phase4_benchmark_before.json) record exact environment,
dimensions, file sizes and stage timings. These are individual local runs, not
statistical benchmarks or speedup claims. Scheduling/caching cause variation;
formula metadata copying and the added XLSX comments have real costs. No peak-RAM,
concurrent-session, maximum-size or cross-platform benchmark was performed. The UI
remains synchronous; larger operations may take seconds and show a spinner.

## Limits and publication readiness

The application is ready for a local portfolio demonstration in the tested
environment. Public publication still needs the Phase 5 work and the following
manual/compatibility verification:

- Desktop/mobile layout, keyboard navigation, native file-picker/save dialogs and
  real-browser downloads have not been manually verified in this phase.
- Excel/LibreOffice rendering of comments, CSV import behavior and recalculation
  behavior have not been manually verified. Automated checks inspect actual XLSX
  XML and cell types and confirm that no executable formulas are emitted.
- Formula functionality, formatting, merged-cell behavior and workbook context
  are preserved only by the unchanged original-file download. It contains no
  cleaning changes and cannot fix an originally broken formula. Flat exports
  require acknowledgment and retain definitions as protected text.
- Worksheet inspection is limited to 2,000,000 addressed cells per sheet, including
  blanks, even for selected-range imports. The UI inspects all sheets; one oversized
  sheet blocks the workbook. Byte limits and this guard do not guarantee peak RAM.
- Only the dependency versions/OS listed above were executed. The full declared
  Python/dependency range still needs a compatibility matrix. Processing remains
  local and in memory, with no persistence or background job service.
- License selection, screenshots, demonstration video and publication materials
  remain Phase 5 tasks. No publication or deployment was performed.
