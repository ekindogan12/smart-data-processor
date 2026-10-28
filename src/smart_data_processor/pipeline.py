"""Reusable, ordered execution of explicit cleaning and transformation steps."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from inspect import signature
from typing import Any

import pandas as pd

from .cleaner import handle_missing, remove_duplicates
from .models import Issue, OperationResult
from .profiler import profile_dataset
from .reporter import Dimensions, ProcessingReport, StepReport
from .transformer import clean_text, convert_numeric, normalize_column_names, standardize_dates
from .validators import DataValidationError, validate_dataframe


@dataclass(frozen=True)
class ProcessingStep:
    """An operation name and keyword arguments; names refer to the current schema."""

    operation: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProcessingResult:
    """Independent processed data and the report for that exact execution."""

    data: pd.DataFrame
    report: ProcessingReport


def _duplicates(data: pd.DataFrame, **parameters: Any) -> OperationResult:
    # Temporary positional index provides unambiguous provenance for repeated labels.
    positional = data.copy(deep=True)
    positional.index = pd.RangeIndex(len(data))
    try:
        signature(remove_duplicates).bind(positional, **parameters)
    except TypeError as exc:
        raise DataValidationError(str(exc)) from exc
    filtered = remove_duplicates(positional, **parameters)
    retained = tuple(int(position) for position in filtered.index)
    retained_set = set(retained)
    removed = tuple(position for position in range(len(data)) if position not in retained_set)
    return OperationResult(
        data.iloc[list(retained)].copy(deep=True), removed, retained_positions=retained
    )


_OPERATIONS = {
    "handle_missing": handle_missing,
    "clean_text": clean_text,
    "normalize_column_names": normalize_column_names,
    "convert_numeric": convert_numeric,
    "standardize_dates": standardize_dates,
    "remove_duplicates": _duplicates,
}


class ProcessingPipeline:
    """Apply steps in listed order, with no implicit preprocessing or reordering.

    Configuration is copied at construction and reused safely across runs. By
    default, stop after a step reports errors. Valid cells from a partially
    successful conversion remain applied; invalid cells retain their originals.
    A failed configuration step changes nothing. Set stop_on_error=False to
    explicitly continue. Earlier successful steps are never rolled back.
    """

    def __init__(self, steps: Sequence[ProcessingStep], *, stop_on_error: bool = True):
        if isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence):
            raise DataValidationError("steps must be a sequence of ProcessingStep objects.")
        if type(stop_on_error) is not bool:
            raise DataValidationError("stop_on_error must be boolean.")
        for step in steps:
            if not isinstance(step, ProcessingStep) or not isinstance(step.operation, str):
                raise DataValidationError("Each step must be a ProcessingStep with a string operation.")
            if not isinstance(step.parameters, Mapping) or any(not isinstance(key, str) for key in step.parameters):
                raise DataValidationError("Step parameters must be a mapping with string keys.")
        self._steps = tuple(ProcessingStep(step.operation, deepcopy(dict(step.parameters))) for step in steps)
        self._stop_on_error = stop_on_error

    def run(self, data: pd.DataFrame) -> ProcessingResult:
        """Run on a copy and return deterministic statistics and original row positions."""
        validate_dataframe(data)
        before = profile_dataset(data)
        current = data.copy(deep=True)
        row_ids = list(range(len(data)))
        reports, affected = [], set()
        stopped = False
        for step in self._steps:
            dimensions = Dimensions(*current.shape)
            parameters = deepcopy(dict(step.parameters))
            try:
                if step.operation not in _OPERATIONS:
                    raise DataValidationError(f"Unknown operation: {step.operation!r}.")
                operation = _OPERATIONS[step.operation]
                try:
                    signature(operation).bind(current, **parameters)
                except TypeError as exc:
                    raise DataValidationError(str(exc)) from exc
                result = operation(current, **parameters)
                status = "partial" if result.errors else "applied"
            except DataValidationError as exc:
                result = OperationResult(current.copy(deep=True), errors=(Issue("invalid_operation", str(exc)),))
                status = "failed"

            positions = tuple(row_ids[position] for position in result.affected_positions)
            affected.update(positions)

            def original_issue(issue):
                return replace(issue, row_position=row_ids[issue.row_position]) if issue.row_position is not None else issue

            reports.append(StepReport(
                operation=step.operation, parameters=parameters, status=status,
                before=dimensions, after=Dimensions(*result.data.shape),
                affected_rows=len(positions), affected_row_positions=positions,
                warnings=tuple(original_issue(issue) for issue in result.warnings),
                errors=tuple(original_issue(issue) for issue in result.errors),
                renamed_columns=result.renamed_columns,
            ))
            # Coordinate provenance follows positional row filtering. Formula
            # inventory remains conservative even if a formula row is removed.
            source = deepcopy(current.attrs.get("xlsx_source"))
            current = result.data
            if source is not None:
                if result.retained_positions is not None:
                    source["row_numbers"] = tuple(source["row_numbers"][pos] for pos in result.retained_positions)
                current.attrs["xlsx_source"] = source
            if result.retained_positions is not None:
                row_ids = [row_ids[position] for position in result.retained_positions]
            if result.errors and self._stop_on_error:
                stopped = True
                break
        status = "stopped_on_error" if stopped else (
            "completed_with_errors" if any(step.errors for step in reports) else "completed"
        )
        report = ProcessingReport(
            before, profile_dataset(current), tuple(reports), status, len(self._steps), len(affected)
        )
        return ProcessingResult(current, report)
