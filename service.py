"""
service.py

화면과 워크플로우 사이의 비즈니스 로직

- 실연결 모드: Studio 에이전트 3개를 실제로 호출한다 (app.run_workflow).
- 데모 모드: 키나 Agent ID가 없거나 FORCE_DEMO=1이면 샘플만 점검한다.
  fixtures/live/에 실제 에이전트 결과가 있으면 그것을 재생하고,
  없으면 팀이 만든 예상 추출값(fixtures/expected/)에 규칙 계산을 적용한다.

어느 모드든 마지막에 규칙 계산으로 교차 검증하고, 두 판정 중 더 엄격한 등급을 보여 준다.
"""

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from openai import APIConnectionError, APIStatusError, RateLimitError

from config import (
    FIXTURE_DIR,
    MAX_UPLOAD_MB,
    RUNS_DIR,
    SAMPLES,
    SAMPLE_DIR,
    create_directories,
    is_live_ready
)
from agent_client import AgentError
from app import normalize_review, run_workflow
from file_manager import load_json
from review_builder import build_review_input, contract_rows
from rules import (
    compute_facts,
    cross_check,
    engine_review,
    evaluate,
    more_severe
)


##################################################
# Errors
##################################################

class ServiceError(RuntimeError):
    """
    화면에 그대로 보여 줄 수 있는 오류
    """


##################################################
# Input Validation
##################################################

def validate_pdf(data: bytes) -> None:

    if not data:
        raise ServiceError("빈 파일입니다. 근로계약서 PDF를 다시 올려 주세요.")

    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ServiceError(f"파일이 너무 큽니다. {MAX_UPLOAD_MB}MB 이하 PDF만 올릴 수 있습니다.")

    if not data.lstrip()[:5] == b"%PDF-":
        raise ServiceError("PDF 파일이 아닙니다. 근로계약서를 PDF로 저장해 올려 주세요.")


def new_run_dir() -> Path:

    create_directories()

    run_dir = RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=False)

    return run_dir


##################################################
# Demo
##################################################

def demo_inputs(sample_id: str) -> tuple[dict, dict, dict | None, dict | None, str]:
    """
    (contract, criteria, review, review_raw, source)
    """

    live, expected = FIXTURE_DIR / "live", FIXTURE_DIR / "expected"

    contract_path = live / f"contract_sample{sample_id}.json"
    review_path = live / f"review_sample{sample_id}.json"
    raw_path = live / f"review_sample{sample_id}_raw.json"

    if contract_path.exists() and review_path.exists() and (live / "criteria.json").exists():
        return (
            load_json(contract_path),
            load_json(live / "criteria.json"),
            load_json(review_path),
            load_json(raw_path) if raw_path.exists() else {},
            "recorded",
        )

    return (
        load_json(expected / f"contract_sample{sample_id}.json"),
        load_json(expected / "criteria.json"),
        None,
        None,
        "rules",
    )


##################################################
# Service
##################################################

def run_review_service(
    pdf_bytes: bytes | None = None,
    sample_id: str | None = None,
    progress=None
) -> dict:
    """
    근로계약서 하나를 점검한다.

    pdf_bytes(업로드한 파일)나 sample_id(체험용 샘플) 중 하나를 준다.
    """

    if (pdf_bytes is None) == (sample_id is None):
        raise ServiceError("계약서 파일이나 샘플 중 하나만 선택해 주세요.")

    if sample_id is not None and sample_id not in SAMPLES:
        raise ServiceError("없는 샘플입니다.")

    live = is_live_ready()

    if pdf_bytes is not None:
        validate_pdf(pdf_bytes)
        if not live:
            raise ServiceError(
                "지금은 데모 모드라 업로드한 계약서는 점검할 수 없습니다. "
                "아래 샘플 계약서로 체험해 주세요."
            )

    run_dir = new_run_dir()

    try:

        if live:
            mode, source = "live", "agent"

            if pdf_bytes is not None:
                contract_file = run_dir / "upload.pdf"
                contract_file.write_bytes(pdf_bytes)
            else:
                contract_file = SAMPLE_DIR / SAMPLES[sample_id]["file"]

            result = run_workflow(contract_file, run_dir=run_dir, progress=progress)
            contract, criteria, facts = result["contract"], result["criteria"], result["facts"]
            review_raw_json, raw = result["review"], result["review_raw"] or {}

        else:
            contract, criteria, review_raw_json, raw, source = demo_inputs(sample_id)
            mode = "demo"
            facts = compute_facts(contract, criteria)

            if progress:
                progress(3, "계약 정보와 기준서를 한 문서로 합치고 있습니다 (데모)")

            build_review_input(contract, criteria, facts, run_dir / "Review_Input.pdf", title="점검 입력 문서 (데모)")

        if progress:
            progress(5, "규칙 계산으로 결과를 교차 검증하고 있습니다")

        engine = evaluate(contract, criteria, facts)

        if not engine["is_contract"]:
            review = None
        elif review_raw_json is not None:
            review = normalize_review(review_raw_json, raw or {})
        else:
            review = engine_review(engine)

        agent_level = review["review_level"] if (review and source != "rules") else None
        check = cross_check(agent_level, review["matched_rules"] if review else [], engine)

        review_pdf = run_dir / "Review_Input.pdf"

        return {
            "mode": mode,
            "source": source,
            "sample_id": sample_id,
            "contract": contract,
            "contract_rows": contract_rows(contract),
            "criteria": criteria,
            "facts": facts,
            "engine": engine,
            "review": review,
            "agent_level": agent_level,
            "engine_level": engine["level"],
            "final_level": more_severe(agent_level, engine["level"]),
            "cross_check": check,
            "review_pdf_bytes": review_pdf.read_bytes() if review_pdf.exists() else None,
        }

    except ServiceError:
        raise

    except RateLimitError as error:
        raise ServiceError("Upstage API 요청 한도를 넘었습니다. 잠시 뒤 다시 시도해 주세요.") from error

    except APIConnectionError as error:
        raise ServiceError("Upstage API에 연결하지 못했습니다. 네트워크를 확인해 주세요.") from error

    except APIStatusError as error:
        raise ServiceError(f"Upstage API 오류({error.status_code})가 났습니다. Agent ID와 API Key를 확인해 주세요.") from error

    except AgentError as error:
        raise ServiceError(f"에이전트 실행 중 문제가 생겼습니다: {error}") from error

    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
