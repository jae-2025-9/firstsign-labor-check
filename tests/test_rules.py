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
    "2": ("check_needed", {"LABOR_REQUIRED_TERMS", "LABOR_BREAK", "LABOR_WEEKLY_HOLIDAY", "LABOR_SIGN_COPY", "LABOR_MIN_WAGE_NEXT"}),
    "3": ("risky", {"LABOR_MIN_WAGE", "LABOR_PENALTY", "LABOR_BREAK", "LABOR_WEEKLY_HOLIDAY", "LABOR_SIGN_COPY", "LABOR_MIN_WAGE_NEXT"}),
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
    assert result["level"] == "safe"


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
