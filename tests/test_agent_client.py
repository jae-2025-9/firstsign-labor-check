"""
Classify 결과 찾기 테스트 (API를 호출하지 않는다)
"""

from agent_client import find_classification
from rules import LEVELS


def test_finds_label_under_classification_key():
    raw = {"output": [{"type": "classify", "classification": "risky"}, {"type": "message", "content": "..."}]}
    assert find_classification(raw, LEVELS) == "risky"


def test_ambiguous_labels_return_none():
    # 워크플로우 정의가 응답에 함께 실려 분류 이름 3개가 모두 보이는 경우
    raw = {"edges": [{"condition": "safe"}, {"condition": "check_needed"}, {"condition": "risky"}]}
    assert find_classification(raw, LEVELS) is None


def test_no_label():
    assert find_classification({"output_text": "{}"}, LEVELS) is None
