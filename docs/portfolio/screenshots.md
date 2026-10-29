# Real-interface screenshot checklist

Use the fictional [portfolio sales workflow](demo_workflow.md). Never use a private
upload for a public screenshot without clearance. The user-provided regression
workbook was cleared on 2026-10-29, but these captures continue to use synthetic data.
Do not generate an imitation UI, replace table values, hide warnings,
or add invented results to an image.

## Manual capture setup

1. Launch `python -m streamlit run app.py` from the repository root using the
   installed virtual environment. Open `http://127.0.0.1:8501` in a desktop browser.
2. Use a clean browser window, 100% zoom and approximately **1440 × 1050 CSS pixels**
   of content area. Close unrelated tabs/notifications and avoid exposing local
   paths or account details. Keep the sidebar open and use the bundled light theme.
3. Select **Reset workspace**, upload `sample_data/portfolio_sales_raw.csv`, then
   **Load dataset**. Verify 12 rows, 8 columns, 3 missing cells and 2 duplicates.
4. Follow all seven configuration steps in the walkthrough. Do not capture a
   transient error while a step's columns are still unselected.
5. Capture the actual viewport with your browser/OS screenshot tool. Save PNGs
   under `docs/screenshots/` using the names below. Do not alter table values or
   composite screenshots from different application states. Cropping browser chrome
   is acceptable if documented, but retain labels and relevant warnings.

## Required shots

| File | Capture steps | Check before keeping |
| --- | --- | --- |
| `01-dashboard-overview.png` | Before cleaning, use **02 · Data Overview** in the sidebar. Frame the four metrics and original table. | 12 / 8 / 3 / 2 metrics; synthetic source; leading-zero order IDs and inconsistent dates/text visible. |
| `02-cleaning-configuration.png` | Add all seven steps. Collapse completed steps, expand the date step if it fits, then navigate to **03 · Cleaning Configuration**. | Ordered operation labels; explicit date formats when expanded; no unresolved validation errors. |
| `03-before-after-results.png` | Click **Preview changes**, enable **Show original and result side by side**, and navigate to **04 · Results**. Capture before checking the approval box. | 10 / 8 / 0 / 0 result metrics; Original and Preview labels; review confirmation visible when viewport permits. |
| `04-downloads.png` (additional) | Review, check confirmation, apply, then prepare downloads. Navigate to **05 · Download**. | Complete 10-row/8-column export statement, CSV/XLSX/JSON buttons, and the Decimal precision warning. |

The tables have a fixed-height viewport and may require internal scrolling to see
every row/column; do not imply that a screenshot shows every value. Downloads remain
complete. Retake images after UI/data changes rather than leaving outdated metrics.

## Verification boundaries

On **2026-10-28**, all four shots above were captured from the real running
application in headless **Edge 156.0.4314.50**, at 1440 × 1050 and scale factor 1.
Automation used a temporary profile, DevTools file upload and normal browser
mouse/keyboard events to configure the documented workflow. Images are unedited
viewport captures; application state and table values were not injected. The
captures were visually inspected. See [the manifest](../screenshots/capture_manifest.json)
for file hashes and data provenance. These are automated browser captures, not
manual desktop/mobile testing or a recorded video.

- [Overview](../screenshots/01-dashboard-overview.png)
- [Cleaning configuration](../screenshots/02-cleaning-configuration.png)
- [Before/after results](../screenshots/03-before-after-results.png)
- [Downloads and precision warning](../screenshots/04-downloads.png)

Real screenshots show the rendered application at specific states. They do not
establish mobile responsiveness, keyboard accessibility, native file-picker/save
dialog behavior, full browser compatibility or Excel/LibreOffice rendering.
The release checklist and screenshot manifest record which captures were actually
produced. The manual steps remain the reproduction path without browser automation
dependencies. A narration script is supplied separately; no video is claimed.
