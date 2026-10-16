"""
app.py

첫사인 알바 안심 체크 - 전체 워크플로우

근로계약서.pdf → [Contract Agent] → contract.json ─┐
                                                   ├→ [review_builder.py] → Review_Input.pdf → [Review Agent] → review_result.json
점검기준서.pdf → [Criteria Agent] → criteria.json ──┘          (3부: rules.py 계산값)

실행
    python app.py                       # 샘플 1 계약서
    python app.py --sample 3            # 샘플 3 계약서
    python app.py --contract my.pdf     # 내 계약서
    python app.py --sample 3 --save-fixture   # 결과를 fixtures/live/에 저장 (데모 모드 재생용)
"""

import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from config import (
    CACHE_DIR,
    CONTRACT_JSON,
    CRITERIA_AGENT_ID,
    CRITERIA_CONFIG_ID,
    CRITERIA_FILE,
    CRITERIA_JSON,
    FIXTURE_DIR,
    REVIEW_PDF,
    REVIEW_RESULT,
    SAMPLES,
    SAMPLE_DIR,
    print_config,
    validate_config
)
from agent_client import AgentError, find_classification
from contract_agent import analyze_contract
from criteria_agent import analyze_criteria
from review_agent import analyze_review
from file_manager import file_lock, file_sha256, load_json, save_json
from review_builder import build_review_input
from rules import (
    LEVELS,
    RULE_CODE_PATTERN,
    as_list,
    compute_facts,
    criteria_problems,
    evaluate,
    is_blank,
    looks_like_contract,
    more_severe,
    normalize_level,
    text
)
from upload import upload_file


# 평가 에이전트 결과 스키마 항목 (Review Agent 수정본)
REVIEW_FIELDS = ("review_level", "summary", "matched_rules", "missing_items", "risky_clauses", "confirmed_items", "recommendations")


class CriteriaError(AgentError):
    """
    기준서 추출 결과로 점검할 수 없음
    """


##################################################
# Step 1, 2. 문서 추출
##################################################

def process_document(
    step: str,
    input_file: Path,
    analyzer,
    output_json: Path
) -> dict:
    """
    PDF 업로드 → 에이전트 실행 → JSON 저장
    """

    print()
    print("=" * 60)
    print(step)
    print("=" * 60)

    file_id = upload_file(input_file)
    result, _ = analyzer(file_id)

    save_json(result, output_json)
    print(f"Saved : {output_json}")

    return result


def criteria_source_codes(criteria_file: Path = CRITERIA_FILE) -> set[str] | None:
    """
    기준서 PDF 원문에서 규칙 코드를 직접 읽는다. 추출 결과에 빠진 규칙이 없는지 대조할 때 쓴다.
    PDF에서 글자를 읽지 못하면 None(대조하지 않음)을 돌려준다.
    """

    try:
        reader = PdfReader(str(criteria_file))
        content = "\n".join(page.extract_text() or "" for page in reader.pages)
    except (OSError, ValueError, PdfReadError):
        return None

    codes = set(RULE_CODE_PATTERN.findall(content))

    return codes or None


def load_or_extract_criteria(
    criteria_file: Path = CRITERIA_FILE,
    output_json: Path = CRITERIA_JSON
) -> dict:
    """
    기준서는 고정 문서라 내용이 같으면 추출 결과를 다시 쓴다.

    캐시 키에는 기준서 PDF 해시와 Criteria Agent ID·Config ID를 넣는다.
    기준서나 에이전트 설정을 바꾸면 다시 추출한다. 읽을 수 없거나 쓸 수 없는 캐시도 다시 추출한다.
    같은 키의 첫 요청이 동시에 들어와도 추출은 한 번만 하도록 키별 잠금을 건다.
    """

    key = f"{file_sha256(criteria_file)[:16]}_{CRITERIA_AGENT_ID}_{CRITERIA_CONFIG_ID}"
    cache = CACHE_DIR / f"criteria_{re.sub(r'[^A-Za-z0-9_.-]', '_', key)}.json"
    source_codes = criteria_source_codes(criteria_file)

    def usable(path: Path) -> dict | None:
        try:
            cached = load_json(path)
        except (OSError, ValueError):
            return None
        return cached if isinstance(cached, dict) and not criteria_problems(cached, source_codes) else None

    with file_lock(cache.with_suffix(".lock")):

        criteria = usable(cache) if cache.exists() else None

        if criteria is not None:
            print(f"\nStep 2. Criteria Agent (캐시 사용: {cache.name})")
        else:
            criteria = process_document("Step 2. Criteria Agent", criteria_file, analyze_criteria, output_json)

            problems = criteria_problems(criteria, source_codes)

            if problems:
                raise CriteriaError("점검 기준서를 읽지 못했습니다: " + ", ".join(problems))

            save_json(criteria, cache)

    save_json(criteria, output_json)

    return criteria


##################################################
# Step 3. 평가 입력 PDF
##################################################

def build_review_pdf(
    contract: dict,
    criteria: dict,
    output_pdf: Path = REVIEW_PDF
) -> tuple[Path, dict]:

    print()
    print("=" * 60)
    print("Step 3. Build Review Input PDF")
    print("=" * 60)

    facts = compute_facts(contract, criteria)
    path = build_review_input(contract, criteria, facts, output_pdf)

    return path, facts


##################################################
# Step 4. 평가 에이전트
##################################################

def normalize_review(review: dict, raw: dict) -> dict:
    """
    평가 에이전트 결과를 화면에서 쓰기 좋은 모양으로 바꾼다.

    분류는 결과 스키마의 review_level과 응답 원본의 Classify 결과를 모두 본다.
    둘이 다르면 더 엄격한 쪽을 쓰고 level_conflict로 알린다.
    결과 스키마의 항목이 하나도 없으면(빈 결과) 평가가 끝난 것으로 보지 않고 오류를 낸다.
    """

    if not any(not is_blank(review.get(key)) for key in REVIEW_FIELDS):
        raise AgentError("평가 에이전트 결과가 비어 있습니다. Review Agent 설정을 확인해 주세요.")

    for key in REVIEW_FIELDS:
        value = review.get(key)
        if value is not None and not isinstance(value, (str, list)):
            raise AgentError(f"평가 에이전트 결과의 {key} 형식이 올바르지 않습니다.")

    schema_level = normalize_level(review.get("review_level"))
    classify_level = find_classification(raw, LEVELS)

    return {
        "review_level": more_severe(schema_level, classify_level),
        "schema_level": schema_level,
        "classify_level": classify_level,
        "level_conflict": bool(schema_level and classify_level and schema_level != classify_level),
        "summary": text(review.get("summary")),
        "matched_rules": [str(item) for item in as_list(review.get("matched_rules"))],
        "missing_items": [str(item) for item in as_list(review.get("missing_items"))],
        "risky_clauses": [str(item) for item in as_list(review.get("risky_clauses"))],
        "confirmed_items": [str(item) for item in as_list(review.get("confirmed_items"))],
        "recommendations": [str(item) for item in as_list(review.get("recommendations"))],
    }


def process_review(
    review_pdf: Path,
    output_json: Path = REVIEW_RESULT
) -> tuple[dict, dict]:

    print()
    print("=" * 60)
    print("Step 4. Review Agent")
    print("=" * 60)

    file_id = upload_file(review_pdf)
    review, raw = analyze_review(file_id)

    save_json(review, output_json)
    print(f"Saved : {output_json}")

    return review, raw


##################################################
# Workflow
##################################################

def run_workflow(
    contract_file: Path,
    run_dir: Path | None = None,
    progress=None
) -> dict:
    """
    네 단계를 순서대로 실행한다. 실패하면 예외를 그대로 올린다.

    run_dir를 주면 결과 파일을 그 폴더에 따로 둔다 (Streamlit 동시 접속용).
    """

    def report(step: int, message: str):
        if progress:
            progress(step, message)

    paths = {
        "contract": (run_dir / "contract.json") if run_dir else CONTRACT_JSON,
        "criteria": (run_dir / "criteria.json") if run_dir else CRITERIA_JSON,
        "review_pdf": (run_dir / "Review_Input.pdf") if run_dir else REVIEW_PDF,
        "review": (run_dir / "review_result.json") if run_dir else REVIEW_RESULT,
    }

    report(1, "계약서를 읽고 항목을 추출하고 있습니다 (Contract Agent)")
    contract = process_document("Step 1. Contract Agent", Path(contract_file), analyze_contract, paths["contract"])

    report(2, "점검 기준서를 불러오고 있습니다 (Criteria Agent)")
    criteria = load_or_extract_criteria(CRITERIA_FILE, paths["criteria"])

    if not looks_like_contract(contract):
        return {
            "contract": contract,
            "criteria": criteria,
            "facts": compute_facts(contract, criteria),
            "review": None,
            "review_raw": None,
            "paths": paths,
        }

    report(3, "계약 정보와 기준서를 한 문서로 합치고 있습니다")
    review_pdf, facts = build_review_pdf(contract, criteria, paths["review_pdf"])

    report(4, "안심 · 확인 필요 · 위험 중 하나로 평가하고 있습니다 (Review Agent)")
    review, raw = process_review(review_pdf, paths["review"])

    return {
        "contract": contract,
        "criteria": criteria,
        "facts": facts,
        "review": review,
        "review_raw": raw,
        "paths": paths,
    }


def save_fixture(sample_id: str, result: dict):
    """
    실제 에이전트 결과를 fixtures/live/에 저장한다.
    FORCE_DEMO=1이나 키 없이 실행할 때 이 결과를 그대로 보여 준다.
    """

    live = FIXTURE_DIR / "live"

    save_json(result["contract"], live / f"contract_sample{sample_id}.json")
    save_json(result["criteria"], live / "criteria.json")

    if result["review"] is not None:
        save_json(result["review"], live / f"review_sample{sample_id}.json")
        save_json(result["review_raw"], live / f"review_sample{sample_id}_raw.json")

    print(f"Fixture Saved : {live}")


##################################################
# Result
##################################################

def print_result(result: dict):

    engine = evaluate(result["contract"], result["criteria"], result["facts"])

    print()
    print("=" * 60)
    print("Result")
    print("=" * 60)

    for name, path in result["paths"].items():
        print(f"{name:<11}: {path}")

    print()

    if result["review"] is None:
        print("핵심 항목이 대부분 비어 있어 근로계약서로 보기 어렵습니다. 평가를 건너뛰었습니다.")
        return

    review = normalize_review(result["review"], result["review_raw"] or {})

    print(f"평가 에이전트 분류 : {review['review_level'] or '찾지 못함'}")
    print(f"규칙 계산 분류     : {engine['level']} (해당 규칙 {', '.join(engine['hit_codes']) or '없음'})")
    print(f"요약               : {review['summary']}")
    print()
    print(json.dumps(review, ensure_ascii=False, indent=2))


##################################################
# Main
##################################################

def main():

    parser = argparse.ArgumentParser(description="첫사인 알바 안심 체크 워크플로우")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--contract", type=Path, help="점검할 근로계약서 PDF 경로")
    group.add_argument("--sample", choices=sorted(SAMPLES), help="체험용 샘플 번호")
    parser.add_argument("--save-fixture", action="store_true", help="샘플 실행 결과를 fixtures/live/에 저장")
    args = parser.parse_args()

    validate_config()
    print_config()

    sample_id = args.sample or ("1" if args.contract is None else None)
    contract_file = args.contract or SAMPLE_DIR / SAMPLES[sample_id]["file"]

    result = run_workflow(contract_file)

    print_result(result)

    if args.save_fixture:
        if sample_id is None:
            parser.error("--save-fixture는 --sample과 함께 써야 합니다.")
        save_fixture(sample_id, result)


if __name__ == "__main__":

    main()

