"""
평가 에이전트 결과 정규화 테스트
"""

from app import normalize_review


def test_schema_and_classify_conflict_uses_stricter():
    review = normalize_review({"review_level": ["safe"], "summary": ["..."]}, {"output": [{"type": "classification", "label": "risky"}]})
    assert review["review_level"] == "risky"
    assert review["level_conflict"] is True


def test_schema_level_only():
    review = normalize_review({"review_level": ["check_needed"]}, {})
    assert review["review_level"] == "check_needed"
    assert review["level_conflict"] is False


def test_no_level_anywhere():
    review = normalize_review({"summary": ["요약"]}, {})
    assert review["review_level"] is None
    assert review["summary"] == "요약"
