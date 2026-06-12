"""Tests for assertion types and EvalAssertion model"""
import pytest
from typing import Any

from app.core.evaluation import AssertionType, EvalAssertion


class TestAssertionTypes:
    """Test new assertion types are properly defined"""

    def test_memory_check_assertion_type_exists(self):
        """Verify MEMORY_CHECK assertion type exists"""
        assert hasattr(AssertionType, "MEMORY_CHECK")
        assert AssertionType.MEMORY_CHECK.value == "memory_check"

    def test_extraction_quality_assertion_type_exists(self):
        """Verify EXTRACTION_QUALITY assertion type exists"""
        assert hasattr(AssertionType, "EXTRACTION_QUALITY")
        assert AssertionType.EXTRACTION_QUALITY.value == "extraction_quality"

    def test_hallucination_check_assertion_type_exists(self):
        """Verify HALLUCINATION_CHECK assertion type exists"""
        assert hasattr(AssertionType, "HALLUCINATION_CHECK")
        assert AssertionType.HALLUCINATION_CHECK.value == "hallucination_check"


class TestEvalAssertionDataModel:
    """Test EvalAssertion model with new fields"""

    def test_memory_check_assertion_serialization(self):
        """Test MEMORY_CHECK assertion with memory-specific fields"""
        assertion = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="profile_memory",
            expected={"interests": "math"},
            weight=1.0,
            memory_check_type="profile",
            should_exist=True,
            max_privacy_exposure=0.1,
        )

        # Verify all fields are set correctly
        assert assertion.type == AssertionType.MEMORY_CHECK
        assert assertion.field == "profile_memory"
        assert assertion.memory_check_type == "profile"
        assert assertion.should_exist is True
        assert assertion.max_privacy_exposure == 0.1

        # Verify serialization works
        data = assertion.model_dump()
        assert data["type"] == "memory_check"
        assert data["memory_check_type"] == "profile"
        assert data["should_exist"] is True
        assert data["max_privacy_exposure"] == 0.1

    def test_extraction_quality_assertion_serialization(self):
        """Test EXTRACTION_QUALITY assertion with optional fields"""
        assertion = EvalAssertion(
            type=AssertionType.EXTRACTION_QUALITY,
            field="teaching_elements",
            expected={
                "subject": "Math",
                "grade": "10",
                "topic": "Algebra",
            },
            weight=2.0,
            min_score=0.8,
            rubric="Ensure all teaching elements are accurately extracted",
        )

        # Verify fields
        assert assertion.type == AssertionType.EXTRACTION_QUALITY
        assert assertion.field == "teaching_elements"
        assert assertion.weight == 2.0
        assert assertion.min_score == 0.8
        assert assertion.rubric == "Ensure all teaching elements are accurately extracted"

        # Verify serialization
        data = assertion.model_dump()
        assert data["type"] == "extraction_quality"
        assert data["weight"] == 2.0

    def test_hallucination_check_assertion_serialization(self):
        """Test HALLUCINATION_CHECK assertion with hallucination keywords"""
        assertion = EvalAssertion(
            type=AssertionType.HALLUCINATION_CHECK,
            field="generated_content",
            expected={"no_hallucinations": True},
            weight=1.5,
            hallucination_keywords=["fictional", "invented", "made-up", "assumed"],
            max_privacy_exposure=0.0,
        )

        # Verify fields
        assert assertion.type == AssertionType.HALLUCINATION_CHECK
        assert assertion.field == "generated_content"
        assert len(assertion.hallucination_keywords) == 4
        assert "fictional" in assertion.hallucination_keywords
        assert assertion.max_privacy_exposure == 0.0

        # Verify serialization
        data = assertion.model_dump()
        assert data["type"] == "hallucination_check"
        assert len(data["hallucination_keywords"]) == 4

    def test_assertion_optional_fields_default_to_none(self):
        """Test that new optional fields default to None when not provided"""
        assertion = EvalAssertion(
            type=AssertionType.ROUTE_MATCH,
            field="route",
            expected="teaching_plan",
        )

        # Verify new fields are None by default
        assert assertion.memory_check_type is None
        assert assertion.should_exist is None
        assert assertion.max_privacy_exposure is None
        assert assertion.hallucination_keywords is None

        # Verify serialization with None values
        data = assertion.model_dump()
        assert data["memory_check_type"] is None
        assert data["should_exist"] is None
        assert data["max_privacy_exposure"] is None
        assert data["hallucination_keywords"] is None

    def test_memory_check_type_validation(self):
        """Test memory_check_type only accepts 'profile' or 'experience'"""
        # Valid values should work
        assertion_profile = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="memory",
            expected={},
            memory_check_type="profile",
        )
        assert assertion_profile.memory_check_type == "profile"

        assertion_experience = EvalAssertion(
            type=AssertionType.MEMORY_CHECK,
            field="memory",
            expected={},
            memory_check_type="experience",
        )
        assert assertion_experience.memory_check_type == "experience"

        # Invalid values should raise validation error
        with pytest.raises(ValueError):
            EvalAssertion(
                type=AssertionType.MEMORY_CHECK,
                field="memory",
                expected={},
                memory_check_type="invalid_type",
            )

    def test_hallucination_keywords_list_validation(self):
        """Test hallucination_keywords accepts list of strings"""
        assertion = EvalAssertion(
            type=AssertionType.HALLUCINATION_CHECK,
            field="content",
            expected={},
            hallucination_keywords=["wrong", "incorrect", "false"],
        )

        assert isinstance(assertion.hallucination_keywords, list)
        assert all(isinstance(kw, str) for kw in assertion.hallucination_keywords)

    def test_max_privacy_exposure_range(self):
        """Test max_privacy_exposure can be any float value between 0 and 1"""
        # Valid values
        for value in [0.0, 0.5, 1.0]:
            assertion = EvalAssertion(
                type=AssertionType.MEMORY_CHECK,
                field="memory",
                expected={},
                max_privacy_exposure=value,
            )
            assert assertion.max_privacy_exposure == value

    def test_assertion_model_deserialization(self):
        """Test EvalAssertion can be deserialized from dict"""
        data = {
            "type": "memory_check",
            "field": "profile_memory",
            "expected": {"interests": "music"},
            "weight": 1.0,
            "rubric": None,
            "min_score": None,
            "memory_check_type": "profile",
            "should_exist": True,
            "max_privacy_exposure": 0.2,
            "hallucination_keywords": None,
        }

        assertion = EvalAssertion(**data)

        assert assertion.type == AssertionType.MEMORY_CHECK
        assert assertion.memory_check_type == "profile"
        assert assertion.should_exist is True
        assert assertion.max_privacy_exposure == 0.2
