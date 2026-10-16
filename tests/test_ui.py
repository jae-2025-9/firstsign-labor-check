"""
Streamlit 화면 자동 테스트 (데모 모드, 에이전트를 호출하지 않는다)
"""

import pytest
from streamlit.testing.v1 import AppTest

import service


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setattr(service, "is_live_ready", lambda: False)


def run_sample(sample_id: str) -> AppTest:
    at = AppTest.from_file("../streamlit_app.py", default_timeout=30).run()
    at.selectbox[0].set_value(sample_id).run()
    at.button[0].click().run()
    assert not at.exception
    return at


def page_text(at: AppTest) -> str:
    return " ".join(str(block.value) for block in (*at.markdown, *at.caption, *at.info, *at.warning, *at.text))


@pytest.mark.parametrize("sample_id,label", [("1", "안심"), ("2", "확인 필요"), ("3", "위험"), ("4", "안심")])
def test_samples_render(sample_id, label):
    text = page_text(run_sample(sample_id))
    assert f"{label}</span>" in text
    assert "데모: 규칙 계산 결과" in text


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
