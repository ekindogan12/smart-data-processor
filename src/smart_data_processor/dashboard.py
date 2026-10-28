"""Streamlit presentation and widget wiring; processing lives in the engine."""

from dataclasses import asdict
import hashlib
import logging
from math import ceil
from pathlib import Path
import re
from uuid import uuid4

import pandas as pd
import streamlit as st

from .dashboard_state import (
    ImportOptions, Workspace, columns_after_steps, display_page, fingerprint, parse_constant,
    region_card_preview, select_region_controls, summarize_regions,
    clear_import_review, initialize_excel_controls, relevant_import_controls, header_problem_messages,
)
from .file_handler import inspect_xlsx_import, inspect_xlsx_layouts
from .excel_import import preview_import, region_import_options
from .excel_layout import spans
from .pipeline import ProcessingStep
from .validators import DataValidationError, FileValidationError, validate_columns


OPERATIONS = {
    "Remove duplicates": "remove_duplicates",
    "Handle missing values": "handle_missing",
    "Clean text": "clean_text",
    "Normalize column names": "normalize_column_names",
    "Convert numbers": "convert_numeric",
    "Standardize dates": "standardize_dates",
}
DELIMITERS = {"Detect automatically": None, "Comma (,)": ",", "Semicolon (;)": ";", "Tab": "\t", "Pipe (|)": "|", "Custom": "custom"}
THOUSANDS = {"None": None, "Comma (,)": ",", "Dot (.)": ".", "Space": " ", "Nonbreaking space": "\u00a0", "Apostrophe (')": "'"}


def _workspace() -> Workspace:
    if "workspace" not in st.session_state:
        st.session_state.workspace = Workspace()
        st.session_state.queue = []
    return st.session_state.workspace


def _reset() -> None:
    st.session_state.clear()
    st.session_state.upload_epoch = uuid4().hex


def _style() -> None:
    st.set_page_config(page_title="Smart Data Processor", page_icon="▦", layout="wide")
    # Also enforce when launched outside the checkout/config directory.
    st.set_option("client.disableDataExport", True)
    # Static CSS only. Uploaded text is never interpolated into HTML.
    st.markdown("""
    <style>
      .block-container {max-width: 1480px; padding-top: 2rem; padding-bottom: 4rem;}
      [data-testid="stMetric"] {background: #FFFFFF; border: 1px solid #DCE4EC;
        border-radius: 10px; padding: 16px 20px;}
      [data-testid="stMetricLabel"] {color: #526477;}
      h1 {letter-spacing: -0.035em;}
      h2 {letter-spacing: -0.02em; padding-top: 1rem;}
      @media (max-width: 700px) {
        .block-container {padding-left: 1rem; padding-right: 1rem;}
      }
    </style>
    """, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("### Smart Data Processor")
        st.caption("LOCAL DATA WORKSPACE")
        st.divider()
        for label, anchor in [("01 · Upload", "upload"), ("02 · Data Overview", "data-overview"),
                              ("03 · Cleaning Configuration", "cleaning-configuration"),
                              ("04 · Results", "results"), ("05 · Download", "download")]:
            st.markdown(f"[{label}](#{anchor})")
        st.divider()
        st.caption("Your files stay on this computer. Changes are applied only after you review and confirm a preview.")
        st.button("Reset workspace", key="reset_workspace", on_click=_reset, width="stretch")
    st.caption("LOCAL WORKSPACE  /  DATA QUALITY")
    st.title("Smart Data Processor")
    st.write("Turn messy spreadsheets into dependable data. Inspect, configure, preview, then apply.")


def _select_region_card(cell_range: str, available: tuple[str, ...]) -> None:
    select_region_controls(st.session_state, cell_range, available)


def _select_region_dropdown(available: tuple[str, ...]) -> None:
    region = st.session_state.get("excel_selected_region")
    if region is not None:
        select_region_controls(st.session_state, region, available)


def _remember_custom_range() -> None:
    # A non-widget key survives progressive disclosure hiding the text input.
    st.session_state.excel_custom_range = st.session_state.excel_range


def _region_card(layout, region) -> None:
    with st.container(border=True):
        st.markdown(f"**{region.cell_range}**")
        st.caption(f"{region.kind} · {region.cell_range} · {region.rows} rows × {region.columns} columns, including any header")
        st.write(f"Contains {region.formula_count} formula {'cell' if region.formula_count == 1 else 'cells'}" if region.formula_count else "No formula cells")
        selected = (st.session_state.get("excel_region_mode") == "Select a detected region"
                    and st.session_state.get("excel_selected_region") == region.cell_range)
        st.button(
            ("Selected " if selected else "Select ") + region.cell_range,
            key=f"region_card_{region.cell_range}", width="stretch",
            type="primary" if selected or (region.kind == "Table candidate" and st.session_state.get("excel_region_mode") == "Choose a table") else "secondary",
            on_click=_select_region_card, args=(region.cell_range, layout.regions),
            help="Select this region for import review. Nothing is imported until you approve the plan and load it.",
        )
        st.dataframe(region_card_preview(layout, region), height=145, width="stretch")
        st.caption(f"Preview: first {min(3, region.rows)} of {region.rows} rows and {min(4, region.columns)} of {region.columns} columns. Import includes the full selected region.")


def _worksheet_structure(layout, key) -> None:
    """Compact discovery UI; classifications and samples never alter engine output."""
    if st.session_state.get("region_summary_key") != key:
        st.session_state.region_summaries = summarize_regions(layout)
        st.session_state.region_summary_key = key
    regions = st.session_state.region_summaries
    initialize_excel_controls(st.session_state, key, regions)
    candidates = sum(item.kind == "Table candidate" for item in regions)
    isolated = sum(item.kind == "Isolated cell" for item in regions)
    st.write("**Worksheet at a glance**")
    summary = [("Worksheet size", f"{layout.rows} rows × {layout.columns} columns"),
               ("Table candidates", str(candidates)), ("Isolated regions", str(isolated)),
               ("Formula cells", str(len(layout.formulas)))]
    for column, (label, value) in zip(st.columns(4), summary):
        with column:
            with st.container(border=True):
                st.caption(label)
                st.markdown(f"**{value}**")
    other = len(regions) - candidates - isolated
    if other:
        st.caption(f"Also detected: {other} small or narrow region(s). They remain available below.")
    st.caption("Select a table to review its range and header row. Candidates are suggestions, not verified tables; no region is imported until you choose and confirm it.")
    featured = tuple(region for region in regions if region.kind == "Table candidate")[:2]
    others = tuple(region for region in regions if region not in featured)
    for column, region in zip(st.columns(2), featured):
        with column:
            _region_card(layout, region)
    if others:
        with st.expander(f"Other regions ({len(others)}) — inspect and import", expanded=False):
            st.info("These regions are retained. Select one below to inspect/import it, or choose Import all regions separately to include every region.")
            for region in others:
                _region_card(layout, region)
    with st.expander("Advanced Details", expanded=False):
        st.write("Display heuristic: a table candidate has at least 2 rows, 2 columns and 4 populated cells. A 1×1 region is an isolated cell; other shapes are small/narrow regions. Size means bounding rows × columns, including blanks and any header; ties use worksheet row/column order. These labels never change detection or import boundaries.")
        for label, values in [("Leading blank rows", layout.leading_rows), ("Trailing blank rows", layout.trailing_rows),
                              ("Leading blank columns", layout.leading_columns), ("Trailing blank columns", layout.trailing_columns),
                              ("All blank rows", layout.blank_rows), ("All blank columns", layout.blank_columns)]:
            st.write(f"{label}: {', '.join(values) or 'None'}")
        st.write("Detected source ranges: " + (", ".join(layout.regions) or "None"))
        if layout.formulas:
            st.dataframe(pd.DataFrame(layout.formulas, columns=["Source cell", "Formula expression"]), hide_index=True, width="stretch")
            st.dataframe(pd.DataFrame(layout.formula_details, columns=["Source cell", "Formula kind", "Formula reference"]), hide_index=True, width="stretch")
        st.caption("Connected cells can include unrelated data. Sparse tables may split into several regions; touching tables may share a region. Review the values and use a custom range if needed.")


def _excel_import_options(payload: bytes, filename: str, sheet, limit: int, layout) -> tuple[dict, str | None, bool]:
    """Render a cached, exact import plan and collect approval for that plan only."""
    if layout.empty:
        initialize_excel_controls(st.session_state, (hashlib.sha256(payload).hexdigest(), filename, sheet), ())
        st.info(f"Worksheet {sheet!r} is empty. Select a worksheet containing data.")
        return {}, "The selected worksheet is empty.", False
    if any(expression is None for coordinate, expression in layout.formulas):
        st.warning("This sheet contains an array/data-table formula that cannot be represented safely in a flat table. Select a range without it, or retain the original workbook.")
        st.download_button("Download unchanged original workbook", payload, file_name=filename,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="download_unsupported_original", on_click="ignore")
    _worksheet_structure(layout, (hashlib.sha256(payload).hexdigest(), filename, sheet))
    cell_range = None
    with st.expander("Advanced import options", expanded=False):
        mode = st.selectbox("Region import mode", ["Choose a table", "Worksheet / custom range", "Select a detected region",
                            "Import all regions separately", "Combine regions in worksheet alignment"], key="excel_region_mode")
        if mode == "Worksheet / custom range":
            cell_range = st.text_input(
                "Excel cell range (optional)", key="excel_range",
                value=st.session_state.get("excel_custom_range", ""), on_change=_remember_custom_range,
                placeholder="Entire worksheet, or A:B / L:M / L1:M20",
                help="Blank means the entire worksheet, including leading blank rows. No automatic trimming or table selection.",
            ).strip() or None
            if cell_range is None:
                st.caption("Whole worksheet selected. Choose its header row below if row 1 is blank.")
        st.caption("All detected regions and the original workbook remain available. Combining regions retains worksheet alignment; it does not join records.")
    if mode == "Select a detected region":
        cell_range = st.selectbox("Detected region", layout.regions, index=None, placeholder="Choose a region or select its card above",
                                  key="excel_selected_region", on_change=_select_region_dropdown, args=(layout.regions,))
    if mode == "Choose a table" or mode == "Select a detected region" and cell_range is None:
        clear_import_review(st.session_state)
        st.info("Choose a table above to preview its range and headers. For the whole worksheet, a custom range or all regions, open Advanced import options. No import range has been selected.")
        return {}, None, True
    if len(layout.regions) > 1 and not cell_range and mode != "Import all regions separately":
        st.warning("This selection spans multiple regions. Loading will combine them by original worksheet position, not join matching keys or stack records. Approval below explicitly confirms this combination. Select a detected region or import separately to keep tables apart.")
    header_row = None
    selected_region = next((region for region in st.session_state.region_summaries if region.cell_range == cell_range), None)
    isolated = mode == "Select a detected region" and selected_region is not None and selected_region.rows == selected_region.columns == 1
    if isolated:
        header_mode = "No header (generate names)"
        st.caption("This isolated cell is kept as one data value. Its generated column name requires your approval.")
    else:
        with st.expander("Header settings", expanded=False):
            header_mode = st.selectbox("Header selection", ["First row of range", "Choose worksheet row", "Infer header (review required)", "No header (generate names)"], key="excel_header_mode")
            if header_mode == "Choose worksheet row":
                header_row = int(st.number_input("Header row (Excel row number)", min_value=1, max_value=max(1, layout.rows), value=selected_region.top if selected_region else 1, key="excel_header_row"))
            st.caption("Changing the header policy never silently changes the selected range. Rows before an explicitly chosen header are shown as exclusions for approval.")
    options = {
        "cell_range": cell_range,
        "header_row": header_row,
        "infer_header": header_mode == "Infer header (review required)",
        "headerless": header_mode == "No header (generate names)",
        "repair_irregular_headers": st.session_state.get("excel_repair_headers", False),
    }
    ranges = layout.regions if mode == "Import all regions separately" else ()
    if mode == "Select a detected region":
        options = region_import_options(cell_range, options)
    if ranges:
        st.caption("Each region stays separate. Single-cell regions are retained as data with generated names; header settings apply to the other regions.")
    st.write(f"**Selected import:** {cell_range or ('all detected regions, separately' if ranges else 'entire worksheet')}")
    controls_key = fingerprint({"source": st.session_state.excel_ui_source, "ranges": ranges, "options": options})
    if st.session_state.get("excel_controls_key") != controls_key:
        try:
            st.session_state.excel_relevant_controls = relevant_import_controls(layout, ranges, options)
        except FileValidationError as exc:
            clear_import_review(st.session_state)
            return options, f"Cannot use these import settings: {exc} Review the range in Advanced import options and the row in Header settings.", False
        st.session_state.excel_controls_key = controls_key
    controls = [
        ("generate_missing_headers", "excel_generate_headers", "Generate names for missing headers"),
        ("deduplicate_headers", "excel_deduplicate_headers", "Make duplicate header names unique"),
        ("repair_irregular_headers", "excel_repair_headers", "Repair irregular headers (trim, collapse whitespace, convert non-text labels)"),
        ("exclude_empty_columns", "excel_exclude_empty", "Exclude completely empty columns"),
        ("remove_empty_rows", "excel_remove_rows", "Remove entirely blank worksheet rows"),
    ]
    relevant = st.session_state.excel_relevant_controls
    visible = [control for control in controls if relevant[control[0]] or st.session_state.get(control[1], False)]
    if visible:
        with st.expander("Optional repairs for this selection", expanded=True):
            st.caption("Repairs are off by default. Enable only the changes you want, then review and approve the resulting plan.")
            for option, key, label in visible:
                options[option] = st.checkbox(label, key=key)
    for option, key, label in controls:
        options.setdefault(option, False)
    plan_key = fingerprint({"bytes": hashlib.sha256(payload).hexdigest(), "filename": filename,
                            "sheet": sheet, "limit": limit, "options": options, "mode": mode, "ranges": ranges})
    if st.session_state.get("excel_plan_key") != plan_key:
        st.session_state.excel_review_revision = st.session_state.get("excel_review_revision", 0) + 1
        try:
            st.session_state.excel_plans = tuple(inspect_xlsx_import(
                payload, sheet_name=sheet, max_size_bytes=limit * 1024**2,
                **{**(region_import_options(region, options) if ranges else options), "cell_range": region},
            ) for region in (ranges or (options["cell_range"],)))
            st.session_state.excel_plan = st.session_state.excel_plans[0]
            st.session_state.excel_before_preview = layout.preview()
            st.session_state.excel_after_previews = tuple(
                None if item.errors else preview_import(layout.records, item) for item in st.session_state.excel_plans
            )
            st.session_state.excel_plan_error = None
        except FileValidationError as exc:
            st.session_state.excel_plan, st.session_state.excel_plan_error = None, str(exc)
            st.session_state.excel_plans = ()
        st.session_state.excel_plan_key = plan_key
    plan = st.session_state.excel_plan
    options["confirm_header_changes"] = False
    options["confirm_import_changes"] = False
    options["region_ranges"] = ranges
    if plan is None:
        return options, st.session_state.excel_plan_error, False
    st.write("Excel import preview — review before loading")
    st.warning("Flat CSV/XLSX exports do not preserve workbook formatting, merged cells or working formulas. Formula expressions are never evaluated. Formula exports require a separate acknowledgment; the unchanged original workbook remains available.")
    plans = st.session_state.excel_plans
    problems = header_problem_messages(plans, repaired=options["repair_irregular_headers"])
    for message in problems:
        st.warning(message)
    number = 0
    if len(plans) > 1:
        st.caption(f"{len(plans)} regions will be imported separately. Inspect each plan below; no region is omitted.")
        number = st.selectbox("Import preview to inspect", range(len(plans)),
                              format_func=lambda index: plans[index].selected_range,
                              key="excel_plan_to_inspect")
    _import_plan_preview(layout, plans[number], number)
    errors = tuple(error for current_plan in st.session_state.excel_plans for error in current_plan.errors)
    if errors:
        if problems:
            return options, "Import is blocked by the header problems listed above. Use Header settings or enable an explicit repair in Optional repairs for this selection. Review the affected cells before approving.", False
        return options, f"Import cannot proceed: {errors[0]} Adjust the range or undo the exclusion options. All original data is retained.", False
    approved = True
    needs_confirmation = (any(item.requires_confirmation for item in st.session_state.excel_plans)
                          or header_row is not None or len(layout.regions) > 1)
    if needs_confirmation:
        approved = st.checkbox(
            "I approve the exact exclusions, header changes and table boundaries above, including combining regions if the selection spans multiple tables.",
            key=f"excel_approve_{st.session_state.excel_review_revision}",
        )
        options["confirm_header_changes"] = approved and any(item.requires_header_confirmation for item in st.session_state.excel_plans)
        options["confirm_import_changes"] = approved and (header_row is not None or options["infer_header"] or options["remove_empty_rows"])
        if not approved:
            st.info("Review and approve this import plan to enable Load dataset. The workbook itself will not be changed.")
    return options, None, not approved


def _import_plan_preview(layout, plan, number: int) -> None:
    st.caption(f"Table boundary: {plan.selected_range} · Header row: {plan.header_row or 'None (generated names)'} · After import: {plan.row_count:,} data rows")
    if plan.inferred_header:
        st.info(f"Suggested header: row {plan.header_row}. Inference is heuristic; check the Before preview and excluded rows.")
    changed = [f"{col.excel_column}{plan.header_row}" for col in plan.columns if plan.header_row and col.action.startswith("rename_")]
    excluded_columns = sum(col.action.startswith("exclude_") for col in plan.columns)
    st.caption(f"Planned changes: {len(plan.excluded_rows)} excluded rows · {excluded_columns} excluded columns · {len(changed)} changed header cells")
    if not plan.header_row:
        st.caption("Column names are generated without consuming any worksheet row as a header.")
    actions = {"keep": "Keep", "exclude_empty": "Exclude: completely empty", "exclude_range": "Exclude: outside range",
               "rename_missing": "Rename: missing header", "rename_duplicate": "Rename: duplicate header",
               "rename_irregular": "Rename: irregular header", "invalid": "Invalid header"}
    with st.expander(f"Advanced Details — import plan {number + 1}", expanded=False):
        st.write("Excluded worksheet rows: " + (", ".join(spans(plan.excluded_rows)) or "None"))
        if plan.removed_blank_rows:
            st.write("Removed entirely blank rows: " + ", ".join(spans(plan.removed_blank_rows)))
        st.write("Changed header cells: " + (", ".join(changed) or "None"))
        if plan.errors:
            st.write("Import validation details")
            for error in plan.errors:
                st.write(error)
        st.dataframe(pd.DataFrame([{
        "Excel column": column.excel_column,
        "Original header": "(missing)" if column.original_header is None else repr(column.original_header),
        "Import header": column.imported_header or "",
        "Completely empty": column.completely_empty,
        "Data outside header row": column.has_data,
        "Action": actions[column.action],
        } for column in plan.columns]), hide_index=True, width="stretch")
    with st.expander(f"Before / After values — table {number + 1}"):
        before, after = st.columns(2)
        with before:
            st.write("Before — worksheet coordinates (including excluded cells)")
            _table(st.session_state.excel_before_preview, f"import_before_{number}")
        with after:
            st.write("After — planned imported values")
            if plan.errors:
                st.info("Resolve the listed header errors to preview the imported table.")
            else:
                _table(st.session_state.excel_after_previews[number], f"import_after_{number}")
                st.caption("Source rows: " + (", ".join(spans(plan.retained_rows)) or "None") + "; data cell values are unchanged.")


def _upload(workspace: Workspace) -> None:
    st.header("01 · Upload", anchor="upload")
    source = st.radio("Data source", ["Upload a file", "Try a sample"], horizontal=True, key="source_mode")
    payload, filename = None, ""
    if source == "Upload a file":
        uploaded = st.file_uploader(
            "Choose a CSV or Excel workbook", type=["csv", "xlsx"],
            key=f"upload_{st.session_state.get('upload_epoch', 'initial')}",
            help="Files remain in session memory. XLSX worksheets are selected below.",
        )
        if uploaded is not None:
            payload, filename = uploaded.getvalue(), uploaded.name
    else:
        samples = {"Sales (CSV)": "sample_sales.csv", "Sales workbook (XLSX)": "sample_sales.xlsx", "Inventory (CSV)": "sample_inventory.csv",
                   "Sparse Excel tables (synthetic)": "sayfa1_like.xlsx"}
        choice = st.selectbox("Sample dataset", list(samples), key="sample_choice")
        filename = samples[choice]
        try:
            payload = (Path(__file__).resolve().parents[2] / "sample_data" / filename).read_bytes()
        except OSError:
            st.error("Sample data is unavailable. Launch from the project checkout or upload your own file.")

    encoding, delimiter, sheet = None, None, 0
    upload_error = None
    excel_options, approval_pending = {}, False
    server_limit = max(1, int(st.get_option("server.maxUploadSize")))
    with st.expander("Import settings", expanded=payload is not None):
        limit = st.number_input(
            "Maximum file size (MiB)", min_value=1, max_value=server_limit,
            value=min(10, server_limit), step=1, key="import_limit",
            help="Default 10 MiB. The server upload limit is the upper bound. XLSX expanded archive limit: 100 MiB.",
        )
        if filename.lower().endswith(".csv"):
            left, right = st.columns(2)
            with left:
                selected_encoding = st.selectbox(
                    "CSV encoding", ["Detect Unicode", "utf-8-sig", "utf-16", "utf-32", "cp1252", "latin-1", "Custom"], key="csv_encoding",
                )
                encoding = None if selected_encoding == "Detect Unicode" else selected_encoding
                if selected_encoding == "Custom":
                    encoding = st.text_input("Encoding name", key="csv_custom_encoding")
            with right:
                delimiter = DELIMITERS[st.selectbox("CSV delimiter", list(DELIMITERS), key="csv_delimiter")]
                if delimiter == "custom":
                    delimiter = st.text_input("Delimiter character", max_chars=1, key="csv_custom_delimiter")
            st.caption("CSV values load as text. Leading zeros and literal NA values are preserved; empty fields are missing.")
        elif payload is not None and filename.lower().endswith(".xlsx"):
            # Metadata cache is session-local and invalidates on bytes/size limit.
            catalog_key = (hashlib.sha256(payload).hexdigest(), limit)
            if st.session_state.get("catalog_key") != catalog_key:
                try:
                    st.session_state.layouts = inspect_xlsx_layouts(payload, max_size_bytes=int(limit) * 1024**2)
                    st.session_state.catalog = tuple(item.sheet_name for item in st.session_state.layouts)
                    st.session_state.catalog_error = None
                except FileValidationError as exc:
                    st.session_state.catalog, st.session_state.catalog_error = (), str(exc)
                st.session_state.catalog_key = catalog_key
            if st.session_state.catalog:
                st.caption("Worksheets: " + " · ".join(
                    f"{item.sheet_name} ({'empty' if item.empty else str(len(item.regions)) + ' suggested regions'})"
                    for item in st.session_state.layouts
                ))
                sheet = st.selectbox("Excel worksheet", st.session_state.catalog, key=f"sheet_{catalog_key[0]}")
                layout = next(item for item in st.session_state.layouts if item.sheet_name == sheet)
                excel_options, upload_error, approval_pending = _excel_import_options(payload, filename, sheet, int(limit), layout)
            else:
                upload_error = st.session_state.catalog_error or "No worksheets are available in this workbook."
            st.caption("Only the selected worksheet is loaded. Formula expressions are preserved as text.")
    options = ImportOptions(encoding, delimiter, sheet, int(limit) * 1024**2, **excel_options)
    prior_source = workspace.active_source
    workspace.observe_source(payload, filename, options)
    if approval_pending or upload_error:
        # Includes range exclusions without header changes: unchecking approval
        # must revoke readiness even when the loader's option values are identical.
        workspace.loaded_source = None
        if workspace.preview is not None or workspace.applied is not None:
            workspace.invalidate()
    if workspace.active_source != prior_source:
        st.session_state.pop("import_error", None)
    if payload is not None and len(payload) > options.max_size_bytes:
        upload_error = f"This file exceeds the selected {limit} MiB limit."
    if upload_error:
        st.error(upload_error)
    if st.button("Load dataset", type="primary", disabled=payload is None or bool(upload_error) or approval_pending, key="load_dataset"):
        try:
            with st.spinner("Validating and loading your dataset…"):
                workspace.load(payload, filename, options)
            st.session_state.pop("import_error", None)
        except (FileValidationError, DataValidationError) as exc:
            st.session_state.import_error = str(exc)
    if st.session_state.get("import_error"):
        st.error(st.session_state.import_error)
    if workspace.source_current:
        if workspace.regions:
            region = st.selectbox("Active imported region", list(workspace.regions),
                                  key=f"active_region_{workspace.loaded_source}")
            workspace.select_region(region)
            st.caption("Each region is stored separately. Switching tables clears the cleaning preview and downloads; original imported tables remain available.")
        st.success(f"Loaded {workspace.filename}. The original dataset is preserved.")
    elif workspace.original is not None:
        st.warning(f"Previous dataset retained: {workspace.filename} — not current. Load the selected file and settings before processing. Previous previews and downloads have been cleared.")
    else:
        st.info("Upload a file or try a sample, review its import settings, then select Load dataset.")


def _metrics(profile, before=None) -> None:
    fields = [("Rows", "row_count"), ("Columns", "column_count"), ("Missing cells", "missing_value_count"), ("Duplicate rows", "duplicate_row_count")]
    for column, (label, field) in zip(st.columns(4), fields):
        value = getattr(profile, field)
        column.metric(label, f"{value:,}", delta=None if before is None else f"{value - getattr(before, field):+,}", delta_color="off")


def _table(data: pd.DataFrame, key: str) -> None:
    pages = max(1, ceil(len(data) / 100))
    page_key = f"{key}_page"
    if st.session_state.get(page_key, 1) > pages:
        st.session_state[page_key] = 1
    page = st.number_input("Preview page", min_value=1, max_value=pages, step=1, key=page_key)
    start, end = ((int(page) - 1) * 100 + 1, min(int(page) * 100, len(data))) if len(data) else (0, 0)
    st.caption(f"Rows {start:,}–{end:,} of {len(data):,} · Values displayed as text; missing cells are blank.")
    st.dataframe(display_page(data, int(page)), width="stretch", height=350)
    st.caption("Table downloads/copy are disabled so exports use the reviewed formula protections. Use Download below for the complete dataset.")


def _overview(workspace: Workspace) -> None:
    st.header("02 · Data Overview", anchor="data-overview")
    if workspace.original is None:
        st.info("Dataset statistics and an interactive original preview will appear after loading.")
        return
    if not workspace.source_current:
        st.info("No current dataset is loaded for this selection. Previous data is retained in memory, but its statistics and table are hidden until a successful load.")
        return
    _metrics(workspace.original_profile)
    with st.expander("Column types and missing values"):
        st.dataframe(pd.DataFrame([asdict(column) for column in workspace.original_profile.columns]), hide_index=True, width="stretch")
    st.subheader("Original dataset")
    _table(workspace.original, "original")
    source = workspace.original.attrs.get("xlsx_source")
    if source:
        with st.expander("Excel source coordinates and formula inventory"):
            st.caption(f"Sheet: {source['sheet_name']} · Header row: {source['header_row']} · Imported range: {source['range']}")
            st.write("Data rows: " + (", ".join(spans(source["row_numbers"])) or "None"))
            st.dataframe(pd.DataFrame({"Imported column": list(workspace.original.columns),
                                       "Excel column": source["column_letters"]}), hide_index=True)
            if source["formulas"]:
                st.dataframe(pd.DataFrame(source["formulas"], columns=["Original cell", "Original formula expression"]), hide_index=True)
            st.caption("The JSON download includes source coordinates and the original formula inventory. Formula expressions are not evaluated or replaced with cached results.")


def _select_columns(label: str, available: list[str], key: str) -> list[str]:
    # Keep old selections visible on reorder/schema changes; never drop them silently.
    existing = st.session_state.get(key, [])
    options = list(dict.fromkeys(available + existing))
    selected = st.multiselect(label, options, key=key)
    unknown = [name for name in selected if name not in available]
    if unknown:
        st.warning("These selected columns do not exist at this step: " + ", ".join(unknown))
    return selected


def _step_controls(operation: str, available: list[str], key: str) -> dict:
    if operation == "normalize_column_names":
        st.caption("Normalize all column names to snake_case. Empty names and collisions are rejected. Later steps use the new names.")
        return {}
    if operation == "remove_duplicates":
        scope = st.radio("Compare", ["All columns", "Selected columns"], horizontal=True, key=f"{key}_scope")
        selected = _select_columns("Duplicate key columns", available, f"{key}_columns") if scope == "Selected columns" else available
        keep = st.selectbox("Retain", ["First record", "Last record", "Remove all matching records"], key=f"{key}_keep")
        insensitive = _select_columns("Case-insensitive text columns (optional)", selected, f"{key}_insensitive")
        validate_columns(selected, available, option="Duplicate key columns")
        parameters = {"keep": {"First record": "first", "Last record": "last", "Remove all matching records": False}[keep]}
        if scope == "Selected columns":
            parameters["subset"] = selected
        if insensitive:
            validate_columns(insensitive, selected, option="Case-insensitive columns")
            parameters["case_insensitive_columns"] = insensitive
        return parameters
    selected = _select_columns("Columns", available, f"{key}_columns")
    parameters = {"columns": selected}
    if operation == "handle_missing":
        strategy = st.selectbox("Missing-value action", ["keep", "drop", "constant", "mean", "median", "mode"], key=f"{key}_strategy")
        parameters["strategy"] = strategy
        if strategy == "constant":
            kind = st.selectbox("Constant type", ["Text", "Number", "Boolean", "Date / time"], key=f"{key}_constant_type")
            text = st.selectbox("Constant value", ["True", "False"], key=f"{key}_bool") if kind == "Boolean" else st.text_input("Constant value", key=f"{key}_value")
            parameters["value"] = parse_constant(text, kind)
        st.caption("Mean/median require numeric values: add numeric conversion first for CSV columns. Drop removes rows missing any selected value.")
    elif operation == "clean_text":
        parameters["operation"] = st.selectbox("Text operation", ["trim", "lower", "upper", "title"], key=f"{key}_text")
    elif operation == "convert_numeric":
        left, right = st.columns(2)
        parameters["decimal_separator"] = left.selectbox("Decimal separator", [".", ","], key=f"{key}_decimal")
        parameters["thousands_separator"] = THOUSANDS[right.selectbox("Thousands separator", list(THOUSANDS), key=f"{key}_thousands")]
        if parameters["decimal_separator"] == parameters["thousands_separator"]:
            raise DataValidationError("Decimal and thousands separators must differ.")
        st.caption("Invalid numbers stay unchanged with errors. Trim surrounding whitespace in a preceding step when needed.")
    elif operation == "standardize_dates":
        text = st.text_area("Input date formats (one per line)", value="%Y-%m-%d", key=f"{key}_formats", help="Examples: %Y-%m-%d or %d/%m/%Y. Day/month order is never guessed.")
        parameters["input_formats"] = [line for line in text.splitlines() if line.strip()]
        if not parameters["input_formats"]:
            raise DataValidationError("Enter at least one explicit date format.")
        st.caption("Output uses ISO 8601. Conflicting interpretations remain unchanged and block confirmation.")
    validate_columns(selected, available, option="Columns")
    return parameters


def _configuration(workspace: Workspace) -> None:
    st.header("03 · Cleaning Configuration", anchor="cleaning-configuration")
    if workspace.original is None:
        st.info("Load the current dataset to configure an ordered cleaning workflow.")
        return
    if not workspace.source_current:
        st.info("Your workflow is retained for the last loaded dataset. Load the current selection before previewing changes.")
    st.write("Build your workflow from top to bottom. Move steps to control the order; every change requires a new preview.")
    selected = st.selectbox("Operation to add", list(OPERATIONS), key="new_operation")
    if st.button("Add operation", key="add_operation"):
        st.session_state.queue.append({"id": uuid4().hex, "label": selected})
        workspace.invalidate()
    steps, errors = [], []
    queue = st.session_state.queue
    for index, item in enumerate(queue):
        key = f"step_{item['id']}"
        with st.expander(f"Step {index + 1} · {item['label']}", expanded=True):
            buttons = st.columns(3)
            up = buttons[0].button("Move up", key=f"{key}_up", disabled=index == 0, width="stretch")
            down = buttons[1].button("Move down", key=f"{key}_down", disabled=index == len(queue) - 1, width="stretch")
            remove = buttons[2].button("Remove step", key=f"{key}_remove", width="stretch")
            if up or down or remove:
                if remove:
                    queue.pop(index)
                else:
                    other = index - 1 if up else index + 1
                    queue[index], queue[other] = queue[other], queue[index]
                workspace.invalidate()
                st.rerun()
            try:
                available = columns_after_steps(list(workspace.original.columns), steps)
                operation = OPERATIONS[item["label"]]
                parameters = _step_controls(operation, available, key)
                steps.append(ProcessingStep(operation, parameters))
                # Validate header normalization before allowing a later selector to use it.
                columns_after_steps(list(workspace.original.columns), steps)
            except DataValidationError as exc:
                message = f"Step {index + 1}: {exc}"
                errors.append(message)
                st.error(message)
    if not queue:
        st.info("No cleaning steps yet. Add an operation, or preview and confirm the unchanged dataset for export.")
    stop = st.checkbox("Stop preview processing on the first step with errors", value=True, key="stop_on_error")
    workspace.configure(steps, stop_on_error=stop, error="\n".join(errors) or None)
    if st.button("Preview changes", type="primary", disabled=bool(errors) or not workspace.source_current, key="preview_changes"):
        try:
            with st.spinner("Computing the full preview…"):
                workspace.make_preview()
        except DataValidationError as exc:
            st.error(str(exc))


def _diagnostics(issues, label: str) -> None:
    if not issues:
        return
    with st.expander(f"{label} ({len(issues):,})", expanded=False):
        rows = [{"Original row (1-based)": "" if issue.row_position is None else str(issue.row_position + 1),
                 "Column": issue.column or "", "Issue": issue.code.replace("_", " "), "Details": issue.message} for issue in issues]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _results(workspace: Workspace) -> None:
    st.header("04 · Results", anchor="results")
    if workspace.preview is None:
        st.info("Select Preview changes to compare the full processing result with your original data. Nothing is applied yet.")
        return
    preview = workspace.preview
    report = preview.report
    _metrics(report.after, before=report.before)
    st.caption(f"{report.affected_rows:,} original rows affected · {len(report.steps)} of {report.planned_steps} steps executed · {report.status.replace('_', ' ')}")
    _diagnostics(report.errors, "Errors — resolve before applying")
    _diagnostics(report.warnings, "Warnings to review")
    with st.expander("Step-by-step summary"):
        st.dataframe(pd.DataFrame([{
            "Step": i + 1, "Operation": step.operation.replace("_", " "), "Status": step.status,
            "Rows before": step.before.rows, "Rows after": step.after.rows, "Affected rows": step.affected_rows,
        } for i, step in enumerate(report.steps)]), hide_index=True, width="stretch")
        for i, step in enumerate(report.steps):
            if step.renamed_columns:
                st.write(f"Step {i + 1} — column name changes")
                st.dataframe(pd.DataFrame(step.renamed_columns, columns=["Original name", "New name"]), hide_index=True)
    if st.checkbox("Show original and result side by side", value=False, key="side_by_side"):
        original, result = st.columns(2)
        with original:
            st.subheader("Original")
            _table(workspace.original, "comparison_original")
        with result:
            st.subheader("Confirmed result" if workspace.applied else "Preview — not applied")
            _table(preview.data, "comparison_result")
    else:
        st.subheader("Confirmed result" if workspace.applied else "Preview — not applied")
        _table(preview.data, "result")
    if report.errors:
        st.error("This preview contains errors. Original values are retained for failed conversions. Update the workflow and preview again before applying or downloading data.")
    elif workspace.applied is None:
        reviewed = st.checkbox("I reviewed this preview and want to apply these changes.", key=f"confirm_{workspace.revision}")
        if st.button("Apply reviewed changes", type="primary", disabled=not reviewed, key="apply_changes"):
            workspace.apply_preview()
    if workspace.applied is not None:
        st.success("Changes confirmed. Your original dataset is preserved; the confirmed result is ready for download.")


def _downloads(workspace: Workspace) -> None:
    st.header("05 · Download", anchor="download")
    has_formulas = bool(workspace.original is not None and workspace.original.attrs.get("xlsx_source", {}).get("formulas"))
    if workspace.source_current and workspace.source_bytes and has_formulas:
        st.download_button("Download unchanged original workbook", data=workspace.source_bytes,
                           file_name=workspace.filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           on_click="ignore", key="download_original")
        st.caption("Exact uploaded bytes, including every worksheet, formula and formatting. No cleaning changes are applied to this download.")
    if workspace.applied is None:
        st.info("Confirm a reviewed preview to unlock complete CSV, Excel, and JSON report downloads.")
        return
    st.write(f"Export all {len(workspace.applied.data):,} rows and {len(workspace.applied.data.columns):,} columns of the confirmed result.")
    st.caption("Spreadsheet formula protection is always enabled. Export warnings appear below; your in-memory data stays unchanged.")
    if has_formulas:
        st.warning("This workbook contains formulas. Flat exports store expressions as protected literal text; formula functionality, formatting and merged cells are not preserved.")
        acknowledged = st.checkbox("I accept the loss of formula functionality in the flat CSV/XLSX exports.",
                                   key=f"formula_ack_{workspace.revision}")
        workspace.acknowledge_formula_loss(acknowledged)
    if st.button("Prepare downloads", key="prepare_downloads", disabled=bool(workspace.exports or workspace.export_errors)):
        with st.spinner("Preparing complete files…"):
            workspace.prepare_downloads()
    basename = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(workspace.filename).stem).strip("_") or "dataset"
    for column, kind in zip(st.columns(3), ["csv", "xlsx", "json"]):
        with column:
            if kind in workspace.export_errors:
                st.error(f"{kind.upper()} export failed: {workspace.export_errors[kind]}")
            if kind in workspace.exports:
                artifact = workspace.exports[kind]
                st.download_button(
                    f"Download {kind.upper()}" + (" report" if kind == "json" else ""),
                    data=artifact.content, file_name=f"{basename}_{'report' if kind == 'json' else 'cleaned'}.{kind}",
                    mime=artifact.media_type, on_click="ignore", width="stretch", key=f"download_{kind}",
                )
                for warning in artifact.warnings:
                    st.warning(warning.message)


def main() -> None:
    """Render the local dashboard; all state is isolated to this browser session."""
    _style()
    workspace = _workspace()
    try:
        _upload(workspace)
        _overview(workspace)
        _configuration(workspace)
        _results(workspace)
        _downloads(workspace)
    except Exception:
        # A final UI boundary for unexpected failures, not an engine error policy.
        # Streamlit's rerun/stop signals inherit BaseException and are not swallowed.
        logging.getLogger(__name__).exception("Dashboard action failed")
        workspace.invalidate()
        workspace.loaded_source = None
        st.error("This action could not be completed. Your original dataset is preserved. Review the settings and try again; technical details are in the local terminal.")
    st.divider()
    st.caption("Smart Data Processor · Local processing · Original data preserved · No account required")
