from __future__ import annotations

from pathlib import Path

from tests.evals.suite_validation import load_cases_strict, validate_suite


def _case_yaml(*, case_id: str = "case_001", category: str = "intent_recognition", field: str = "intent") -> str:
    return f"""case_id: {case_id}
category: {category}
description: validation fixture
version: "1.0"
input:
  message: hello
context: {{}}
expectations: {{}}
assertions:
  - type: route_match
    field: {field}
    expected: basic_chat
metadata: {{}}
"""


def test_current_suite_discovers_all_24_cases() -> None:
    cases_dir = Path(__file__).parent / "cases"
    result = validate_suite(cases_dir, expected_count=24)

    assert result.valid, [item.message for item in result.diagnostics]
    assert result.discovered_files == 24
    assert len(result.cases) == 24
    assert result.category_counts == {
        "context_compression": 4,
        "extraction_quality": 7,
        "intent_recognition": 5,
        "memory_retrieval": 3,
        "memory_update": 1,
        "memory_write": 4,
    }


def test_invalid_yaml_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("case_id: [", encoding="utf-8")
    result = validate_suite(tmp_path)
    assert not result.valid
    assert {item.code for item in result.diagnostics} == {"yaml_parse_error"}


def test_duplicate_case_id_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(_case_yaml(), encoding="utf-8")
    (tmp_path / "b.yaml").write_text(_case_yaml(), encoding="utf-8")
    result = validate_suite(tmp_path)
    assert not result.valid
    assert "duplicate_case_id" in {item.code for item in result.diagnostics}


def test_unknown_assertion_is_rejected_before_runtime(tmp_path: Path) -> None:
    content = _case_yaml().replace("type: route_match", "type: unknown_assertion")
    (tmp_path / "case.yaml").write_text(content, encoding="utf-8")
    result = validate_suite(tmp_path)
    assert not result.valid
    assert "unsupported_assertion" in {item.code for item in result.diagnostics}


def test_invalid_output_field_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "case.yaml").write_text(_case_yaml(field="missing_output"), encoding="utf-8")
    result = validate_suite(tmp_path)
    assert not result.valid
    assert "invalid_field_reference" in {item.code for item in result.diagnostics}


def test_category_filter_uses_yaml_metadata_not_directory(tmp_path: Path) -> None:
    misleading_dir = tmp_path / "memory"
    misleading_dir.mkdir()
    (misleading_dir / "case.yaml").write_text(_case_yaml(), encoding="utf-8")
    cases = load_cases_strict(tmp_path, category="intent_recognition")
    assert [case.case_id for case in cases] == ["case_001"]
