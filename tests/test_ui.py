"""
Streamlit 화면 자동 테스트 (데모 모드, 에이전트를 호출하지 않는다)
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import service


FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "expected"


@pytest.fixture(autouse=True)
def demo(monkeypatch, tmp_path):
    # 저장된 실제 결과(fixtures/live)와 상관없이 예상값(fixtures/expected)만 쓰게 한다
    monkeypatch.setattr(service, "is_live_ready", lambda: False)
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "expected").symlink_to(FIXTURES)
    monkeypatch.setattr(service, "FIXTURE_DIR", tmp_path / "fixtures")


def run_sample(sample_id: str) -> AppTest:
    at = AppTest.from_file("../streamlit_app.py", default_timeout=30).run()
    at.selectbox[0].set_value(sample_id).run()
    at.button[0].click().run()
    assert not at.exception
    return at


def page_text(at: AppTest) -> str:
    return " ".join(str(block.value) for block in (*at.markdown, *at.caption, *at.info, *at.warning, *at.text))


def overall_badge(at: AppTest) -> str:
    """
    종합 진단 카드에 찍힌 배지 문구
    """

    card = next(str(block.value) for block in at.markdown if "종합 진단" in str(block.value))
    head = card.split('<p class="fs-summary">')[0]
    return head.rsplit("</span>", 2)[-2].rsplit(">", 1)[-1]


@pytest.mark.parametrize("sample_id,label", [("1", "안심"), ("2", "확인 필요"), ("3", "위험"), ("4", "안심")])
def test_samples_render(sample_id, label):
    at = run_sample(sample_id)
    assert overall_badge(at) == label
    assert "데모: 규칙 계산 결과" in page_text(at)


def test_pending_result_renders(monkeypatch):
    original = service.demo_inputs

    def with_unclear_terms(sample_id):
        contract, criteria, review, raw, source = original(sample_id)
        contract = dict(contract, special_terms=["퇴사시 마지막 임금을 지급한다."], is_signed=[False])
        return contract, criteria, review, raw, source

    monkeypatch.setattr(service, "demo_inputs", with_unclear_terms)
    text = page_text(run_sample("1"))
    assert "판단 보류" in text
    assert "최소 '확인 필요'" in text


def test_partial_cross_check_is_not_shown_as_match(monkeypatch):
    original = service.demo_inputs

    def recorded_with_changed_conditions(sample_id):
        contract, criteria, _, _, _ = original(sample_id)
        criteria = {**criteria, "check_rules": [{**r, "check_condition": "점검 조건: " + r["check_condition"]} for r in criteria["check_rules"]]}
        review = {"review_level": ["safe"], "summary": ["문제가 없습니다."], "matched_rules": [], "missing_items": [],
                  "risky_clauses": [], "confirmed_items": [], "recommendations": []}
        return contract, criteria, review, {}, "recorded"

    monkeypatch.setattr(service, "demo_inputs", recorded_with_changed_conditions)
    at = run_sample("1")
    text = page_text(at)
    assert "교차 검증 일부만 완료" in text
    assert "교차 검증 일치" not in text
    assert overall_badge(at) == "안심"
