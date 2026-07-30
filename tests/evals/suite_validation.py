"""Strict discovery and static validation for evaluation suites."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.core.evaluation import EvalCase
from tests.evals.evaluators.base import BaseEvaluator

SUPPORTED_CATEGORIES = {
    "intent_recognition",
    "memory_retrieval",
    "memory_write",
    "memory_update",
    "extraction_quality",
    "context_compression",
}

CATEGORY_OUTPUT_FIELDS: dict[str, set[str]] = {
    "intent_recognition": {
        "intent",
        "teaching_metadata",
        "response",
        "rag_triggered",
        "memory_operations",
    },
    "memory_retrieval": {
        "profile_memory_context",
        "experience_memory_context",
        "loaded_experience_memories",
        "memory_operations",
        "profile_memory_created",
        "experience_memory_created",
        "profile_memory_id",
        "profile_memory_content",
        "total_profile_memories",
        "memory_reflection_goto",
        "privacy_exposure",
        "input_message",
        "response",
    },
    "memory_write": {
        "profile_memory_context",
        "experience_memory_context",
        "loaded_experience_memories",
        "memory_operations",
        "profile_memory_created",
        "experience_memory_created",
        "profile_memory_id",
        "profile_memory_content",
        "total_profile_memories",
        "memory_reflection_goto",
        "privacy_exposure",
        "input_message",
        "response",
    },
    "memory_update": {
        "profile_memory_context",
        "experience_memory_context",
        "loaded_experience_memories",
        "memory_operations",
        "profile_memory_created",
        "experience_memory_created",
        "profile_memory_id",
        "profile_memory_content",
        "total_profile_memories",
        "memory_reflection_goto",
        "privacy_exposure",
        "input_message",
        "response",
    },
    "extraction_quality": {
        "teaching_metadata",
        "intent",
        "input_message",
        "response",
        "rag_triggered",
    },
    "context_compression": {
        "compression_status",
        "compression_reason",
        "update_created",
        "stream_completed",
        "compressed_context",
        "has_compressed_marker",
        "teaching_metadata",
        "retained_message_count",
        "artifact_catalog",
    },
}


@dataclass(frozen=True)
class SuiteDiagnostic:
    code: str
    message: str
    path: str
    case_id: str | None = None
    severity: str = "error"


@dataclass
class SuiteValidationResult:
    discovered_files: int
    cases: list[EvalCase] = field(default_factory=list)
    diagnostics: list[SuiteDiagnostic] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)
    assertion_counts: dict[str, int] = field(default_factory=dict)
    field_references: dict[str, list[str]] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def raise_for_errors(self) -> None:
        if not self.valid:
            raise SuiteValidationError(self)


class SuiteValidationError(ValueError):
    def __init__(self, result: SuiteValidationResult):
        self.result = result
        details = "; ".join(
            f"{item.code} ({item.case_id or item.path}): {item.message}"
            for item in result.diagnostics
            if item.severity == "error"
        )
        super().__init__(details or "Evaluation suite validation failed")


def _field_is_allowed(category: str, field_name: str) -> bool:
    roots = CATEGORY_OUTPUT_FIELDS.get(category, set())
    root = field_name.split(".", 1)[0]
    return root in roots


def validate_suite(cases_dir: Path, *, expected_count: int | None = None) -> SuiteValidationResult:
    yaml_files = sorted(cases_dir.rglob("*.yaml"))
    diagnostics: list[SuiteDiagnostic] = []
    cases: list[EvalCase] = []
    seen_ids: dict[str, Path] = {}
    supported_assertions = {item.value for item in BaseEvaluator.supported_assertion_types()}
    fields_by_category: dict[str, set[str]] = defaultdict(set)

    for yaml_file in yaml_files:
        relative_path = str(yaml_file.relative_to(cases_dir))
        try:
            with open(yaml_file, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            diagnostics.append(
                SuiteDiagnostic("yaml_parse_error", str(exc), relative_path)
            )
            continue

        if not isinstance(data, dict):
            diagnostics.append(
                SuiteDiagnostic("invalid_case_document", "Top-level YAML value must be a mapping", relative_path)
            )
            continue

        raw_case_id = str(data.get("case_id") or "").strip() or None
        raw_assertions = data.get("assertions")
        if isinstance(raw_assertions, list):
            for raw_assertion in raw_assertions:
                if not isinstance(raw_assertion, dict):
                    continue
                raw_type = str(raw_assertion.get("type") or "")
                if raw_type and raw_type not in supported_assertions:
                    diagnostics.append(
                        SuiteDiagnostic(
                            "unsupported_assertion",
                            f"Assertion handler is not registered: {raw_type}",
                            relative_path,
                            raw_case_id,
                        )
                    )

        try:
            case = EvalCase(**data)
        except ValidationError as exc:
            diagnostics.append(
                SuiteDiagnostic("schema_error", str(exc), relative_path, raw_case_id)
            )
            continue

        if case.case_id in seen_ids:
            diagnostics.append(
                SuiteDiagnostic(
                    "duplicate_case_id",
                    f"Also declared in {seen_ids[case.case_id].relative_to(cases_dir)}",
                    relative_path,
                    case.case_id,
                )
            )
        else:
            seen_ids[case.case_id] = yaml_file

        if case.category not in SUPPORTED_CATEGORIES:
            diagnostics.append(
                SuiteDiagnostic(
                    "unsupported_category",
                    f"Unsupported category: {case.category}",
                    relative_path,
                    case.case_id,
                )
            )

        if not case.assertions:
            diagnostics.append(
                SuiteDiagnostic("empty_assertions", "At least one assertion is required", relative_path, case.case_id)
            )

        for assertion in case.assertions:
            fields_by_category[case.category].add(assertion.field)
            if not _field_is_allowed(case.category, assertion.field):
                diagnostics.append(
                    SuiteDiagnostic(
                        "invalid_field_reference",
                        f"{assertion.field!r} is not in the {case.category} output contract",
                        relative_path,
                        case.case_id,
                    )
                )
        cases.append(case)

    if expected_count is not None and len(yaml_files) != expected_count:
        diagnostics.append(
            SuiteDiagnostic(
                "unexpected_file_count",
                f"Expected {expected_count} YAML files, discovered {len(yaml_files)}",
                str(cases_dir),
            )
        )
    if expected_count is not None and len(cases) != expected_count:
        diagnostics.append(
            SuiteDiagnostic(
                "unexpected_loaded_count",
                f"Expected {expected_count} valid cases, loaded {len(cases)}",
                str(cases_dir),
            )
        )

    category_counts = Counter(case.category for case in cases)
    assertion_counts = Counter(assertion.type.value for case in cases for assertion in case.assertions)
    return SuiteValidationResult(
        discovered_files=len(yaml_files),
        cases=cases,
        diagnostics=diagnostics,
        category_counts=dict(sorted(category_counts.items())),
        assertion_counts=dict(sorted(assertion_counts.items())),
        field_references={
            category: sorted(fields) for category, fields in sorted(fields_by_category.items())
        },
    )


def load_cases_strict(cases_dir: Path, *, category: str | None = None) -> list[EvalCase]:
    result = validate_suite(cases_dir)
    result.raise_for_errors()
    if category is None:
        return result.cases
    return [case for case in result.cases if case.category == category]


def format_audit(result: SuiteValidationResult) -> str:
    lines = [
        f"Discovered YAML files: {result.discovered_files}",
        f"Loaded cases: {len(result.cases)}",
        "Categories:",
    ]
    lines.extend(f"  - {name}: {count}" for name, count in result.category_counts.items())
    lines.append("Assertions:")
    lines.extend(f"  - {name}: {count}" for name, count in result.assertion_counts.items())
    lines.append("Field references:")
    for category, fields in result.field_references.items():
        lines.append(f"  - {category}: {', '.join(fields)}")
    if result.diagnostics:
        lines.append("Diagnostics:")
        lines.extend(
            f"  - [{item.code}] {item.case_id or item.path}: {item.message}"
            for item in result.diagnostics
        )
    return "\n".join(lines)
