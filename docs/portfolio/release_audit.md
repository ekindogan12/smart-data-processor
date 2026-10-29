# Public-release privacy verification — 2026-10-29

**Privacy and history-preservation checks passed, and all 471 tests now pass.**
The approved retry used a fresh, writable project-local temporary directory.
The earlier five setup errors and their cause are retained below as history.
No application logic, tests, dependency specifications, system permissions or
original-repository files were changed. No further history rewriting,
line-ending normalization, push, publication or deployment was performed.

## Verified public checkout

Verification ran against `C:\Github\smart-data-processor-public`. The original
`C:\Github\smart-data-processor` remains the private backup and was not modified
by this work. The earlier approved rewrite used git-filter-repo 2.47.0 on a
separate `git clone --no-local` checkout; this continuation did not rewrite again.

- All **six reachable commits** use
  `99815817+ekindogan12@users.noreply.github.com` as both author and committer email.
  The public repository's local email and effective author/committer identities
  also use that address. Global Git configuration was not changed.
- Each rewritten commit was compared against its original Git object. Only the
  authorized email replacement and parent commit IDs differ. Messages, author
  and committer names, both dates and timezone offsets, and other commit content
  are preserved. All **six historical tree IDs are identical**, preserving
  historical file contents, paths and modes independently of checkout endings.
- The public checkout has only `refs/heads/main`, at
  `d63ee713b1ee0ff06f1402442ec70b1c2a101916`. No remote, old-history ref,
  replacement ref, remote-tracking ref, Codex snapshot ref, reflog entry,
  alternate object store or unreachable object remains. No seventh commit exists.
- Scanned all **145 stored/reachable Git objects**: six commits, 35 trees and
  104 blobs. Also scanned all **73 release-candidate files** (71 tracked plus two
  pending additions), decompressed workbook archive members and local Git
  administrative files for the old personal address. **No personal-email matches
  were found.** Email-pattern matches in publication content use only
  `example.com` and `users.noreply.github.com`. The private address is not printed
  in this report. `git fsck --full --no-reflogs` passed.
- Rechecked **327 previously recorded private-source file hashes**, including
  tracked files, pending release files and Git metadata, plus working-tree status
  and non-Codex refs. They matched the pre-cleanup baseline. Tool-maintained
  ephemeral Codex snapshot refs are excluded from this source comparison.

| Original commit | Public commit |
| --- | --- |
| `e31fa89` | `fba74e6` |
| `09275b6` | `c97d79d` |
| `b3cd631` | `6f9c25a` |
| `eda3a1b` | `1e322ea` |
| `aab892a` | `cd9eb46` |
| `b260acc` | `d63ee71` |

## Accepted Windows checkout differences

The previous byte-for-byte working-file check stopped on **49 text files** that
use CRLF in the Windows checkout instead of LF in the private working copy.
The user approved continuation on 2026-10-29 provided these were exclusively
line-ending differences and the historical Git trees were identical.

Both conditions passed. For each differing file, replacing CRLF with LF **in
memory for comparison only** produced identical bytes. No non-line-ending
content discrepancy was found. Historical Git objects are the preservation
baseline; no file was rewritten or normalized to satisfy the check. Existing
`.gitattributes` rules, including LF for the two portfolio CSVs, remain unchanged.
The audit/checklist updates and the new project-local test-directory ignore rule
are intentional release changes, separate from those 49 original checkout-only
differences. The current comparison finds 48 files with only line-ending
differences; `.gitignore` is now the remaining file with the explicitly approved
three-line addition. Application code and tests still have no content changes.

## MIT license, release files and workbook

The original eight pending release files remain present, plus `.gitignore`:

- `.gitignore`
- `LICENSE`
- `README.md`
- `pyproject.toml`
- `docs/architecture.md`
- `docs/user_guide.md`
- `docs/portfolio/release_checklist.md`
- `docs/portfolio/release_audit.md`
- `tests/fixtures/README.md`

The eight original files were copied byte for byte from the private repository.
This audit and the release checklist now record the successful verification; the
other six still match their private-source copies byte for byte. `.gitignore`
adds only a comment, spacing and `/.pytest_temp_release/`. The standard MIT text,
`Copyright (c) 2026 ekndg`, package license reference and fixture clearance remain
intact. All **nine pending paths** are uncommitted and must be reviewed and
committed before publication. No other tracked file changed; no test output or
environment file is tracked. There are still 71 tracked files plus two pending
additions (`LICENSE` and this audit). Nothing is staged.

The user's 2026-10-29 redistribution clearance for `sayfa1.xlsx` remains recorded
in [fixture provenance](../../tests/fixtures/README.md). The actual workbook
matches its recorded SHA-256:

```text
021b6691857db0867b75467344ea7e67adaca9e38b7e7e888b7cb63ceb81d685
```

The workbook's previously disclosed personal `lastModifiedBy` metadata is retained
as part of the cleared, unmodified fixture. No workbook values or metadata changed.

## Actual complete-suite result — successful retry

The user authorized a fresh project-local temporary directory on 2026-10-29.
Created `.pytest_temp_release`, verified it was writable, and verified that the
new root ignore rule excludes its contents from Git. The selected basetemp
`run-20261029` did not exist before pytest ran. No existing system temporary
directory was reused, deleted or given different permissions.

Executed from `C:\Github\smart-data-processor-public`:

```text
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest_temp_release/run-20261029
471 passed in 37.05s
```

Exit code: **0**. All 471 tests passed; no failures, errors or skips were reported.
The five previously blocked tests ran successfully. Full output is retained
locally in ignored `.pytest_temp_release/pytest-release.txt`. The temporary
artifacts are untracked and were not deleted after the run. For a future rerun,
choose a new basetemp child directory; pytest manages the contents of its selected
basetemp, so do not point it at unrelated or valuable files.

The public checkout's environment remains Python 3.13.9, pytest 9.2.0, pandas
3.1.0, openpyxl 3.1.5 and Streamlit 1.66.1 on Windows. The application imports from
this checkout's `src` directory. No test was changed, hidden or skipped. The
measured duration is a test-run observation, not a performance claim.

After the run, rechecked Git-object/email preservation, license and fixture
hashes, the exact pending file list and ignore behavior. The original private
repository still matches the recorded source baseline. `git fsck --full
--no-reflogs` and `git diff --check` passed. Only the nine intended pending release
paths are exposed by Git status; the local test artifacts remain ignored.

## Previous complete-suite attempt — setup errors, now resolved

Executed in the public checkout using its own virtual environment installed from
the unchanged `requirements.txt`. Before running, verified that the application
imports from the public checkout's `src` directory.

```text
.\.venv\Scripts\python.exe -m pytest -q
466 passed, 5 errors in 47.20s
```

Exit code: **1**. Five tests errored during setup involving pytest's `tmp_path`
fixture. The traceback reports `PermissionError: [WinError 5] Access is denied`
when enumerating the existing `%LOCALAPPDATA%\Temp\pytest-of-ekndg` directory.
This was an environment/setup blocker in that earlier run. The following five
tests did not complete then; all passed in the approved retry above:

- `tests/test_excel_import.py::test_workbook_bytes_paths_and_stream_positions_are_preserved`
- `tests/test_excel_layout.py::test_separate_regions_fail_atomically_and_source_bytes_unchanged`
- `tests/test_file_handler.py::test_csv_preserves_values_and_original_file`
- `tests/test_file_handler.py::test_missing_file_and_directory`
- `tests/test_portfolio.py::test_demo_script_exports_expected_values_and_preserves_source`

Environment: Windows, Python 3.13.9, pytest 9.2.0, pandas 3.1.0, openpyxl 3.1.5 and
Streamlit 1.66.1. The fresh installation selected pytest 9.2.0 within the existing
constraints; no dependency specification or test was changed. Work initially
stopped on these errors. The subsequent retry above was explicitly approved and
did not change permissions or delete unrelated temporary directories.

## Remaining release blockers and limitations

No test or commit-email blocker remains in the verified public checkout. It is
ready for final review and a release-preparation commit. Before publication:

1. Review and commit the **nine pending paths** using the verified noreply
   identity; inspect the staged file list and final history. No commit was made
   during this verification. See the [release checklist](release_checklist.md).
2. Confirm the intended GitHub destination and obtain separate publication
   approval. No remote is configured and no push was performed or authorized.
3. Complete or disclose the remaining native file/save-dialog, mobile/keyboard/
   accessibility, Excel/LibreOffice and cross-platform checks. No new browser or
   manual spreadsheet verification was performed during this cleanup.

The personal-email finding is resolved for the public checkout, but the original
private backup intentionally retains the old history and email. Keep it private.
Local verification cannot determine whether an older copy was shared elsewhere;
no remote repository, external cache, fork or account was inspected. This targeted
scan is not a guarantee that every possible secret or identifying detail is absent.

The earlier MIT audit below is retained as a historical record. Its statements
about exposed commit email, no rewrite and passing tests apply to the private
repository before cleanup. The verified identities and **successful project-local
basetemp run above** are the current status for the public checkout.

---

## Earlier MIT preparation audit — before privacy cleanup

MIT licensing and the requested verification are complete. No application code,
fixture bytes or Git history was changed. No push, publication or deployment was
performed. Review the personal-data finding below before approving a public push.

### License and copyright identity

The user selected the **MIT License** on 2026-10-29. The root [LICENSE](../../LICENSE)
uses the standard [Open Source Initiative MIT text](https://opensource.org/license/mit)
and `Copyright (c) 2026 ekndg`. All six existing commits identify their author as
`ekndg`, the configured Git author name; their author dates are in 2026. No legal
name, organization or contact address was invented for the notice.

`pyproject.toml` references the LICENSE file using the file-based license metadata
supported by the existing setuptools requirement. No dependency constraint or
application behavior changed. A package build was not part of this verification.

### Audit scope and method

- Reviewed **71 tracked files**, all **6 commits reachable from all local refs**,
  and **104 historical blobs**. No remote was configured at audit time.
- Scanned text and decompressed XLSX XML/relationship parts for private-key blocks,
  GitHub/AWS/Google/Slack credential formats, quoted credential assignments,
  authenticated URLs, absolute user-directory paths and email addresses.
- Checked tracked/historical paths for local environments, secret files, private
  data directories, logs, temporary files, compiled Python files and key containers.
- Inspected all three XLSX archives for author metadata, external relationships,
  external-link and embedded parts, and non-XML binary content.
- Checked the four PNGs for metadata and verified their hashes against the existing
  capture manifest. They are unchanged synthetic-data screenshots from Phase 5;
  no new browser capture or manual spreadsheet test was performed in this audit.
- Checked fixture SHA-256, license metadata syntax, documentation links and
  `git diff --check`. Temporary audit output stays under ignored `.demo-output/`.

This is a targeted pattern/content review, not a guarantee that every possible
secret or category of personal information can be detected. It covers the current
tree and reachable local history, not remote repositories, unreachable objects,
ignored private files or external accounts. Credential values and personal names
were not copied into this report.

### Findings

| Area | Finding | Disposition |
| --- | --- | --- |
| Credentials | No credential-pattern matches in the scanned text or workbook XML. No authenticated URLs or absolute user-directory paths matched. | No credentials removed or rotated. |
| Commit metadata | All six commits contain one personal **Gmail address** in author/committer metadata, alongside the public alias `ekndg`. | Publishing this history exposes that address. Review whether to retain it publicly or separately authorize a history rewrite. No history was rewritten and no new public copy of the address was added to documentation. |
| Workbook metadata | `tests/fixtures/sayfa1.xlsx` contains a personal `lastModifiedBy` value. | Retained as part of the exact workbook explicitly cleared for redistribution. The clearance applies to this unchanged fixture; no additional clearance has been invented for other private data. |
| Sample content | Email matches in CSV, sample-generator code and the synthetic sales workbook use `example.com`. Sample records are documented as fictional. | Intentional demonstration content. |
| XLSX containers | Three workbook blobs; no external relationships, external-link parts, embedded objects or non-XML binary parts found. | Retained as intentional samples/regression data. Formulas remain subject to the documented export restrictions. |
| Screenshots | Four PNGs; no metadata fields exposed by Pillow, and all hashes match the capture manifest. | Intentional portfolio assets; no regenerated or edited images. |
| Unintended files | No matching environment, secret, log, temporary, compiled-code or key-container paths in tracked files/history. | Ignore rules continue to exclude local data, environments, debug files and generated exports. No private dataset beyond the disclosed, cleared regression fixture was identified. |

To inspect the existing commit contact address locally without copying it into a
public document:

```powershell
git log --all --format="%h %an <%ae>"
```

Changing Git configuration alone would affect future commits, not remove the
address from this history. History rewriting is deliberately outside this task.

### Workbook redistribution verification

The user's **2026-10-29** confirmation is recorded in
[tests/fixtures/README.md](../../tests/fixtures/README.md). The actual workbook
matches `tests/fixtures/sayfa1.sha256`:

```text
021b6691857db0867b75467344ea7e67adaca9e38b7e7e888b7cb63ceb81d685
```

The workbook, recorded hash and test coverage were not modified. Its presence in
Git history is known and is no longer a redistribution-clearance blocker.

### Exact test result

```text
.\.venv\Scripts\python.exe -m pytest -q
471 passed in 58.28s
```

No failures or skips were reported. All existing tests remain intact. Environment:
Windows 11, Python 3.13.9, pytest 9.1.1, pandas 3.1.0, openpyxl 3.1.5 and Streamlit
1.66.1. This is a fresh full-suite run; the earlier Phase 5 result was 471 passed
in 33.01 seconds. Test durations are observations, not performance claims.

### Readiness

The local repository has its MIT license, documented fixture clearance and passing
tests. Before approving publication, review the commit-email exposure and the
remaining manual/compatibility checks in the [release checklist](release_checklist.md).
Native file/save dialogs, mobile/accessibility coverage and Excel/LibreOffice
rendering remain unverified. No remote action is authorized by this report.
