// 기준값과 판정 문구는 원본 Python 규칙 엔진을 보존합니다.
export type Level = "safe" | "check_needed" | "risky";
export type ExtractedData = Record<string, unknown>;
export const LEVELS: readonly Level[] = ["safe", "check_needed", "risky"];
export const LEVEL_LABELS: Record<Level, string> = { safe: "안심", check_needed: "확인 필요", risky: "위험" };
export const LEVEL_SEVERITY: Record<Level, number> = { safe: 0, check_needed: 1, risky: 2 };

export const RULE_TITLES: Record<string, string> = {
  "LABOR_MIN_WAGE": "최저임금 미달",
  "LABOR_PENALTY": "위약금·손해배상·임금 공제 조항",
  "LABOR_REQUIRED_TERMS": "필수 기재사항 누락",
  "LABOR_BREAK": "휴게시간 부족",
  "LABOR_WEEKLY_HOLIDAY": "주휴일 미기재",
  "LABOR_SIGN_COPY": "서명·교부 누락",
  "LABOR_MIN_WAGE_NEXT": "다음 해 최저임금 미달 예정"
};

export const RULE_PASS_TITLES: Record<string, string> = {
  "LABOR_MIN_WAGE": "최저임금 이상",
  "LABOR_PENALTY": "불리한 특약 없음",
  "LABOR_REQUIRED_TERMS": "필수 기재사항 모두 기재",
  "LABOR_BREAK": "휴게시간 기준 충족",
  "LABOR_WEEKLY_HOLIDAY": "주휴일 기준 충족",
  "LABOR_SIGN_COPY": "서명·교부 문구 있음",
  "LABOR_MIN_WAGE_NEXT": "다음 해 최저임금 기준 충족"
};

export const KNOWN_CONDITIONS: Record<string, [string, boolean]> = {
  "LABOR_MIN_WAGE": [
    "계약 시작일 기준 시급이 최저임금보다 낮다. 2026년 시작 계약은 10,320원, 2027년 1월 1일 이후 시작 계약은 10,700원과 비교한다.",
    true
  ],
  "LABOR_PENALTY": [
    "위약금, 손해배상액의 예정, 임금 공제, 부당한 퇴사 제한 등 불리한 조항이 있다.",
    false
  ],
  "LABOR_REQUIRED_TERMS": [
    "법정 필수 기재사항 6가지(임금, 소정근로시간, 휴일, 연차유급휴가, 근무장소와 업무, 근로계약기간) 중 하나라도 적혀 있지 않다. 단 1주 소정근로시간이 15시간 미만인 근로자는 휴일과 연차유급휴가 항목에 '해당 없음'이라고 적혀 있으면 적힌 것으로 본다.",
    false
  ],
  "LABOR_BREAK": [
    "근로시간 4시간 이상 8시간 미만이면 휴게 30분 이상, 8시간 이상이면 휴게 1시간 이상이 없다. 4시간 미만은 해당 없다. (2026-12-10부터 근로시간이 정확히 4시간이고 근로자가 명시적으로 휴게 미사용을 요청하면 예외)",
    false
  ],
  "LABOR_WEEKLY_HOLIDAY": [
    "1주 소정근로시간이 15시간 이상인데 주휴일이 적혀 있지 않다. 1주 15시간 미만이면 해당 없다.",
    false
  ],
  "LABOR_SIGN_COPY": [
    "사업주 또는 근로자의 서명·날인이 없거나, 계약서를 근로자에게 교부한다는 문구가 없다.",
    false
  ],
  "LABOR_MIN_WAGE_NEXT": [
    "계약기간이 2027년 1월 1일 이후까지 이어지는데 시급이 2027년 최저임금 10,700원 미만이다. 종료일이 없으면 이어진다고 본다.",
    true
  ]
};

export const REQUIRED_TERM_KEYS: Record<string, string[]> = {
  "임금": [
    "임금"
  ],
  "소정근로시간": [
    "소정근로시간",
    "근로시간"
  ],
  "휴일": [
    "휴일"
  ],
  "연차유급휴가": [
    "연차"
  ],
  "근무장소와 업무": [
    "장소",
    "업무"
  ],
  "근로계약기간": [
    "기간"
  ]
};

export const CORE_FIELDS: readonly string[] = [
  "employer_name",
  "contract_start_date",
  "workplace",
  "work_start_time",
  "work_end_time",
  "wage_amount"
];

export const RULE_SOURCE_FIELDS: Record<string, string> = {
  "LABOR_PENALTY": "special_terms",
  "LABOR_BREAK": "break_time",
  "LABOR_WEEKLY_HOLIDAY": "weekly_holiday",
  "LABOR_SIGN_COPY": "copy_delivery_clause"
};

export const KNOWN_BASE_YEAR = 2026;
export const DECISIVE_PASS_RULES: ReadonlySet<string> = new Set(["LABOR_BREAK", "LABOR_MIN_WAGE", "LABOR_MIN_WAGE_NEXT", "LABOR_SIGN_COPY", "LABOR_WEEKLY_HOLIDAY"]);
export const SOURCE_FIELDS = ["check_condition", "legal_basis", "recommended_action"] as const;
export type SourceTable = Record<string, Partial<Record<typeof SOURCE_FIELDS[number], string>>>;
export const RULE_KEYWORDS: Record<string, string[]> = {
  "LABOR_MIN_WAGE": [
    "최저임금",
    "시급"
  ],
  "LABOR_PENALTY": [
    "위약",
    "손해배상",
    "배상",
    "공제",
    "벌금",
    "퇴사",
    "퇴직",
    "사직",
    "그만",
    "해지"
  ],
  "LABOR_REQUIRED_TERMS": [
    "업무",
    "근무장소",
    "근무 장소",
    "임금지급",
    "지급일",
    "지급 방법",
    "연차",
    "소정근로",
    "계약기간"
  ],
  "LABOR_BREAK": [
    "휴게"
  ],
  "LABOR_WEEKLY_HOLIDAY": [
    "주휴"
  ],
  "LABOR_SIGN_COPY": [
    "서명",
    "날인",
    "교부",
    "사본"
  ]
};
const DATE_PATTERN = new RegExp("(\\d{4})\\s*[-./년]\\s*(\\d{1,2})\\s*[-./월]\\s*(\\d{1,2})");
const RENEWAL_PATTERN = new RegExp("(?:자동\\s*)?(?:연장|갱신|재계약)");
const MONTH_PATTERN = new RegExp("(\\d{4})\\s*(?:[-./]|년)\\s*(\\d{1,2})(?!\\s*[-./월]\\s*\\d)(?:\\s*월)?");
const RENEWAL_DENIED_PATTERN = new RegExp("^\\s*(?:은|는|이|가|을|를)?\\s*(?:없|않|불가|금지|아니|하지)");
const BREAK_ALTERNATIVE_PATTERN = new RegExp("또는|혹은|선택|교대|요일별|요일에\\s*따라|격주");
const BREAK_BY_DAY_PATTERN = new RegExp("평일|주말|[월화수목금토일]\\s*요일|[월화수목금토일](?:\\s*[~,·]\\s*[월화수목금토일])+");

export const BREAK_EXCEPTION_START = new Date("2026-12-10T00:00:00.000Z");
export const NEXT_MIN_WAGE_FIELD = "min_wage_hourly_2027";
export const NEXT_MIN_WAGE_YEAR = 2027;
const EMPTY_MARKERS = new Set(["", "(비어 있음)", "비어 있음", "null", "none", "n/a", "-"]);
const EXPLICIT_NO_BREAK_PATTERN = new RegExp("근로자\\s*(?:가|는|이|본인이|의)[^.()]{0,30}?(?:미사용|사용하지\\s*않|없이|생략)[^.()]{0,15}?요청(?:함|하였|했|한다|하여|에\\s*따라)");
const NO_REQUEST_PATTERN = new RegExp("요청\\s*하지|요청\\s*안|요청\\s*없|요청이\\s*없|(?:사용자|사업주|회사)\\s*(?:가|는|이)[^.()]{0,30}?요청");
const NONE_PATTERN = new RegExp("없|미부여|미지정|해당\\s*사항\\s*없");
const UNDECIDED_PATTERN = new RegExp("미정|추후|결정\\s*되지|정하지\\s*않|협의\\s*(?:후|하여)?\\s*(?:결정|정함|정한다)|협의한다|협의함|협의\\s*예정");
const WAGE_DEDUCTION_PATTERN = new RegExp("(?:임금|급여|월급|시급|일당)\\s*(?:에서|을|를)?\\s*(?:공제|차감|감액|삭감|몰수)");
const PENALTY_PURPOSE_PATTERN = new RegExp("손해|위약|배상|변상|벌금|벌칙|지각|결근|파손|분실|실수|과실|퇴사");
const STATUTORY_DEDUCTION_PATTERN = new RegExp("세금|소득세|주민세|지방세|원천징수|보험료|4대\\s*보험|사회보험|고용보험|건강보험|국민연금|산재보험");
const WORKER_PAYS_PATTERN = new RegExp("(?:근로자|을)\\s*(?:은|는|이|가)\\s*[^.]{0,40}?(?:위약금|위약|손해\\s*배상|배상|변상|벌금)[^.]{0,20}?(?:지급|배상|변상|부담|물어|납부)");
const PENALTY_HINT_PATTERN = new RegExp("위약|손해\\s*배상|배상|변상|벌금|벌칙|몰수|감액|차감|(?<!보험료\\s)(?<!보험료)(?<!보험\\s)(?<!보험)(?<!세금\\s)(?<!세금)(?<!세\\s)(?<!세)공제");
const RESIGN_PATTERN = new RegExp("퇴사|퇴직|사직|그만\\s*두|그만\\s*둘|중도\\s*해지");
const NEGATION_PATTERN = new RegExp("금지|않|아니|없|불가|못|면제|말아야|아님");
const EMPLOYER_PAYS_PATTERN = new RegExp("(?:회사|사업주|사용자|갑)\\s*(?:은|는|이|가)[^.]{0,40}?근로자\\s*에게");
const COPY_POSITIVE_PATTERN = new RegExp("근로자\\s*에게\\s*[^.]{0,20}?(?:교부|내어\\s*준|전달|지급|제공)\\s*(?:한다|함|하였다|했다|하기로\\s*한다)|(?:교부|내어\\s*준|전달)\\s*(?:한다|함|하였다|했다)[^.]{0,10}?근로자");
const COPY_HINT_PATTERN = new RegExp("교부|사본|근로자\\s*에게\\s*(?:1부|한\\s*부)");
const COPY_REFUSAL_PATTERN = new RegExp("교부\\s*(?:를|는)?\\s*하지|교부하지|교부\\s*안|미교부|교부\\s*불가|교부(?:할|하는)?\\s*의무(?:는|가)?\\s*없|(?:주|제공하|전달하)지\\s*(?:않|아니)");
const ABSENT_ONLY_PATTERN = new RegExp("^(?:주휴일|휴일|연차\\s*유급\\s*휴가|연차|임금\\s*지급\\s*방법|지급\\s*방법|임금\\s*지급일|지급일|근무\\s*장소|업무(?:의)?\\s*내용)?\\s*(?:은|는|:)?\\s*(?:없음|없다|없습니다|해당\\s*(?:사항\\s*)?없음|미부여|미지정|미기재)\\s*\\.?$");
const UNDECIDED_ONLY_PATTERN = new RegExp("^(?:주휴일|휴일|연차\\s*유급\\s*휴가|연차|임금\\s*지급\\s*방법|지급\\s*방법|임금\\s*지급일|지급일|근무\\s*장소|업무(?:의)?\\s*내용)?\\s*(?:은|는|:)?\\s*(?:미정|추후\\s*\\S*|협의|추후\\s*협의|협의\\s*(?:후|하여)?\\s*(?:결정|정함)|결정\\s*예정|정하지\\s*않음)\\s*\\.?$");
const ANNUAL_GRANT_PATTERN = new RegExp("부여|발생|사용할\\s*수|근로기준법|제\\s*60\\s*조|법정|법에\\s*따");
const DAYS = "월화수목금토일";

export interface CriteriaRule {
  rule_code: string;
  check_condition: string;
  category: string;
  level: Level | null;
  legal_basis: string;
  recommended_action: string;
}
export interface CriteriaSummary {
  name: string; version: string; base_year: number | null;
  required_items: string[]; min_wage_current: number | null; min_wage_next: number | null;
  min_wage_next_year: number | null; min_wage_next_dropped: boolean;
  legal_basis: string[]; rules: CriteriaRule[];
}
export interface Facts {
  daily_span_minutes: number | null; break_stated: boolean; break_minutes: number | null;
  daily_work_hours: number | null; work_days_per_week: number | null;
  weekly_hours: number | null; weekly_15_or_more: boolean | null;
  wage_type: string; wage_amount: number | null; hourly_wage: number | null; hourly_basis: string;
  contract_start_date: string; contract_start_year: number | null; contract_end_date: string;
  base_year: number | null; applicable_min_wage: number | null; applicable_min_wage_year: number | null;
  next_min_wage: number | null; next_min_wage_start: string; continues_into_next_year: boolean | null;
  notes: string[];
}
export interface Finding extends CriteriaRule {
  title: string; hit: boolean | null; reason: string;
  contract_value: string; criteria_value: string; clause: string;
}
export interface EngineResult {
  level: Level | null; min_level: Level | null; is_contract: boolean; findings: Finding[]; hit_codes: string[];
  undetermined_codes: string[]; missing_items: string[]; criteria_problems: string[];
  facts: Facts; criteria: CriteriaSummary;
}
export interface CrossCheck {
  status: "match" | "mismatch" | "partial" | "unavailable"; undetermined: string[];
  agent_level: Level | null; engine_level: Level | null; level_match: boolean;
  agent_codes: string[]; agent_unlinked: string[]; agent_only: string[]; engine_only: string[]; agent_on_undetermined: string[];
}
export interface Review {
  review_level: Level | null; summary: string; matched_rules: string[]; missing_items: string[];
  risky_clauses: string[]; confirmed_items: string[]; recommendations: string[];
}
export interface ResultCard extends Finding { source: "agent" | "engine" | "both" }
export interface FinalView {
  incomplete: boolean; agent_summary: string; disputed: ResultCard[];
  level: Level | null; summary: string; cards: ResultCard[]; recommendations: string[];
  requests: string[]; requests_missing: string[]; confirmed_items: string[]; missing_items: string[];
  pending: Finding[]; disagree: boolean;
}
export type RuleCheck = [boolean | null, string, string, string];

export function is_blank(value: unknown): boolean {
  if (value == null) return true;
  if (typeof value === "string") return EMPTY_MARKERS.has(value.trim().toLowerCase());
  return Array.isArray(value) ? value.every(is_blank) : false;
}
export function first(value: unknown, fallback: unknown = ""): unknown {
  if (Array.isArray(value)) return value.find(item => !is_blank(item)) ?? fallback;
  return is_blank(value) ? fallback : value;
}
export function as_list(value: unknown): unknown[] {
  if (value == null) return [];
  return (Array.isArray(value) ? value : [value]).filter(item => !is_blank(item));
}
// Python의 bool 문자열 표기를 유지합니다.
const stringValue = (value: unknown): string => typeof value === "boolean" ? (value ? "True" : "False") : String(value);
export function text(value: unknown): string { return as_list(value).map(item => stringValue(item).trim()).join(", "); }
export function consistent<T>(value: unknown, parse: (item: unknown) => T | null): T | null {
  if (Array.isArray(value)) {
    const parsed = value.filter(item => !is_blank(item)).map(parse);
    if (!parsed.length || parsed.includes(null)) return null;
    const values = new Set(parsed);
    return values.size === 1 ? parsed[0] : null;
  }
  return is_blank(value) ? null : parse(value);
}
export function parse_number(raw: unknown): number | null {
  if (typeof raw === "boolean") return null;
  if (typeof raw === "number") return raw;
  const s = String(raw).replace(/[, ]/g, "");
  const match = /\d+(?:\.\d+)?/.exec(s);
  if (!match) return null;
  return Number(match[0]) * (s[match.index + match[0].length] === "만" ? 10000 : 1);
}
export function to_number(value: unknown): number | null { return consistent(value, parse_number); }
export function amount_candidates(value: unknown): Set<number> {
  const found = new Set<number>();
  for (const item of as_list(value)) {
    if (typeof item === "boolean" || is_blank(item)) continue;
    if (typeof item === "number") { found.add(item); continue; }
    const s = String(item).replace(new RegExp(DATE_PATTERN.source, "g"), " ").replace(new RegExp(MONTH_PATTERN.source, "g"), " ");
    for (const match of s.matchAll(/(?<![\d,.])(\d[\d,]*(?:\.\d+)?)\s*(만|천)?(?![\d,.])(?!\s*[년월일시분주회개세])/g)) {
      const number = Number(match[1].replace(/,/g, "")) * (match[2] === "만" ? 10000 : match[2] === "천" ? 1000 : 1);
      if (number >= 1000) found.add(number);
    }
  }
  return found;
}
export function parse_bool(raw: unknown): boolean | null {
  if (typeof raw === "boolean") return raw;
  const s = String(raw).trim().toLowerCase();
  if (["true", "예", "yes", "y", "o", "있음", "1", "서명", "서명함"].includes(s)) return true;
  if (["false", "아니오", "아니요", "no", "n", "x", "없음", "0", "서명 없음"].includes(s)) return false;
  return null;
}
export function to_bool(value: unknown): boolean | null { return consistent(value, parse_bool); }
const dateFromParts = (year: number, month: number, day: number): Date | null => {
  const result = new Date(0);
  result.setUTCFullYear(year, month - 1, day);
  result.setUTCHours(0, 0, 0, 0);
  return year >= 1 && result.getUTCFullYear() === year && result.getUTCMonth() === month - 1 && result.getUTCDate() === day ? result : null;
};
export function dates_in(value: unknown): Set<Date> {
  const found = new Map<number, Date>();
  for (const item of as_list(value)) for (const match of String(item).matchAll(new RegExp(DATE_PATTERN.source, "g"))) {
    const date = dateFromParts(Number(match[1]), Number(match[2]), Number(match[3]));
    if (date) found.set(date.getTime(), date);
  }
  return new Set(found.values());
}
export type DateCandidate = Date | ["invalid", string] | ["month", number, number];
export function date_candidates(value: unknown): Set<DateCandidate> {
  const found = new Map<string, DateCandidate>();
  for (const item of as_list(value)) {
    const s = String(item);
    for (const match of s.matchAll(new RegExp(DATE_PATTERN.source, "g"))) {
      const candidate: DateCandidate = dateFromParts(Number(match[1]), Number(match[2]), Number(match[3])) ?? ["invalid", match[0]];
      found.set(JSON.stringify(candidate), candidate);
    }
    const rest = s.replace(new RegExp(DATE_PATTERN.source, "g"), " ");
    for (const match of rest.matchAll(new RegExp(MONTH_PATTERN.source, "g"))) {
      const candidate: DateCandidate = ["month", Number(match[1]), Number(match[2])];
      found.set(JSON.stringify(candidate), candidate);
    }
  }
  return new Set(found.values());
}
export function to_date(value: unknown): Date | null {
  const dates = dates_in(value);
  return dates.size === 1 ? [...dates][0] : null;
}
export function to_year(value: unknown): number | null {
  const years = new Set(as_list(value).flatMap(item => [...String(item).matchAll(/(20\d{2})/g)].map(match => Number(match[1]))));
  return years.size === 1 ? [...years][0] : null;
}
export function date_ambiguous(value: unknown): boolean {
  const candidates = date_candidates(value);
  if (candidates.size > 1 || [...candidates].some(c => Array.isArray(c) && c[0] === "invalid")) return true;
  const joined = as_list(value).map(stringValue).join(" ");
  if (/또는|혹은/.test(joined)) return true;
  return [...joined.matchAll(new RegExp(RENEWAL_PATTERN.source, "g"))].some(match => {
    const tail = joined.slice(match.index + match[0].length, match.index + match[0].length + 15);
    return !RENEWAL_DENIED_PATTERN.test(tail.slice(0, 8)) || /(?:않|아니)\S{0,3}\s*(?:경우|때|면)/.test(tail);
  });
}
export function normalize_level(value: unknown): Level | null {
  const s = String(first(value)).trim().toLowerCase().replace(/ /g, "_");
  const aliases: Record<string, Level> = { safe: "safe", 안심: "safe", 안전: "safe", check_needed: "check_needed", 확인_필요: "check_needed", 확인필요: "check_needed", 주의: "check_needed", caution: "check_needed", risky: "risky", 위험: "risky", danger: "risky" };
  return aliases[s] ?? null;
}
export function more_severe(...levels: (string | null | undefined)[]): Level | null {
  const known = levels.filter((level): level is Level => LEVELS.includes(level as Level));
  return known.reduce<Level | null>((result, level) => result == null || LEVEL_SEVERITY[level] > LEVEL_SEVERITY[result] ? level : result, null);
}
export function less_severe(a: Level | null, b: Level | null): Level | null {
  return a === null || b === null || !LEVELS.includes(a) || !LEVELS.includes(b) ? null : LEVEL_SEVERITY[a] <= LEVEL_SEVERITY[b] ? a : b;
}
export function won(value: number | null | undefined): string {
  if (value == null) return "-";
  const integer = Math.abs(value - Math.round(value)) < 1e-9;
  return (integer ? value : Math.floor(value * 100) / 100).toLocaleString("en-US", { minimumFractionDigits: integer ? 0 : 2, maximumFractionDigits: integer ? 0 : 2 }) + "원";
}
export function parse_times(value: unknown): number[] {
  const minutes: number[] = [];
  for (const match of text(value).matchAll(/(오전|오후)?\s*(\d{1,2})(?::(\d{2})|\s*시(?!간)\s*(?:(\d{1,2})\s*분)?)/g)) {
    let hour = Number(match[2]);
    const minute = Number(match[3] || match[4] || 0);
    if (match[1] === "오후" && hour < 12) hour += 12;
    if (match[1] === "오전" && hour === 12) hour = 0;
    if (hour <= 24 && minute < 60) minutes.push(hour * 60 + minute);
  }
  return minutes;
}
const moduloDay = (value: number) => ((value % 1440) + 1440) % 1440;
const roundEven = (value: number): number => {
  const floor = Math.floor(value);
  return value - floor === 0.5 ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(value);
};
export function break_intervals(value: unknown): [number, number][] {
  const times = parse_times(text(value).replace(/\([^)]*\)/g, " "));
  if (times.length < 2 || times.length % 2) return [];
  return Array.from({ length: times.length / 2 }, (_, i) => [times[i * 2], times[i * 2 + 1]]);
}
export function parse_break(value: unknown): [boolean, number | null] {
  const s = text(value);
  if (!s) return [false, null];
  const core = s.replace(/\([^)]*\)/g, " ");
  const notesInBrackets = [...s.matchAll(/\(([^)]*)\)/g)].map(match => match[1]).join(" ");
  if (parse_times(notesInBrackets).length || BREAK_ALTERNATIVE_PATTERN.test(notesInBrackets) || BREAK_BY_DAY_PATTERN.test(notesInBrackets)) return [true, null];
  if (BREAK_ALTERNATIVE_PATTERN.test(core)) return [true, null];
  const times = parse_times(core);
  if (times.length >= 2) {
    const intervals = break_intervals(core);
    if (!intervals.length || (intervals.length > 1 && BREAK_BY_DAY_PATTERN.test(core))) return [true, null];
    const spans = intervals.map(([start, end]) => [start, start + moduloDay(end - start)]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (spans.slice(1).some((next, i) => next[0] < spans[i][1])) return [true, null];
    return [true, spans.reduce((total, [start, end]) => total + end - start, 0)];
  }
  const hours = /(\d+(?:\.\d+)?)\s*시간/.exec(core);
  const mins = /(\d+)\s*분/.exec(core);
  if (hours || mins) return [true, roundEven(Number(hours?.[1] ?? 0) * 60 + Number(mins?.[1] ?? 0))];
  return [true, NONE_PATTERN.test(core) ? 0 : null];
}
export function parse_work_days(value: unknown): number | null {
  const s = text(value);
  if (!s) return null;
  const weekly = /주\s*(\d)\s*일/.exec(s);
  if (weekly) return Number(weekly[1]);
  const days = new Set<string>();
  for (const match of s.matchAll(/([월화수목금토일])(?:요일)?\s*[~\-–]\s*([월화수목금토일])(?:요일)?/g)) {
    let index = DAYS.indexOf(match[1]);
    const last = DAYS.indexOf(match[2]);
    while (true) { days.add(DAYS[index]); if (index === last) break; index = (index + 1) % 7; }
  }
  for (const match of s.matchAll(/(?<![가-힣0-9])([월화수목금토일])(?:요일)?(?![가-힣])/g)) days.add(match[1]);
  return days.size || null;
}
export function category_level(value: unknown): Level | null {
  const s = String(first(value)).replace(/ /g, "");
  if (s.includes("위험") || s.toLowerCase().includes("risky")) return "risky";
  return s.includes("확인") || s.toLowerCase().includes("check") ? "check_needed" : null;
}
export function cell(column: unknown, index: number): unknown {
  const values = Array.isArray(column) ? column : [column];
  return index < values.length ? values[index] : "";
}
const isRecord = (value: unknown): value is ExtractedData => typeof value === "object" && value !== null && !Array.isArray(value);
export function criteria_rows(criteria: ExtractedData): ExtractedData[] {
  const columns = ["rule_code", "check_condition", "category", "legal_basis", "recommended_action"];
  const raw = criteria.check_rules;
  if (Array.isArray(raw) && raw.length && raw.every(isRecord)) return raw;
  if (isRecord(raw)) {
    const length = Math.max(...columns.map(c => Array.isArray(raw[c]) ? raw[c].length : Number(c in raw)));
    return Array.from({ length }, (_, index) => Object.fromEntries(columns.map(c => [c, cell(raw[c], index)])));
  }
  return [];
}
export function criteria_rules(criteria: ExtractedData): CriteriaRule[] {
  return criteria_rows(criteria).flatMap(row => {
    const code = String(first(row.rule_code)).trim();
    return code ? [{ rule_code: code, check_condition: text(row.check_condition), category: text(row.category), level: category_level(row.category), legal_basis: text(row.legal_basis), recommended_action: text(row.recommended_action) }] : [];
  });
}
export function criteria_base_year(criteria: ExtractedData): number | null {
  for (const key of ["criteria_version", "criteria_name"]) {
    const s = text(criteria[key]);
    const match = /기준일\D{0,5}(20\d{2})/.exec(s) || /(20\d{2})/.exec(s);
    if (match) return Number(match[1]);
  }
  return null;
}
export function summarize_criteria(criteria: ExtractedData): CriteriaSummary {
  const baseYear = criteria_base_year(criteria);
  const nextRaw = to_number(criteria[NEXT_MIN_WAGE_FIELD]);
  const nextOk = baseYear !== null && baseYear + 1 === NEXT_MIN_WAGE_YEAR;
  return { name: text(criteria.criteria_name), version: text(criteria.criteria_version), base_year: baseYear, required_items: as_list(criteria.required_items).map(stringValue), min_wage_current: to_number(criteria.min_wage_hourly), min_wage_next: nextOk ? nextRaw : null, min_wage_next_year: nextOk ? NEXT_MIN_WAGE_YEAR : null, min_wage_next_dropped: nextRaw !== null && !nextOk, legal_basis: as_list(criteria.legal_basis).map(stringValue), rules: criteria_rules(criteria) };
}
export function criteria_problems(criteria: ExtractedData, source_codes: ReadonlySet<string> | null = null): string[] {
  const summary = summarize_criteria(criteria);
  const codes = summary.rules.map(rule => rule.rule_code);
  const problems: string[] = [];
  if (!codes.length) problems.push("점검 규칙 표를 읽지 못했습니다");
  const blank = criteria_rows(criteria).filter(row => !String(first(row.rule_code)).trim()).length;
  if (blank) problems.push(`규칙 코드가 비어 있는 행이 ${blank}개 있습니다`);
  const duplicates = [...new Set(codes.filter(code => codes.filter(item => item === code).length > 1))].sort();
  if (duplicates.length) problems.push("규칙 코드가 중복됐습니다: " + duplicates.join(", "));
  if (source_codes !== null) {
    const missing = [...source_codes].filter(code => !codes.includes(code)).sort();
    const extra = [...new Set(codes)].filter(code => !source_codes.has(code)).sort();
    if (missing.length) problems.push("기준서 원문에 있는데 추출 결과에서 빠진 규칙: " + missing.join(", "));
    if (extra.length) problems.push("기준서 원문에 없는 규칙 코드가 추출됐습니다: " + extra.join(", "));
  }
  if (summary.min_wage_current === null) problems.push("최저임금 금액을 읽지 못했습니다");
  if (summary.base_year === null) problems.push("기준서의 기준 연도를 읽지 못했습니다");
  return problems;
}
export function apply_source_table(criteria: ExtractedData, source: SourceTable | null): [ExtractedData, string[]] {
  if (!source || !Object.keys(source).length) return [criteria, []];
  const repaired: string[] = [];
  const rows = criteria_rows(criteria).map(originalRow => {
    const row = { ...originalRow };
    const code = String(first(row.rule_code)).trim();
    for (const field of SOURCE_FIELDS) {
      const original = source[code]?.[field] ?? "";
      const extracted = condition_shape(text(row[field])), full = condition_shape(original);
      if (extracted && full.length > extracted.length && full.startsWith(extracted)) {
        row[field] = original;
        if (!repaired.includes(code)) repaired.push(code);
      }
    }
    return row;
  });
  return repaired.length ? [{ ...criteria, check_rules: rows }, repaired] : [criteria, []];
}
export function condition_shape(sentence: string, base_year: number | null = null, allow_amounts = false): string {
  let s = sentence.replace(/\s+/g, "");
  if (allow_amounts) {
    s = s.replace(/\d{1,3}(?:,\d{3})+원|\d{4,}원/g, "AMOUNT원");
    if (base_year) s = s.split(`${base_year + 1}년`).join("NEXTYEAR년").split(`${base_year}년`).join("BASEYEAR년");
  }
  return s.replace(/[^\p{L}\p{N}]+/gu, "");
}
export function condition_supported(rule: Pick<CriteriaRule, "rule_code" | "check_condition">, base_year: number | null = null): [boolean, string] {
  const known = KNOWN_CONDITIONS[rule.rule_code];
  if (!known) return [false, "코드에 판정 로직이 없는 규칙입니다. 평가 에이전트의 판단을 따릅니다."];
  if (!rule.check_condition) return [false, "기준서에서 이 규칙의 점검 조건을 읽지 못해 코드로 판단하지 않습니다."];
  if (condition_shape(known[0], KNOWN_BASE_YEAR, known[1]) !== condition_shape(rule.check_condition, base_year, known[1])) return [false, "기준서의 점검 조건 문장이 코드가 구현한 조건과 정확히 같지 않아 코드로 판단하지 않습니다. 평가 에이전트의 판단을 따릅니다."];
  return [true, ""];
}
export function required_items_supported(criteria: ExtractedData): boolean {
  const items = as_list(criteria.required_items).map(item => stringValue(item).replace(/\s+/g, ""));
  if (!items.length) return true;
  const keys = Object.values(REQUIRED_TERM_KEYS);
  return keys.every(group => items.some(item => group.some(key => item.includes(key)))) && items.every(item => keys.some(group => group.some(key => item.includes(key))));
}

const round4 = (value: number) => Number(value.toFixed(4));
const generalNumber = (value: number) => Number(value.toPrecision(6)).toString();
const isoDate = (value: Date | null) => value?.toISOString().slice(0, 10) ?? "";
export function compute_facts(contract: ExtractedData, criteria: ExtractedData): Facts {
  const notes: string[] = [], summary = summarize_criteria(criteria);
  let startTimes = parse_times(contract.work_start_time), endTimes = parse_times(contract.work_end_time);
  if (startTimes.length === 2 && !endTimes.length) { endTimes = startTimes.slice(1); startTimes = startTimes.slice(0, 1); }
  else if (endTimes.length === 2 && !startTimes.length) { startTimes = endTimes.slice(0, 1); endTimes = endTimes.slice(1); }
  let span: number | null = null;
  if (startTimes.length === 1 && endTimes.length === 1) span = moduloDay(endTimes[0] - startTimes[0]) || null;
  else if (startTimes.length || endTimes.length) notes.push("소정근로 시각이 여러 개라 어느 시작과 종료가 짝인지 알 수 없어 근로시간을 계산하지 않았습니다.");
  else notes.push("소정근로 시작·종료 시각을 읽지 못해 근로시간을 계산하지 못했습니다.");
  const [breakStated, breakMinutes] = parse_break(contract.break_time);
  let daily: number | null = null;
  if (span !== null) {
    const offsets = break_intervals(contract.break_time).map(([start, end]) => [moduloDay(start - startTimes[0]), moduloDay(start - startTimes[0]) + moduloDay(end - start)]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const outside = offsets.some(([, end]) => end > span!);
    const overlap = offsets.slice(1).some((next, i) => next[0] < offsets[i][1]);
    if (breakStated && breakMinutes === null) notes.push("휴게시간 문구에서 길이를 정하지 못해(대안·겹침·짝이 맞지 않는 시각) 근로시간을 계산하지 않았습니다.");
    else if (outside) notes.push("휴게시간이 출근부터 퇴근까지의 시간 밖에 있어 근로시간을 계산하지 않았습니다.");
    else if (overlap) notes.push("휴게 구간이 서로 겹쳐 휴게 길이를 정하지 못해 근로시간을 계산하지 않았습니다.");
    else if ((breakMinutes || 0) >= span) notes.push("휴게시간이 출근부터 퇴근까지의 시간보다 길거나 같아 근로시간을 계산하지 않았습니다.");
    else daily = span - (breakMinutes || 0);
  }
  const days = parse_work_days(contract.work_days);
  let weekly: number | null = null;
  if (daily !== null && days) weekly = round4(daily * days / 60);
  else if (daily !== null) notes.push("근무일(요일 또는 주 N일)을 읽지 못해 1주 소정근로시간을 계산하지 못했습니다.");
  const wageType = text(contract.wage_type);
  let amount = to_number(contract.wage_amount);
  let hourly: number | null = null, basis = "";
  const candidates = amount_candidates(contract.wage_amount);
  if (amount === null && !is_blank(contract.wage_amount)) notes.push("임금 금액이 여러 개이거나 읽을 수 없어 어느 금액인지 정하지 못했습니다.");
  else if (candidates.size > 1) {
    notes.push("임금 금액 문구에 서로 다른 금액이 여러 개 있어 어느 금액인지 정하지 못했습니다.");
    amount = null;
  } else if (candidates.size === 1 && amount !== null) amount = [...candidates][0];
  if (amount !== null) {
    if (wageType.includes("시")) { hourly = amount; basis = "시급"; }
    else if (wageType.includes("일") && daily) { hourly = amount / (daily / 60); basis = `일급 ÷ 1일 근로시간 ${generalNumber(daily / 60)}시간`; }
    else if ((wageType.includes("월") || wageType.includes("주")) && weekly) {
      const holiday = weekly >= 15 ? Math.min(weekly / 5, 8) : 0;
      const paid = wageType.includes("월") ? (weekly + holiday) * 365 / 7 / 12 : weekly + holiday;
      basis = wageType.includes("월") ? `월급 ÷ 월 환산 ${paid.toFixed(1)}시간(주휴 포함)` : `주급 ÷ 주 ${generalNumber(paid)}시간(주휴 포함)`;
      hourly = amount / paid;
    } else notes.push("임금 구분(시급·일급·월급)과 근로시간으로 시급을 환산하지 못했습니다.");
  }
  const base = summary.base_year, currentMin = summary.min_wage_current;
  const nextMin = summary.min_wage_next;
  if (summary.min_wage_next_dropped) {
    notes.push(`기준서 기준 연도(${base === null ? "None" : base})가 Criteria Agent 스키마의 다음 해 항목(${NEXT_MIN_WAGE_FIELD})과 맞지 않아 다음 해 최저임금을 쓰지 않았습니다.`);
  }
  const startRaw = contract.contract_start_date, endRaw = contract.contract_end_date;
  const startAmbiguous = date_candidates(startRaw).size > 1, endAmbiguous = date_ambiguous(endRaw);
  const start = startAmbiguous ? null : to_date(startRaw), end = endAmbiguous ? null : to_date(endRaw);
  const startYear = startAmbiguous ? null : start?.getUTCFullYear() ?? to_year(startRaw);
  const endYear = endAmbiguous ? null : end?.getUTCFullYear() ?? to_year(endRaw);
  if (startAmbiguous) notes.push("계약 시작일이 여러 개 적혀 있어 어느 날짜인지 정하지 못했습니다.");
  let minimum: number | null = null, minimumYear: number | null = null;
  const nextStart = base ? new Date(Date.UTC(base + 1, 0, 1)) : null;
  if (base === null) notes.push("기준서의 기준 연도를 읽지 못해 적용 최저임금을 정하지 못했습니다.");
  else if (startYear === null) notes.push("계약 시작일을 읽지 못해 적용 최저임금을 정하지 못했습니다.");
  else if (startYear > base) {
    minimum = nextMin; minimumYear = base + 1;
    if (nextMin === null) notes.push(`계약이 ${base + 1}년에 시작하는데 기준서에서 그해 최저임금을 확정하지 못했습니다.`);
  } else {
    minimum = currentMin; minimumYear = base;
    if (startYear < base) notes.push(`계약 시작 연도(${startYear})가 기준서 기준 연도보다 이르지만, 현재 일하는 기간에 적용되는 ${base}년 최저임금으로 비교했습니다.`);
  }
  if (start === null && startYear !== null) notes.push(`계약 시작일은 연도(${startYear})만 읽었습니다.`);
  let continues: boolean | null;
  if (nextStart === null || (startYear !== null && base !== null && startYear > base)) continues = null;
  else if (endAmbiguous) { continues = null; notes.push("계약 종료일이 여러 개이거나 연장·갱신 조건이 붙어 있어 다음 해까지 이어지는지 판단하지 못했습니다."); }
  else if (is_blank(contract.contract_end_date)) continues = true;
  else if (end !== null) continues = end >= nextStart;
  else if (endYear !== null) continues = endYear > base!;
  else { continues = null; notes.push("계약 종료일 형식을 읽지 못해 다음 해까지 이어지는지 판단하지 못했습니다."); }
  return { daily_span_minutes: span, break_stated: breakStated, break_minutes: breakMinutes, daily_work_hours: daily === null ? null : round4(daily / 60), work_days_per_week: days, weekly_hours: weekly, weekly_15_or_more: weekly === null ? null : weekly >= 15, wage_type: wageType, wage_amount: amount, hourly_wage: hourly, hourly_basis: basis, contract_start_date: isoDate(start), contract_start_year: startYear, contract_end_date: isoDate(end), base_year: base, applicable_min_wage: minimum, applicable_min_wage_year: minimumYear, next_min_wage: nextMin, next_min_wage_start: isoDate(nextStart), continues_into_next_year: continues, notes };
}
export function check_min_wage(_contract: ExtractedData, facts: Facts): RuleCheck {
  const hourly = facts.hourly_wage, minimum = facts.applicable_min_wage, year = facts.applicable_min_wage_year;
  if (hourly === null || minimum === null) return [null, "시급 또는 적용 최저임금을 알 수 없어 판단하지 못했습니다.", won(hourly), won(minimum)];
  if (hourly < minimum) return [true, `시급 ${won(hourly)}이 계약 시작일 기준 ${year}년 최저임금 ${won(minimum)}보다 ${won(minimum - hourly)} 낮습니다.`, won(hourly), won(minimum)];
  return [false, `시급 ${won(hourly)}은 ${year}년 최저임금 ${won(minimum)} 이상입니다.`, won(hourly), won(minimum)];
}
export function classify_penalty_clauses(contract: ExtractedData): [string[], string[]] {
  const hits: string[] = [], unclear: string[] = [];
  for (const clause of as_list(contract.special_terms).map(stringValue)) {
    const negated = NEGATION_PATTERN.test(clause), employerPays = EMPLOYER_PAYS_PATTERN.test(clause);
    const statutory = STATUTORY_DEDUCTION_PATTERN.test(clause), purpose = PENALTY_PURPOSE_PATTERN.test(clause);
    const deduction = WAGE_DEDUCTION_PATTERN.test(clause), workerPays = WORKER_PAYS_PATTERN.test(clause);
    if (deduction && statutory && !purpose && !workerPays) continue;
    const clear = (deduction && purpose && !statutory) || workerPays;
    if (clear && !negated && !employerPays) hits.push(clause);
    else if (deduction || workerPays || PENALTY_HINT_PATTERN.test(clause) || RESIGN_PATTERN.test(clause)) unclear.push(clause);
  }
  return [hits, unclear];
}
export function check_penalty(contract: ExtractedData, _facts?: Facts): RuleCheck {
  void _facts;
  const [hits, unclear] = classify_penalty_clauses(contract);
  if (hits.length) return [true, `특약에 위약금·손해배상 예정·임금 공제처럼 근로자에게 불리한 조항이 ${hits.length}건 있습니다.`, `불리한 조항 ${hits.length}건`, "해당 조항 없음"];
  if (unclear.length) return [null, `퇴사·공제 관련 조항 ${unclear.length}건의 의미를 코드로 확정할 수 없어 평가 에이전트의 판단을 따릅니다.`, `확인할 조항 ${unclear.length}건`, "해당 조항 없음"];
  return [false, "위약금·손해배상·임금 공제 조항이 없습니다.", text(contract.special_terms) || "없음", "해당 조항 없음"];
}
export function field_core(value: unknown): string {
  return text(value).replace(/\([^)]*\)/g, " ").trim() || text(value);
}
export function field_state(value: unknown): "blank" | "absent" | "undecided" | "written" {
  if (is_blank(value) || !text(value)) return "blank";
  const core = field_core(value);
  if (ABSENT_ONLY_PATTERN.test(core)) return "absent";
  if (UNDECIDED_ONLY_PATTERN.test(core)) return "undecided";
  return "written";
}
export function required_missing(contract: ExtractedData, facts?: Pick<Facts, "weekly_hours"> | null): [string[], string[]] {
  const weekly = facts?.weekly_hours ?? null;
  const missing: string[] = [], unclear: string[] = [];
  const state = (field: string) => field_state(contract[field]);
  if (is_blank(contract.wage_amount)) missing.push("임금(금액)");
  for (const [key, label] of [["wage_type", "임금(시급·일급·월급 구분)"], ["wage_payment_date", "임금지급일"], ["wage_payment_method", "임금지급방법"]]) if (state(key) !== "written") missing.push(label);
  if (is_blank(contract.work_start_time) || is_blank(contract.work_end_time)) missing.push("소정근로시간");
  for (const [key, label] of [["weekly_holiday", "휴일(주휴일)"], ["annual_leave_clause", "연차유급휴가"]]) {
    const current = state(key);
    if (current === "blank" || current === "undecided") missing.push(label);
    else if (current === "absent") {
      if (weekly === null) unclear.push(label);
      else if (weekly >= 15) missing.push(label);
    } else if (key === "annual_leave_clause" && UNDECIDED_PATTERN.test(field_core(contract[key])) && !ANNUAL_GRANT_PATTERN.test(field_core(contract[key]))) unclear.push(label);
  }
  for (const [key, label] of [["workplace", "근무장소"], ["job_description", "업무의 내용"]]) if (state(key) !== "written") missing.push(label);
  if (is_blank(contract.contract_start_date)) missing.push("근로계약기간");
  return [missing, unclear];
}
export function check_required_terms(contract: ExtractedData, facts: Facts): RuleCheck {
  const [missing, unclear] = required_missing(contract, facts);
  if (missing.length) return [true, "계약서에 적혀 있지 않거나 정해지지 않은 필수 기재사항: " + missing.join(", "), missing.join(", ") + " 없음", "6개 항목 모두 기재"];
  if (unclear.length) return [null, "1주 소정근로시간을 계산하지 못해 '" + unclear.join(", ") + "'의 '해당 없음' 표기가 맞는지 확정하지 못했습니다.", unclear.join(", ") + " 확인 필요", "6개 항목 모두 기재"];
  return [false, "필수 기재사항이 모두 적혀 있습니다.", "모두 기재", "6개 항목 모두 기재"];
}
export function check_break(contract: ExtractedData, facts: Facts): RuleCheck {
  const span = facts.daily_span_minutes;
  if (span === null || facts.daily_work_hours === null) return [null, "근로시간을 알 수 없거나 앞뒤가 맞지 않아 휴게시간 기준을 판단하지 못했습니다.", text(contract.break_time) || "-", "-"];
  const rest = facts.break_minutes || 0, work = span - rest, required = work >= 480 ? 60 : work >= 240 ? 30 : 0;
  const current = `근로 ${generalNumber(work / 60)}시간, 휴게 ${rest}분` + (facts.break_stated ? "" : "(미기재)");
  if (!required) return [false, "1일 근로시간이 4시간 미만이라 해당 없습니다.", current, "4시간 미만 해당 없음"];
  const standard = `휴게 ${required}분 이상`;
  if (rest >= required) return [false, `1일 근로시간 ${generalNumber(work / 60)}시간에 휴게 ${rest}분이 있습니다.`, current, standard];
  if (work === 240 && rest === 0) {
    const breakText = text(contract.break_time);
    const explicit = EXPLICIT_NO_BREAK_PATTERN.test(breakText) && !NO_REQUEST_PATTERN.test(breakText);
    const start = to_date(facts.contract_start_date);
    const exceptionStart = isoDate(BREAK_EXCEPTION_START);
    if (explicit && start !== null && start >= BREAK_EXCEPTION_START) return [false, `정확히 4시간 근무이고 근로자가 휴게 미사용을 명시적으로 요청해 ${exceptionStart}부터의 예외에 해당합니다.`, current, standard];
    const reason = explicit ? `근로자의 휴게 미사용 요청이 적혀 있지만, 예외는 ${exceptionStart}부터 적용됩니다. 그 전 근무에는 휴게 30분이 필요합니다.` : `1일 근로시간 4시간에는 휴게 30분이 필요합니다. ${exceptionStart}부터는 근로자가 명시적으로 요청하면 휴게 없이 일할 수 있으나, 계약서에 그런 요청이 적혀 있지 않습니다.`;
    return [true, reason, current, standard];
  }
  return [true, `1일 근로시간 ${generalNumber(work / 60)}시간에는 ${standard}이 필요한데 휴게가 ${rest}분입니다.`, current, standard];
}
export function holiday_specified(contract: ExtractedData): boolean | null {
  const current = field_state(contract.weekly_holiday);
  if (["blank", "absent", "undecided"].includes(current)) return false;
  return /[월화수목금토일]\s*요일|(?<![가-힣\d])[월화수목금토일](?![가-힣])/.test(field_core(contract.weekly_holiday)) ? true : null;
}
export function check_weekly_holiday(contract: ExtractedData, facts: Facts): RuleCheck {
  const weekly = facts.weekly_hours, current = text(contract.weekly_holiday) || "(비어 있음)", standard = "주 15시간 이상이면 주휴일 기재";
  const specified = holiday_specified(contract);
  if (specified) return [false, "주휴일이 적혀 있습니다.", current, standard];
  if (weekly !== null && weekly < 15) return [false, `1주 소정근로시간이 ${generalNumber(weekly)}시간으로 15시간 미만이라 해당 없습니다.`, current, standard];
  if (specified === null) return [null, "주휴일 문구에 요일이 없어 주휴일이 정해졌는지 코드로 확정할 수 없습니다.", current, standard];
  if (weekly === null) return [null, "1주 소정근로시간을 계산하지 못했는데 주휴일이 정해져 있지 않습니다. 15시간 이상이면 해당합니다.", current, standard];
  return [true, `1주 소정근로시간이 ${generalNumber(weekly)}시간으로 15시간 이상인데 주휴일이 정해져 있지 않습니다.`, current, standard];
}
export function copy_clause_status(contract: ExtractedData): "ok" | "missing" | "negated" | "unclear" {
  const clause = text(contract.copy_delivery_clause);
  if (!clause) return "missing";
  if (COPY_REFUSAL_PATTERN.test(clause)) return "negated";
  const positive = COPY_POSITIVE_PATTERN.exec(clause);
  if (positive) {
    const rest = clause.slice(positive.index + positive[0].length).split(/[.!?\n]/, 1)[0];
    return NEGATION_PATTERN.test(rest) ? "unclear" : "ok";
  }
  return COPY_HINT_PATTERN.test(clause) ? "unclear" : "missing";
}
export function check_sign_copy(contract: ExtractedData, _facts?: Facts): RuleCheck {
  void _facts;
  const signed = to_bool(contract.is_signed), copy = copy_clause_status(contract), problems: string[] = [];
  if (copy === "unclear" && signed === true) return [null, "교부 문구의 뜻을 코드로 확정할 수 없어 평가 에이전트의 판단을 따릅니다.", "서명 있음, 교부 문구 확인 필요", "양측 서명 + 교부 문구"];
  if (signed !== true) problems.push("사업주·근로자 서명 확인 안 됨");
  if (copy === "missing" || copy === "negated") problems.push(copy === "missing" ? "근로자에게 계약서를 교부한다는 문구 없음" : "교부하지 않는다는 취지의 문구");
  const copyText = { ok: "있음", missing: "없음", negated: "부정형", unclear: "확인 필요" }[copy];
  const current = `서명 ${signed ? "있음" : "없음/불명"}, 교부 문구 ${copyText}`;
  return problems.length ? [true, problems.join(", ") + ".", current, "양측 서명 + 교부 문구"] : [false, "양측 서명과 교부 문구가 있습니다.", current, "양측 서명 + 교부 문구"];
}
export function check_min_wage_next(_contract: ExtractedData, facts: Facts): RuleCheck {
  const nextMin = facts.next_min_wage, hourly = facts.hourly_wage, base = facts.base_year;
  if (base === null) return [null, "기준서의 기준 연도를 읽지 못해 판단하지 못했습니다.", won(hourly), "-"];
  const year = base + 1, standard = `${year}년 최저임금 ${won(nextMin)}`;
  if (facts.contract_start_year !== null && facts.contract_start_year > base) return [false, `계약이 ${year}년에 시작해 최저임금 규칙에서 이미 ${year}년 기준으로 비교했습니다.`, won(hourly), standard];
  if (facts.continues_into_next_year === null) return [null, "계약이 다음 해까지 이어지는지 판단하지 못했습니다.", won(hourly), standard];
  if (!facts.continues_into_next_year) return [false, `계약이 ${year}년 1월 1일 전에 끝나 해당 없습니다.`, won(hourly), standard];
  if (nextMin === null || hourly === null) return [null, `시급 또는 ${year}년 최저임금을 알 수 없어 판단하지 못했습니다.`, won(hourly), standard];
  if (hourly < nextMin) return [true, `계약이 ${year}년 이후까지 이어지는데(${facts.contract_end_date || "종료일 없음"}) 시급 ${won(hourly)}이 ${standard}보다 낮습니다.`, won(hourly), standard];
  return [false, `시급 ${won(hourly)}이 ${standard} 이상입니다.`, won(hourly), standard];
}
export const RULE_CHECKS: Record<string, (contract: ExtractedData, facts: Facts) => RuleCheck> = {
  LABOR_MIN_WAGE: check_min_wage, LABOR_PENALTY: check_penalty, LABOR_REQUIRED_TERMS: check_required_terms,
  LABOR_BREAK: check_break, LABOR_WEEKLY_HOLIDAY: check_weekly_holiday, LABOR_SIGN_COPY: check_sign_copy, LABOR_MIN_WAGE_NEXT: check_min_wage_next,
};
export function looks_like_contract(contract: ExtractedData): boolean { return CORE_FIELDS.filter(field => !is_blank(contract[field])).length >= 3; }
export function overall_level(findings: Pick<Finding, "hit" | "level">[]): Level | null {
  const hits = findings.filter(f => f.hit), pending = findings.filter(f => f.hit === null);
  if (hits.some(f => f.level === "risky")) return "risky";
  if (hits.some(f => f.level === null)) return null;
  if (pending.some(f => f.level !== "check_needed")) return null;
  if (hits.length) return "check_needed";
  return pending.length || !findings.length ? null : "safe";
}
export function confirmed_min_level(findings: Pick<Finding, "hit" | "level">[]): Level | null {
  return more_severe(...findings.filter(f => f.hit).map(f => f.level));
}
export function missing_items(contract: ExtractedData, facts: Facts): string[] {
  const [items] = required_missing(contract, facts);
  if (!facts.break_stated) items.push("휴게시간");
  if (to_bool(contract.is_signed) !== true) items.push("사업주·근로자 서명");
  if (["missing", "negated"].includes(copy_clause_status(contract))) items.push("계약서 교부 문구");
  return items;
}
export function evaluate(contract: ExtractedData, criteria: ExtractedData, facts: Facts | null = null, source_codes: ReadonlySet<string> | null = null): EngineResult {
  facts = facts ?? compute_facts(contract, criteria);
  const summary = summarize_criteria(criteria);
  const problems = criteria_problems(criteria, source_codes);
  const findings = summary.rules.map(rule => {
    const code = rule.rule_code;
    let [supported, why] = condition_supported(rule, summary.base_year);
    if (supported && code === "LABOR_REQUIRED_TERMS" && !required_items_supported(criteria)) { supported = false; why = "기준서의 필수 기재사항 목록이 코드가 아는 6가지와 달라 코드로 판단하지 않습니다."; }
    const [hit, reason, current, standard]: RuleCheck = !supported ? [null, why, "-", "-"] : rule.level === null ? [null, "기준서에서 이 규칙의 분류(위험/확인 필요)를 읽지 못했습니다.", "-", "-"] : RULE_CHECKS[code](contract, facts);
    const source = RULE_SOURCE_FIELDS[code];
    return { ...rule, title: RULE_TITLES[code] ?? code, hit, reason, contract_value: current, criteria_value: standard, clause: source ? as_list(contract[source]).map(stringValue).join(" / ") : "" };
  });
  const isContract = looks_like_contract(contract);
  return { level: isContract && !problems.length ? overall_level(findings) : null, min_level: isContract ? confirmed_min_level(findings) : null, is_contract: isContract, findings, hit_codes: findings.filter(f => f.hit).map(f => f.rule_code), undetermined_codes: findings.filter(f => f.hit === null).map(f => f.rule_code), missing_items: missing_items(contract, facts), criteria_problems: problems, facts, criteria: summary };
}
export function rule_codes_in(values: unknown): Set<string> {
  return new Set(as_list(values).map(stringValue).join(" ").match(/[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+/g) ?? []);
}
export function cross_check(agent_level: Level | null, agent_rules: unknown, engine: EngineResult): CrossCheck {
  const all = new Set(engine.findings.map(f => f.rule_code));
  const decided = new Set([...all].filter(code => !engine.undetermined_codes.includes(code)));
  const agent = new Set([...rule_codes_in(agent_rules)].filter(code => all.has(code)));
  const unlinked = as_list(agent_rules).flatMap(item => stringValue(item).split(/[;\n]/)).map(part => part.trim()).filter(part => part && ![...rule_codes_in([part])].some(code => all.has(code)));
  const computed = new Set(engine.hit_codes);
  const agentOnly = [...agent].filter(code => decided.has(code) && !computed.has(code)).sort();
  const engineOnly = [...computed].filter(code => !agent.has(code)).sort();
  const status = agent_level === null ? "unavailable" : agentOnly.length || engineOnly.length || (engine.level !== null && agent_level !== engine.level) ? "mismatch" : engine.level === null ? "partial" : "match";
  return { status, agent_level, engine_level: engine.level, level_match: status === "match", agent_codes: [...agent].sort(), agent_unlinked: unlinked, agent_only: agentOnly, engine_only: engineOnly, agent_on_undetermined: [...agent].filter(code => !decided.has(code)).sort(), undetermined: [...all].filter(code => !decided.has(code)).sort() };
}
export function compose_summary(engine: EngineResult, hits: Pick<Finding, "title" | "level">[], level: Level | null, incomplete: boolean, agent_level: Level | null = null, disputed: Pick<Finding, "title">[] | null = null): string {
  const facts = engine.facts, hourly = facts.hourly_wage, minimum = facts.applicable_min_wage;
  const sentences: string[] = [];
  if (hourly !== null && minimum !== null) {
    const start = facts.contract_start_date || String(facts.contract_start_year || "시작일 미상");
    const comparison = hourly < minimum ? `보다 ${won(minimum - hourly)} 낮습니다` : " 이상입니다";
    sentences.push(`시급 ${won(hourly)}은 계약 시작일(${start}) 기준 최저임금 ${won(minimum)}${comparison}.`);
  } else sentences.push("시급 또는 적용 최저임금을 확인하지 못했습니다.");
  if (hits.length) sentences.push("해당한 규칙: " + hits.map(f => f.title).join(", ") + ".");
  else if (level === "safe") sentences.push("점검 기준서의 규칙에 해당하는 항목이 없습니다.");
  if (incomplete) sentences.push(level === null ? "판단하지 못한 규칙이 있어 등급을 확정하지 않았습니다." : `판단하지 못한 규칙이 있어 최소 '${LEVEL_LABELS[level]}'입니다.`);
  if (disputed?.length) sentences.push("평가 에이전트가 지적한 " + disputed.map(f => f.title).join(", ") + " 항목은 계약서 값으로 계산하면 해당하지 않아 등급에 넣지 않았습니다.");
  if (agent_level !== null && level !== null && agent_level !== level) {
    const basis = LEVEL_SEVERITY[agent_level] < LEVEL_SEVERITY[level] ? "해당 규칙의 기준서 분류에 맞춰" : hits.length ? "근거 규칙의 기준서 분류에 맞춰" : disputed?.length ? "근거로 든 규칙이 계약서 값으로 해당하지 않아" : "기준서 규칙에서 근거를 찾지 못해";
    sentences.push(`평가 에이전트는 '${LEVEL_LABELS[agent_level]}'(으)로 판단했지만, ${basis} '${LEVEL_LABELS[level]}'(으)로 표시합니다.`);
  }
  const cardLevel = more_severe(...hits.map(h => h.level)) || "safe";
  if (agent_level === level && level !== null && LEVEL_SEVERITY[level] > LEVEL_SEVERITY[cardLevel]) {
    const confirmed = cardLevel === "safe" ? "기준서 규칙으로 확정한 지적은 없지만" : `기준서 규칙으로 확정한 지적은 '${LEVEL_LABELS[cardLevel]}' 수준이지만`;
    sentences.push(`${confirmed}, 규칙 계산이 판단하지 못한 규칙이나 규칙 코드 없이 적힌 평가 에이전트의 지적이 있어 에이전트 판단대로 '${LEVEL_LABELS[level]}'(으)로 표시합니다. 계약서 원문으로 확인하세요.`);
  }
  return sentences.join(" ");
}
export function sentence_rules(sentence: string, next_year: number | null): Set<string> {
  const found = new Set(Object.entries(RULE_KEYWORDS).filter(([, words]) => words.some(word => sentence.includes(word))).map(([code]) => code));
  if (next_year && (sentence.includes(`${next_year}년`) || sentence.includes("다음 해") || sentence.includes("내년"))) { found.delete("LABOR_MIN_WAGE"); found.add("LABOR_MIN_WAGE_NEXT"); }
  return found;
}
export function drop_disputed(sentences: unknown[], disputed_codes: ReadonlySet<string>, next_year: number | null): string[] {
  return sentences.map(stringValue).filter(sentence => {
    const codes = sentence_rules(sentence, next_year);
    return !codes.size || ![...codes].every(code => disputed_codes.has(code));
  });
}
export function clause_note(finding: Finding): string {
  return finding.clause ? `"${finding.clause}" → ${finding.reason}` : `해당 조항 없음 - ${finding.reason}`;
}
export function engine_review(engine: EngineResult): Review {
  const hits = engine.findings.filter(f => f.hit);
  return { review_level: engine.level, summary: compose_summary(engine, hits, engine.level, engine.level === null), matched_rules: hits.map(f => `${f.rule_code} - ${f.legal_basis}`), missing_items: engine.missing_items, risky_clauses: hits.filter(f => !["LABOR_MIN_WAGE", "LABOR_MIN_WAGE_NEXT"].includes(f.rule_code)).map(clause_note), confirmed_items: engine.findings.filter(f => f.hit === false).map(f => RULE_PASS_TITLES[f.rule_code] ?? f.title + " 통과"), recommendations: hits.map(f => f.recommended_action).filter(Boolean) };
}
export function final_view(review: Review, engine: EngineResult, agent_level: Level | null, check: CrossCheck): FinalView {
  const agentCodes = new Set(check.agent_codes);
  const disputedCodes = new Set(engine.findings.filter(f => agentCodes.has(f.rule_code) && f.hit === false && DECISIVE_PASS_RULES.has(f.rule_code)).map(f => f.rule_code));
  const finalCodes = new Set([...engine.hit_codes, ...agentCodes].filter(code => !disputedCodes.has(code)));
  const cards: ResultCard[] = [], disputed: ResultCard[] = [];
  for (const f of engine.findings) {
    if (disputedCodes.has(f.rule_code)) {
      disputed.push({ ...f, source: "agent", reason: `평가 에이전트는 해당한다고 봤지만, 계약서 값으로 계산하면 해당하지 않습니다. ${f.reason}` });
      continue;
    }
    if (!finalCodes.has(f.rule_code)) continue;
    const card: ResultCard = { ...f, source: "engine" };
    if (agentCodes.has(f.rule_code) && !f.hit) {
      card.source = "agent";
      const note = f.hit === null ? "규칙 계산으로는 판단하지 못했습니다." : `규칙 계산에서는 통과로 나왔습니다(${f.reason}).`;
      card.reason = `평가 에이전트가 이 규칙에 해당한다고 판단했습니다. ${note}`;
    } else if (!agentCodes.has(f.rule_code) && agent_level !== null) card.source = "engine";
    else card.source = agent_level !== null ? "both" : "engine";
    cards.push(card);
  }
  cards.sort((a, b) => (b.level === null ? 3 : LEVEL_SEVERITY[b.level]) - (a.level === null ? 3 : LEVEL_SEVERITY[a.level]));
  const cardLevel = more_severe(...cards.map(c => c.level));
  const pending = engine.findings.filter(f => f.hit === null && !finalCodes.has(f.rule_code));
  const nextYear = engine.facts.base_year ? engine.facts.base_year + 1 : null;
  let level: Level | null, incomplete: boolean;
  if (agent_level !== null) {
    const evidence = [...check.agent_unlinked, ...review.risky_clauses.map(stringValue)];
    const linked = new Set(evidence.flatMap(e => [...sentence_rules(e, nextYear)]));
    let allowance = more_severe(...pending.filter(f => linked.has(f.rule_code)).map(f => f.level || "risky"));
    const stray = review.risky_clauses.filter(clause => !sentence_rules(stringValue(clause), nextYear).size);
    if (check.agent_unlinked.length || stray.length || (!agentCodes.size && (pending.length || review.risky_clauses.length || review.missing_items.length))) allowance = more_severe(allowance, "check_needed");
    level = more_severe(cardLevel || "safe", less_severe(agent_level, allowance));
    incomplete = false;
  } else if (engine.level !== null) {
    level = more_severe(engine.level, cardLevel);
    incomplete = false;
  } else {
    level = cardLevel;
    incomplete = true;
  }
  const disagree = check.status === "mismatch" || (agent_level !== null && agent_level !== level);
  const agentText = agent_level !== null && level !== "safe";
  const agentRequests = agentText ? drop_disputed(review.recommendations, disputedCodes, nextYear) : [];
  const recommendations = agent_level !== null ? [...agentRequests] : [...review.recommendations];
  const actions = new Map(engine.findings.map(f => [f.rule_code, f.recommended_action]));
  const covered = new Set(agentRequests.flatMap(request => [...sentence_rules(request, nextYear)]));
  for (const code of [...check.engine_only, ...cards.filter(c => !covered.has(c.rule_code)).map(c => c.rule_code)]) {
    const action = actions.get(code);
    if (action && !recommendations.includes(action)) recommendations.push(action);
  }
  const confirmed = disagree || agent_level === null ? engine.findings.filter(f => f.hit === false && !finalCodes.has(f.rule_code)).map(f => RULE_PASS_TITLES[f.rule_code] ?? f.title + " 통과") : [...review.confirmed_items];
  return { level, incomplete, summary: compose_summary(engine, cards, level, incomplete, agent_level, disputed), agent_summary: agent_level !== null ? review.summary : "", cards, recommendations, requests: agentRequests, requests_missing: agentRequests.length ? cards.filter(card => !covered.has(card.rule_code)).map(card => card.title) : [], confirmed_items: confirmed, missing_items: [...new Set([...engine.missing_items, ...drop_disputed(review.missing_items, disputedCodes, nextYear)])], pending, disputed, disagree };
}
