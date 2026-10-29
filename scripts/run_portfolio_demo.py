"""Reproduce the documented synthetic demo using the unchanged public engine API.

Run from the checkout: python scripts/run_portfolio_demo.py
Only named generated artifacts under --output-dir are overwritten, never inputs.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from smart_data_processor import (
    ProcessingPipeline, ProcessingStep, export_csv, export_report, export_xlsx, load_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "sample_data" / "portfolio_sales_raw.csv"
CONFIG = ROOT / "docs" / "portfolio" / "demo_steps.json"


def run_demo(output_dir: Path) -> dict:
    """Write complete demo exports and return measured before/after statistics."""
    source = INPUT.read_bytes()
    original = load_dataset(INPUT)
    definitions = json.loads(CONFIG.read_text(encoding="utf-8"))
    result = ProcessingPipeline([ProcessingStep(**step) for step in definitions]).run(original)
    if result.report.errors:
        raise RuntimeError(f"Demo failed: {result.report.errors}")
    artifacts = {"csv": export_csv(result.data), "xlsx": export_xlsx(result.data)}
    summary = {
        "dataset": "Synthetic portfolio sales; not customer data",
        "input_sha256": hashlib.sha256(source).hexdigest(),
        "before": result.report.before.to_dict(),
        "after": result.report.after.to_dict(),
        "status": result.report.status,
        "steps": len(result.report.steps),
        "exports": {kind: {"protected_cell_count": artifact.protected_cell_count,
                           "warnings": [asdict(issue) for issue in artifact.warnings]}
                    for kind, artifact in artifacts.items()},
    }
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for kind, artifact in artifacts.items():
        (output_dir / f"portfolio_sales_cleaned.{kind}").write_bytes(artifact.content)
    (output_dir / "portfolio_sales_report.json").write_bytes(export_report(result.report))
    (output_dir / "demo_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if INPUT.read_bytes() != source:
        raise RuntimeError("The demo source changed during processing.")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".demo-output")
    args = parser.parse_args()
    summary = run_demo(args.output_dir)
    for label in ("before", "after"):
        profile = summary[label]
        print(f"{label}: {profile['row_count']} rows, {profile['column_count']} columns, "
              f"{profile['missing_value_count']} missing cells, {profile['duplicate_row_count']} duplicates")
    print(f"Complete artifacts: {args.output_dir.resolve()}")
