import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  compute_facts, criteria_rules, cross_check, engine_review, evaluate, final_view,
  looks_like_contract, more_severe, normalize_level, parse_break, parse_times,
  parse_work_days, to_number, won, to_date, condition_supported, KNOWN_CONDITIONS,
  type ExtractedData, type Review,
} from "../src/lib/rules";

const load = (name: string): ExtractedData => JSON.parse(readFileSync(new URL(`../fixtures/expected/${name}.json`, import.meta.url), "utf8"));
const criteria = () => load("criteria");
const sample = (id = 1) => load(`contract_sample${id}`);
const rules = (data: ExtractedData) => data.check_rules as ExtractedData[];
const review = (overrides: Partial<Review> = {}): Review => ({ review_level: "safe", summary: "모든 규칙을 충족합니다.", matched_rules: [], missing_items: [], risky_clauses: [], confirmed_items: ["불리한 특약 없음"], recommendations: [], ...overrides });

describe("원본 샘플 판정", () => {
  it.each([
    [1, "safe", []],
    [2, "check_needed", ["LABOR_REQUIRED_TERMS", "LABOR_BREAK", "LABOR_WEEKLY_HOLIDAY", "LABOR_SIGN_COPY", "LABOR_MIN_WAGE_NEXT"]],
    [3, "risky", ["LABOR_MIN_WAGE", "LABOR_PENALTY", "LABOR_BREAK", "LABOR_WEEKLY_HOLIDAY", "LABOR_SIGN_COPY", "LABOR_MIN_WAGE_NEXT"]],
    [4, "safe", []],
  ] as const)("샘플 %i", (id, level, codes) => {
    const result = evaluate(sample(id), criteria());
    expect(result.level).toBe(level);
    expect(new Set(result.hit_codes)).toEqual(new Set(codes));
    expect(result.undetermined_codes).toEqual([]);
  });
  it("샘플의 계산값을 보존한다", () => {
    expect(compute_facts(sample(4), criteria())).toMatchObject({ daily_work_hours: 3.5, weekly_hours: 10.5, weekly_15_or_more: false });
    expect(compute_facts(sample(3), criteria())).toMatchObject({ hourly_wage: 9500, applicable_min_wage: 10320, weekly_hours: 15, continues_into_next_year: true });
  });
});

describe("파싱", () => {
  it.each<[unknown, [boolean, number | null]]>([["12:00 ~ 12:30 (30분)", [true, 30]], ["없음 (근로시간 5시간)", [true, 0]], ["1시간", [true, 60]], ["1시간 30분", [true, 90]], ["", [false, null]], [["(비어 있음)"], [false, null]], ["근무 중 자유롭게", [true, null]], ["0.075시간", [true, 4]]])("휴게 %j", (value, expected) => expect(parse_break(value)).toEqual(expected));
  it.each<[unknown, number | null]>([[["월", "화", "수", "목", "금"], 5], [["월, 수, 금"], 3], ["월~금", 5], ["주 5일 (요일은 협의)", 5], ["토요일, 일요일", 2], ["평일", null], ["없음", null], ["금~월", 4]])("근무일 %j", (value, expected) => expect(parse_work_days(value)).toBe(expected));
  it.each<[unknown, number | null]>([[[10800], 10800], [["10,320원"], 10320], ["1만원", 10000], [[""], null], [[true], null]])("숫자 %j", (value, expected) => expect(to_number(value)).toBe(expected));
  it("시각과 기간을 구별한다", () => {
    expect(parse_times("18:00 ~ 23:00 (5시간)")).toEqual([1080, 1380]);
    expect(parse_times("오후 6시 30분")).toEqual([1110]);
    expect(parse_times("오전 12시 ~ 오후 12시")).toEqual([0, 720]);
  });
  it("잘못된 날짜를 보류한다", () => { expect(to_date("2026-02-30")).toBeNull(); expect(to_date("2026년 10월 16일")?.toISOString()).toBe("2026-10-16T00:00:00.000Z"); });
  it("등급 별칭과 심각도를 정규화한다", () => {
    expect(normalize_level(["위험"])).toBe("risky"); expect(normalize_level("확인 필요")).toBe("check_needed");
    expect(more_severe("safe", "risky", null)).toBe("risky"); expect(more_severe(null, null)).toBeNull();
  });
  it("금액을 올림하지 않는다", () => { expect(won(10319.875)).toBe("10,319.87원"); expect(won(10320)).toBe("10,320원"); });
});

describe("기준서 변경과 보류", () => {
  it("최저임금 변경을 적용한다", () => {
    const c = criteria(); c.min_wage_hourly = [11000];
    expect(evaluate(sample(), c)).toMatchObject({ level: "risky", hit_codes: ["LABOR_MIN_WAGE"] });
  });
  it("규칙 분류 변경을 적용한다", () => {
    const c = criteria(); rules(c).find(r => r.rule_code === "LABOR_SIGN_COPY")!.category = "위험";
    expect(evaluate(sample(2), c).level).toBe("risky");
  });
  it("새 규칙이 있으면 안심을 보류한다", () => {
    const c = criteria(); rules(c).push({ rule_code: "LABOR_NEW_RULE", category: "위험", check_condition: "새 규칙" });
    expect(evaluate(sample(), c)).toMatchObject({ level: null, undetermined_codes: ["LABOR_NEW_RULE"] });
  });
  it("열 형식과 빈 셀 위치를 보존한다", () => {
    const result = criteria_rules({ check_rules: { rule_code: ["LABOR_MIN_WAGE", "LABOR_PENALTY", "LABOR_BREAK"], category: ["위험", "", "확인 필요"], legal_basis: ["법1", "", "법3"] } });
    expect(result.map(r => [r.rule_code, r.level, r.legal_basis])).toEqual([["LABOR_MIN_WAGE", "risky", "법1"], ["LABOR_PENALTY", null, ""], ["LABOR_BREAK", "check_needed", "법3"]]);
  });
  it.each([{}, { check_rules: [] }])("기준서 누락 시 안심을 보류한다", c => {
    const result = evaluate(sample(), c); expect(result.level).toBeNull(); expect(result.criteria_problems.length).toBeGreaterThan(0);
  });
  it("분류 누락 시 안심을 보류한다", () => {
    const c = criteria(); rules(c)[1].category = "";
    expect(evaluate(sample(), c)).toMatchObject({ level: null, undetermined_codes: ["LABOR_PENALTY"] });
  });
  it("변경된 조건을 보류한다", () => {
    const c = criteria(); rules(c).find(r => r.rule_code === "LABOR_BREAK")!.check_condition = "근로시간 6시간 이상이면 휴게 30분 이상이 없다. 6시간 미만은 해당 없다.";
    expect(evaluate(sample(3), c).undetermined_codes).toContain("LABOR_BREAK");
  });
  it("숫자만 바뀐 조건도 보류한다", () => {
    const c = criteria(), rule = rules(c).find(r => r.rule_code === "LABOR_WEEKLY_HOLIDAY")!;
    rule.check_condition = String(rule.check_condition).replaceAll("15시간", "20시간");
    expect(evaluate(sample(3), c).undetermined_codes).toContain("LABOR_WEEKLY_HOLIDAY");
  });
  it("추출 공백 차이는 허용한다", () => {
    const c = criteria(); for (const r of rules(c)) r.check_condition = String(r.check_condition).replaceAll(" ", "").replaceAll(",", " , ");
    expect(evaluate(sample(3), c).undetermined_codes).toEqual([]);
  });
  it("최저임금 조건의 금액 변경은 허용한다", () => {
    const c = criteria(); c.min_wage_hourly = [10900]; rules(c)[0].check_condition = String(rules(c)[0].check_condition).replace("10,320", "10,900");
    expect(evaluate(sample(), c).hit_codes).toContain("LABOR_MIN_WAGE");
  });
  it("필수 기재사항 추가를 보류한다", () => {
    const c = criteria(); c.required_items = [...c.required_items as string[], "취업규칙 교부"];
    expect(evaluate(sample(), c).undetermined_codes).toContain("LABOR_REQUIRED_TERMS");
  });
  it("다른 기준 연도의 다음 해 스키마를 쓰지 않는다", () => {
    const c = criteria(); c.criteria_version = ["v3.0 (법령 기준일 2027-10-01)"];
    const facts = compute_facts(sample(), c); expect(facts.next_min_wage).toBeNull(); expect(facts.notes.some(n => n.includes("다음 해 최저임금"))).toBe(true);
  });
  it("모든 원본 조건을 지원한다", () => {
    for (const [code, [sentence]] of Object.entries(KNOWN_CONDITIONS)) expect(condition_supported({ rule_code: code, check_condition: sentence })).toEqual([true, ""]);
  });
});

describe("계약 계산과 회귀", () => {
  it("야간 근무를 계산한다", () => {
    expect(compute_facts({ ...sample(), work_start_time: ["22:00"], work_end_time: ["06:00"], break_time: ["02:00 ~ 03:00"] }, criteria()).daily_work_hours).toBe(7);
  });
  it("월급을 시급으로 환산한다", () => {
    expect(compute_facts({ ...sample(), wage_type: ["월급"], wage_amount: [1000000] }, criteria()).hourly_wage).toBeCloseTo(1000000 / (33 * 365 / 7 / 12));
  });
  it.each(["2027-01-02", "2027년 1월"])("다음 해 계약에 다음 해 기준을 적용한다: %s", start => {
    const result = evaluate({ ...sample(), contract_start_date: [start], contract_end_date: ["2027-06-30"], wage_amount: [10500] }, criteria());
    expect(result.facts.applicable_min_wage).toBe(10700); expect(result.hit_codes).toContain("LABOR_MIN_WAGE"); expect(result.hit_codes).not.toContain("LABOR_MIN_WAGE_NEXT");
  });
  it("4시간 근무에 휴게가 필요하다", () => {
    expect(evaluate({ ...sample(4), work_start_time: ["13:00"], work_end_time: ["17:00"] }, criteria()).hit_codes).toContain("LABOR_BREAK");
  });
  it("보험료 공제를 불리한 조항에서 제외한다", () => {
    expect(evaluate({ ...sample(), special_terms: ["4대 보험료 공제 후 지급한다."] }, criteria()).hit_codes).not.toContain("LABOR_PENALTY");
  });
  it("계약서가 아니면 판정하지 않는다", () => {
    const blank = Object.fromEntries(Object.keys(sample()).map(k => [k, [""]])); expect(looks_like_contract(blank)).toBe(false); expect(evaluate(blank, criteria()).level).toBeNull();
  });
  it("빈 임금을 안심으로 판정하지 않는다", () => {
    const result = evaluate({ ...sample(), wage_amount: [""] }, criteria()); expect(result.level).not.toBe("safe"); expect(result.missing_items).toContain("임금(금액)");
  });
  it("읽지 못한 근무시간을 보류한다", () => {
    expect(evaluate({ ...sample(), work_start_time: ["판독 불가"], work_end_time: ["판독 불가"] }, criteria()).level).toBeNull();
  });
  it.each(["퇴사 시 마지막 근무일까지의 임금을 지급한다.", "퇴사 시 위약금과 손해배상액의 예정을 금지한다."])("모호한 특약을 보류한다: %s", clause => {
    const result = evaluate({ ...sample(), special_terms: [clause] }, criteria()); expect(result.hit_codes).not.toContain("LABOR_PENALTY"); expect(result.undetermined_codes).toContain("LABOR_PENALTY");
  });
  it("교부 부정 문구를 누락으로 판정한다", () => {
    const result = evaluate({ ...sample(), copy_delivery_clause: ["계약서를 근로자에게 교부하지 않는다."] }, criteria()); expect(result.hit_codes).toContain("LABOR_SIGN_COPY"); expect(result.missing_items).toContain("계약서 교부 문구");
  });
  it("최저임금 비교 전에 반올림하지 않는다", () => {
    const result = evaluate({ ...sample(), work_start_time: ["09:00"], work_end_time: ["18:00"], break_time: ["1시간"], wage_type: ["일급"], wage_amount: [82559], contract_end_date: ["2026-12-31"] }, criteria());
    expect(result.facts.hourly_wage).toBe(10319.875); expect(result.hit_codes).toContain("LABOR_MIN_WAGE"); expect(result.level).toBe("risky");
  });
  it("시작일을 모르면 최저임금을 선택하지 않는다", () => {
    const result = evaluate({ ...sample(), contract_start_date: ["협의 후 결정"] }, criteria()); expect(result.facts.applicable_min_wage).toBeNull(); expect(result.undetermined_codes).toContain("LABOR_MIN_WAGE");
  });
});

describe("교차 검증과 최종 결과", () => {
  it("일치와 불일치를 구분한다", () => {
    const engine = evaluate(sample(3), criteria());
    expect(cross_check("risky", engine_review(engine).matched_rules, engine)).toMatchObject({ level_match: true, agent_only: [], engine_only: [] });
    const check = cross_check("check_needed", ["LABOR_BREAK - 근로기준법 제54조"], engine); expect(check.level_match).toBe(false); expect(check.engine_only).toContain("LABOR_PENALTY");
  });
  it("등급을 올리고 모순된 충족 항목을 제거한다", () => {
    const engine = evaluate(sample(3), criteria()), agent = review();
    const result = final_view(agent, engine, "safe", cross_check("safe", agent.matched_rules, engine));
    expect(result.level).toBe("risky"); expect(result.summary).toContain("올렸습니다"); expect(result.confirmed_items).not.toContain("불리한 특약 없음"); expect(result.recommendations.some(r => r.includes("삭제"))).toBe(true);
    expect(new Set(result.cards.map(c => c.rule_code))).toEqual(new Set(engine.hit_codes)); expect(result.cards.every(c => c.source === "engine")).toBe(true);
  });
  it("에이전트만 지적한 규칙을 표시한다", () => {
    const engine = evaluate(sample(), criteria()), agent = review({ review_level: "check_needed", matched_rules: ["LABOR_BREAK - 근로기준법 제54조"], recommendations: ["휴게시간을 적어 주세요."] });
    const result = final_view(agent, engine, "check_needed", cross_check("check_needed", agent.matched_rules, engine));
    expect(result.level).toBe("check_needed"); expect(result.cards.find(c => c.rule_code === "LABOR_BREAK")).toMatchObject({ source: "agent" }); expect(result.cards[0].reason).toContain("평가 에이전트가");
  });
  it("에이전트가 지적한 새 규칙을 보류에서 제외한다", () => {
    const c = criteria(); rules(c).push({ rule_code: "LABOR_NEW_RULE", category: "위험", check_condition: "새 규칙" });
    const engine = evaluate(sample(), c), agent = review({ review_level: "risky", matched_rules: ["LABOR_NEW_RULE - 새 법"] });
    const result = final_view(agent, engine, "risky", cross_check("risky", agent.matched_rules, engine));
    expect(result.level).toBe("risky"); expect(result.cards.map(c => c.rule_code)).toEqual(["LABOR_NEW_RULE"]); expect(result.pending).toEqual([]);
  });
  it("사업주 요청 문장은 에이전트 결과에서만 가져온다", () => {
    const engine = evaluate(sample(3), criteria());
    const demo = final_view(engine_review(engine), engine, null, cross_check(null, [], engine)); expect(demo.recommendations.length).toBeGreaterThan(0); expect(demo.requests).toEqual([]);
    const agent = review({ review_level: "risky", recommendations: ["사장님, 위약금 조항을 빼 주실 수 있을까요?"] });
    expect(final_view(agent, engine, "risky", cross_check("risky", agent.matched_rules, engine)).requests).toEqual(agent.recommendations);
  });
});
