"""
rules.py

규칙 계산과 교차 검증

FirstSign의 원칙("AI는 주관적으로 판단하지 않는다")을 Document Agent 구조에 옮긴 모듈이다.

1. 계약 정보에서 계산할 수 있는 값(1일·1주 근로시간, 시급 환산, 적용 최저임금)을
   코드가 직접 계산한다. 이 값은 평가 에이전트 입력 PDF의 3부로 넘겨,
   에이전트가 숫자를 잘못 계산하지 않게 돕는다. 판정은 에이전트가 한다.
2. 같은 기준서 규칙을 코드로도 판정해 평가 에이전트 결과와 맞는지 교차 검증한다.

기준값(최저임금, 규칙별 분류, 법령 근거, 권장 행동)은 모두 기준서 추출 결과에서 읽는다.
기준서 PDF만 바꾸면 계산과 판정이 함께 바뀐다. 코드에 판정 로직이 없는 새 규칙은
"판단 보류"로 두고 평가 에이전트의 판단을 따른다.
"""

import re
from datetime import date

##################################################
# 상수
##################################################

LEVELS = ("safe", "check_needed", "risky")

LEVEL_LABELS = {
    "safe": "안심",
    "check_needed": "확인 필요",
    "risky": "위험",
}

LEVEL_SEVERITY = {level: index for index, level in enumerate(LEVELS)}

RULE_TITLES = {
    "LABOR_MIN_WAGE": "최저임금 미달",
    "LABOR_PENALTY": "위약금·손해배상·임금 공제 조항",
    "LABOR_REQUIRED_TERMS": "필수 기재사항 누락",
    "LABOR_BREAK": "휴게시간 부족",
    "LABOR_WEEKLY_HOLIDAY": "주휴일 미기재",
    "LABOR_SIGN_COPY": "서명·교부 누락",
    "LABOR_MIN_WAGE_NEXT": "다음 해 최저임금 미달 예정",
}

RULE_PASS_TITLES = {
    "LABOR_MIN_WAGE": "최저임금 이상",
    "LABOR_PENALTY": "불리한 특약 없음",
    "LABOR_REQUIRED_TERMS": "필수 기재사항 모두 기재",
    "LABOR_BREAK": "휴게시간 기준 충족",
    "LABOR_WEEKLY_HOLIDAY": "주휴일 기준 충족",
    "LABOR_SIGN_COPY": "서명·교부 문구 있음",
    "LABOR_MIN_WAGE_NEXT": "다음 해 최저임금 기준 충족",
}

# 기준서 추출 에이전트의 다음 해 최저임금 항목 이름 (Criteria Agent 스키마)
NEXT_MIN_WAGE_FIELD = "min_wage_hourly_2027"

# 계약서가 아니거나 읽지 못한 파일을 가려내는 핵심 항목
CORE_FIELDS = (
    "employer_name",
    "contract_start_date",
    "workplace",
    "work_start_time",
    "work_end_time",
    "wage_amount",
)

EMPTY_MARKERS = {"", "(비어 있음)", "비어 있음", "null", "none", "n/a", "-"}

NONE_PATTERN = re.compile(r"없|미부여|미지정|해당\s*사항\s*없")

PENALTY_PATTERN = re.compile(
    r"위약|손해\s*배상|배상|변상|벌금|벌칙|몰수|반납|감액|차감"
    r"|(?<!보험료\s)(?<!세금\s)(?<!보험\s)공제"
    r"|(?:퇴사|퇴직|사직|그만\s*두|그만\s*둘)[^.]{0,20}(?:경우|시|때)"
)

COPY_PATTERN = re.compile(r"교부|근로자에게\s*(?:1부|한\s*부|사본)|사본을?\s*(?:지급|전달|제공)")

DAYS = "월화수목금토일"

TIME_PATTERN = re.compile(
    r"(오전|오후)?\s*(\d{1,2})(?::(\d{2})|\s*시(?!간)\s*(?:(\d{1,2})\s*분)?)"
)


##################################################
# Studio 결과 정규화
##################################################

def is_blank(value) -> bool:

    if value is None:
        return True

    if isinstance(value, str):
        return value.strip().lower() in EMPTY_MARKERS

    if isinstance(value, (list, tuple)):
        return all(is_blank(item) for item in value)

    return False


def first(value, default=""):
    """
    Studio Extract 결과는 값이 목록으로 온다. 첫 번째 의미 있는 값을 꺼낸다.
    """

    if isinstance(value, (list, tuple)):
        for item in value:
            if not is_blank(item):
                return item
        return default

    return default if is_blank(value) else value


def as_list(value) -> list:

    if value is None:
        return []

    items = value if isinstance(value, (list, tuple)) else [value]

    return [item for item in items if not is_blank(item)]


def text(value) -> str:
    """
    목록이면 ", "로 이어 한 문자열로 만든다.
    """

    return ", ".join(str(item).strip() for item in as_list(value))


def to_number(value) -> float | None:

    raw = first(value, None)

    if raw is None or isinstance(raw, bool):
        return None

    if isinstance(raw, (int, float)):
        return float(raw)

    s = str(raw).replace(",", "").replace(" ", "")
    match = re.search(r"\d+(?:\.\d+)?", s)

    if not match:
        return None

    number = float(match.group())

    if s[match.end():match.end() + 1] == "만":
        number *= 10000

    return number


def to_bool(value) -> bool | None:

    raw = first(value, None)

    if raw is None:
        return None

    if isinstance(raw, bool):
        return raw

    s = str(raw).strip().lower()

    if s in {"true", "예", "yes", "y", "o", "있음", "1", "서명", "서명함"}:
        return True

    if s in {"false", "아니오", "아니요", "no", "n", "x", "없음", "0", "서명 없음"}:
        return False

    return None


def to_date(value) -> date | None:

    s = str(first(value, "")).strip()
    match = re.search(r"(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})", s)

    if not match:
        return None

    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def normalize_level(value) -> str | None:

    s = str(first(value, "")).strip().lower().replace(" ", "_")

    if not s:
        return None

    aliases = {
        "safe": "safe", "안심": "safe", "안전": "safe",
        "check_needed": "check_needed", "확인_필요": "check_needed", "확인필요": "check_needed",
        "주의": "check_needed", "caution": "check_needed",
        "risky": "risky", "위험": "risky", "danger": "risky",
    }

    return aliases.get(s)


def more_severe(*levels: str | None) -> str | None:

    known = [level for level in levels if level in LEVEL_SEVERITY]

    return max(known, key=LEVEL_SEVERITY.get) if known else None


##################################################
# 시각·시간 파싱
##################################################

def parse_times(value) -> list[int]:
    """
    문자열에 나온 시각을 0시부터의 분으로 바꿔 순서대로 돌려준다.
    "18:00 ~ 23:00" → [1080, 1380], "오후 6시 30분" → [1110]
    """

    s = text(value)
    minutes = []

    for meridiem, hour, minute_colon, minute_korean in TIME_PATTERN.findall(s):

        h = int(hour)
        m = int(minute_colon or minute_korean or 0)

        if meridiem == "오후" and h < 12:
            h += 12

        if meridiem == "오전" and h == 12:
            h = 0

        if h <= 24 and m < 60:
            minutes.append(h * 60 + m)

    return minutes


def parse_break(value) -> tuple[bool, int | None]:
    """
    휴게시간 항목을 (적혀 있는지, 휴게 분)으로 바꾼다.

    괄호 안의 보충 설명("없음 (근로시간 5시간)")은 휴게 길이로 읽지 않는다.
    적혀 있지만 길이를 알 수 없으면 (True, None)이다.
    """

    s = text(value)

    if not s:
        return False, None

    core = re.sub(r"\([^)]*\)", " ", s)
    times = parse_times(core)

    if len(times) >= 2:
        pairs = zip(times[0::2], times[1::2])
        return True, sum((end - start) % 1440 for start, end in pairs)

    hours = re.search(r"(\d+(?:\.\d+)?)\s*시간", core)
    mins = re.search(r"(\d+)\s*분", core)

    if hours or mins:
        total = float(hours.group(1)) * 60 if hours else 0
        total += int(mins.group(1)) if mins else 0
        return True, int(round(total))

    if NONE_PATTERN.search(core):
        return True, 0

    return True, None


def parse_work_days(value) -> int | None:
    """
    근무일 항목에서 1주 근무일 수를 센다. "월~금" → 5, "주 3일" → 3
    """

    s = text(value)

    if not s:
        return None

    weekly = re.search(r"주\s*(\d)\s*일", s)

    if weekly:
        return int(weekly.group(1))

    days = set()

    for a, b in re.findall(r"([월화수목금토일])(?:요일)?\s*[~\-–]\s*([월화수목금토일])(?:요일)?", s):
        i, j = DAYS.index(a), DAYS.index(b)
        span = range(i, j + 1) if i <= j else [*range(i, 7), *range(0, j + 1)]
        days.update(DAYS[k] for k in span)

    days.update(re.findall(r"(?<![가-힣0-9])([월화수목금토일])(?:요일)?(?![가-힣])", s))

    return len(days) or None


##################################################
# 기준서 정규화
##################################################

def category_level(value) -> str | None:

    s = str(first(value, "")).replace(" ", "")

    if "위험" in s or "risky" in s.lower():
        return "risky"

    if "확인" in s or "check" in s.lower():
        return "check_needed"

    return None


def criteria_rules(criteria: dict) -> list[dict]:
    """
    기준서 추출 결과의 check_rules를 규칙 목록으로 바꾼다.

    Studio는 표를 행 객체 목록으로 주기도 하고, 열마다 목록으로 주기도 한다.
    두 모양을 모두 받는다.
    """

    columns = ("rule_code", "check_condition", "category", "legal_basis", "recommended_action")
    raw = criteria.get("check_rules")
    rows: list[dict] = []

    if isinstance(raw, list) and raw and all(isinstance(item, dict) for item in raw):
        rows = raw

    elif isinstance(raw, dict):
        length = max((len(as_list(raw.get(c))) for c in columns), default=0)
        rows = [{c: (as_list(raw.get(c)) + [""] * length)[i] for c in columns} for i in range(length)]

    rules = []

    for row in rows:

        code = str(first(row.get("rule_code"), "")).strip()

        if not code:
            continue

        rules.append({
            "rule_code": code,
            "check_condition": text(row.get("check_condition")),
            "category": text(row.get("category")),
            "level": category_level(row.get("category")) or "check_needed",
            "legal_basis": text(row.get("legal_basis")),
            "recommended_action": text(row.get("recommended_action")),
        })

    return rules


def criteria_base_year(criteria: dict) -> int | None:
    """
    기준서의 기준 연도. "법령 기준일 2026-10-14"가 있으면 그 연도, 없으면 처음 나온 연도
    """

    for key in ("criteria_version", "criteria_name"):

        s = text(criteria.get(key))
        match = re.search(r"기준일\D{0,5}(20\d{2})", s) or re.search(r"(20\d{2})", s)

        if match:
            return int(match.group(1))

    return None


def summarize_criteria(criteria: dict) -> dict:
    """
    화면과 입력 PDF에 쓸 기준서 요약
    """

    base_year = criteria_base_year(criteria)

    return {
        "name": text(criteria.get("criteria_name")),
        "version": text(criteria.get("criteria_version")),
        "base_year": base_year,
        "required_items": [str(item) for item in as_list(criteria.get("required_items"))],
        "min_wage_current": to_number(criteria.get("min_wage_hourly")),
        "min_wage_next": to_number(criteria.get(NEXT_MIN_WAGE_FIELD)),
        "legal_basis": [str(item) for item in as_list(criteria.get("legal_basis"))],
        "rules": criteria_rules(criteria),
    }


##################################################
# 계산값
##################################################

def compute_facts(contract: dict, criteria: dict) -> dict:
    """
    계약 정보와 기준서로 계산할 수 있는 값을 모두 계산한다.
    알 수 없는 값은 None으로 두고 notes에 이유를 남긴다.
    """

    notes: list[str] = []
    summary = summarize_criteria(criteria)

    # 1일 근로시간
    start_times = parse_times(contract.get("work_start_time"))
    end_times = parse_times(contract.get("work_end_time"))

    if len(start_times) >= 2 and not end_times:
        start_times, end_times = start_times[:1], start_times[-1:]

    span_minutes = None

    if start_times and end_times:
        span_minutes = (end_times[-1] - start_times[0]) % 1440 or None

    break_stated, break_minutes = parse_break(contract.get("break_time"))
    daily_work_minutes = None

    if span_minutes is not None:
        daily_work_minutes = span_minutes - (break_minutes or 0)
        if break_stated and break_minutes is None:
            notes.append("휴게시간 문구에서 길이를 읽지 못해 휴게를 0분으로 보고 근로시간을 계산했습니다.")
    else:
        notes.append("소정근로 시작·종료 시각을 읽지 못해 근로시간을 계산하지 못했습니다.")

    # 1주 근로시간
    work_days = parse_work_days(contract.get("work_days"))
    weekly_hours = None

    if daily_work_minutes is not None and work_days:
        weekly_hours = round(daily_work_minutes * work_days / 60, 2)
    elif daily_work_minutes is not None:
        notes.append("근무일(요일 또는 주 N일)을 읽지 못해 1주 소정근로시간을 계산하지 못했습니다.")

    # 시급 환산
    wage_type = text(contract.get("wage_type"))
    wage_amount = to_number(contract.get("wage_amount"))
    hourly_wage, hourly_basis = None, ""

    if wage_amount is not None:

        if "시" in wage_type or (not wage_type and wage_amount < 50000):
            hourly_wage, hourly_basis = wage_amount, "시급"

        elif "일" in wage_type and daily_work_minutes:
            hourly_wage = wage_amount / (daily_work_minutes / 60)
            hourly_basis = f"일급 ÷ 1일 근로시간 {daily_work_minutes / 60:g}시간"

        elif ("월" in wage_type or "주" in wage_type) and weekly_hours:
            holiday_hours = min(weekly_hours / 5, 8) if weekly_hours >= 15 else 0
            if "월" in wage_type:
                paid_hours = (weekly_hours + holiday_hours) * 365 / 7 / 12
                hourly_basis = f"월급 ÷ 월 환산 {paid_hours:.1f}시간(주휴 포함)"
            else:
                paid_hours = weekly_hours + holiday_hours
                hourly_basis = f"주급 ÷ 주 {paid_hours:g}시간(주휴 포함)"
            hourly_wage = wage_amount / paid_hours

        else:
            notes.append("임금 구분과 근로시간으로 시급을 환산하지 못했습니다.")

    # 적용 최저임금
    start_date = to_date(contract.get("contract_start_date"))
    end_date = to_date(contract.get("contract_end_date"))
    end_written = not is_blank(contract.get("contract_end_date"))
    base_year = summary["base_year"] or (start_date.year if start_date else date.today().year)
    next_start = date(base_year + 1, 1, 1)

    current_min = summary["min_wage_current"]
    next_min = summary["min_wage_next"]

    if start_date and start_date >= next_start and next_min:
        applicable_min, applicable_year = next_min, base_year + 1
    else:
        applicable_min, applicable_year = current_min, base_year

    if start_date is None:
        notes.append(f"계약 시작일을 읽지 못해 {base_year}년 최저임금으로 비교했습니다.")

    if end_written and end_date is None:
        notes.append("계약 종료일 형식을 읽지 못해 다음 해까지 이어지는지 판단하지 못했습니다.")
        continues_next = None
    elif start_date and start_date >= next_start:
        continues_next = None
    else:
        continues_next = (end_date is None) or (end_date >= next_start)

    return {
        "daily_span_minutes": span_minutes,
        "break_stated": break_stated,
        "break_minutes": break_minutes,
        "daily_work_hours": None if daily_work_minutes is None else round(daily_work_minutes / 60, 2),
        "work_days_per_week": work_days,
        "weekly_hours": weekly_hours,
        "weekly_15_or_more": None if weekly_hours is None else weekly_hours >= 15,
        "wage_type": wage_type,
        "wage_amount": wage_amount,
        "hourly_wage": None if hourly_wage is None else round(hourly_wage),
        "hourly_basis": hourly_basis,
        "contract_start_date": start_date.isoformat() if start_date else "",
        "contract_end_date": end_date.isoformat() if end_date else "",
        "base_year": base_year,
        "applicable_min_wage": applicable_min,
        "applicable_min_wage_year": applicable_year,
        "next_min_wage": next_min,
        "next_min_wage_start": next_start.isoformat(),
        "continues_into_next_year": continues_next,
        "notes": notes,
    }


##################################################
# 규칙별 판정
##################################################

def won(value) -> str:

    return "-" if value is None else f"{value:,.0f}원"


def check_min_wage(contract, facts):

    hourly, minimum = facts["hourly_wage"], facts["applicable_min_wage"]

    if hourly is None or minimum is None:
        return None, "시급 또는 적용 최저임금을 알 수 없어 판단하지 못했습니다.", won(hourly), won(minimum)

    if hourly < minimum:
        reason = (
            f"시급 {won(hourly)}이 계약 시작일 기준 {facts['applicable_min_wage_year']}년 "
            f"최저임금 {won(minimum)}보다 {won(minimum - hourly)} 낮습니다."
        )
        return True, reason, won(hourly), won(minimum)

    return False, f"시급 {won(hourly)}은 {facts['applicable_min_wage_year']}년 최저임금 {won(minimum)} 이상입니다.", won(hourly), won(minimum)


def check_penalty(contract, facts):

    clauses = [str(item) for item in as_list(contract.get("special_terms"))]
    hits = [clause for clause in clauses if PENALTY_PATTERN.search(clause)]

    if hits:
        reason = f"특약에 위약금·손해배상 예정·임금 공제·퇴사 제한처럼 근로자에게 불리한 조항이 {len(hits)}건 있습니다."
        return True, reason, f"불리한 조항 {len(hits)}건", "해당 조항 없음"

    return False, "위약금·손해배상·임금 공제 조항이 없습니다.", text(clauses) or "없음", "해당 조항 없음"


def required_missing(contract) -> list[str]:

    missing = []

    if is_blank(contract.get("wage_amount")) and is_blank(contract.get("wage_type")):
        missing.append("임금")
    else:
        if is_blank(contract.get("wage_payment_date")):
            missing.append("임금지급일")
        if is_blank(contract.get("wage_payment_method")):
            missing.append("임금지급방법")

    if is_blank(contract.get("work_start_time")) or is_blank(contract.get("work_end_time")):
        missing.append("소정근로시간")

    if is_blank(contract.get("weekly_holiday")):
        missing.append("휴일(주휴일)")

    if is_blank(contract.get("annual_leave_clause")):
        missing.append("연차유급휴가")

    if is_blank(contract.get("workplace")):
        missing.append("근무장소")

    if is_blank(contract.get("job_description")):
        missing.append("업무의 내용")

    if is_blank(contract.get("contract_start_date")):
        missing.append("근로계약기간")

    return missing


def check_required_terms(contract, facts):

    missing = required_missing(contract)

    if missing:
        return True, "계약서에 적혀 있지 않은 필수 기재사항: " + ", ".join(missing), ", ".join(missing) + " 없음", "6개 항목 모두 기재"

    return False, "필수 기재사항이 모두 적혀 있습니다.", "모두 기재", "6개 항목 모두 기재"


def check_break(contract, facts):

    span = facts["daily_span_minutes"]

    if span is None:
        return None, "근로시간을 알 수 없어 휴게시간 기준을 판단하지 못했습니다.", "-", "-"

    if facts["break_stated"] and facts["break_minutes"] is None:
        return None, "휴게시간 문구에서 길이를 읽지 못했습니다.", text(contract.get("break_time")), "-"

    rest = facts["break_minutes"] or 0
    work = span - rest
    required = 60 if work >= 480 else 30 if work >= 240 else 0
    current = f"근로 {work / 60:g}시간, 휴게 {rest}분" + ("" if facts["break_stated"] else "(미기재)")

    if required == 0:
        return False, "1일 근로시간이 4시간 미만이라 해당 없습니다.", current, "4시간 미만 해당 없음"

    standard = f"휴게 {required}분 이상"

    if rest < required:
        reason = f"1일 근로시간 {work / 60:g}시간에는 {standard}이 필요한데 휴게가 {rest}분입니다."
        if work == 240 and rest == 0:
            reason += " 2026-12-10부터는 근로자가 명시적으로 요청하면 4시간 근무에 휴게 없이 일할 수 있으니 그 여부를 확인하세요."
        return True, reason, current, standard

    return False, f"1일 근로시간 {work / 60:g}시간에 휴게 {rest}분이 있습니다.", current, standard


def holiday_specified(contract) -> bool:

    value = text(contract.get("weekly_holiday"))

    return bool(value) and not NONE_PATTERN.search(value)


def check_weekly_holiday(contract, facts):

    weekly = facts["weekly_hours"]
    specified = holiday_specified(contract)
    current = text(contract.get("weekly_holiday")) or "(비어 있음)"

    if specified:
        return False, "주휴일이 적혀 있습니다.", current, "주 15시간 이상이면 주휴일 기재"

    if weekly is not None and weekly < 15:
        return False, f"1주 소정근로시간이 {weekly:g}시간으로 15시간 미만이라 해당 없습니다.", current, "주 15시간 이상이면 주휴일 기재"

    if weekly is None:
        reason = "근무일을 알 수 없어 1주 소정근로시간을 계산하지 못했고, 주휴일도 정해져 있지 않아 확인이 필요합니다."
    else:
        reason = f"1주 소정근로시간이 {weekly:g}시간으로 15시간 이상인데 주휴일이 정해져 있지 않습니다."

    return True, reason, current, "주 15시간 이상이면 주휴일 기재"


def check_sign_copy(contract, facts):

    signed = to_bool(contract.get("is_signed"))
    copy_clause = text(contract.get("copy_delivery_clause"))
    copy_ok = bool(copy_clause) and bool(COPY_PATTERN.search(copy_clause))

    problems = []

    if signed is not True:
        problems.append("사업주·근로자 서명 확인 안 됨")

    if not copy_ok:
        problems.append("근로자에게 계약서를 교부한다는 문구 없음")

    current = f"서명 {'있음' if signed else '없음/불명'}, 교부 문구 {'있음' if copy_ok else '없음'}"

    if problems:
        return True, ", ".join(problems) + ".", current, "양측 서명 + 교부 문구"

    return False, "양측 서명과 교부 문구가 있습니다.", current, "양측 서명 + 교부 문구"


def check_min_wage_next(contract, facts):

    next_min, hourly = facts["next_min_wage"], facts["hourly_wage"]
    year = facts["base_year"] + 1
    standard = f"{year}년 최저임금 {won(next_min)}"

    if facts["continues_into_next_year"] is None:
        if facts["contract_start_date"] and facts["contract_start_date"] >= facts["next_min_wage_start"]:
            return False, f"계약이 {year}년에 시작해 최저임금 규칙에서 이미 {year}년 기준으로 비교했습니다.", won(hourly), standard
        return None, "계약 종료일을 읽지 못해 판단하지 못했습니다.", won(hourly), standard

    if not facts["continues_into_next_year"]:
        return False, f"계약이 {year}년 1월 1일 전에 끝나 해당 없습니다.", won(hourly), standard

    if next_min is None or hourly is None:
        return None, f"시급 또는 {year}년 최저임금을 알 수 없어 판단하지 못했습니다.", won(hourly), standard

    if hourly < next_min:
        until = facts["contract_end_date"] or "종료일 없음"
        return True, f"계약이 {year}년 이후까지 이어지는데({until}) 시급 {won(hourly)}이 {standard}보다 낮습니다.", won(hourly), standard

    return False, f"시급 {won(hourly)}이 {standard} 이상입니다.", won(hourly), standard


# 규칙마다 화면과 결과에 인용할 계약서 원문 항목
RULE_SOURCE_FIELDS = {
    "LABOR_MIN_WAGE": "wage_amount",
    "LABOR_PENALTY": "special_terms",
    "LABOR_BREAK": "break_time",
    "LABOR_WEEKLY_HOLIDAY": "weekly_holiday",
    "LABOR_SIGN_COPY": "copy_delivery_clause",
    "LABOR_MIN_WAGE_NEXT": "wage_amount",
}


RULE_CHECKS = {
    "LABOR_MIN_WAGE": check_min_wage,
    "LABOR_PENALTY": check_penalty,
    "LABOR_REQUIRED_TERMS": check_required_terms,
    "LABOR_BREAK": check_break,
    "LABOR_WEEKLY_HOLIDAY": check_weekly_holiday,
    "LABOR_SIGN_COPY": check_sign_copy,
    "LABOR_MIN_WAGE_NEXT": check_min_wage_next,
}


##################################################
# 규칙 엔진
##################################################

def looks_like_contract(contract: dict) -> bool:
    """
    핵심 항목이 대부분 비어 있으면 근로계약서가 아니거나 읽지 못한 파일로 본다.
    """

    filled = sum(not is_blank(contract.get(field)) for field in CORE_FIELDS)

    return filled >= 3


def evaluate(contract: dict, criteria: dict, facts: dict | None = None) -> dict:
    """
    기준서의 규칙을 계약 정보에 하나씩 적용한다.

    hit: True(해당) / False(통과) / None(판단 보류)
    """

    facts = facts or compute_facts(contract, criteria)
    summary = summarize_criteria(criteria)
    findings = []

    for rule in summary["rules"]:

        check = RULE_CHECKS.get(rule["rule_code"])

        if check is None:
            hit, reason, current, standard = None, "코드에 판정 로직이 없는 규칙입니다. 평가 에이전트의 판단을 따릅니다.", "-", "-"
        else:
            hit, reason, current, standard = check(contract, facts)

        source = RULE_SOURCE_FIELDS.get(rule["rule_code"])

        findings.append({
            **rule,
            "title": RULE_TITLES.get(rule["rule_code"], rule["rule_code"]),
            "hit": hit,
            "reason": reason,
            "contract_value": current,
            "criteria_value": standard,
            "clause": " / ".join(str(item) for item in as_list(contract.get(source))) if source else "",
        })

    hits = [f for f in findings if f["hit"]]

    if not looks_like_contract(contract):
        level = None
    elif any(f["level"] == "risky" for f in hits):
        level = "risky"
    elif hits:
        level = "check_needed"
    else:
        level = "safe"

    missing = required_missing(contract)

    if not facts["break_stated"]:
        missing.append("휴게시간")

    if to_bool(contract.get("is_signed")) is not True:
        missing.append("사업주·근로자 서명")

    if not COPY_PATTERN.search(text(contract.get("copy_delivery_clause"))):
        missing.append("계약서 교부 문구")

    return {
        "level": level,
        "is_contract": looks_like_contract(contract),
        "findings": findings,
        "hit_codes": [f["rule_code"] for f in hits],
        "undetermined_codes": [f["rule_code"] for f in findings if f["hit"] is None],
        "missing_items": missing,
        "facts": facts,
        "criteria": summary,
    }


##################################################
# 교차 검증
##################################################

RULE_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")


def rule_codes_in(values) -> set[str]:

    return set(RULE_CODE_PATTERN.findall(" ".join(str(v) for v in as_list(values))))


def cross_check(agent_level: str | None, agent_rules, engine: dict) -> dict:
    """
    평가 에이전트 결과와 규칙 계산 결과를 비교한다.
    판단 보류 규칙은 비교에서 뺀다.
    """

    known = {f["rule_code"] for f in engine["findings"]} - set(engine["undetermined_codes"])
    agent_codes = rule_codes_in(agent_rules) & known
    engine_codes = set(engine["hit_codes"]) & known

    return {
        "agent_level": agent_level,
        "engine_level": engine["level"],
        "level_match": agent_level is not None and agent_level == engine["level"],
        "agent_only": sorted(agent_codes - engine_codes),
        "engine_only": sorted(engine_codes - agent_codes),
    }


##################################################
# 규칙 계산 결과를 평가 결과 모양으로
##################################################

def engine_review(engine: dict) -> dict:
    """
    평가 에이전트를 부를 수 없을 때(데모 모드) 규칙 계산 결과로
    평가 에이전트와 같은 모양의 결과를 만든다.
    """

    facts = engine["facts"]
    hits = [f for f in engine["findings"] if f["hit"]]

    hourly, minimum = facts["hourly_wage"], facts["applicable_min_wage"]

    if hourly is not None and minimum is not None:
        start = facts["contract_start_date"] or "시작일 미상"
        comparison = f"보다 {won(minimum - hourly)} 낮습니다" if hourly < minimum else " 이상입니다"
        first_sentence = f"시급 {won(hourly)}은 계약 시작일({start}) 기준 최저임금 {won(minimum)}{comparison}."
    else:
        first_sentence = "시급 또는 적용 최저임금을 확인하지 못했습니다."

    if not hits:
        rest = "점검 기준서의 규칙에 해당하는 항목이 없습니다."
    else:
        rest = "해당한 규칙: " + ", ".join(f["title"] for f in hits) + "."

    risky_clauses = []

    for f in hits:
        if f["rule_code"] in ("LABOR_MIN_WAGE", "LABOR_MIN_WAGE_NEXT"):
            continue
        if f["clause"]:
            risky_clauses.append(f"\"{f['clause']}\" → {f['reason']}")
        else:
            risky_clauses.append(f"해당 조항 없음 - {f['reason']}")

    return {
        "review_level": engine["level"],
        "summary": f"{first_sentence} {rest}",
        "matched_rules": [f"{f['rule_code']} - {f['legal_basis']}" for f in hits],
        "missing_items": engine["missing_items"],
        "risky_clauses": risky_clauses,
        "confirmed_items": [RULE_PASS_TITLES.get(f["rule_code"], f["title"] + " 통과") for f in engine["findings"] if f["hit"] is False],
        "recommendations": [f["recommended_action"] for f in hits if f["recommended_action"]],
    }
