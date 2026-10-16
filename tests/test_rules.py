"""
rules.py 테스트

샘플 4종의 정답 등급은 NPOS 기획서와 입력_N PDF를 따른다.
"""

import copy
import json
from pathlib import Path

import pytest

from rules import (
    compute_facts,
    criteria_rules,
    cross_check,
    engine_review,
    evaluate,
    looks_like_contract,
    more_severe,
    normalize_level,
    parse_break,
    parse_times,
    parse_work_days,
    to_number,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "expected"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def criteria():
    return load("criteria.json")


EXPECTED = {
    "1": ("safe", set()),
    "2": ("check_needed", {"LABOR_REQUIRED_TERMS", "LABOR_BREAK", "LABOR_WEEKLY_HOLIDAY", "LABOR_SIGN_COPY", "LABOR_MIN_WAGE_NEXT"}),  # 주 5일 × 6시간
    # 주 15시간인데 "주휴일 없음", 연차는 "협의한다"(정해지지 않음)라 필수 기재사항도 해당
    "3": ("risky", {"LABOR_MIN_WAGE", "LABOR_PENALTY", "LABOR_REQUIRED_TERMS", "LABOR_BREAK", "LABOR_WEEKLY_HOLIDAY", "LABOR_SIGN_COPY", "LABOR_MIN_WAGE_NEXT"}),
    "4": ("safe", set()),
}


@pytest.mark.parametrize("sample_id", sorted(EXPECTED))
def test_samples_match_team_labels(sample_id, criteria):
    contract = load(f"contract_sample{sample_id}.json")
    result = evaluate(contract, criteria)
    level, hits = EXPECTED[sample_id]
    assert result["level"] == level
    assert set(result["hit_codes"]) == hits
    assert result["undetermined_codes"] == []


def test_sample4_short_hours(criteria):
    facts = compute_facts(load("contract_sample4.json"), criteria)
    assert facts["daily_work_hours"] == 3.5
    assert facts["weekly_hours"] == 10.5
    assert facts["weekly_15_or_more"] is False


def test_sample3_numbers(criteria):
    facts = compute_facts(load("contract_sample3.json"), criteria)
    assert facts["hourly_wage"] == 9500
    assert facts["applicable_min_wage"] == 10320
    assert facts["weekly_hours"] == 15
    assert facts["continues_into_next_year"] is True


##################################################
# 기준서만 바꾸면 판정이 바뀌는지
##################################################

def test_changing_min_wage_in_criteria_changes_result(criteria):
    raised = copy.deepcopy(criteria)
    raised["min_wage_hourly"] = [11000]
    result = evaluate(load("contract_sample1.json"), raised)
    assert result["level"] == "risky"
    assert "LABOR_MIN_WAGE" in result["hit_codes"]


def test_changing_rule_category_in_criteria_changes_level(criteria):
    stricter = copy.deepcopy(criteria)
    for rule in stricter["check_rules"]:
        if rule["rule_code"] == "LABOR_SIGN_COPY":
            rule["category"] = "위험"
    result = evaluate(load("contract_sample2.json"), stricter)
    assert result["level"] == "risky"


def test_unknown_rule_is_undetermined(criteria):
    extended = copy.deepcopy(criteria)
    extended["check_rules"].append({"rule_code": "LABOR_NEW_RULE", "category": "위험", "check_condition": "새 규칙"})
    result = evaluate(load("contract_sample1.json"), extended)
    assert result["undetermined_codes"] == ["LABOR_NEW_RULE"]
    # 새 위험 규칙을 코드가 판단하지 못하면 안심이라고 하지 않는다
    assert result["level"] is None


def test_column_oriented_rules():
    columns = {
        "check_rules": {
            "rule_code": ["LABOR_MIN_WAGE", "LABOR_BREAK"],
            "category": ["위험", "확인 필요"],
            "legal_basis": ["최저임금법 제6조", "근로기준법 제54조"],
        }
    }
    rules = criteria_rules(columns)
    assert [r["rule_code"] for r in rules] == ["LABOR_MIN_WAGE", "LABOR_BREAK"]
    assert [r["level"] for r in rules] == ["risky", "check_needed"]


##################################################
# 파싱
##################################################

@pytest.mark.parametrize("value,expected", [
    ("12:00 ~ 12:30 (30분)", (True, 30)),
    ("없음 (근로시간 5시간)", (True, 0)),
    ("1시간", (True, 60)),
    ("1시간 30분", (True, 90)),
    ("", (False, None)),
    (["(비어 있음)"], (False, None)),
    ("근무 중 자유롭게", (True, None)),
])
def test_parse_break(value, expected):
    assert parse_break(value) == expected


@pytest.mark.parametrize("value,expected", [
    (["월", "화", "수", "목", "금"], 5),
    (["월, 수, 금"], 3),
    ("월~금", 5),
    ("주 5일 (요일은 협의)", 5),
    ("토요일, 일요일", 2),
    ("평일", None),
    ("없음", None),
])
def test_parse_work_days(value, expected):
    assert parse_work_days(value) == expected


def test_parse_times_ignores_durations():
    assert parse_times("18:00 ~ 23:00 (5시간)") == [1080, 1380]
    assert parse_times("오후 6시 30분") == [1110]


@pytest.mark.parametrize("value,expected", [([10800], 10800), (["10,320원"], 10320), ("1만원", 10000), ([""], None), ([True], None)])
def test_to_number(value, expected):
    assert to_number(value) == expected


def test_overnight_shift(criteria):
    contract = load("contract_sample1.json")
    contract.update(work_start_time=["22:00"], work_end_time=["06:00"], break_time=["02:00 ~ 03:00"])
    facts = compute_facts(contract, criteria)
    assert facts["daily_work_hours"] == 7


def test_monthly_wage_is_converted(criteria):
    contract = load("contract_sample1.json")
    contract.update(wage_type=["월급"], wage_amount=[1_000_000])
    facts = compute_facts(contract, criteria)
    # 주 27.5시간 + 주휴 5.5시간 = 주 33시간 → 월 약 143.4시간
    assert facts["hourly_wage"] == pytest.approx(1_000_000 / (33 * 365 / 7 / 12), abs=1)


def test_contract_starting_next_year_uses_next_min_wage(criteria):
    contract = load("contract_sample1.json")
    contract.update(contract_start_date=["2027-01-02"], contract_end_date=["2027-06-30"], wage_amount=[10500])
    result = evaluate(contract, criteria)
    assert result["facts"]["applicable_min_wage"] == 10700
    assert "LABOR_MIN_WAGE" in result["hit_codes"]
    assert "LABOR_MIN_WAGE_NEXT" not in result["hit_codes"]


def test_four_hour_shift_needs_break(criteria):
    contract = load("contract_sample4.json")
    contract.update(work_start_time=["13:00"], work_end_time=["17:00"])
    result = evaluate(contract, criteria)
    assert "LABOR_BREAK" in result["hit_codes"]


def test_penalty_ignores_insurance_deduction(criteria):
    contract = load("contract_sample1.json")
    contract["special_terms"] = ["4대 보험료 공제 후 지급한다."]
    assert "LABOR_PENALTY" not in evaluate(contract, criteria)["hit_codes"]


def test_not_a_contract(criteria):
    blank = {key: [""] for key in load("contract_sample1.json")}
    assert not looks_like_contract(blank)
    assert evaluate(blank, criteria)["level"] is None


##################################################
# 교차 검증
##################################################

def test_cross_check(criteria):
    engine = evaluate(load("contract_sample3.json"), criteria)
    agree = cross_check("risky", engine_review(engine)["matched_rules"], engine)
    assert agree["level_match"] and not agree["agent_only"] and not agree["engine_only"]

    differ = cross_check("check_needed", ["LABOR_BREAK - 근로기준법 제54조"], engine)
    assert not differ["level_match"]
    assert "LABOR_PENALTY" in differ["engine_only"]


def test_levels():
    assert normalize_level(["위험"]) == "risky"
    assert normalize_level("확인 필요") == "check_needed"
    assert more_severe("safe", "risky", None) == "risky"
    assert more_severe(None, None) is None


##################################################
# Codex 검수 1차 회귀 테스트
##################################################

def test_blank_wage_amount_is_not_safe(criteria):
    contract = load("contract_sample1.json")
    contract["wage_amount"] = [""]
    result = evaluate(contract, criteria)
    assert result["level"] != "safe"
    assert "임금(금액)" in result["missing_items"]


def test_unreadable_times_are_not_safe(criteria):
    contract = load("contract_sample1.json")
    contract.update(work_start_time=["판독 불가"], work_end_time=["판독 불가"])
    assert evaluate(contract, criteria)["level"] is None


@pytest.mark.parametrize("bad", [{}, {"check_rules": []}])
def test_missing_criteria_is_not_safe(bad):
    result = evaluate(load("contract_sample1.json"), bad)
    assert result["level"] is None
    assert result["criteria_problems"]


def test_column_rules_keep_blank_cells():
    rules = criteria_rules({"check_rules": {
        "rule_code": ["LABOR_MIN_WAGE", "LABOR_PENALTY", "LABOR_BREAK"],
        "category": ["위험", "", "확인 필요"],
        "legal_basis": ["법1", "", "법3"],
    }})
    assert [(r["rule_code"], r["level"], r["legal_basis"]) for r in rules] == [
        ("LABOR_MIN_WAGE", "risky", "법1"),
        ("LABOR_PENALTY", None, ""),
        ("LABOR_BREAK", "check_needed", "법3"),
    ]


def test_rule_without_category_blocks_safe(criteria):
    broken = copy.deepcopy(criteria)
    broken["check_rules"][1]["category"] = ""
    result = evaluate(load("contract_sample1.json"), broken)
    assert "LABOR_PENALTY" in result["undetermined_codes"]
    assert result["level"] is None


@pytest.mark.parametrize("clause", [
    "퇴사 시 마지막 근무일까지의 임금을 지급한다.",
    "퇴사 시 위약금과 손해배상액의 예정을 금지한다.",
])
def test_penalty_negation_or_resign_only_is_undetermined(clause, criteria):
    contract = load("contract_sample1.json")
    contract["special_terms"] = [clause]
    result = evaluate(contract, criteria)
    assert "LABOR_PENALTY" not in result["hit_codes"]
    assert "LABOR_PENALTY" in result["undetermined_codes"]


def test_copy_negation_is_missing(criteria):
    contract = load("contract_sample1.json")
    contract["copy_delivery_clause"] = ["계약서를 근로자에게 교부하지 않는다."]
    result = evaluate(contract, criteria)
    assert "LABOR_SIGN_COPY" in result["hit_codes"]
    assert "계약서 교부 문구" in result["missing_items"]


def test_no_rounding_before_min_wage_comparison(criteria):
    contract = load("contract_sample1.json")
    contract.update(work_start_time=["09:00"], work_end_time=["18:00"], break_time=["1시간"],
                    wage_type=["일급"], wage_amount=[82559], contract_end_date=["2026-12-31"])
    result = evaluate(contract, criteria)
    assert result["facts"]["hourly_wage"] == pytest.approx(10319.875)
    assert "LABOR_MIN_WAGE" in result["hit_codes"]
    assert result["level"] == "risky"


def test_won_display_does_not_round_up():
    from rules import won
    assert won(10319.875) == "10,319.87원"
    assert won(10320.0) == "10,320원"


def test_start_year_only_uses_next_min_wage(criteria):
    contract = load("contract_sample1.json")
    contract.update(contract_start_date=["2027년 1월"], wage_amount=[10500])
    result = evaluate(contract, criteria)
    assert result["facts"]["applicable_min_wage"] == 10700
    assert "LABOR_MIN_WAGE" in result["hit_codes"]


def test_unreadable_start_date_does_not_pick_a_min_wage(criteria):
    contract = load("contract_sample1.json")
    contract["contract_start_date"] = ["협의 후 결정"]
    result = evaluate(contract, criteria)
    assert result["facts"]["applicable_min_wage"] is None
    assert "LABOR_MIN_WAGE" in result["undetermined_codes"]


def test_changed_condition_threshold_is_undetermined(criteria):
    changed = copy.deepcopy(criteria)
    for rule in changed["check_rules"]:
        if rule["rule_code"] == "LABOR_BREAK":
            rule["check_condition"] = "근로시간 6시간 이상이면 휴게 30분 이상이 없다. 6시간 미만은 해당 없다."
    result = evaluate(load("contract_sample3.json"), changed)
    assert "LABOR_BREAK" in result["undetermined_codes"]


def test_changed_number_only_is_undetermined(criteria):
    changed = copy.deepcopy(criteria)
    for rule in changed["check_rules"]:
        if rule["rule_code"] == "LABOR_WEEKLY_HOLIDAY":
            rule["check_condition"] = rule["check_condition"].replace("15시간", "20시간")
    assert "LABOR_WEEKLY_HOLIDAY" in evaluate(load("contract_sample3.json"), changed)["undetermined_codes"]


def test_extraction_spacing_differences_are_tolerated(criteria):
    spaced = copy.deepcopy(criteria)
    for rule in spaced["check_rules"]:
        rule["check_condition"] = rule["check_condition"].replace(" ", "").replace(",", " , ")
    assert evaluate(load("contract_sample3.json"), spaced)["undetermined_codes"] == []


def test_min_wage_amount_change_is_still_supported(criteria):
    updated = copy.deepcopy(criteria)
    updated["min_wage_hourly"] = [10900]
    updated["check_rules"][0]["check_condition"] = updated["check_rules"][0]["check_condition"].replace("10,320", "10,900")
    result = evaluate(load("contract_sample1.json"), updated)
    assert "LABOR_MIN_WAGE" in result["hit_codes"]


def test_changed_required_items_is_undetermined(criteria):
    changed = copy.deepcopy(criteria)
    changed["required_items"] = changed["required_items"] + ["취업규칙 교부"]
    assert "LABOR_REQUIRED_TERMS" in evaluate(load("contract_sample1.json"), changed)["undetermined_codes"]


def test_other_base_year_drops_next_year_field(criteria):
    later = copy.deepcopy(criteria)
    later["criteria_version"] = ["v3.0 (법령 기준일 2027-10-01)"]
    facts = compute_facts(load("contract_sample1.json"), later)
    assert facts["next_min_wage"] is None
    assert any("다음 해 최저임금" in note for note in facts["notes"])


##################################################
# 최종 결과 조립
##################################################

def agent_review(**overrides):
    review = {
        "review_level": "safe", "summary": "모든 규칙을 충족합니다.", "matched_rules": [],
        "missing_items": [], "risky_clauses": [], "confirmed_items": ["불리한 특약 없음"], "recommendations": [],
    }
    review.update(overrides)
    return review


def test_final_view_upgrades_and_stays_consistent(criteria):
    from rules import final_view
    engine = evaluate(load("contract_sample3.json"), criteria)
    review = agent_review()
    check = cross_check("safe", review["matched_rules"], engine)
    final = final_view(review, engine, "safe", check)
    assert final["level"] == "risky"
    assert "평가 에이전트는 '안심'" in final["summary"]
    assert "모든 규칙을 충족합니다" not in final["summary"]
    assert final["agent_summary"] == "모든 규칙을 충족합니다."
    assert "불리한 특약 없음" not in final["confirmed_items"]
    assert any("삭제" in action for action in final["recommendations"])
    assert {c["rule_code"] for c in final["cards"]} == set(engine["hit_codes"])
    assert all(c["source"] == "engine" for c in final["cards"])


def test_final_view_shows_agent_only_rule(criteria):
    # 문장 해석이 필요한 규칙은 규칙 계산이 통과로 봐도 에이전트 지적을 카드로 남긴다
    from rules import final_view
    engine = evaluate(load("contract_sample1.json"), criteria)
    review = agent_review(review_level="check_needed", matched_rules=["LABOR_REQUIRED_TERMS - 근로기준법 제17조"],
                          recommendations=["업무 내용을 구체적으로 적어 주세요."])
    check = cross_check("check_needed", review["matched_rules"], engine)
    final = final_view(review, engine, "check_needed", check)
    assert final["level"] == "check_needed"
    card = next(c for c in final["cards"] if c["rule_code"] == "LABOR_REQUIRED_TERMS")
    assert card["source"] == "agent"
    assert "평가 에이전트가" in card["reason"]
    assert final["disputed"] == []


def test_agent_flag_on_decisive_pass_is_disputed(criteria):
    # 계약서 숫자로 통과가 확인된 규칙(휴게시간)을 에이전트가 지적하면 등급에 넣지 않고 의견 차이로 둔다
    from rules import final_view
    engine = evaluate(load("contract_sample1.json"), criteria)
    review = agent_review(review_level="check_needed", matched_rules=["LABOR_BREAK - 근로기준법 제54조"],
                          recommendations=["휴게시간을 적어 주세요."])
    check = cross_check("check_needed", review["matched_rules"], engine)
    final = final_view(review, engine, "check_needed", check)
    assert final["cards"] == []
    assert [d["rule_code"] for d in final["disputed"]] == ["LABOR_BREAK"]
    assert final["level"] == "safe"
    assert final["requests"] == [] and final["recommendations"] == []
    assert "등급에 넣지 않았습니다" in final["summary"]
    assert check["status"] == "mismatch" and final["disagree"]


def test_agent_level_capped_by_criteria_category(criteria):
    # 에이전트가 '위험'이라 해도 근거 규칙이 모두 기준서상 '확인 필요'면 '확인 필요'로 표시한다
    from rules import final_view
    engine = evaluate(load("contract_sample2.json"), criteria)
    codes = [f"{code} - 근거" for code in engine["hit_codes"]]
    review = agent_review(review_level="risky", matched_rules=codes)
    final = final_view(review, engine, "risky", cross_check("risky", codes, engine))
    assert {c["level"] for c in final["cards"]} == {"check_needed"}
    assert final["level"] == "check_needed"
    assert "기준서 분류에 맞춰" in final["summary"]


def test_agent_warning_without_rule_codes_is_check_needed(criteria):
    # 기준서 규칙 코드 없이 경고만 하면 근거가 없으므로 '확인 필요'까지만 올린다
    from rules import final_view
    engine = evaluate(load("contract_sample1.json"), criteria)
    review = agent_review(review_level="risky", matched_rules=["기타 - 사장님 태도"])
    final = final_view(review, engine, "risky", cross_check("risky", review["matched_rules"], engine))
    assert final["cards"] == [] and final["level"] == "check_needed"
    assert "근거를 찾지 못해" in final["summary"]


def run_final(contract, criteria, agent_level, matched_rules, **review):
    from rules import compute_facts, final_view
    engine = evaluate(contract, criteria, compute_facts(contract, criteria))
    review = agent_review(review_level=agent_level, matched_rules=matched_rules, **review)
    check = cross_check(agent_level, matched_rules, engine)
    return engine, final_view(review, engine, agent_level, check)


AMBIGUOUS_INPUTS = [
    ({"wage_amount": [10800, 9500]}, "LABOR_MIN_WAGE"),
    ({"wage_amount": "10,800원 (수습 3개월은 9,500원)"}, "LABOR_MIN_WAGE"),
    ({"wage_amount": "10,800원 (수습기간 9천원)"}, "LABOR_MIN_WAGE"),
    ({"wage_amount": 10500, "contract_end_date": ["2026-12-31, 2027-12-31"]}, "LABOR_MIN_WAGE_NEXT"),
    ({"wage_amount": 10500, "contract_end_date": "2026-12-31 (자동 연장 시 2027-12-31)"}, "LABOR_MIN_WAGE_NEXT"),
    ({"wage_amount": 10500, "contract_end_date": ["2026-12-31", "2027년 12월"]}, "LABOR_MIN_WAGE_NEXT"),
    ({"wage_amount": 10500, "contract_end_date": ["2026-12-31", "2027-02-30"]}, "LABOR_MIN_WAGE_NEXT"),
    ({"break_time": "12:00~12:30 또는 13:00~13:30"}, "LABOR_BREAK"),
    ({"break_time": "21:00~22:00"}, "LABOR_BREAK"),
    ({"work_start_time": "22:00", "work_end_time": "07:00", "break_time": "23:45~00:15, 00:00~00:30"}, "LABOR_BREAK"),
    ({"work_end_time": "18:00", "break_time": "평일 12:00~12:30, 주말 12:00~13:00"}, "LABOR_BREAK"),
    ({"weekly_holiday": "매주 협의하여 정한다."}, "LABOR_WEEKLY_HOLIDAY"),
    ({"copy_delivery_clause": "근로자에게 계약서를 교부한다는 규정은 없다."}, "LABOR_SIGN_COPY"),
]


@pytest.mark.parametrize("changes,code", AMBIGUOUS_INPUTS)
def test_ambiguous_input_never_disputes_agent(criteria, changes, code):
    # 계약서 값이 모호하면 규칙 계산은 판단을 보류한다. 에이전트 지적은 카드로 남고 등급은 기준서 분류대로다.
    contract = {**load("contract_sample1.json"), **changes}
    engine, final = run_final(contract, criteria, "check_needed", [f"{code} - 근거"], recommendations=["확인해 주세요."])
    finding = next(f for f in engine["findings"] if f["rule_code"] == code)
    assert finding["hit"] is None, changes
    assert code in {c["rule_code"] for c in final["cards"]}
    assert final["disputed"] == []
    assert final["level"] == finding["level"]
    assert final["requests"] == ["확인해 주세요."]


@pytest.mark.parametrize("signed", [[True, False], [True, "미서명"]])
def test_conflicting_signature_is_not_a_pass(criteria, signed):
    contract = {**load("contract_sample1.json"), "is_signed": signed}
    engine, final = run_final(contract, criteria, "check_needed", ["LABOR_SIGN_COPY - 근거"])
    assert next(f for f in engine["findings"] if f["rule_code"] == "LABOR_SIGN_COPY")["hit"] is not False
    assert final["disputed"] == [] and final["level"] == "check_needed"


NORMAL_INPUTS = [
    ({"work_end_time": "18:00", "break_time": "평일 12:00~13:00"}, "LABOR_BREAK"),
    ({"break_time": "12:00~12:30, 14:00~14:15"}, "LABOR_BREAK"),
    ({"wage_amount": "10,800원 (2026-10-01 기준)"}, "LABOR_MIN_WAGE"),
    ({"wage_amount": "월 2,300,000원 (주 40시간, 주휴 포함 209시간)", "wage_type": "월급",
      "work_end_time": "18:00", "break_time": "12:00~13:00"}, "LABOR_MIN_WAGE"),
    ({"wage_amount": ["10,800원", "10800"]}, "LABOR_MIN_WAGE"),
    ({"wage_amount": 10800, "contract_end_date": "2027-09-30 (연장 없음)"}, "LABOR_MIN_WAGE_NEXT"),
    ({"wage_amount": 10500, "contract_end_date": "2026-12-31 (연장 없음)"}, "LABOR_MIN_WAGE_NEXT"),
    ({"copy_delivery_clause": "근로자에게 계약서를 교부한다. 교부 비용은 없다."}, "LABOR_SIGN_COPY"),
    ({"is_signed": ["true", "예"]}, "LABOR_SIGN_COPY"),
]


@pytest.mark.parametrize("changes,code", NORMAL_INPUTS)
def test_clear_input_still_decides(criteria, changes, code):
    # 뜻이 분명한 정상 문구는 계속 계산한다. 계산상 통과인 규칙을 에이전트가 지적하면 의견 차이로 둔다.
    contract = {**load("contract_sample1.json"), **changes}
    engine, final = run_final(contract, criteria, "check_needed", [f"{code} - 근거"])
    assert next(f for f in engine["findings"] if f["rule_code"] == code)["hit"] is False, changes
    assert [d["rule_code"] for d in final["disputed"]] == [code]
    assert final["level"] == "safe" and final["cards"] == []


def test_unrelated_pending_rule_does_not_raise_level(criteria):
    # 에이전트가 지적하지 않은 판단 보류 규칙의 분류를 빌려 위험으로 올리지 않는다
    contract = {**load("contract_sample1.json"), "special_terms": ["위약금은 없다."]}
    engine, final = run_final(contract, criteria, "risky", ["LABOR_BREAK - 제54조"])
    assert "LABOR_PENALTY" in engine["undetermined_codes"]
    assert final["level"] == "safe"

    contract = {**load("contract_sample1.json"), "wage_amount": [10800, 9500]}
    _, final = run_final(contract, criteria, "risky", ["기타 - 사장님 태도"])
    assert final["level"] == "check_needed"


def test_evidence_free_agent_warning_is_not_followed(criteria):
    # 실제 배포에서 나온 응답: 지적 규칙·조항 없이 '위험'만 반환 → 기준서 판정을 따른다
    _, final = run_final(load("contract_sample1.json"), criteria, "risky", [], recommendations=[])
    assert final["level"] == "safe"
    assert "근거를 찾지 못해" in final["summary"]


@pytest.mark.parametrize("rules", [
    ["LABOR_SIGN_COPY - 서명 누락; 기준서 밖 지적 - 계약 외 사항"],
    ["LABOR_SIGN_COPY - 서명 누락", "기준서 밖 지적 - 계약 외 사항"],
])
def test_unlinked_part_survives_regardless_of_split(criteria, rules):
    _, final = run_final(load("contract_sample1.json"), criteria, "risky", rules, recommendations=["계약 외 사항을 확인해 주세요."])
    assert final["level"] == "check_needed"
    assert final["requests"] == ["계약 외 사항을 확인해 주세요."]


def test_adopted_request_survives_mixed_keywords(criteria):
    # 채택된 규칙(필수 기재사항)의 요청에 '교부'가 섞여도 지우지 않는다
    contract = {**load("contract_sample1.json"), "job_description": ""}
    _, final = run_final(contract, criteria, "check_needed", ["LABOR_REQUIRED_TERMS", "LABOR_SIGN_COPY"],
                         recommendations=["업무 내용을 명시한 계약서를 교부해 주세요."])
    assert [d["rule_code"] for d in final["disputed"]] == ["LABOR_SIGN_COPY"]
    assert final["requests"] == ["업무 내용을 명시한 계약서를 교부해 주세요."]


def test_every_card_keeps_an_action(criteria):
    # 의견 차이 문장을 뺀 뒤에도 남은 카드마다 할 일이 있다
    contract = {**load("contract_sample1.json"), "job_description": ""}
    _, final = run_final(contract, criteria, "check_needed", ["LABOR_REQUIRED_TERMS", "LABOR_BREAK"],
                         recommendations=["휴게시간을 넣어 주세요."])
    assert final["requests"] == []
    assert any("빠진 항목" in r for r in final["recommendations"])


def test_review_input_keeps_ambiguous_raw_values():
    # 모호한 값은 평가 입력 문서에 원문 그대로 남겨 평가 에이전트가 판단할 수 있게 한다
    from review_builder import contract_value
    assert "10800" in contract_value({"wage_amount": [10800, 9500]}, "wage_amount")
    assert "9500" in contract_value({"wage_amount": [10800, 9500]}, "wage_amount")
    value = contract_value({"wage_amount": "10,800원 (수습 3개월은 9,500원)"}, "wage_amount")
    assert "9,500원" in value and "정하지 못함" in value
    assert contract_value({"wage_amount": [10800]}, "wage_amount") == "10800"
    assert "정하지 못함" in contract_value({"is_signed": [True, False]}, "is_signed")
    assert contract_value({"is_signed": [True]}, "is_signed") == "예"
    assert contract_value({}, "is_signed") == "(비어 있음)"


def test_unlinked_warning_survives_unrelated_dispute(criteria):
    # 코드 없이 쓴 위험 지적에 무관한 의견 차이가 섞여도 위험 판단이 사라지지 않는다
    contract = load("contract_sample1.json")
    contract["special_terms"] = ["퇴사하려면 사장님의 허가를 받아야 한다."]
    rules = ["부당한 퇴사 제한 - 퇴사하려면 사장님 허가 필요", "LABOR_SIGN_COPY - 근로기준법 제17조 제2항"]
    engine, final = run_final(contract, criteria, "risky", rules, recommendations=["퇴사 제한 조항을 빼 주세요."])
    assert next(f for f in engine["findings"] if f["rule_code"] == "LABOR_PENALTY")["hit"] is None
    assert [d["rule_code"] for d in final["disputed"]] == ["LABOR_SIGN_COPY"]
    assert final["level"] == "risky"
    assert final["requests"] == ["퇴사 제한 조항을 빼 주세요."]
    assert "에이전트 판단대로 '위험'" in final["summary"]


def test_unlinked_warning_without_pending_rules_is_check_needed(criteria):
    contract = load("contract_sample1.json")
    _, final = run_final(contract, criteria, "risky", ["부당한 퇴사 제한 - 근거 없음"])
    assert final["level"] == "check_needed"


def test_partial_dispute_drops_only_refuted_sentences(criteria):
    # 일부 지적만 의견 차이면 그 규칙에 관한 요청·누락 문장만 뺀다
    contract = load("contract_sample1.json")
    contract["job_description"] = ""
    engine, final = run_final(
        contract, criteria, "check_needed", ["LABOR_REQUIRED_TERMS - 제17조", "LABOR_BREAK - 제54조"],
        missing_items=["휴게시간", "업무의 내용"],
        recommendations=["업무 내용을 적어 주세요.", "휴게시간이 없으니 30분을 넣어 주세요."],
    )
    assert [d["rule_code"] for d in final["disputed"]] == ["LABOR_BREAK"]
    assert final["level"] == "check_needed"
    assert final["requests"] == ["업무 내용을 적어 주세요."]
    assert "휴게시간이 없으니 30분을 넣어 주세요." not in final["recommendations"]
    assert "휴게시간" not in final["missing_items"]
    assert "업무의 내용" in final["missing_items"]


def test_next_year_sentence_attributed_to_next_year_rule():
    from rules import drop_disputed
    sentences = ["2027년 1월 1일부터 시급을 10,700원 이상으로 올려 주세요.", "시급을 최저임금 이상으로 올려 주세요."]
    assert drop_disputed(sentences, {"LABOR_MIN_WAGE_NEXT"}, 2027) == [sentences[1]]
    assert drop_disputed(sentences, {"LABOR_MIN_WAGE"}, 2027) == [sentences[0]]


def test_source_table_repairs_truncated_cells(criteria):
    from rules import KNOWN_CONDITIONS, apply_source_table, condition_supported, criteria_rules
    truncated = copy.deepcopy(criteria)
    for row in truncated["check_rules"]:
        if row["rule_code"] == "LABOR_MIN_WAGE_NEXT":
            row["check_condition"] = "계약기간이 2027년 1월 1일 이후까지 이어지는데 시급이 2027년 최저임금 10,700원 미만이다. 종료"
            row["recommended_action"] = "2027년 1월 1일부 터 시급을 10,700"
    rule = next(r for r in criteria_rules(truncated) if r["rule_code"] == "LABOR_MIN_WAGE_NEXT")
    assert condition_supported(rule, 2026)[0] is False

    source = {"LABOR_MIN_WAGE_NEXT": {
        "check_condition": KNOWN_CONDITIONS["LABOR_MIN_WAGE_NEXT"][0],
        "recommended_action": "2027년 1월 1일부 터 시급을 10,700 원 이상으로 올려 달라고 요청하세 요.",
    }}
    fixed, repaired = apply_source_table(truncated, source)
    assert repaired == ["LABOR_MIN_WAGE_NEXT"]
    rule = next(r for r in criteria_rules(fixed) if r["rule_code"] == "LABOR_MIN_WAGE_NEXT")
    assert condition_supported(rule, 2026)[0] is True
    assert rule["recommended_action"].endswith("요청하세 요.")
    assert truncated["check_rules"] is not fixed["check_rules"]  # 원본은 그대로

    same, none = apply_source_table(fixed, source)
    assert none == [] and same is fixed
    assert apply_source_table(truncated, {}) == (truncated, [])


def test_source_table_never_cuts_a_longer_extraction(criteria):
    # 원문 판독이 바닥글 등으로 끊겨 더 짧으면, 새 조건이 담긴 추출 값을 지우지 않는다 (기준서 변경을 가리지 않음)
    from rules import KNOWN_CONDITIONS, apply_source_table, condition_supported, criteria_rules
    changed = copy.deepcopy(criteria)
    known = KNOWN_CONDITIONS["LABOR_MIN_WAGE"][0]
    for row in changed["check_rules"]:
        if row["rule_code"] == "LABOR_MIN_WAGE":
            row["check_condition"] = known + " 단, 시급이 11,000원 미만이면 위반으로 본다."
    fixed, repaired = apply_source_table(changed, {"LABOR_MIN_WAGE": {"check_condition": known}})
    assert repaired == [] and fixed is changed
    rule = next(r for r in criteria_rules(fixed) if r["rule_code"] == "LABOR_MIN_WAGE")
    assert condition_supported(rule, 2026)[0] is False

    # 내용이 다른 경우도 바꾸지 않는다
    other = apply_source_table(changed, {"LABOR_MIN_WAGE": {"check_condition": "전혀 다른 조건이다. 그리고 더 길다. 훨씬 더 길다."}})
    assert other == (changed, [])


def test_source_table_read_from_pdf():
    from app import criteria_source_table
    from rules import KNOWN_CONDITIONS, condition_shape
    table = criteria_source_table()
    assert set(table) == set(KNOWN_CONDITIONS)
    for code, cells in table.items():
        assert condition_shape(cells["check_condition"]) == condition_shape(KNOWN_CONDITIONS[code][0]), code
        assert cells["legal_basis"] and cells["recommended_action"], code
    assert condition_shape(table["LABOR_MIN_WAGE_NEXT"]["recommended_action"]).endswith("원이상으로올려달라고요청하세요")


def test_source_table_drops_row_cut_at_page_edge(tmp_path):
    # 칸 내용이 페이지 아래 가장자리까지 이어지면 잘렸을 수 있어 그 행은 원문으로 쓰지 않는다
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from app import criteria_source_table
    from config import FONT_NAME
    import review_builder  # noqa: F401  (한글 글꼴 등록)

    path = tmp_path / "criteria.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont(FONT_NAME, 9)
    for x, label in ((42, "규칙 코드"), (155, "점검 조건"), (367, "분류")):
        c.drawString(x, 700, label)
    c.drawString(42, 680, "LABOR_A")
    c.drawString(155, 680, "온전한 조건이다.")
    c.drawString(42, 60, "LABOR_B")
    c.drawString(155, 60, "기존 조건이다.")
    c.drawString(155, 25, "단, 추가 조건이 있다.")
    c.save()

    table = criteria_source_table(path)
    assert table["LABOR_A"]["check_condition"] == "온전한 조건이다."
    assert "LABOR_B" not in table


def test_source_table_skips_footer_and_repeated_header(tmp_path):
    # 바닥글(쪽번호)과 다음 페이지에 반복된 머리글이 표를 끊거나 칸에 섞이지 않는다
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from app import criteria_source_table
    from config import FONT_NAME
    import review_builder  # noqa: F401  (한글 글꼴 등록)

    path = tmp_path / "criteria.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont(FONT_NAME, 9)
    for x, label in ((42, "규칙 코드"), (155, "점검 조건"), (367, "분류"), (391, "법령 근거"), (479, "권장 행동")):
        c.drawString(x, 700, label)
    c.drawString(42, 680, "LABOR_A")
    c.drawString(155, 680, "첫 줄 조건이")
    c.drawString(42, 20, "1 / 2")
    c.showPage()
    c.setFont(FONT_NAME, 9)
    c.drawString(42, 800, "규칙 코드")
    c.drawString(155, 800, "점검 조건")
    c.drawString(155, 780, "다음 쪽으로 이어진다.")
    c.drawString(42, 760, "LABOR_B")
    c.drawString(155, 760, "둘째 규칙")
    c.drawString(36, 700, "4. 분류 정의")
    c.drawString(155, 680, "표 밖 문장")
    c.save()

    table = criteria_source_table(path)
    assert table["LABOR_A"]["check_condition"] == "첫 줄 조건이 다음 쪽으로 이어진다."
    assert table["LABOR_B"]["check_condition"] == "둘째 규칙"


def test_final_view_agent_flags_new_rule(criteria):
    from rules import final_view
    extended = copy.deepcopy(criteria)
    extended["check_rules"].append({"rule_code": "LABOR_NEW_RULE", "category": "위험", "check_condition": "새 규칙"})
    engine = evaluate(load("contract_sample1.json"), extended)
    review = agent_review(review_level="risky", matched_rules=["LABOR_NEW_RULE - 새 법"])
    check = cross_check("risky", review["matched_rules"], engine)
    final = final_view(review, engine, "risky", check)
    assert final["level"] == "risky"
    assert [c["rule_code"] for c in final["cards"]] == ["LABOR_NEW_RULE"]
    assert final["pending"] == []


def test_requests_only_from_agent(criteria):
    from rules import final_view
    engine = evaluate(load("contract_sample3.json"), criteria)
    demo = final_view(engine_review(engine), engine, None, cross_check(None, [], engine))
    assert demo["recommendations"] and demo["requests"] == []

    review = agent_review(review_level="risky", recommendations=["사장님, 위약금 조항을 빼 주실 수 있을까요?"])
    live = final_view(review, engine, "risky", cross_check("risky", review["matched_rules"], engine))
    assert live["requests"] == ["사장님, 위약금 조항을 빼 주실 수 있을까요?"]



##################################################
# Codex 검수 2차 회귀 테스트
##################################################

def with_condition(criteria, code, transform):
    changed = copy.deepcopy(criteria)
    for rule in changed["check_rules"]:
        if rule["rule_code"] == code:
            rule["check_condition"] = transform(rule["check_condition"])
    return changed


@pytest.mark.parametrize("code,old,new", [
    ("LABOR_WEEKLY_HOLIDAY", "15시간 이상인데", "15시간 초과인데"),
    ("LABOR_MIN_WAGE", "최저임금보다 낮다", "최저임금보다 높다"),
    ("LABOR_SIGN_COPY", "없거나", "없고"),
    ("LABOR_MIN_WAGE_NEXT", "2027년 1월 1일", "2027년 7월 1일"),
    ("LABOR_BREAK", "휴게 30분 이상, 8시간 이상이면 휴게 1시간", "휴게 1분 이상, 8시간 이상이면 휴게 30시간"),
])
def test_meaning_changes_are_undetermined(code, old, new, criteria):
    changed = with_condition(criteria, code, lambda c: c.replace(old, new))
    assert code in evaluate(load("contract_sample3.json"), changed)["undetermined_codes"]


def test_next_year_criteria_with_new_amounts_is_supported(criteria):
    next_year = copy.deepcopy(criteria)
    rule = next(r for r in next_year["check_rules"] if r["rule_code"] == "LABOR_MIN_WAGE")
    rule["check_condition"] = rule["check_condition"].replace("10,320", "10,500")
    next_year["min_wage_hourly"] = [10500]
    result = evaluate(load("contract_sample1.json"), next_year)
    assert "LABOR_MIN_WAGE" not in result["undetermined_codes"]


def test_final_level_never_below_confirmed_card(criteria):
    from rules import final_view
    contract = load("contract_sample1.json")
    contract.update(special_terms=["퇴사시 마지막 임금을 지급한다."], is_signed=[False])
    engine = evaluate(contract, criteria)
    assert engine["level"] is None and engine["min_level"] == "check_needed"
    review = agent_review()
    final = final_view(review, engine, "safe", cross_check("safe", [], engine))
    assert final["level"] == "check_needed"
    assert final["incomplete"] is False


def test_agent_level_lower_than_its_own_rules(criteria):
    from rules import final_view
    engine = evaluate(load("contract_sample1.json"), criteria)
    review = agent_review(matched_rules=["LABOR_PENALTY - 근로기준법 제20조"])
    final = final_view(review, engine, "safe", cross_check("safe", review["matched_rules"], engine))
    assert final["level"] == "risky"
    assert final["disagree"] is True


def test_no_agent_and_pending_is_incomplete(criteria):
    from rules import final_view
    contract = load("contract_sample1.json")
    contract.update(special_terms=["퇴사시 마지막 임금을 지급한다."], is_signed=[False])
    engine = evaluate(contract, criteria)
    final = final_view(engine_review(engine), engine, None, cross_check(None, [], engine))
    assert final["level"] == "check_needed"
    assert final["incomplete"] is True
    assert "최소 '확인 필요'" in final["summary"]


def test_missing_rule_row_is_a_criteria_problem(criteria):
    from rules import criteria_problems
    trimmed = copy.deepcopy(criteria)
    trimmed["check_rules"] = [r for r in trimmed["check_rules"] if r["rule_code"] != "LABOR_MIN_WAGE"]
    codes = {r["rule_code"] for r in criteria["check_rules"]}
    assert any("빠진 규칙" in p for p in criteria_problems(trimmed, codes))
    contract = load("contract_sample1.json")
    contract.update(wage_amount=[9500], contract_end_date=["2026-12-31"])
    assert evaluate(contract, trimmed, source_codes=codes)["level"] is None


def test_duplicate_rule_codes_are_a_problem(criteria):
    from rules import criteria_problems
    doubled = copy.deepcopy(criteria)
    doubled["check_rules"].append(dict(doubled["check_rules"][0]))
    assert any("중복" in p for p in criteria_problems(doubled))


@pytest.mark.parametrize("field,value", [
    ("annual_leave_clause", "해당 없음"),
    ("annual_leave_clause", "없음"),
    ("wage_payment_method", "미정"),
    ("job_description", "추후 결정"),
])
def test_absent_or_undecided_values_are_missing(field, value, criteria):
    contract = load("contract_sample1.json")
    contract[field] = [value]
    assert "LABOR_REQUIRED_TERMS" in evaluate(contract, criteria)["hit_codes"]


def test_not_applicable_needs_weekly_hours(criteria):
    contract = load("contract_sample4.json")
    contract["work_days"] = [""]
    assert "LABOR_REQUIRED_TERMS" in evaluate(contract, criteria)["undetermined_codes"]


@pytest.mark.parametrize("start,break_text,hit", [
    ("2026-12-10", "휴게 없음 (근로자가 명시적으로 휴게 미사용을 요청함)", False),
    ("2026-11-01", "휴게 없음 (근로자가 명시적으로 휴게 미사용을 요청함)", True),
    ("2026-12-10", "없음", True),
])
def test_four_hour_break_exception(start, break_text, hit, criteria):
    contract = load("contract_sample1.json")
    contract.update(contract_start_date=[start], work_start_time=["09:00"], work_end_time=["13:00"], break_time=[break_text])
    finding = next(f for f in evaluate(contract, criteria)["findings"] if f["rule_code"] == "LABOR_BREAK")
    assert finding["hit"] is hit


def test_employer_paying_damages_is_not_a_penalty(criteria):
    contract = load("contract_sample1.json")
    contract["special_terms"] = ["회사가 근로자에게 손해배상금을 지급한다."]
    assert "LABOR_PENALTY" not in evaluate(contract, criteria)["hit_codes"]


@pytest.mark.parametrize("clause", ["계약서를 근로자에게 교부할 의무는 없다.", "계약서를 근로자에게 교부는 하지 않는다."])
def test_copy_negations(clause, criteria):
    contract = load("contract_sample1.json")
    contract["copy_delivery_clause"] = [clause]
    assert "LABOR_SIGN_COPY" in evaluate(contract, criteria)["hit_codes"]


def test_break_longer_than_shift_is_not_computed(criteria):
    contract = load("contract_sample1.json")
    contract.update(work_start_time=["09:00"], work_end_time=["10:00"], break_time=["2시간"])
    facts = compute_facts(contract, criteria)
    assert facts["daily_work_hours"] is None
    assert any("휴게시간이" in note for note in facts["notes"])


def test_multiple_shift_times_are_not_merged(criteria):
    contract = load("contract_sample1.json")
    contract.update(work_start_time=["09:00", "18:00"], work_end_time=["13:00", "22:00"], break_time=["없음"])
    assert compute_facts(contract, criteria)["daily_work_hours"] is None


def test_summary_drops_mismatched_next_year():
    from rules import summarize_criteria
    later = load("criteria.json")
    later["criteria_version"] = ["v3.0 (법령 기준일 2027-10-01)"]
    summary = summarize_criteria(later)
    assert summary["min_wage_next"] is None and summary["min_wage_next_dropped"] is True


def test_line_wrap_inside_numbers_is_tolerated(criteria):
    # PDF 표 셀의 줄바꿈("2026\n년", "1\n5시간")은 공백으로 보고 지운다. 숫자를 바꾸는 보정은 하지 않는다.
    wrapped = with_condition(criteria, "LABOR_REQUIRED_TERMS", lambda c: c.replace("15시간 미만", "1\n5시간 미만"))
    assert "LABOR_REQUIRED_TERMS" not in evaluate(load("contract_sample1.json"), wrapped)["undetermined_codes"]


##################################################
# Codex 검수 3차 회귀 테스트
##################################################

def test_cross_check_partial_when_engine_pending(criteria):
    from rules import final_view
    prefixed = copy.deepcopy(criteria)
    for rule in prefixed["check_rules"]:
        rule["check_condition"] = "점검 조건: " + rule["check_condition"]
    engine = evaluate(load("contract_sample1.json"), prefixed)
    check = cross_check("safe", [], engine)
    assert engine["level"] is None and check["status"] == "partial"
    final = final_view(agent_review(), engine, "safe", check)
    assert final["level"] == "safe" and final["incomplete"] is False


def test_cross_check_mismatch_on_level_only(criteria):
    engine = evaluate(load("contract_sample1.json"), criteria)
    check = cross_check("risky", [], engine)
    assert check["status"] == "mismatch"


def test_summary_is_always_rebuilt(criteria):
    from rules import final_view
    engine = evaluate(load("contract_sample3.json"), criteria)
    review = agent_review(review_level="risky", summary="모든 규칙을 충족합니다.",
                          matched_rules=[f"{code} - x" for code in engine["hit_codes"]])
    final = final_view(review, engine, "risky", cross_check("risky", review["matched_rules"], engine))
    assert "모든 규칙을 충족합니다" not in final["summary"]
    assert final["agent_summary"] == "모든 규칙을 충족합니다."


@pytest.mark.parametrize("field,value", [
    ("annual_leave_clause", "연차유급휴가는 근로기준법에 따라 부여하며 사용일은 협의하여 정한다."),
    ("weekly_holiday", "매주 일요일 (변경 없음)"),
])
def test_normal_sentences_are_not_missing(field, value, criteria):
    contract = load("contract_sample1.json")
    contract[field] = [value]
    result = evaluate(contract, criteria)
    assert result["level"] == "safe"


def test_unclear_annual_leave_sentence_is_pending(criteria):
    contract = load("contract_sample1.json")
    contract["annual_leave_clause"] = ["연차유급휴가는 회사 사정에 따라 협의한다."]
    assert "LABOR_REQUIRED_TERMS" in evaluate(contract, criteria)["undetermined_codes"]


def test_copy_with_unrelated_negation_is_ok(criteria):
    contract = load("contract_sample1.json")
    contract["copy_delivery_clause"] = ["근로자의 교부 요구와 관계없이 계약서 1부를 근로자에게 교부한다."]
    assert evaluate(contract, criteria)["level"] == "safe"


def test_tax_and_insurance_deduction_is_not_a_penalty(criteria):
    contract = load("contract_sample1.json")
    contract["special_terms"] = ["소득세와 4대 보험료를 임금에서 공제한다."]
    result = evaluate(contract, criteria)
    assert "LABOR_PENALTY" not in result["hit_codes"] + result["undetermined_codes"]


@pytest.mark.parametrize("break_text", [
    "휴게 없음 (근로자가 휴게 미사용을 요청하지 않음)",
    "휴게 없음 (사용자가 휴게 미사용을 요청함)",
])
def test_break_exception_needs_worker_request(break_text, criteria):
    contract = load("contract_sample1.json")
    contract.update(contract_start_date=["2026-12-10"], work_start_time=["09:00"], work_end_time=["13:00"], break_time=[break_text])
    finding = next(f for f in evaluate(contract, criteria)["findings"] if f["rule_code"] == "LABOR_BREAK")
    assert finding["hit"] is True


@pytest.mark.parametrize("old,new", [("2026년", "2026\n년"), ("2027년", "2027\n년"), ("10,320", "1\n0,320")])
def test_line_wraps_in_years_and_amounts_are_tolerated(old, new, criteria):
    wrapped = with_condition(criteria, "LABOR_MIN_WAGE", lambda c: c.replace(old, new))
    assert "LABOR_MIN_WAGE" not in evaluate(load("contract_sample1.json"), wrapped)["undetermined_codes"]
