from __future__ import annotations

from tests.evals.evaluators.memory_evaluator import MemoryEvaluator


def test_privacy_exposure_increases_with_sensitive_keywords() -> None:
    evaluator = MemoryEvaluator()
    clean = evaluator._calculate_privacy_exposure("偏好互动教学", "小组讨论效果好")
    one = evaluator._calculate_privacy_exposure("电话：13800138000", "")
    many = evaluator._calculate_privacy_exposure("电话：13800138000，邮箱：teacher@example.com", "地址：北京市")
    assert clean == 0.0
    assert 0.0 < one < many <= 1.0


def test_memory_operations_distinguish_create_and_update() -> None:
    operations = MemoryEvaluator._memory_operations(
        [{"id": "profile-1", "content": "old"}],
        [
            {"id": "profile-1", "content": "new"},
            {"id": "profile-2", "content": "created"},
        ],
        [],
        [{"id": "experience-1", "content": "created"}],
    )
    assert {tuple(sorted(item.items())) for item in operations} == {
        tuple(sorted({"operation": "update", "kind": "profile", "id": "profile-1"}.items())),
        tuple(sorted({"operation": "create", "kind": "profile", "id": "profile-2"}.items())),
        tuple(sorted({"operation": "create", "kind": "experience", "id": "experience-1"}.items())),
    }


def test_memory_evaluator_declares_stable_output_fields() -> None:
    fields = {
        "profile_memory_context",
        "experience_memory_context",
        "loaded_experience_memories",
        "profile_memory_created",
        "experience_memory_created",
        "profile_memory_id",
        "profile_memory_content",
        "total_profile_memories",
        "privacy_exposure",
    }
    assert fields
