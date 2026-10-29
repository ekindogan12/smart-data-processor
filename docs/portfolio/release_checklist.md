# Release-readiness checklist

Prepared on 2026-10-28; clearance decisions updated on 2026-10-29. **Publication
requires review of the remaining audit findings and explicit approval.** No push, remote publication, deployment
or Upwork posting is authorized by this checklist.

## Prepared materials

- [x] Concise English README with installation, usage, stack, architecture, tests
  and formula/formatting limitations.
- [x] Existing detailed README contracts preserved in `docs/user_guide.md`.
- [x] Short project summary, role description, five skill tags and Upwork copy.
  Canonical title: **35 characters** (limit 40); description: **510** (limit 600).
- [x] Approximately 45–60 second demo narration and shot plan. No video claimed.
- [x] Clearly fictional CSV, documented seven-step settings, expected cleaned CSV,
  measured before/after profiles and a reproducible export script.
- [x] Manual screenshot steps and a checklist for the actual interface.
- [x] Four real desktop viewport screenshots captured from the running application
  using the synthetic sales data; visually inspected without pixel edits.
- [x] Existing application/backend modules and regression fixtures preserved.
- [x] No application dependency added; generated demonstration files are ignored.

## Repository and data audit

- [x] Reviewed the 51 previously tracked files. Existing XLSX binaries serve as
  sample data or regression fixtures; none is an executable/distribution bundle.
  New PNGs, if listed in the capture manifest, are intentional screenshot assets.
- [x] Checked tracked text for private-key blocks, common GitHub/AWS token patterns
  and quoted credential assignments. No matches were found in that limited scan.
- [x] Inspected 77 historical Git blobs across the five existing commits; scanned
  text blobs for private-key/GitHub/AWS credential patterns. No matches were found.
  This is a targeted review, not a comprehensive secret-detection guarantee; binary
  workbook contents/metadata are not cleared by these text scans.
- [x] Rechecked the final 71-file candidate tree (tracked plus non-ignored additions)
  for private-key/GitHub/AWS token patterns in text; no matches were found.
- [x] `.gitignore` now covers local credentials, Streamlit secrets, private-data
  directories, temporary logs, environments and generated demo/export files.
  Verified representative ignored paths without creating secret files. Synthetic
  samples and portfolio PNGs remain trackable.
- [x] `.gitattributes` pins the two portfolio CSVs to LF so the recorded source hash
  and expected export remain reproducible across Git line-ending configurations.
- [x] **`tests/fixtures/sayfa1.xlsx` is cleared for public redistribution.** The user
  explicitly confirmed this on **2026-10-29**. The workbook is already tracked in
  the current tree **and Git history**; its bytes, recorded hash and regression
  coverage remain unchanged. See [fixture provenance](../../tests/fixtures/README.md).
  A synthetic replacement or history rewrite is not needed for this clearance item.
- [x] **MIT License selected.** On **2026-10-29**, the user instructed preparation
  under MIT, replacing the earlier pending decision. The standard [LICENSE](../../LICENSE)
  records `Copyright (c) 2026 ekndg`, using the sole author identity in Git history.
  Package metadata references this file. No application functionality changed.
- [x] Fresh [public-release audit](release_audit.md): 71 tracked files, six commits
  and 104 historical blobs reviewed, including decompressed workbook XML and image
  metadata. No credential-pattern matches or unexpected tracked paths were found.
  The personal-email finding is resolved in the separate public checkout: all
  six commits use the approved noreply address for author and committer, with
  identical historical trees. The cleared workbook metadata remains unchanged.
- [x] Rechecked all 145 Git objects and 73 release-candidate files after the privacy
  cleanup. No personal-email matches or unexpected pending paths were found.
- [x] Project-local `.pytest_temp_release/` is writable and ignored. A full retry
  with a fresh `--basetemp` passed without changing system permissions or tests.

## Verification record

The demo-specific automated checks passed: **3 passed in 4.54 seconds**. These
exercise the command-line artifacts, actual Streamlit controls and Upwork limits.

Latest complete-suite command and actual outcome (public checkout, 2026-10-29):

```text
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest_temp_release/run-20261029
471 passed in 37.05s
```

The previous public-checkout attempt had 466 passes and five setup errors because
pytest could not access its existing system temporary directory. The approved
project-local basetemp retry above passed all 471 tests, with no failures, errors
or skips. No tests were modified or skipped. For later runs, use a fresh basetemp
child directory; pytest manages the contents of the selected directory.

Earlier results: private MIT preparation, 471 passed in 58.28 seconds; Phase 5,
471 passed in 33.01 seconds. All existing 468 tests and three portfolio checks
remain intact. Current environment: Windows, Python 3.13.9, pytest 9.2.0, pandas
3.1.0, openpyxl 3.1.5, Streamlit 1.66.1. The historical Phase 4 record remains in
[phase4_validation.md](../phase4_validation.md); its timings were not remeasured
or reused as new performance claims.

The demo script generated complete CSV/XLSX/JSON artifacts and before/after evidence:
12 rows / 3 missing cells / 2 duplicates became 10 / 0 / 0, with 8 columns retained.
Its input bytes stayed unchanged. The XLSX precision warning remains visible.

Real browser capture used headless **Edge 156.0.4314.50**, a temporary browser profile,
and a local Streamlit server. Browser mouse/keyboard events configured all seven
steps; file input was populated through DevTools; preview, side-by-side inspection,
confirmation and download preparation were exercised. Four unedited **1440 × 1050**
viewport PNGs were inspected. No application state or displayed values were injected.
Owned server/browser processes were stopped after capture. See the
[capture manifest](../screenshots/capture_manifest.json) for image/input hashes.
This does not claim native file-picker/save dialog testing, mobile testing or
opening downloaded files in Excel/LibreOffice.

Local documentation links and `git diff --check` were checked. The intended final
tree adds documentation, synthetic CSVs, scripts/tests and four purposeful PNGs;
generated XLSX exports, debug logs and browser automation scratch files stay ignored.

## Before an approved public release

- [x] Resolve the workbook redistribution and repository license decisions.
- [x] Resolve the commit-email exposure and verify the approved rewrite in the
  public checkout. All six author/committer emails use the GitHub noreply address;
  the private original remains unchanged. See the [2026-10-29 audit](release_audit.md).
- [x] Pass all 471 tests using a fresh, Git-ignored project-local temporary directory.
- [ ] Review and commit the nine pending license/release paths, including the
  `.gitignore` update, with the verified local noreply identity. No commit exists
  yet for these pending changes. Keep the original backup private.
- [ ] Review the exact files that will be staged with `git status --short`,
  `git diff --stat`, and `git diff --cached --stat` after staging. Review names and
  content rather than blindly using `git add .`.
- [ ] Review the intended public Git history before an approved push. The workbook's
  redistribution clearance is recorded above; publication itself is not yet approved.
- [ ] Re-run `python -m pytest -q` in the installed environment after any further
  source, fixture or dependency changes.
- [ ] Check layout and keyboard use in a normal desktop browser and at a narrow
  viewport. Exercise native file selection, saving downloads and opening them in
  Excel/LibreOffice. Headless screenshots and AppTest do not establish these checks.
- [ ] Verify installation on the other claimed Python/OS/dependency targets, or
  continue to disclose the single tested environment.
- [ ] Review the Upwork copy for accurate personal role/skill claims, select tags
  available in the actual editor, and record the demo if desired.
- [ ] Obtain explicit approval before pushing, creating a public repository/release,
  deploying the app or posting the portfolio entry. No such action has been taken.
