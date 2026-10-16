import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  compute_facts, criteria_rules, cross_check, engine_review, evaluate, final_view,
  looks_like_contract, more_severe, normalize_level, parse_break, parse_times,
  parse_work_days, to_number, won, to_date, condition_supported, KNOWN_CONDITIONS,
  criteria_problems, summarize_criteria, field_state, copy_clause_status, type ExtractedData, type Review,
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
    [3, "risky", ["LABOR_MIN_WAGE", "LABOR_PENALTY", "LABOR_REQUIRED_TERMS", "LABOR_BREAK", "LABOR_WEEKLY_HOLIDAY", "LABOR_SIGN_COPY", "LABOR_MIN_WAGE_NEXT"]],
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
    for (const [code, [sentence]] of Object.entries(KNOWN_CONDITIONS)) expect(condition_supported({ rule_code: code, check_condition: sentence }, 2026)).toEqual([true, ""]);
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
    expect(result.level).toBe("risky"); expect(result.summary).toContain("평가 에이전트는 '안심'"); expect(result.summary).not.toContain("모든 규칙을 충족합니다"); expect(result.agent_summary).toBe(agent.summary); expect(result.confirmed_items).not.toContain("불리한 특약 없음"); expect(result.recommendations.some(r => r.includes("삭제"))).toBe(true);
    expect(new Set(result.cards.map(c => c.rule_code))).toEqual(new Set(engine.hit_codes)); expect(result.cards.every(c => c.source === "engine")).toBe(true);
  });
  it("에이전트만 지적한 규칙을 표시한다", () => {
    const engine = evaluate(sample(), criteria()), agent = review({ review_level: "check_needed", matched_rules: ["LABOR_REQUIRED_TERMS - 근로기준법 제17조"], recommendations: ["업무 내용을 구체적으로 적어 주세요."] });
    const result = final_view(agent, engine, "check_needed", cross_check("check_needed", agent.matched_rules, engine));
    expect(result.level).toBe("check_needed"); expect(result.cards.find(c => c.rule_code === "LABOR_REQUIRED_TERMS")).toMatchObject({ source: "agent" }); expect(result.cards[0].reason).toContain("평가 에이전트가");
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

const withCondition = (code: string, transform: (value: string) => string) => {
  const c = criteria();
  const rule = rules(c).find(r => r.rule_code === code)!;
  rule.check_condition = transform(String(rule.check_condition));
  return c;
};

describe("최신 원본 2차 회귀", () => {
  it.each([
    ["LABOR_WEEKLY_HOLIDAY", "15시간 이상인데", "15시간 초과인데"],
    ["LABOR_MIN_WAGE", "최저임금보다 낮다", "최저임금보다 높다"],
    ["LABOR_SIGN_COPY", "없거나", "없고"],
    ["LABOR_MIN_WAGE_NEXT", "2027년 1월 1일", "2027년 7월 1일"],
    ["LABOR_BREAK", "휴게 30분 이상, 8시간 이상이면 휴게 1시간", "휴게 1분 이상, 8시간 이상이면 휴게 30시간"],
  ])("의미가 바뀐 조건을 보류한다: %s", (code, old, next) => {
    expect(evaluate(sample(3), withCondition(code, text => text.replaceAll(old, next))).undetermined_codes).toContain(code);
  });
  it("금액만 바뀐 최저임금 조건을 지원한다", () => {
    const c = withCondition("LABOR_MIN_WAGE", text => text.replace("10,320", "10,500")); c.min_wage_hourly = [10500];
    expect(evaluate(sample(), c).undetermined_codes).not.toContain("LABOR_MIN_WAGE");
  });
  it("최종 등급이 확정 카드보다 낮지 않다", () => {
    const engine = evaluate({ ...sample(), special_terms: ["퇴사시 마지막 임금을 지급한다."], is_signed: [false] }, criteria());
    expect(engine.level).toBeNull(); expect(engine.min_level).toBe("check_needed");
    const result = final_view(review(), engine, "safe", cross_check("safe", [], engine));
    expect(result.level).toBe("check_needed"); expect(result.incomplete).toBe(false);
  });
  it("에이전트 자체 규칙보다 낮은 등급을 올린다", () => {
    const engine = evaluate(sample(), criteria()), agent = review({ matched_rules: ["LABOR_PENALTY - 근로기준법 제20조"] });
    const result = final_view(agent, engine, "safe", cross_check("safe", agent.matched_rules, engine));
    expect(result.level).toBe("risky"); expect(result.disagree).toBe(true);
  });
  it("에이전트 없이 보류 규칙이 있으면 최소 등급을 표시한다", () => {
    const engine = evaluate({ ...sample(), special_terms: ["퇴사시 마지막 임금을 지급한다."], is_signed: [false] }, criteria());
    const result = final_view(engine_review(engine), engine, null, cross_check(null, [], engine));
    expect(result.level).toBe("check_needed"); expect(result.incomplete).toBe(true); expect(result.summary).toContain("최소 '확인 필요'");
  });
  it("원문에서 빠진 규칙은 기준서 문제다", () => {
    const c = criteria(), codes = new Set(rules(c).map(rule => String(rule.rule_code)));
    c.check_rules = rules(c).filter(rule => rule.rule_code !== "LABOR_MIN_WAGE");
    expect(criteria_problems(c, codes).some(p => p.includes("빠진 규칙"))).toBe(true);
    expect(evaluate({ ...sample(), wage_amount: [9500], contract_end_date: ["2026-12-31"] }, c, null, codes).level).toBeNull();
  });
  it("중복 규칙 코드는 기준서 문제다", () => {
    const c = criteria(); rules(c).push({ ...rules(c)[0] });
    expect(criteria_problems(c).some(p => p.includes("중복"))).toBe(true);
  });
  it.each([["annual_leave_clause", "해당 없음"], ["annual_leave_clause", "없음"], ["wage_payment_method", "미정"], ["job_description", "추후 결정"]])("없음과 미정은 누락이다: %s %s", (field, value) => {
    expect(evaluate({ ...sample(), [field]: [value] }, criteria()).hit_codes).toContain("LABOR_REQUIRED_TERMS");
  });
  it("해당 없음의 판정에는 주 근로시간이 필요하다", () => {
    expect(evaluate({ ...sample(4), work_days: [""] }, criteria()).undetermined_codes).toContain("LABOR_REQUIRED_TERMS");
  });
  it.each([
    ["2026-12-10", "휴게 없음 (근로자가 명시적으로 휴게 미사용을 요청함)", false],
    ["2026-11-01", "휴게 없음 (근로자가 명시적으로 휴게 미사용을 요청함)", true],
    ["2026-12-10", "없음", true],
  ])("4시간 휴게 예외: %s %s", (start, breakText, hit) => {
    const engine = evaluate({ ...sample(), contract_start_date: [start], work_start_time: ["09:00"], work_end_time: ["13:00"], break_time: [breakText] }, criteria());
    expect(engine.findings.find(f => f.rule_code === "LABOR_BREAK")?.hit).toBe(hit);
  });
  it("사업주가 지급하는 배상금을 불리한 조항으로 확정하지 않는다", () => {
    expect(evaluate({ ...sample(), special_terms: ["회사가 근로자에게 손해배상금을 지급한다."] }, criteria()).hit_codes).not.toContain("LABOR_PENALTY");
  });
  it.each(["계약서를 근로자에게 교부할 의무는 없다.", "계약서를 근로자에게 교부는 하지 않는다."])("교부 부정 문구: %s", clause => {
    expect(evaluate({ ...sample(), copy_delivery_clause: [clause] }, criteria()).hit_codes).toContain("LABOR_SIGN_COPY");
  });
  it("휴게가 근무 구간보다 길면 계산하지 않는다", () => {
    const facts = compute_facts({ ...sample(), work_start_time: ["09:00"], work_end_time: ["10:00"], break_time: ["2시간"] }, criteria());
    expect(facts.daily_work_hours).toBeNull(); expect(facts.notes.some(n => n.includes("휴게시간이"))).toBe(true);
  });
  it("여러 근무 구간을 합치지 않는다", () => {
    expect(compute_facts({ ...sample(), work_start_time: ["09:00", "18:00"], work_end_time: ["13:00", "22:00"], break_time: ["없음"] }, criteria()).daily_work_hours).toBeNull();
  });
  it("요약에서도 연도가 다른 다음 해 임금을 제외한다", () => {
    const c = criteria(); c.criteria_version = ["v3.0 (법령 기준일 2027-10-01)"];
    expect(summarize_criteria(c)).toMatchObject({ min_wage_next: null, min_wage_next_dropped: true });
  });
  it("숫자 내부 줄바꿈을 허용한다", () => {
    expect(evaluate(sample(), withCondition("LABOR_REQUIRED_TERMS", text => text.replace("15시간 미만", "1\n5시간 미만"))).undetermined_codes).not.toContain("LABOR_REQUIRED_TERMS");
  });
});

describe("최신 원본 3차 회귀", () => {
  it("계산 보류는 부분 교차 검증이다", () => {
    const c = criteria(); for (const rule of rules(c)) rule.check_condition = "점검 조건: " + rule.check_condition;
    const engine = evaluate(sample(), c), check = cross_check("safe", [], engine);
    expect(engine.level).toBeNull(); expect(check.status).toBe("partial");
    expect(final_view(review(), engine, "safe", check)).toMatchObject({ level: "safe", incomplete: false });
  });
  it("등급만 달라도 불일치다", () => {
    expect(cross_check("risky", [], evaluate(sample(), criteria())).status).toBe("mismatch");
  });
  it("요약은 항상 다시 작성한다", () => {
    const engine = evaluate(sample(3), criteria());
    const agent = review({ review_level: "risky", summary: "모든 규칙을 충족합니다.", matched_rules: engine.hit_codes.map(code => `${code} - x`) });
    const result = final_view(agent, engine, "risky", cross_check("risky", agent.matched_rules, engine));
    expect(result.summary).not.toContain("모든 규칙을 충족합니다"); expect(result.agent_summary).toBe(agent.summary);
  });
  it.each([["annual_leave_clause", "연차유급휴가는 근로기준법에 따라 부여하며 사용일은 협의하여 정한다."], ["weekly_holiday", "매주 일요일 (변경 없음)"]])("정상 설명 문장을 누락으로 보지 않는다: %s", (field, value) => {
    expect(evaluate({ ...sample(), [field]: [value] }, criteria()).level).toBe("safe");
  });
  it("모호한 연차 문장을 보류한다", () => {
    expect(evaluate({ ...sample(), annual_leave_clause: ["연차유급휴가는 회사 사정에 따라 협의한다."] }, criteria()).undetermined_codes).toContain("LABOR_REQUIRED_TERMS");
  });
  it("교부와 무관한 부정을 구분한다", () => {
    expect(evaluate({ ...sample(), copy_delivery_clause: ["근로자의 교부 요구와 관계없이 계약서 1부를 근로자에게 교부한다."] }, criteria()).level).toBe("safe");
  });
  it("세금과 보험료 공제를 정상으로 본다", () => {
    const result = evaluate({ ...sample(), special_terms: ["소득세와 4대 보험료를 임금에서 공제한다."] }, criteria());
    expect([...result.hit_codes, ...result.undetermined_codes]).not.toContain("LABOR_PENALTY");
  });
  it.each(["휴게 없음 (근로자가 휴게 미사용을 요청하지 않음)", "휴게 없음 (사용자가 휴게 미사용을 요청함)"])("휴게 예외에는 근로자의 긍정 요청이 필요하다: %s", breakText => {
    const engine = evaluate({ ...sample(), contract_start_date: ["2026-12-10"], work_start_time: ["09:00"], work_end_time: ["13:00"], break_time: [breakText] }, criteria());
    expect(engine.findings.find(f => f.rule_code === "LABOR_BREAK")?.hit).toBe(true);
  });
  it.each([["2026년", "2026\n년"], ["2027년", "2027\n년"], ["10,320", "1\n0,320"]])("연도와 금액 내부 줄바꿈: %s", (old, next) => {
    expect(evaluate(sample(), withCondition("LABOR_MIN_WAGE", text => text.replaceAll(old, next))).undetermined_codes).not.toContain("LABOR_MIN_WAGE");
  });
  it("필드 상태와 교부 상태를 구별한다", () => {
    expect(["", "없음", "미정", "매주 일요일 (변경 없음)"].map(field_state)).toEqual(["blank", "absent", "undecided", "written"]);
    expect(copy_clause_status({ copy_delivery_clause: ["계약서 교부"] })).toBe("unclear");
  });
  it("빈 코드와 원문에 없는 코드를 검출한다", () => {
    const c = criteria(); rules(c).push({ rule_code: "", category: "위험" }, { rule_code: "LABOR_EXTRA", category: "위험" });
    const problems = criteria_problems(c, new Set(Object.keys(KNOWN_CONDITIONS)));
    expect(problems.some(p => p.includes("비어 있는 행"))).toBe(true); expect(problems.some(p => p.includes("원문에 없는 규칙"))).toBe(true);
  });
});

// 원본 pytest 143개와 추가 경계 사례에서 기록한 전체 결과를 비교합니다.
import * as pythonRules from "../src/lib/rules";
interface ParityCase { function: string; args: unknown[]; expected: unknown }
const parity = JSON.parse(readFileSync(new URL("./fixtures/rules-python-parity.json", import.meta.url), "utf8")) as {
  source_revision: string;
  recorded_sample3: { cross_status: string; final_level: string; incomplete: boolean };
  cases: ParityCase[];
};
function decodePython(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(decodePython);
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (Array.isArray(record.$set)) return new Set(record.$set);
    if (typeof record.$date === "string") return new Date(`${record.$date}T00:00:00.000Z`);
    return Object.fromEntries(Object.entries(record).map(([key, item]) => [key, decodePython(item)]));
  }
  return value;
}
function encodePython(value: unknown): unknown {
  if (value instanceof Set) return { $set: [...value].sort((a, b) => typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b))) };
  if (value instanceof Date) return { $date: value.toISOString().slice(0, 10) };
  if (Array.isArray(value)) return value.map(encodePython);
  if (value !== null && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, encodePython(item)]));
  return value;
}
describe("최신 Python 전체 JSON 동등성", () => {
  it("요청한 원본 커밋과 녹화된 샘플 3을 포함한다", () => {
    expect(parity.source_revision).toBe("561d8bc334aeef6b25f456640315554c4361bf3e");
    expect(parity.recorded_sample3).toMatchObject({ cross_status: "mismatch", final_level: "risky", incomplete: false });
  });
  it.each(parity.cases.map((test, index) => ({ ...test, index })))("$index: $function", ({ function: name, args, expected }) => {
    const fn = pythonRules[name as keyof typeof pythonRules] as (...input: unknown[]) => unknown;
    expect(typeof fn).toBe("function");
    expect(encodePython(fn(...args.map(decodePython)))).toEqual(expected);
  });
});

const edgeInputs = JSON.parse(readFileSync(new URL("./fixtures/rules-edge-inputs.json", import.meta.url), "utf8")) as {
  AMBIGUOUS_INPUTS: [ExtractedData, string][]; NORMAL_INPUTS: [ExtractedData, string][];
};
const runFinal = (contract: ExtractedData, level: Review["review_level"], matched: string[], overrides: Partial<Review> = {}, c = criteria()) => {
  const engine = evaluate(contract, c, compute_facts(contract, c));
  const agent = review({ review_level: level, matched_rules: matched, ...overrides });
  return { engine, final: final_view(agent, engine, level, cross_check(level, matched, engine)) };
};
describe("561d8bc 원본 4·5차 회귀", () => {
  it("통과가 확정된 규칙은 의견 차이로 분리한다", () => {
    const { final } = runFinal(sample(), "check_needed", ["LABOR_BREAK - 제54조"], { recommendations: ["휴게시간을 적어 주세요."] });
    expect(final.cards).toEqual([]); expect(final.disputed.map(d => d.rule_code)).toEqual(["LABOR_BREAK"]);
    expect(final.level).toBe("safe"); expect(final.requests).toEqual([]); expect(final.recommendations).toEqual([]);
    expect(final.summary).toContain("등급에 넣지 않았습니다"); expect(final.disagree).toBe(true);
  });
  it("에이전트 등급을 기준서의 규칙 분류에 맞춘다", () => {
    const contract = sample(2), engine = evaluate(contract, criteria());
    const { final } = runFinal(contract, "risky", engine.hit_codes);
    expect(new Set(final.cards.map(card => card.level))).toEqual(new Set(["check_needed"]));
    expect(final.level).toBe("check_needed"); expect(final.summary).toContain("기준서 분류에 맞춰");
  });
  it("규칙 코드가 없는 지적은 확인 필요까지 표시한다", () => {
    const { final } = runFinal(sample(), "risky", ["기타 - 사장님 태도"]);
    expect(final.cards).toEqual([]); expect(final.level).toBe("check_needed"); expect(final.summary).toContain("근거를 찾지 못해");
  });
  it.each(edgeInputs.AMBIGUOUS_INPUTS)("모호한 입력에서는 에이전트 지적을 의견 차이로 빼지 않는다: %j", (changes, code) => {
    const { engine, final } = runFinal({ ...sample(), ...changes }, "check_needed", [`${code} - 근거`], { recommendations: ["확인해 주세요."] });
    const finding = engine.findings.find(f => f.rule_code === code)!;
    expect(finding.hit).toBeNull(); expect(final.cards.map(c => c.rule_code)).toContain(code);
    expect(final.disputed).toEqual([]); expect(final.level).toBe(finding.level); expect(final.requests).toEqual(["확인해 주세요."]);
  });
  it.each([[true, false], [true, "미서명"]])("상충하는 서명을 통과로 보지 않는다: %j", (...signed) => {
    const { engine, final } = runFinal({ ...sample(), is_signed: signed }, "check_needed", ["LABOR_SIGN_COPY"]);
    expect(engine.findings.find(f => f.rule_code === "LABOR_SIGN_COPY")?.hit).not.toBe(false);
    expect(final.disputed).toEqual([]); expect(final.level).toBe("check_needed");
  });
  it.each(edgeInputs.NORMAL_INPUTS)("명확한 입력의 통과 판정을 유지한다: %j", (changes, code) => {
    const { engine, final } = runFinal({ ...sample(), ...changes }, "check_needed", [`${code} - 근거`]);
    expect(engine.findings.find(f => f.rule_code === code)?.hit).toBe(false);
    expect(final.disputed.map(d => d.rule_code)).toEqual([code]); expect(final.level).toBe("safe"); expect(final.cards).toEqual([]);
  });
  it("무관한 보류 규칙으로 등급을 올리지 않는다", () => {
    const { engine, final } = runFinal({ ...sample(), special_terms: ["위약금은 없다."] }, "risky", ["LABOR_BREAK - 제54조"]);
    expect(engine.undetermined_codes).toContain("LABOR_PENALTY"); expect(final.level).toBe("safe");
    expect(runFinal({ ...sample(), wage_amount: [10800, 9500] }, "risky", ["기타 - 사장님 태도"]).final.level).toBe("check_needed");
  });
  it("근거가 없는 에이전트 경고를 따르지 않는다", () => {
    const { final } = runFinal(sample(), "risky", [], { recommendations: [] });
    expect(final.level).toBe("safe"); expect(final.summary).toContain("근거를 찾지 못해");
  });
  it.each([
    [["LABOR_SIGN_COPY - 서명 누락; 기준서 밖 지적 - 계약 외 사항"]],
    [["LABOR_SIGN_COPY - 서명 누락", "기준서 밖 지적 - 계약 외 사항"]],
  ])("한 문장에 합쳐진 코드 없는 지적도 보존한다: %j", matched => {
    const { final } = runFinal(sample(), "risky", matched, { recommendations: ["계약 외 사항을 확인해 주세요."] });
    expect(final.level).toBe("check_needed"); expect(final.requests).toEqual(["계약 외 사항을 확인해 주세요."]);
  });
  it("채택된 규칙과 의견 차이 규칙을 함께 다룬 요청은 보존한다", () => {
    const { final } = runFinal({ ...sample(), job_description: "" }, "check_needed", ["LABOR_REQUIRED_TERMS", "LABOR_SIGN_COPY"], { recommendations: ["업무 내용을 명시한 계약서를 교부해 주세요."] });
    expect(final.disputed.map(d => d.rule_code)).toEqual(["LABOR_SIGN_COPY"]); expect(final.requests).toEqual(["업무 내용을 명시한 계약서를 교부해 주세요."]);
  });
  it("요청을 제거해도 각 카드의 권장 행동은 유지한다", () => {
    const { final } = runFinal({ ...sample(), job_description: "" }, "check_needed", ["LABOR_REQUIRED_TERMS", "LABOR_BREAK"], { recommendations: ["휴게시간을 넣어 주세요."] });
    expect(final.requests).toEqual([]); expect(final.recommendations.some(action => action.includes("빠진 항목"))).toBe(true);
  });
  it("무관한 의견 차이가 있어도 보류 규칙의 코드 없는 지적은 유지한다", () => {
    const { engine, final } = runFinal({ ...sample(), special_terms: ["퇴사하려면 사장님의 허가를 받아야 한다."] }, "risky", ["부당한 퇴사 제한 - 퇴사하려면 사장님 허가 필요", "LABOR_SIGN_COPY - 제17조"], { recommendations: ["퇴사 제한 조항을 빼 주세요."] });
    expect(engine.findings.find(f => f.rule_code === "LABOR_PENALTY")?.hit).toBeNull(); expect(final.disputed.map(d => d.rule_code)).toEqual(["LABOR_SIGN_COPY"]);
    expect(final.level).toBe("risky"); expect(final.requests).toEqual(["퇴사 제한 조항을 빼 주세요."]); expect(final.summary).toContain("에이전트 판단대로 '위험'");
  });
  it("보류 규칙이 없으면 코드 없는 지적은 확인 필요다", () => {
    expect(runFinal(sample(), "risky", ["부당한 퇴사 제한 - 근거 없음"]).final.level).toBe("check_needed");
  });
  it("일부 의견 차이에서는 반박된 문장만 제거한다", () => {
    const { final } = runFinal({ ...sample(), job_description: "" }, "check_needed", ["LABOR_REQUIRED_TERMS - 제17조", "LABOR_BREAK - 제54조"], { missing_items: ["휴게시간", "업무의 내용"], recommendations: ["업무 내용을 적어 주세요.", "휴게시간이 없으니 30분을 넣어 주세요."] });
    expect(final.disputed.map(d => d.rule_code)).toEqual(["LABOR_BREAK"]); expect(final.level).toBe("check_needed"); expect(final.requests).toEqual(["업무 내용을 적어 주세요."]);
    expect(final.recommendations).not.toContain("휴게시간이 없으니 30분을 넣어 주세요."); expect(final.missing_items).not.toContain("휴게시간"); expect(final.missing_items).toContain("업무의 내용");
  });
  it("다음 해 금액 문장을 다음 해 규칙에 연결한다", () => {
    const sentences = ["2027년 1월 1일부터 시급을 10,700원 이상으로 올려 주세요.", "시급을 최저임금 이상으로 올려 주세요."];
    expect(pythonRules.drop_disputed(sentences, new Set(["LABOR_MIN_WAGE_NEXT"]), 2027)).toEqual([sentences[1]]);
    expect(pythonRules.drop_disputed(sentences, new Set(["LABOR_MIN_WAGE"]), 2027)).toEqual([sentences[0]]);
  });
  it("잘린 추출 칸만 원문 표로 복구한다", () => {
    const c = criteria(), row = rules(c).find(r => r.rule_code === "LABOR_MIN_WAGE_NEXT")!;
    row.check_condition = "계약기간이 2027년 1월 1일 이후까지 이어지는데 시급이 2027년 최저임금 10,700원 미만이다. 종료";
    row.recommended_action = "2027년 1월 1일부 터 시급을 10,700";
    const source = { LABOR_MIN_WAGE_NEXT: { check_condition: KNOWN_CONDITIONS.LABOR_MIN_WAGE_NEXT[0], recommended_action: "2027년 1월 1일부 터 시급을 10,700 원 이상으로 올려 달라고 요청하세 요." } };
    const [fixed, repaired] = pythonRules.apply_source_table(c, source);
    expect(repaired).toEqual(["LABOR_MIN_WAGE_NEXT"]); expect(fixed.check_rules).not.toBe(c.check_rules);
    const rule = criteria_rules(fixed).find(r => r.rule_code === "LABOR_MIN_WAGE_NEXT")!;
    expect(condition_supported(rule, 2026)[0]).toBe(true); expect(rule.recommended_action.endsWith("요청하세 요.")).toBe(true);
    const [same, none] = pythonRules.apply_source_table(fixed, source); expect(same).toBe(fixed); expect(none).toEqual([]);
    expect(pythonRules.apply_source_table(c, {})).toEqual([c, []]);
  });
  it("더 길거나 다른 내용인 추출을 자르지 않는다", () => {
    const c = criteria(), known = KNOWN_CONDITIONS.LABOR_MIN_WAGE[0];
    rules(c).find(r => r.rule_code === "LABOR_MIN_WAGE")!.check_condition = known + " 단, 시급이 11,000원 미만이면 위반으로 본다.";
    const [fixed, repaired] = pythonRules.apply_source_table(c, { LABOR_MIN_WAGE: { check_condition: known } });
    expect(fixed).toBe(c); expect(repaired).toEqual([]); expect(condition_supported(criteria_rules(fixed)[0], 2026)[0]).toBe(false);
    expect(pythonRules.apply_source_table(c, { LABOR_MIN_WAGE: { check_condition: "전혀 다른 조건이다. 그리고 더 길다. 훨씬 더 길다." } })).toEqual([c, []]);
  });
});
