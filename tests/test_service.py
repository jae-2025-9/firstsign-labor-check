"""
데모 모드 서비스와 평가 입력 PDF 테스트 (에이전트를 호출하지 않는다)
"""

import json
from pathlib import Path

import pytest

import config
import service
from review_builder import build_review_input
from rules import compute_facts

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "expected"


@pytest.fixture(autouse=True)
def demo_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "is_live_ready", lambda: False)
    monkeypatch.setattr(service, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(service, "FIXTURE_DIR", tmp_path / "fixtures")
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "expected").symlink_to(FIXTURES)


@pytest.mark.parametrize("sample_id,level", [("1", "safe"), ("2", "check_needed"), ("3", "risky"), ("4", "safe")])
def test_demo_samples(sample_id, level):
    result = service.run_review_service(sample_id=sample_id)
    assert result["mode"] == "demo"
    assert result["source"] == "rules"
    assert result["final_level"] == level
    assert result["final"]["level"] == level
    assert result["review"]["review_level"] == level
    assert result["review_pdf_bytes"][:5] == b"%PDF-"


def test_demo_cleans_run_dir(tmp_path):
    service.run_review_service(sample_id="1")
    assert list((tmp_path / "runs").iterdir()) == []


def test_upload_rejected_in_demo():
    with pytest.raises(service.ServiceError, match="데모 모드"):
        service.run_review_service(pdf_bytes=(config.SAMPLE_DIR / "sample1.pdf").read_bytes())


@pytest.mark.parametrize("data,message", [
    (b"", "빈 파일"),
    (b"hello", "PDF 파일이 아닙니다"),
    (b"%PDF-", "손상"),
    (b"%PDF-1.4 not a PDF", "손상"),
])
def test_upload_validation(data, message):
    with pytest.raises(service.ServiceError, match=message):
        service.run_review_service(pdf_bytes=data)


def test_real_pdf_passes_validation():
    service.validate_pdf((config.SAMPLE_DIR / "sample1.pdf").read_bytes())


def test_encrypted_pdf_is_rejected(tmp_path):
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    for page in PdfReader(config.SAMPLE_DIR / "sample1.pdf").pages:
        writer.add_page(page)
    writer.encrypt("secret")
    target = tmp_path / "locked.pdf"
    with open(target, "wb") as f:
        writer.write(f)
    with pytest.raises(service.ServiceError, match="암호"):
        service.validate_pdf(target.read_bytes())


def test_requires_exactly_one_input():
    with pytest.raises(service.ServiceError):
        service.run_review_service()


def test_review_input_pdf_with_very_long_terms(tmp_path):
    contract = json.loads((FIXTURES / "contract_sample3.json").read_text(encoding="utf-8"))
    criteria = json.loads((FIXTURES / "criteria.json").read_text(encoding="utf-8"))
    contract["special_terms"] = ["기타 계약 조항입니다. " * 1000]
    path = build_review_input(contract, criteria, compute_facts(contract, criteria), tmp_path / "long.pdf")
    assert path.read_bytes()[:5] == b"%PDF-"


def test_review_input_pdf_with_many_short_lines(tmp_path):
    contract = json.loads((FIXTURES / "contract_sample3.json").read_text(encoding="utf-8"))
    criteria = json.loads((FIXTURES / "criteria.json").read_text(encoding="utf-8"))
    contract["special_terms"] = ["조항\n" * 60]
    path = build_review_input(contract, criteria, compute_facts(contract, criteria), tmp_path / "lines.pdf")
    assert path.read_bytes()[:5] == b"%PDF-"


def test_review_input_pdf(tmp_path):
    contract = json.loads((FIXTURES / "contract_sample3.json").read_text(encoding="utf-8"))
    criteria = json.loads((FIXTURES / "criteria.json").read_text(encoding="utf-8"))
    path = build_review_input(contract, criteria, compute_facts(contract, criteria), tmp_path / "Review_Input.pdf")
    assert path.read_bytes()[:5] == b"%PDF-"
    assert path.stat().st_size > 5000


def test_live_needs_all_settings(monkeypatch):
    monkeypatch.setattr(config, "FORCE_DEMO", False)
    monkeypatch.setattr(config, "UPSTAGE_API_KEY", "")
    assert not config.is_live_ready()
    assert "UPSTAGE_API_KEY" in config.missing_settings()
