"""评估系统核心模块"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EvalCaseStatus(str, Enum):
    """评估用例状态"""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class AssertionType(str, Enum):
    """断言类型"""

    ROUTE_MATCH = "route_match"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    RESPONSE_QUALITY = "response_quality"
    MEMORY_CHECK = "memory_check"
    EXTRACTION_QUALITY = "extraction_quality"
    HALLUCINATION_CHECK = "hallucination_check"
    ARTIFACT_VALID = "artifact_valid"
    SECURITY_CHECK = "security_check"
    PERFORMANCE_CHECK = "performance_check"
    COUNT_CHECK = "count_check"
    ENCODING_CHECK = "encoding_check"


class EvalAssertion(BaseModel):
    """评估断言"""

    type: AssertionType
    field: str
    expected: Any
    weight: float = 1.0
    rubric: Optional[str] = None
    min_score: Optional[float] = None
    memory_check_type: Optional[Literal["profile", "experience"]] = None
    should_exist: Optional[bool] = None
    max_privacy_exposure: Optional[float] = None
    hallucination_keywords: Optional[list[str]] = None


class EvalCase(BaseModel):
    """评估用例"""

    case_id: str
    category: str
    description: str
    version: str
    input: dict[str, Any]
    context: dict[str, Any]
    expectations: dict[str, Any]
    assertions: list[EvalAssertion]
    rubric: Optional[str] = None
    metadata: dict[str, Any]


class EvalResult(BaseModel):
    """评估结果"""

    case_id: str
    run_id: str
    status: EvalCaseStatus
    score: float = Field(ge=0.0, le=1.0)
    assertion_results: list[dict[str, Any]]
    actual_output: dict[str, Any]
    execution_time: float
    error_message: Optional[str] = None
    trace_id: Optional[str] = None
    run_mode: Literal["deterministic", "model-eval", "smoke"] = "model-eval"
    model: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class EvalCategoryMetrics(BaseModel):
    """Unambiguous metrics for one evaluation category."""

    count: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0
    pass_rate: float = 0.0
    error_rate: float = 0.0
    avg_score: float = 0.0


class EvalRunManifest(BaseModel):
    """Non-sensitive metadata required to reproduce an evaluation run."""

    dataset_fingerprint: str = ""
    git_commit: str = "unknown"
    environment: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, Any] = Field(default_factory=dict)
    commands: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    """评估报告"""

    suite_id: str
    total_cases: int
    passed: int
    failed: int
    error: int
    avg_score: float
    category_scores: dict[str, float]
    schema_version: str = "2.0"
    run_mode: Literal["deterministic", "model-eval", "smoke", "legacy"] = "model-eval"
    pass_rate: float = 0.0
    error_rate: float = 0.0
    category_metrics: dict[str, EvalCategoryMetrics] = Field(default_factory=dict)
    dataset_fingerprint: str = ""
    git_commit: str = "unknown"
    model: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    manifest: EvalRunManifest = Field(default_factory=EvalRunManifest)
    results: list[EvalResult]
    execution_time: float
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
