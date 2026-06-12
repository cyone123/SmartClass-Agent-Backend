"""评估系统核心模块"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

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
    ARTIFACT_VALID = "artifact_valid"
    SECURITY_CHECK = "security_check"
    PERFORMANCE_CHECK = "performance_check"


class EvalAssertion(BaseModel):
    """评估断言"""
    type: AssertionType
    field: str
    expected: Any
    weight: float = 1.0
    rubric: Optional[str] = None
    min_score: Optional[float] = None


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
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class EvalReport(BaseModel):
    """评估报告"""
    suite_id: str
    total_cases: int
    passed: int
    failed: int
    error: int
    avg_score: float
    category_scores: dict[str, float]
    results: list[EvalResult]
    execution_time: float
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
