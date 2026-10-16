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


def test_empty_review_is_an_error():
    import pytest
    from agent_client import AgentError
    with pytest.raises(AgentError):
        normalize_review({}, {})


def test_classify_prefers_executed_output():
    from agent_client import find_classification
    from rules import LEVELS
    raw = {
        "output": [{"type": "classification", "label": "risky"}],
        "edges": [{"condition": "safe"}, {"condition": "check_needed"}, {"condition": "risky"}],
    }
    assert find_classification(raw, LEVELS) == "risky"
    review = normalize_review({"review_level": ["safe"], "summary": ["..."]}, raw)
    assert review["review_level"] == "risky" and review["level_conflict"] is True


def test_polling_respects_deadline(monkeypatch):
    import pytest
    import agent_client

    clock = {"now": 0.0}

    class Responses:
        def retrieve(self, job_id, include):
            clock["now"] += 100
            return type("R", (), {"status": "in_progress"})()

    class Client:
        responses = Responses()
        def with_options(self, timeout):
            assert timeout <= agent_client.HTTP_TIMEOUT_SECONDS
            return self

    monkeypatch.setattr(agent_client, "get_client", lambda: Client())
    monkeypatch.setattr(agent_client, "AGENT_TIMEOUT_SECONDS", 180)
    monkeypatch.setattr(agent_client.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(agent_client.time, "sleep", lambda seconds: None)

    with pytest.raises(agent_client.AgentError, match="180초"):
        agent_client.AgentClient("agt_x", "1", "Test").wait_until_complete("job")
    assert clock["now"] <= 200
