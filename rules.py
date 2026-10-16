"""
rules.py

규칙 계산과 교차 검증

FirstSign의 원칙("AI는 주관적으로 판단하지 않는다")을 Document Agent 구조에 옮긴 모듈이다.

1. 계약 정보에서 계산할 수 있는 값(1일·1주 근로시간, 시급 환산, 적용 최저임금)을
   코드가 직접 계산한다. 이 값은 평가 에이전트 입력 PDF의 3부로 넘겨,
   에이전트가 숫자를 잘못 계산하지 않게 돕는다. 판정은 에이전트가 한다.
2. 같은 기준서 규칙을 코드로도 판정해 평가 에이전트 결과와 맞는지 교차 검증한다.

기준값(최저임금, 규칙별 분류, 법령 근거, 권장 행동)은 기준서 추출 결과에서 읽는다.
코드가 구현한 점검 조건은 KNOWN_CONDITIONS에 적어 두고, 기준서의 점검 조건이
그와 다르면(임계값이 바뀌었거나 새 규칙이면) 그 규칙은 "판단 보류"로 두고
평가 에이전트의 판단을 따른다. 코드가 옛 기준으로 새 기준의 판정을 덮어쓰지 않게 하기 위해서다.
"""

import difflib
import math
import re
from collections import Counter
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

# 코드가 구현한 점검 조건 (점검 기준서 v2). (조건 문장, 숫자까지 같아야 하는지)
# 최저임금 규칙은 금액·연도를 기준서의 최저임금 항목에서 읽으므로 숫자는 비교하지 않는다.
KNOWN_CONDITIONS = {
    "LABOR_MIN_WAGE": (
        "계약 시작일 기준 시급이 최저임금보다 낮다. 2026년 시작 계약은 10,320원, "
        "2027년 1월 1일 이후 시작 계약은 10,700원과 비교한다.",
        False,
    ),
    "LABOR_PENALTY": (
        "위약금, 손해배상액의 예정, 임금 공제, 부당한 퇴사 제한 등 불리한 조항이 있다.",
        True,
    ),
    "LABOR_REQUIRED_TERMS": (
        "법정 필수 기재사항 6가지(임금, 소정근로시간, 휴일, 연차유급휴가, 근무장소와 업무, 근로계약기간) "
        "중 하나라도 적혀 있지 않다. 단 1주 소정근로시간이 15시간 미만인 근로자는 휴일과 연차유급휴가 "
        "항목에 '해당 없음'이라고 적혀 있으면 적힌 것으로 본다.",
        True,
    ),
    "LABOR_BREAK": (
        "근로시간 4시간 이상 8시간 미만이면 휴게 30분 이상, 8시간 이상이면 휴게 1시간 이상이 없다. "
        "4시간 미만은 해당 없다. (2026-12-10부터 근로시간이 정확히 4시간이고 근로자가 명시적으로 "
        "휴게 미사용을 요청하면 예외)",
        True,
    ),
    "LABOR_WEEKLY_HOLIDAY": (
        "1주 소정근로시간이 15시간 이상인데 주휴일이 적혀 있지 않다. 1주 15시간 미만이면 해당 없다.",
        True,
    ),
    "LABOR_SIGN_COPY": (
        "사업주 또는 근로자의 서명·날인이 없거나, 계약서를 근로자에게 교부한다는 문구가 없다.",
        True,
    ),
    "LABOR_MIN_WAGE_NEXT": (
        "계약기간이 2027년 1월 1일 이후까지 이어지는데 시급이 2027년 최저임금 10,700원 미만이다. "
        "종료일이 없으면 이어진다고 본다.",
        False,
    ),
}

CONDITION_SIMILARITY = 0.88

# 필수 기재사항 6가지와 기준서 항목명에서 찾을 핵심어
REQUIRED_TERM_KEYS = {
    "임금": ("임금",),
    "소정근로시간": ("소정근로시간", "근로시간"),
    "휴일": ("휴일",),
    "연차유급휴가": ("연차",),
    "근무장소와 업무": ("장소", "업무"),
    "근로계약기간": ("기간",),
}

# 기준서 추출 에이전트의 다음 해 최저임금 항목 (Criteria Agent 스키마에 연도가 들어 있다)
NEXT_MIN_WAGE_FIELD = "min_wage_hourly_2027"
NEXT_MIN_WAGE_YEAR = 2027

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

# 불리한 조항의 핵심어. 보험료·세금 공제는 정상 공제라 뺀다.
PENALTY_PATTERN = re.compile(
    r"위약|손해\s*배상|배상|변상|벌금|벌칙|몰수|감액|차감"
    r"|(?<!보험료\s)(?<!보험료)(?<!보험\s)(?<!보험)(?<!세금\s)(?<!세금)(?<!세\s)(?<!세)공제"
)

# 퇴사 제한처럼 핵심어 없이도 불리할 수 있는 문맥. 단독이면 판단을 보류한다.
RESIGN_PATTERN = re.compile(r"퇴사|퇴직|사직|그만\s*두|그만\s*둘|중도\s*해지")

NEGATION_PATTERN = re.compile(r"금지|하지\s*않|하지\s*아니|않는다|아니한다|없다|없음|불가|못한다|면제|청구하지")

COPY_PATTERN = re.compile(r"교부|근로자에게\s*(?:1부|한\s*부|사본)|사본을?\s*(?:지급|전달|제공)")

COPY_NEGATION_PATTERN = re.compile(r"교부\s*하지|교부하지|미교부|교부\s*안|교부\s*없|교부\s*불|교부를?\s*하지|주지\s*않|제공하지|전달하지")

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


def to_year(value) -> int | None:
    """
    날짜를 다 읽지 못해도 연도는 쓸 수 있다. "2027년 1월" → 2027
    """

    match = re.search(r"(20\d{2})", str(first(value, "")))

    return int(match.group(1)) if match else None


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


def won(value) -> str:
    """
    금액 표시. 판정은 반올림 전 값으로 하고, 화면에서는 소수점 둘째 자리 아래를 버린다.
    10,319.875원을 10,320원으로 보여 최저임금 이상처럼 보이지 않게 하기 위해서다.
    """

    if value is None:
        return "-"

    if abs(value - round(value)) < 1e-9:
        return f"{value:,.0f}원"

    return f"{math.floor(value * 100) / 100:,.2f}원"


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


def cell(column, index: int):
    """
    열 목록에서 index번째 값. 빈 셀도 자리를 지켜야 행이 어긋나지 않는다.
    """

    values = column if isinstance(column, (list, tuple)) else [column]

    return values[index] if index < len(values) else ""


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
        length = max(
            (len(raw[c]) if isinstance(raw.get(c), (list, tuple)) else int(c in raw) for c in columns),
            default=0
        )
        rows = [{c: cell(raw.get(c), i) for c in columns} for i in range(length)]

    rules = []

    for row in rows:

        code = str(first(row.get("rule_code"), "")).strip()

        if not code:
            continue

        rules.append({
            "rule_code": code,
            "check_condition": text(row.get("check_condition")),
            "category": text(row.get("category")),
            "level": category_level(row.get("category")),
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

    return {
        "name": text(criteria.get("criteria_name")),
        "version": text(criteria.get("criteria_version")),
        "base_year": criteria_base_year(criteria),
        "required_items": [str(item) for item in as_list(criteria.get("required_items"))],
        "min_wage_current": to_number(criteria.get("min_wage_hourly")),
        "min_wage_next": to_number(criteria.get(NEXT_MIN_WAGE_FIELD)),
        "legal_basis": [str(item) for item in as_list(criteria.get("legal_basis"))],
        "rules": criteria_rules(criteria),
    }


def criteria_problems(criteria: dict) -> list[str]:
    """
    기준서 추출 결과로 점검을 할 수 없는 이유. 비어 있으면 쓸 수 있다.
    """

    summary = summarize_criteria(criteria)
    problems = []

    if not summary["rules"]:
        problems.append("점검 규칙 표를 읽지 못했습니다")

    if summary["min_wage_current"] is None:
        problems.append("최저임금 금액을 읽지 못했습니다")

    if summary["base_year"] is None:
        problems.append("기준서의 기준 연도를 읽지 못했습니다")

    return problems


##################################################
# 점검 조건 비교
##################################################

def condition_shape(sentence: str) -> str:
    """
    공백·문장부호를 지우고 숫자를 #로 바꾼 조건 문장의 모양
    """

    s = re.sub(r"[\s\W_]+", "", sentence)

    return re.sub(r"\d+", "#", s)


def condition_numbers(sentence: str) -> Counter:

    return Counter(re.findall(r"\d+", sentence.replace(",", "")))


def condition_supported(rule: dict) -> tuple[bool, str]:
    """
    기준서의 점검 조건이 코드가 구현한 조건과 같은지 본다.
    추출 과정의 띄어쓰기·줄바꿈 차이는 허용하고, 임계값이 바뀌면 다르다고 본다.
    """

    known = KNOWN_CONDITIONS.get(rule["rule_code"])

    if known is None:
        return False, "코드에 판정 로직이 없는 규칙입니다. 평가 에이전트의 판단을 따릅니다."

    if not rule["check_condition"]:
        return False, "기준서에서 이 규칙의 점검 조건을 읽지 못해 코드로 판단하지 않습니다."

    sentence, numbers_matter = known
    similarity = difflib.SequenceMatcher(None, condition_shape(sentence), condition_shape(rule["check_condition"])).ratio()

    if similarity < CONDITION_SIMILARITY:
        return False, "기준서의 점검 조건이 코드가 구현한 조건과 달라 코드로 판단하지 않습니다. 평가 에이전트의 판단을 따릅니다."

    if numbers_matter and condition_numbers(sentence) != condition_numbers(rule["check_condition"]):
        return False, "기준서의 점검 조건 숫자(시간·인원 등)가 바뀌어 코드로 판단하지 않습니다. 평가 에이전트의 판단을 따릅니다."

    return True, ""


def required_items_supported(criteria: dict) -> bool:
    """
    기준서의 필수 기재사항이 코드가 아는 6가지와 같은지 본다.
    목록을 읽지 못했으면 점검 조건 문장(6가지를 나열함)으로 판단한다.
    """

    items = [re.sub(r"\s+", "", str(item)) for item in as_list(criteria.get("required_items"))]

    if not items:
        return True

    covered = {term for term, keys in REQUIRED_TERM_KEYS.items() if any(any(k in item for k in keys) for item in items)}
    unknown = [item for item in items if not any(k in item for keys in REQUIRED_TERM_KEYS.values() for k in keys)]

    return covered == set(REQUIRED_TERM_KEYS) and not unknown


##################################################
# 계산값
##################################################

def compute_facts(contract: dict, criteria: dict) -> dict:
    """
    계약 정보와 기준서로 계산할 수 있는 값을 모두 계산한다.
    알 수 없는 값은 None으로 두고 notes에 이유를 남긴다. 임의의 기준으로 채우지 않는다.
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
        if break_stated and break_minutes is None:
            notes.append("휴게시간 문구에서 길이를 읽지 못해 근로시간을 계산하지 않았습니다.")
        else:
            daily_work_minutes = span_minutes - (break_minutes or 0)
    else:
        notes.append("소정근로 시작·종료 시각을 읽지 못해 근로시간을 계산하지 못했습니다.")

    # 1주 근로시간
    work_days = parse_work_days(contract.get("work_days"))
    weekly_hours = None

    if daily_work_minutes is not None and work_days:
        weekly_hours = round(daily_work_minutes * work_days / 60, 4)
    elif daily_work_minutes is not None:
        notes.append("근무일(요일 또는 주 N일)을 읽지 못해 1주 소정근로시간을 계산하지 못했습니다.")

    # 시급 환산 (반올림하지 않는다)
    wage_type = text(contract.get("wage_type"))
    wage_amount = to_number(contract.get("wage_amount"))
    hourly_wage, hourly_basis = None, ""

    if wage_amount is not None:

        if "시" in wage_type:
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
            notes.append("임금 구분(시급·일급·월급)과 근로시간으로 시급을 환산하지 못했습니다.")

    # 적용 최저임금
    base_year = summary["base_year"]
    current_min = summary["min_wage_current"]
    next_min = summary["min_wage_next"]

    if base_year is not None and base_year + 1 != NEXT_MIN_WAGE_YEAR:
        notes.append(f"기준서 기준 연도({base_year})가 Criteria Agent 스키마의 다음 해 항목({NEXT_MIN_WAGE_FIELD})과 맞지 않아 다음 해 최저임금을 쓰지 않았습니다.")
        next_min = None

    start_date = to_date(contract.get("contract_start_date"))
    start_year = start_date.year if start_date else to_year(contract.get("contract_start_date"))
    end_date = to_date(contract.get("contract_end_date"))
    end_written = not is_blank(contract.get("contract_end_date"))
    end_year = end_date.year if end_date else to_year(contract.get("contract_end_date"))

    applicable_min, applicable_year = None, None
    next_start = date(base_year + 1, 1, 1) if base_year else None

    if base_year is None:
        notes.append("기준서의 기준 연도를 읽지 못해 적용 최저임금을 정하지 못했습니다.")
    elif start_year is None:
        notes.append("계약 시작일을 읽지 못해 적용 최저임금을 정하지 못했습니다.")
    elif start_year > base_year:
        applicable_min, applicable_year = next_min, base_year + 1
        if next_min is None:
            notes.append(f"계약이 {base_year + 1}년에 시작하는데 기준서에 그해 최저임금이 없습니다.")
    else:
        applicable_min, applicable_year = current_min, base_year
        if start_year < base_year:
            notes.append(f"계약 시작 연도({start_year})가 기준서 기준 연도보다 이르지만, 현재 일하는 기간에 적용되는 {base_year}년 최저임금으로 비교했습니다.")

    if start_date is None and start_year is not None:
        notes.append(f"계약 시작일은 연도({start_year})만 읽었습니다.")

    # 다음 해까지 이어지는지
    if next_start is None or (start_year is not None and start_year > base_year):
        continues_next = None
    elif not end_written:
        continues_next = True
    elif end_date is not None:
        continues_next = end_date >= next_start
    elif end_year is not None:
        continues_next = end_year > base_year
    else:
        continues_next = None
        notes.append("계약 종료일 형식을 읽지 못해 다음 해까지 이어지는지 판단하지 못했습니다.")

    return {
        "daily_span_minutes": span_minutes,
        "break_stated": break_stated,
        "break_minutes": break_minutes,
        "daily_work_hours": None if daily_work_minutes is None else round(daily_work_minutes / 60, 4),
        "work_days_per_week": work_days,
        "weekly_hours": weekly_hours,
        "weekly_15_or_more": None if weekly_hours is None else weekly_hours >= 15,
        "wage_type": wage_type,
        "wage_amount": wage_amount,
        "hourly_wage": hourly_wage,
        "hourly_basis": hourly_basis,
        "contract_start_date": start_date.isoformat() if start_date else "",
        "contract_start_year": start_year,
        "contract_end_date": end_date.isoformat() if end_date else "",
        "base_year": base_year,
        "applicable_min_wage": applicable_min,
        "applicable_min_wage_year": applicable_year,
        "next_min_wage": next_min,
        "next_min_wage_start": next_start.isoformat() if next_start else "",
        "continues_into_next_year": continues_next,
        "notes": notes,
    }


##################################################
# 규칙별 판정
#
# 각 함수는 (hit, reason, 계약서 값, 기준값)을 돌려준다.
# hit: True(해당) / False(통과) / None(판단 보류)
##################################################

def check_min_wage(contract, facts):

    hourly, minimum = facts["hourly_wage"], facts["applicable_min_wage"]

    if hourly is None or minimum is None:
        return None, "시급 또는 적용 최저임금을 알 수 없어 판단하지 못했습니다.", won(hourly), won(minimum)

    year = facts["applicable_min_wage_year"]

    if hourly < minimum:
        reason = f"시급 {won(hourly)}이 계약 시작일 기준 {year}년 최저임금 {won(minimum)}보다 {won(minimum - hourly)} 낮습니다."
        return True, reason, won(hourly), won(minimum)

    return False, f"시급 {won(hourly)}은 {year}년 최저임금 {won(minimum)} 이상입니다.", won(hourly), won(minimum)


def classify_penalty_clauses(contract) -> tuple[list[str], list[str]]:
    """
    특약을 (불리한 조항, 의미를 확정할 수 없는 조항)으로 나눈다.

    핵심어(위약금, 배상, 공제 등)가 있고 금지·부정 문맥이 없으면 불리한 조항이다.
    핵심어와 금지 문맥이 함께 있거나, 퇴사 관련 문구만 있으면 코드로 확정하지 않는다.
    """

    hits, unclear = [], []

    for clause in (str(item) for item in as_list(contract.get("special_terms"))):

        strong = PENALTY_PATTERN.search(clause)
        negated = NEGATION_PATTERN.search(clause)

        if strong and not negated:
            hits.append(clause)
        elif strong or RESIGN_PATTERN.search(clause):
            unclear.append(clause)

    return hits, unclear


def check_penalty(contract, facts):

    hits, unclear = classify_penalty_clauses(contract)

    if hits:
        reason = f"특약에 위약금·손해배상 예정·임금 공제처럼 근로자에게 불리한 조항이 {len(hits)}건 있습니다."
        return True, reason, f"불리한 조항 {len(hits)}건", "해당 조항 없음"

    if unclear:
        reason = f"퇴사·공제 관련 조항 {len(unclear)}건의 의미를 코드로 확정할 수 없어 평가 에이전트의 판단을 따릅니다."
        return None, reason, f"확인할 조항 {len(unclear)}건", "해당 조항 없음"

    return False, "위약금·손해배상·임금 공제 조항이 없습니다.", text(contract.get("special_terms")) or "없음", "해당 조항 없음"


def required_missing(contract) -> list[str]:

    missing = []

    if is_blank(contract.get("wage_amount")):
        missing.append("임금(금액)")

    if is_blank(contract.get("wage_type")):
        missing.append("임금(시급·일급·월급 구분)")

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
    current = text(contract.get("weekly_holiday")) or "(비어 있음)"
    standard = "주 15시간 이상이면 주휴일 기재"

    if holiday_specified(contract):
        return False, "주휴일이 적혀 있습니다.", current, standard

    if weekly is not None and weekly < 15:
        return False, f"1주 소정근로시간이 {weekly:g}시간으로 15시간 미만이라 해당 없습니다.", current, standard

    if weekly is None:
        return None, "1주 소정근로시간을 계산하지 못했는데 주휴일이 정해져 있지 않습니다. 15시간 이상이면 해당합니다.", current, standard

    return True, f"1주 소정근로시간이 {weekly:g}시간으로 15시간 이상인데 주휴일이 정해져 있지 않습니다.", current, standard


def copy_clause_ok(contract) -> bool:
    """
    근로자에게 계약서를 교부한다는 문구가 있는지. "교부하지 않는다"는 없는 것으로 본다.
    """

    clause = text(contract.get("copy_delivery_clause"))

    return bool(COPY_PATTERN.search(clause)) and not COPY_NEGATION_PATTERN.search(clause)


def check_sign_copy(contract, facts):

    signed = to_bool(contract.get("is_signed"))
    copy_ok = copy_clause_ok(contract)

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
    base_year = facts["base_year"]

    if base_year is None:
        return None, "기준서의 기준 연도를 읽지 못해 판단하지 못했습니다.", won(hourly), "-"

    year = base_year + 1
    standard = f"{year}년 최저임금 {won(next_min)}"

    start_year = facts["contract_start_year"]

    if start_year is not None and start_year > base_year:
        return False, f"계약이 {year}년에 시작해 최저임금 규칙에서 이미 {year}년 기준으로 비교했습니다.", won(hourly), standard

    if facts["continues_into_next_year"] is None:
        return None, "계약이 다음 해까지 이어지는지 판단하지 못했습니다.", won(hourly), standard

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
    "LABOR_PENALTY": "special_terms",
    "LABOR_BREAK": "break_time",
    "LABOR_WEEKLY_HOLIDAY": "weekly_holiday",
    "LABOR_SIGN_COPY": "copy_delivery_clause",
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


def overall_level(findings: list[dict]) -> str | None:
    """
    규칙 결과로 종합 등급을 정한다.

    판단 보류가 있으면 안심이라고 하지 않는다. 위험 규칙에 해당하면 다른 규칙과 상관없이 위험이다.
    """

    hits = [f for f in findings if f["hit"]]
    pending = [f for f in findings if f["hit"] is None]

    if any(f["level"] == "risky" for f in hits):
        return "risky"

    if any(f["level"] is None for f in hits):
        return None

    if any(f["level"] != "check_needed" for f in pending):
        return None

    if hits:
        return "check_needed"

    if pending or not findings:
        return None

    return "safe"


def missing_items(contract: dict, facts: dict) -> list[str]:
    """
    화면에 보여 줄 계약서에 없는 항목 (필수 기재사항 + 휴게시간 + 서명·교부)
    """

    items = required_missing(contract)

    if not facts["break_stated"]:
        items.append("휴게시간")

    if to_bool(contract.get("is_signed")) is not True:
        items.append("사업주·근로자 서명")

    if not copy_clause_ok(contract):
        items.append("계약서 교부 문구")

    return items


def evaluate(contract: dict, criteria: dict, facts: dict | None = None) -> dict:
    """
    기준서의 규칙을 계약 정보에 하나씩 적용한다.
    """

    facts = facts or compute_facts(contract, criteria)
    summary = summarize_criteria(criteria)
    findings = []

    for rule in summary["rules"]:

        code = rule["rule_code"]
        supported, why = condition_supported(rule)

        if supported and code == "LABOR_REQUIRED_TERMS" and not required_items_supported(criteria):
            supported, why = False, "기준서의 필수 기재사항 목록이 코드가 아는 6가지와 달라 코드로 판단하지 않습니다."

        if not supported:
            hit, reason, current, standard = None, why, "-", "-"
        elif rule["level"] is None:
            hit, reason, current, standard = None, "기준서에서 이 규칙의 분류(위험/확인 필요)를 읽지 못했습니다.", "-", "-"
        else:
            hit, reason, current, standard = RULE_CHECKS[code](contract, facts)

        source = RULE_SOURCE_FIELDS.get(code)

        findings.append({
            **rule,
            "title": RULE_TITLES.get(code, code),
            "hit": hit,
            "reason": reason,
            "contract_value": current,
            "criteria_value": standard,
            "clause": " / ".join(str(item) for item in as_list(contract.get(source))) if source else "",
        })

    is_contract = looks_like_contract(contract)

    return {
        "level": overall_level(findings) if is_contract else None,
        "is_contract": is_contract,
        "findings": findings,
        "hit_codes": [f["rule_code"] for f in findings if f["hit"]],
        "undetermined_codes": [f["rule_code"] for f in findings if f["hit"] is None],
        "missing_items": missing_items(contract, facts),
        "criteria_problems": criteria_problems(criteria),
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

    agent_codes는 기준서에 있는 규칙 중 에이전트가 해당한다고 본 전체 목록이다.
    agent_only / engine_only는 코드가 판단한 규칙만 비교한다.
    """

    all_codes = {f["rule_code"] for f in engine["findings"]}
    decided = all_codes - set(engine["undetermined_codes"])
    agent_codes = rule_codes_in(agent_rules) & all_codes
    engine_codes = set(engine["hit_codes"])

    return {
        "agent_level": agent_level,
        "engine_level": engine["level"],
        "level_match": agent_level is not None and agent_level == engine["level"],
        "agent_codes": sorted(agent_codes),
        "agent_only": sorted((agent_codes & decided) - engine_codes),
        "engine_only": sorted(engine_codes - agent_codes),
        "agent_on_undetermined": sorted(agent_codes - decided),
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
    pending = [f for f in engine["findings"] if f["hit"] is None]

    hourly, minimum = facts["hourly_wage"], facts["applicable_min_wage"]

    if hourly is not None and minimum is not None:
        start = facts["contract_start_date"] or str(facts["contract_start_year"] or "시작일 미상")
        comparison = f"보다 {won(minimum - hourly)} 낮습니다" if hourly < minimum else " 이상입니다"
        first_sentence = f"시급 {won(hourly)}은 계약 시작일({start}) 기준 최저임금 {won(minimum)}{comparison}."
    else:
        first_sentence = "시급 또는 적용 최저임금을 확인하지 못했습니다."

    if hits:
        rest = "해당한 규칙: " + ", ".join(f["title"] for f in hits) + "."
    elif pending:
        rest = "판단하지 못한 규칙이 있어 안심이라고 단정하지 않습니다."
    else:
        rest = "점검 기준서의 규칙에 해당하는 항목이 없습니다."

    return {
        "review_level": engine["level"],
        "summary": f"{first_sentence} {rest}",
        "matched_rules": [f"{f['rule_code']} - {f['legal_basis']}" for f in hits],
        "missing_items": engine["missing_items"],
        "risky_clauses": [clause_note(f) for f in hits if f["rule_code"] not in ("LABOR_MIN_WAGE", "LABOR_MIN_WAGE_NEXT")],
        "confirmed_items": [RULE_PASS_TITLES.get(f["rule_code"], f["title"] + " 통과") for f in engine["findings"] if f["hit"] is False],
        "recommendations": [f["recommended_action"] for f in hits if f["recommended_action"]],
    }


def clause_note(finding: dict) -> str:

    if finding["clause"]:
        return f"\"{finding['clause']}\" → {finding['reason']}"

    return f"해당 조항 없음 - {finding['reason']}"


##################################################
# 최종 결과 조립
##################################################

def final_view(review: dict, engine: dict, agent_level: str | None, check: dict) -> dict:
    """
    평가 에이전트 결과와 규칙 계산을 합쳐 화면에 보여 줄 최종 결과를 만든다.

    - 등급: 두 판정 중 더 엄격한 쪽
    - 지적 규칙: 규칙 계산이 해당한다고 본 규칙 + 에이전트가 해당한다고 본 규칙
    - 요약·권장 행동·충족 항목: 최종 지적과 모순되지 않게 고친다
    """

    level = more_severe(agent_level, engine["level"])
    final_codes = set(engine["hit_codes"]) | set(check["agent_codes"])
    disagree = bool(check["agent_only"] or check["engine_only"]) or (agent_level is not None and agent_level != engine["level"])

    cards = []

    for f in engine["findings"]:

        if f["rule_code"] not in final_codes:
            continue

        card = dict(f)

        if f["rule_code"] in check["agent_codes"] and not f["hit"]:
            card["source"] = "agent"
            engine_note = "규칙 계산으로는 판단하지 못했습니다." if f["hit"] is None else f"규칙 계산에서는 통과로 나왔습니다({f['reason']})."
            card["reason"] = f"평가 에이전트가 이 규칙에 해당한다고 판단했습니다. {engine_note}"
        elif f["rule_code"] not in check["agent_codes"] and agent_level is not None:
            card["source"] = "engine"
        else:
            card["source"] = "both" if agent_level is not None else "engine"

        cards.append(card)

    cards.sort(key=lambda c: -LEVEL_SEVERITY.get(c["level"], 3))

    summary = review["summary"]
    notes = []

    if agent_level is not None and level != agent_level:
        notes.append(f"규칙 계산 결과를 반영해 등급을 '{LEVEL_LABELS[agent_level]}'에서 '{LEVEL_LABELS[level]}'(으)로 올렸습니다.")

    if check["engine_only"]:
        titles = ", ".join(RULE_TITLES.get(code, code) for code in check["engine_only"])
        notes.append(f"평가 에이전트가 놓친 항목: {titles}.")

    if notes:
        summary = " ".join(notes) + " " + summary

    recommendations = list(review["recommendations"])
    engine_actions = {f["rule_code"]: f["recommended_action"] for f in engine["findings"]}

    for code in check["engine_only"]:
        action = engine_actions.get(code)
        if action and action not in recommendations:
            recommendations.append(action)

    if disagree:
        confirmed = [
            RULE_PASS_TITLES.get(f["rule_code"], f["title"] + " 통과")
            for f in engine["findings"]
            if f["hit"] is False and f["rule_code"] not in final_codes
        ]
    else:
        confirmed = list(review["confirmed_items"])

    return {
        "level": level,
        "summary": summary,
        "cards": cards,
        # 근로자가 할 일 (에이전트 문장 + 에이전트가 놓친 규칙의 기준서 권장 행동)
        "recommendations": recommendations,
        # 사장님께 그대로 보낼 문장. 평가 에이전트가 사업주용으로 쓴 문장만 쓴다.
        "requests": list(review["recommendations"]) if agent_level is not None else [],
        "confirmed_items": confirmed,
        "missing_items": list(dict.fromkeys(engine["missing_items"] + review["missing_items"])),
        "pending": [f for f in engine["findings"] if f["hit"] is None and f["rule_code"] not in final_codes],
        "disagree": disagree,
    }
