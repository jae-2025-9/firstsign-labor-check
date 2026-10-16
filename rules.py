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

import math
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

# 코드가 구현한 점검 조건 (점검 기준서 v2). (조건 문장, 금액·연도 변경 허용 여부)
# 기준서의 조건 문장이 이 문장과 공백·문장부호를 빼고 정확히 같을 때만 코드가 판정한다.
# 최저임금 규칙만 금액과 기준 연도가 바뀌는 것을 허용한다(값은 기준서의 최저임금 항목에서 읽는다).
KNOWN_CONDITIONS = {
    "LABOR_MIN_WAGE": (
        "계약 시작일 기준 시급이 최저임금보다 낮다. 2026년 시작 계약은 10,320원, "
        "2027년 1월 1일 이후 시작 계약은 10,700원과 비교한다.",
        True,
    ),
    "LABOR_PENALTY": (
        "위약금, 손해배상액의 예정, 임금 공제, 부당한 퇴사 제한 등 불리한 조항이 있다.",
        False,
    ),
    "LABOR_REQUIRED_TERMS": (
        "법정 필수 기재사항 6가지(임금, 소정근로시간, 휴일, 연차유급휴가, 근무장소와 업무, 근로계약기간) "
        "중 하나라도 적혀 있지 않다. 단 1주 소정근로시간이 15시간 미만인 근로자는 휴일과 연차유급휴가 "
        "항목에 '해당 없음'이라고 적혀 있으면 적힌 것으로 본다.",
        False,
    ),
    "LABOR_BREAK": (
        "근로시간 4시간 이상 8시간 미만이면 휴게 30분 이상, 8시간 이상이면 휴게 1시간 이상이 없다. "
        "4시간 미만은 해당 없다. (2026-12-10부터 근로시간이 정확히 4시간이고 근로자가 명시적으로 "
        "휴게 미사용을 요청하면 예외)",
        False,
    ),
    "LABOR_WEEKLY_HOLIDAY": (
        "1주 소정근로시간이 15시간 이상인데 주휴일이 적혀 있지 않다. 1주 15시간 미만이면 해당 없다.",
        False,
    ),
    "LABOR_SIGN_COPY": (
        "사업주 또는 근로자의 서명·날인이 없거나, 계약서를 근로자에게 교부한다는 문구가 없다.",
        False,
    ),
    "LABOR_MIN_WAGE_NEXT": (
        "계약기간이 2027년 1월 1일 이후까지 이어지는데 시급이 2027년 최저임금 10,700원 미만이다. "
        "종료일이 없으면 이어진다고 본다.",
        True,
    ),
}

# KNOWN_CONDITIONS 문장이 쓰인 기준 연도
KNOWN_BASE_YEAR = 2026

# 통과 판정이 계약서 숫자·서명 값으로 정해지는 규칙. 규칙 계산이 통과로 확인했는데 평가 에이전트가
# 해당한다고 하면 등급에 넣지 않고 '의견 차이'로 따로 보여 준다.
# 위약금·필수 기재사항은 문장 해석이 필요해 에이전트 지적을 그대로 등급에 넣는다(놓치는 쪽이 더 해롭다).
DECISIVE_PASS_RULES = {"LABOR_MIN_WAGE", "LABOR_MIN_WAGE_NEXT", "LABOR_BREAK", "LABOR_WEEKLY_HOLIDAY", "LABOR_SIGN_COPY"}

# 2026-12-10 시행 근로기준법 제54조 개정: 정확히 4시간 근무에 근로자가 명시적으로 요청하면 휴게 없이 가능
BREAK_EXCEPTION_START = date(2026, 12, 10)

# 근로자가 휴게 미사용을 요청했다는 긍정 문장. 요청 주체가 근로자가 아니거나 부정이면 예외로 보지 않는다.
EXPLICIT_NO_BREAK_PATTERN = re.compile(r"근로자\s*(?:가|는|이|본인이|의)[^.()]{0,30}?(?:미사용|사용하지\s*않|없이|생략)[^.()]{0,15}?요청(?:함|하였|했|한다|하여|에\s*따라)")
NO_REQUEST_PATTERN = re.compile(r"요청\s*하지|요청\s*안|요청\s*없|요청이\s*없|(?:사용자|사업주|회사)\s*(?:가|는|이)[^.()]{0,30}?요청")

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

# 적혀 있지만 정해지지 않은 값 ("미정", "추후 결정", "협의한다")
UNDECIDED_PATTERN = re.compile(r"미정|추후|결정\s*되지|정하지\s*않|협의\s*(?:후|하여)?\s*(?:결정|정함|정한다)|협의한다|협의함|협의\s*예정")

# 불리한 조항은 의미와 부담 주체가 분명한 형태만 코드가 확정하고, 나머지는 평가 에이전트에 맡긴다.
# 1) 임금에서 떼는 조항: 근로자 부담이 문장 구조로 분명하다
WAGE_DEDUCTION_PATTERN = re.compile(r"(?:임금|급여|월급|시급|일당)\s*(?:에서|을|를)?\s*(?:공제|차감|감액|삭감|몰수)")

# 임금 공제의 목적. 손해·위약 목적이면 불리한 조항, 세금·보험료 정산이면 정상 공제다.
PENALTY_PURPOSE_PATTERN = re.compile(r"손해|위약|배상|변상|벌금|벌칙|지각|결근|파손|분실|실수|과실|퇴사")
STATUTORY_DEDUCTION_PATTERN = re.compile(r"세금|소득세|주민세|지방세|원천징수|보험료|4대\s*보험|사회보험|고용보험|건강보험|국민연금|산재보험")

# 2) 근로자가 주어인 위약금·배상 조항
WORKER_PAYS_PATTERN = re.compile(
    r"(?:근로자|을)\s*(?:은|는|이|가)\s*[^.]{0,40}?(?:위약금|위약|손해\s*배상|배상|변상|벌금)[^.]{0,20}?(?:지급|배상|변상|부담|물어|납부)"
)

# 판단을 보류할 핵심어 (주체·의미를 코드로 확정하지 않는다). 보험료·세금 공제는 정상 공제라 뺀다.
PENALTY_HINT_PATTERN = re.compile(
    r"위약|손해\s*배상|배상|변상|벌금|벌칙|몰수|감액|차감"
    r"|(?<!보험료\s)(?<!보험료)(?<!보험\s)(?<!보험)(?<!세금\s)(?<!세금)(?<!세\s)(?<!세)공제"
)

# 퇴사 제한처럼 핵심어 없이도 불리할 수 있는 문맥. 단독이면 판단을 보류한다.
RESIGN_PATTERN = re.compile(r"퇴사|퇴직|사직|그만\s*두|그만\s*둘|중도\s*해지")

NEGATION_PATTERN = re.compile(r"금지|않|아니|없|불가|못|면제|말아야|아님")

# 사업주가 근로자에게 주는 문장 ("회사가 근로자에게 손해배상금을 지급한다")
EMPLOYER_PAYS_PATTERN = re.compile(r"(?:회사|사업주|사용자|갑)\s*(?:은|는|이|가)[^.]{0,40}?근로자\s*에게")

# 교부 문구는 긍정형이 분명할 때만 충족으로 본다
COPY_POSITIVE_PATTERN = re.compile(
    r"근로자\s*에게\s*[^.]{0,20}?(?:교부|내어\s*준|전달|지급|제공)\s*(?:한다|함|하였다|했다|하기로\s*한다)"
    r"|(?:교부|내어\s*준|전달)\s*(?:한다|함|하였다|했다)[^.]{0,10}?근로자"
)

COPY_HINT_PATTERN = re.compile(r"교부|사본|근로자\s*에게\s*(?:1부|한\s*부)")

# 교부 행위 자체를 부정하는 표현만 거부로 본다 ("관계없이 교부한다"는 거부가 아니다)
COPY_REFUSAL_PATTERN = re.compile(
    r"교부\s*(?:를|는)?\s*하지|교부하지|교부\s*안|미교부|교부\s*불가"
    r"|교부(?:할|하는)?\s*의무(?:는|가)?\s*없|(?:주|제공하|전달하)지\s*(?:않|아니)"
)

# 상태값만 적힌 경우 ("없음", "주휴일 없음", "미정", "추후 결정", "협의")
FIELD_PREFIX = r"(?:주휴일|휴일|연차\s*유급\s*휴가|연차|임금\s*지급\s*방법|지급\s*방법|임금\s*지급일|지급일|근무\s*장소|업무(?:의)?\s*내용)?\s*(?:은|는|:)?\s*"
ABSENT_ONLY_PATTERN = re.compile(rf"^{FIELD_PREFIX}(?:없음|없다|없습니다|해당\s*(?:사항\s*)?없음|미부여|미지정|미기재)\s*\.?$")
UNDECIDED_ONLY_PATTERN = re.compile(rf"^{FIELD_PREFIX}(?:미정|추후\s*\S*|협의|추후\s*협의|협의\s*(?:후|하여)?\s*(?:결정|정함)|결정\s*예정|정하지\s*않음)\s*\.?$")

# 연차를 주거나 법에 따른다는 표현이 있으면 '사용일 협의'가 함께 있어도 적힌 것으로 본다
ANNUAL_GRANT_PATTERN = re.compile(r"부여|발생|사용할\s*수|근로기준법|제\s*60\s*조|법정|법에\s*따")

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


def criteria_rows(criteria: dict) -> list[dict]:
    """
    기준서 추출 결과의 check_rules 표를 행 목록으로 바꾼다.

    Studio는 표를 행 객체 목록으로 주기도 하고, 열마다 목록으로 주기도 한다.
    두 모양을 모두 받고, 열 목록의 빈 셀도 자리를 지켜 행이 어긋나지 않게 한다.
    """

    columns = ("rule_code", "check_condition", "category", "legal_basis", "recommended_action")
    raw = criteria.get("check_rules")

    if isinstance(raw, list) and raw and all(isinstance(item, dict) for item in raw):
        return raw

    if isinstance(raw, dict):
        length = max(
            (len(raw[c]) if isinstance(raw.get(c), (list, tuple)) else int(c in raw) for c in columns),
            default=0
        )
        return [{c: cell(raw.get(c), i) for c in columns} for i in range(length)]

    return []


def criteria_rules(criteria: dict) -> list[dict]:
    """
    기준서 추출 결과의 check_rules를 규칙 목록으로 바꾼다. 규칙 코드가 빈 행은 뺀다.
    """

    rules = []

    for row in criteria_rows(criteria):

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
    화면과 입력 PDF에 쓸 기준서 요약. 계산·PDF·화면이 모두 이 값을 쓴다.

    다음 해 최저임금 항목은 스키마에 연도(2027)가 고정되어 있어,
    기준 연도의 다음 해와 맞지 않으면 다른 연도 금액으로 쓰지 않도록 비운다.
    """

    base_year = criteria_base_year(criteria)
    next_raw = to_number(criteria.get(NEXT_MIN_WAGE_FIELD))
    next_ok = base_year is not None and base_year + 1 == NEXT_MIN_WAGE_YEAR

    return {
        "name": text(criteria.get("criteria_name")),
        "version": text(criteria.get("criteria_version")),
        "base_year": base_year,
        "required_items": [str(item) for item in as_list(criteria.get("required_items"))],
        "min_wage_current": to_number(criteria.get("min_wage_hourly")),
        "min_wage_next": next_raw if next_ok else None,
        "min_wage_next_year": NEXT_MIN_WAGE_YEAR if next_ok else None,
        "min_wage_next_dropped": next_raw is not None and not next_ok,
        "legal_basis": [str(item) for item in as_list(criteria.get("legal_basis"))],
        "rules": criteria_rules(criteria),
    }


def criteria_problems(criteria: dict, source_codes: set[str] | None = None) -> list[str]:
    """
    기준서 추출 결과로 점검을 할 수 없는 이유. 비어 있으면 쓸 수 있다.

    source_codes는 기준서 PDF 원문에서 직접 읽은 규칙 코드 목록이다.
    추출 결과와 대조해 규칙이 빠지거나 더 생기지 않았는지 본다.
    """

    summary = summarize_criteria(criteria)
    codes = [rule["rule_code"] for rule in summary["rules"]]
    problems = []

    if not codes:
        problems.append("점검 규칙 표를 읽지 못했습니다")

    blank = sum(1 for row in criteria_rows(criteria) if not str(first(row.get("rule_code"), "")).strip())

    if blank:
        problems.append(f"규칙 코드가 비어 있는 행이 {blank}개 있습니다")

    duplicates = sorted({code for code in codes if codes.count(code) > 1})

    if duplicates:
        problems.append("규칙 코드가 중복됐습니다: " + ", ".join(duplicates))

    if source_codes is not None:
        missing = sorted(set(source_codes) - set(codes))
        extra = sorted(set(codes) - set(source_codes))
        if missing:
            problems.append("기준서 원문에 있는데 추출 결과에서 빠진 규칙: " + ", ".join(missing))
        if extra:
            problems.append("기준서 원문에 없는 규칙 코드가 추출됐습니다: " + ", ".join(extra))

    if summary["min_wage_current"] is None:
        problems.append("최저임금 금액을 읽지 못했습니다")

    if summary["base_year"] is None:
        problems.append("기준서의 기준 연도를 읽지 못했습니다")

    return problems


def apply_source_conditions(criteria: dict, source_conditions: dict[str, str] | None) -> tuple[dict, list[str]]:
    """
    기준서 PDF 원문에서 읽은 점검 조건으로 추출 결과의 조건 문장을 바로잡는다.

    표 칸이 페이지를 넘어가면 Criteria Agent가 조건 문장 끝을 놓칠 수 있다("…미만이다. 종료").
    공백·문장부호를 지운 모양이 원문과 다른 규칙만 원문 문장으로 바꾸고, 바꾼 규칙 코드를 돌려준다.
    원문을 읽지 못했으면 그대로 둔다.
    """

    if not source_conditions:
        return criteria, []

    rows, repaired = [], []

    for row in criteria_rows(criteria):

        row = dict(row)
        code = str(first(row.get("rule_code"), "")).strip()
        source = source_conditions.get(code)

        if source and condition_shape(source) != condition_shape(text(row.get("check_condition"))):
            row["check_condition"] = source
            repaired.append(code)

        rows.append(row)

    if not repaired:
        return criteria, []

    return {**criteria, "check_rules": rows}, repaired


##################################################
# 점검 조건 비교
##################################################

def condition_shape(sentence: str, base_year: int | None = None, allow_amounts: bool = False) -> str:
    """
    공백·줄바꿈·문장부호를 지운 조건 문장.

    공백과 줄바꿈을 먼저 지운 뒤 비교한다(PDF 표 셀의 "2026\n년", "1\n0,320" 대응).
    allow_amounts이면 금액을 AMOUNT로, 기준 연도와 다음 해를 BASEYEAR·NEXTYEAR로 바꿔
    해마다 금액만 바뀌는 최저임금 규칙을 같은 조건으로 본다. 그 밖의 숫자·낱말은 그대로 비교한다.
    """

    s = re.sub(r"\s+", "", sentence)

    if allow_amounts:
        s = re.sub(r"\d{1,3}(?:,\d{3})+원|\d{4,}원", "AMOUNT원", s)
        if base_year:
            s = s.replace(f"{base_year + 1}년", "NEXTYEAR년").replace(f"{base_year}년", "BASEYEAR년")

    return re.sub(r"[\W_]+", "", s)



def condition_supported(rule: dict, base_year: int | None = None) -> tuple[bool, str]:
    """
    기준서의 점검 조건이 코드가 구현한 조건과 같은지 본다.

    유사도가 아니라 정확히 같은지만 본다. "이상→초과", "낮다→높다", "1월 1일→7월 1일"처럼
    한두 글자로 의미가 바뀔 수 있어서다. 다르면 코드는 판단하지 않고 평가 에이전트를 따른다.
    """

    known = KNOWN_CONDITIONS.get(rule["rule_code"])

    if known is None:
        return False, "코드에 판정 로직이 없는 규칙입니다. 평가 에이전트의 판단을 따릅니다."

    if not rule["check_condition"]:
        return False, "기준서에서 이 규칙의 점검 조건을 읽지 못해 코드로 판단하지 않습니다."

    sentence, allow_amounts = known

    if condition_shape(sentence, KNOWN_BASE_YEAR, allow_amounts) != condition_shape(rule["check_condition"], base_year, allow_amounts):
        return False, "기준서의 점검 조건 문장이 코드가 구현한 조건과 정확히 같지 않아 코드로 판단하지 않습니다. 평가 에이전트의 판단을 따릅니다."

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
    알 수 없거나 앞뒤가 맞지 않는 값은 None으로 두고 notes에 이유를 남긴다. 임의의 기준으로 채우지 않는다.
    """

    notes: list[str] = []
    summary = summarize_criteria(criteria)

    # 1일 근로시간: 시작·종료 시각이 한 쌍으로 분명할 때만 계산한다
    start_times = parse_times(contract.get("work_start_time"))
    end_times = parse_times(contract.get("work_end_time"))

    if len(start_times) == 2 and not end_times:
        start_times, end_times = start_times[:1], start_times[1:]
    elif len(end_times) == 2 and not start_times:
        start_times, end_times = end_times[:1], end_times[1:]

    span_minutes = None

    if len(start_times) == 1 and len(end_times) == 1:
        span_minutes = (end_times[0] - start_times[0]) % 1440 or None
    elif start_times or end_times:
        notes.append("소정근로 시각이 여러 개라 어느 시작과 종료가 짝인지 알 수 없어 근로시간을 계산하지 않았습니다.")
    else:
        notes.append("소정근로 시작·종료 시각을 읽지 못해 근로시간을 계산하지 못했습니다.")

    break_stated, break_minutes = parse_break(contract.get("break_time"))
    daily_work_minutes = None

    if span_minutes is not None:
        if break_stated and break_minutes is None:
            notes.append("휴게시간 문구에서 길이를 읽지 못해 근로시간을 계산하지 않았습니다.")
        elif (break_minutes or 0) >= span_minutes:
            notes.append("휴게시간이 출근부터 퇴근까지의 시간보다 길거나 같아 근로시간을 계산하지 않았습니다.")
        else:
            daily_work_minutes = span_minutes - (break_minutes or 0)

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

    if summary["min_wage_next_dropped"]:
        notes.append(f"기준서 기준 연도({base_year})가 Criteria Agent 스키마의 다음 해 항목({NEXT_MIN_WAGE_FIELD})과 맞지 않아 다음 해 최저임금을 쓰지 않았습니다.")

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
            notes.append(f"계약이 {base_year + 1}년에 시작하는데 기준서에서 그해 최저임금을 확정하지 못했습니다.")
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

    부담 주체·목적이 문장 구조로 분명한 두 형태만 불리한 조항으로 확정한다.
    - 손해·위약·지각 같은 목적으로 임금에서 공제·차감하는 조항
    - 근로자가 주어로 위약금·배상금을 지급·부담하는 조항
    세금·보험료만 떼는 조항은 정상 공제로 본다. 목적이 섞였거나 없거나, 부정·금지 표현이 있거나,
    회사가 주는 문장이거나, 핵심어만 있으면 판단을 보류한다.
    """

    hits, unclear = [], []

    for clause in (str(item) for item in as_list(contract.get("special_terms"))):

        negated = NEGATION_PATTERN.search(clause)
        employer_pays = EMPLOYER_PAYS_PATTERN.search(clause)
        statutory = STATUTORY_DEDUCTION_PATTERN.search(clause)
        purpose = PENALTY_PURPOSE_PATTERN.search(clause)
        deduction = WAGE_DEDUCTION_PATTERN.search(clause)
        worker_pays = WORKER_PAYS_PATTERN.search(clause)

        if deduction and statutory and not purpose and not worker_pays:
            continue

        clear = (deduction and purpose and not statutory) or worker_pays

        if clear and not negated and not employer_pays:
            hits.append(clause)
        elif deduction or worker_pays or PENALTY_HINT_PATTERN.search(clause) or RESIGN_PATTERN.search(clause):
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


def field_core(value) -> str:
    """
    괄호 안 보충 설명을 뺀 값. "매주 일요일 (변경 없음)" → "매주 일요일"
    """

    core = re.sub(r"\([^)]*\)", " ", text(value)).strip()

    return core or text(value)


def field_state(value) -> str:
    """
    blank(비어 있음) / absent(상태값 "없음") / undecided(상태값 "미정"·"협의") / written(그 밖의 기재)
    """

    if is_blank(value) or not text(value):
        return "blank"

    core = field_core(value)

    if ABSENT_ONLY_PATTERN.match(core):
        return "absent"

    if UNDECIDED_ONLY_PATTERN.match(core):
        return "undecided"

    return "written"


def required_missing(contract, facts: dict | None = None) -> tuple[list[str], list[str]]:
    """
    필수 기재사항 중 (적혀 있지 않은 항목, 적힌 것인지 확정할 수 없는 항목)

    값 전체가 상태값("없음", "미정", "추후 결정", "협의")일 때만 적히지 않은 것으로 본다.
    "사용일은 협의하여 정한다", "매주 일요일 (변경 없음)"처럼 설명 문장 안의 낱말로는 판단하지 않는다.
    휴일·연차의 "해당 없음"·"없음"은 1주 15시간 미만일 때만 적힌 것으로 본다(기준서 v2).
    """

    facts = facts or {}
    weekly = facts.get("weekly_hours")
    missing, unclear = [], []

    def state(field: str) -> str:
        return field_state(contract.get(field))

    if is_blank(contract.get("wage_amount")):
        missing.append("임금(금액)")

    for field, name in (("wage_type", "임금(시급·일급·월급 구분)"), ("wage_payment_date", "임금지급일"), ("wage_payment_method", "임금지급방법")):
        if state(field) != "written":
            missing.append(name)

    if is_blank(contract.get("work_start_time")) or is_blank(contract.get("work_end_time")):
        missing.append("소정근로시간")

    for field, name in (("weekly_holiday", "휴일(주휴일)"), ("annual_leave_clause", "연차유급휴가")):

        current = state(field)

        if current in ("blank", "undecided"):
            missing.append(name)
        elif current == "absent":
            if weekly is None:
                unclear.append(name)
            elif weekly >= 15:
                missing.append(name)
        elif field == "annual_leave_clause" and UNDECIDED_PATTERN.search(field_core(contract.get(field))) \
                and not ANNUAL_GRANT_PATTERN.search(field_core(contract.get(field))):
            # "회사 사정에 따라 협의한다"처럼 연차를 준다는 말 없이 협의만 적힌 경우
            unclear.append(name)

    for field, name in (("workplace", "근무장소"), ("job_description", "업무의 내용")):
        if state(field) != "written":
            missing.append(name)

    if is_blank(contract.get("contract_start_date")):
        missing.append("근로계약기간")

    return missing, unclear


def check_required_terms(contract, facts):

    missing, unclear = required_missing(contract, facts)

    if missing:
        return True, "계약서에 적혀 있지 않거나 정해지지 않은 필수 기재사항: " + ", ".join(missing), ", ".join(missing) + " 없음", "6개 항목 모두 기재"

    if unclear:
        reason = "1주 소정근로시간을 계산하지 못해 '" + ", ".join(unclear) + "'의 '해당 없음' 표기가 맞는지 확정하지 못했습니다."
        return None, reason, ", ".join(unclear) + " 확인 필요", "6개 항목 모두 기재"

    return False, "필수 기재사항이 모두 적혀 있습니다.", "모두 기재", "6개 항목 모두 기재"


def check_break(contract, facts):

    span = facts["daily_span_minutes"]

    if span is None or facts["daily_work_hours"] is None:
        return None, "근로시간을 알 수 없거나 앞뒤가 맞지 않아 휴게시간 기준을 판단하지 못했습니다.", text(contract.get("break_time")) or "-", "-"

    rest = facts["break_minutes"] or 0
    work = span - rest
    required = 60 if work >= 480 else 30 if work >= 240 else 0
    current = f"근로 {work / 60:g}시간, 휴게 {rest}분" + ("" if facts["break_stated"] else "(미기재)")

    if required == 0:
        return False, "1일 근로시간이 4시간 미만이라 해당 없습니다.", current, "4시간 미만 해당 없음"

    standard = f"휴게 {required}분 이상"

    if rest >= required:
        return False, f"1일 근로시간 {work / 60:g}시간에 휴게 {rest}분이 있습니다.", current, standard

    if work == 240 and rest == 0:

        break_text = text(contract.get("break_time"))
        explicit = bool(EXPLICIT_NO_BREAK_PATTERN.search(break_text)) and not NO_REQUEST_PATTERN.search(break_text)
        start = to_date(contract.get("contract_start_date"))

        if explicit and start is not None and start >= BREAK_EXCEPTION_START:
            reason = f"정확히 4시간 근무이고 근로자가 휴게 미사용을 명시적으로 요청해 {BREAK_EXCEPTION_START.isoformat()}부터의 예외에 해당합니다."
            return False, reason, current, standard

        if explicit:
            reason = f"근로자의 휴게 미사용 요청이 적혀 있지만, 예외는 {BREAK_EXCEPTION_START.isoformat()}부터 적용됩니다. 그 전 근무에는 휴게 30분이 필요합니다."
        else:
            reason = f"1일 근로시간 4시간에는 휴게 30분이 필요합니다. {BREAK_EXCEPTION_START.isoformat()}부터는 근로자가 명시적으로 요청하면 휴게 없이 일할 수 있으나, 계약서에 그런 요청이 적혀 있지 않습니다."

        return True, reason, current, standard

    return True, f"1일 근로시간 {work / 60:g}시간에는 {standard}이 필요한데 휴게가 {rest}분입니다.", current, standard


def holiday_specified(contract) -> bool | None:
    """
    주휴일이 정해져 있는지. True(요일이 적힘) / False(비어 있거나 "없음") / None(뜻을 확정할 수 없음)
    """

    current = field_state(contract.get("weekly_holiday"))

    if current in ("blank", "absent", "undecided"):
        return False

    core = field_core(contract.get("weekly_holiday"))

    if re.search(r"[월화수목금토일]\s*요일|(?<![가-힣])[월화수목금토일](?![가-힣])|매주", core):
        return True

    return None


def check_weekly_holiday(contract, facts):

    weekly = facts["weekly_hours"]
    current = text(contract.get("weekly_holiday")) or "(비어 있음)"
    standard = "주 15시간 이상이면 주휴일 기재"
    specified = holiday_specified(contract)

    if specified:
        return False, "주휴일이 적혀 있습니다.", current, standard

    if weekly is not None and weekly < 15:
        return False, f"1주 소정근로시간이 {weekly:g}시간으로 15시간 미만이라 해당 없습니다.", current, standard

    if specified is None:
        return None, "주휴일 문구에 요일이 없어 주휴일이 정해졌는지 코드로 확정할 수 없습니다.", current, standard

    if weekly is None:
        return None, "1주 소정근로시간을 계산하지 못했는데 주휴일이 정해져 있지 않습니다. 15시간 이상이면 해당합니다.", current, standard

    return True, f"1주 소정근로시간이 {weekly:g}시간으로 15시간 이상인데 주휴일이 정해져 있지 않습니다.", current, standard


def copy_clause_status(contract) -> str:
    """
    교부 문구 상태: ok(긍정형이 분명함) / missing(비어 있음) / negated(교부 행위를 부정) / unclear(뜻을 확정할 수 없음)

    "관계없이", "없이"처럼 교부 행위를 꾸미지 않는 부정어는 거부로 보지 않는다.
    """

    clause = text(contract.get("copy_delivery_clause"))

    if not clause:
        return "missing"

    if COPY_REFUSAL_PATTERN.search(clause):
        return "negated"

    if COPY_POSITIVE_PATTERN.search(clause):
        return "ok"

    if not COPY_HINT_PATTERN.search(clause):
        return "missing"

    return "unclear"


def check_sign_copy(contract, facts):

    signed = to_bool(contract.get("is_signed"))
    copy = copy_clause_status(contract)

    if copy == "unclear" and signed is True:
        return None, "교부 문구의 뜻을 코드로 확정할 수 없어 평가 에이전트의 판단을 따릅니다.", "서명 있음, 교부 문구 확인 필요", "양측 서명 + 교부 문구"

    problems = []

    if signed is not True:
        problems.append("사업주·근로자 서명 확인 안 됨")

    if copy in ("missing", "negated"):
        problems.append("근로자에게 계약서를 교부한다는 문구 없음" if copy == "missing" else "교부하지 않는다는 취지의 문구")

    copy_text = {"ok": "있음", "missing": "없음", "negated": "부정형", "unclear": "확인 필요"}[copy]
    current = f"서명 {'있음' if signed else '없음/불명'}, 교부 문구 {copy_text}"

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
    규칙 결과로 종합 등급을 정한다. 모든 규칙을 판단했을 때만 등급을 낸다.

    판단 보류가 있으면 안심이라고 하지 않는다. 위험 규칙에 해당하면 다른 규칙과 상관없이 위험이다.
    확정된 위반의 최소 등급은 confirmed_min_level이 따로 계산한다.
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


def confirmed_min_level(findings: list[dict]) -> str | None:
    """
    확정된 지적(hit=True) 중 가장 엄격한 기준서 분류. 판단 보류가 있어도 이보다 낮은 등급은 나오면 안 된다.
    """

    return more_severe(*(f["level"] for f in findings if f["hit"]))


def missing_items(contract: dict, facts: dict) -> list[str]:
    """
    화면에 보여 줄 계약서에 없는 항목 (필수 기재사항 + 휴게시간 + 서명·교부)
    """

    items, _ = required_missing(contract, facts)

    if not facts["break_stated"]:
        items.append("휴게시간")

    if to_bool(contract.get("is_signed")) is not True:
        items.append("사업주·근로자 서명")

    if copy_clause_status(contract) in ("missing", "negated"):
        items.append("계약서 교부 문구")

    return items


def evaluate(contract: dict, criteria: dict, facts: dict | None = None, source_codes: set[str] | None = None) -> dict:
    """
    기준서의 규칙을 계약 정보에 하나씩 적용한다.

    source_codes(기준서 PDF 원문의 규칙 코드)를 주면 추출 결과에 빠진 규칙이 없는지 함께 본다.
    기준서에 문제가 있으면 종합 등급을 내지 않는다.
    """

    facts = facts or compute_facts(contract, criteria)
    summary = summarize_criteria(criteria)
    problems = criteria_problems(criteria, source_codes)
    findings = []

    for rule in summary["rules"]:

        code = rule["rule_code"]
        supported, why = condition_supported(rule, summary["base_year"])

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
    level = overall_level(findings) if is_contract and not problems else None

    return {
        "level": level,
        "min_level": confirmed_min_level(findings) if is_contract else None,
        "is_contract": is_contract,
        "findings": findings,
        "hit_codes": [f["rule_code"] for f in findings if f["hit"]],
        "undetermined_codes": [f["rule_code"] for f in findings if f["hit"] is None],
        "missing_items": missing_items(contract, facts),
        "criteria_problems": problems,
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

    status:
    - match: 둘 다 등급을 냈고 등급과 (코드가 판단한) 해당 규칙이 같다
    - mismatch: 등급이나 해당 규칙이 다르다
    - partial: 에이전트 등급은 있지만 규칙 계산이 일부 규칙을 판단하지 못해 끝까지 비교하지 못했다
    - unavailable: 에이전트 분류가 없다

    agent_codes는 기준서에 있는 규칙 중 에이전트가 해당한다고 본 전체 목록이다.
    agent_only / engine_only는 코드가 판단한 규칙만 비교한다.
    """

    all_codes = {f["rule_code"] for f in engine["findings"]}
    decided = all_codes - set(engine["undetermined_codes"])
    agent_codes = rule_codes_in(agent_rules) & all_codes
    engine_codes = set(engine["hit_codes"])
    agent_only = sorted((agent_codes & decided) - engine_codes)
    engine_only = sorted(engine_codes - agent_codes)

    if agent_level is None:
        status = "unavailable"
    elif agent_only or engine_only or (engine["level"] is not None and agent_level != engine["level"]):
        status = "mismatch"
    elif engine["level"] is None:
        status = "partial"
    else:
        status = "match"

    return {
        "status": status,
        "agent_level": agent_level,
        "engine_level": engine["level"],
        "level_match": status == "match",
        "agent_codes": sorted(agent_codes),
        "agent_only": agent_only,
        "engine_only": engine_only,
        "agent_on_undetermined": sorted(agent_codes - decided),
        "undetermined": sorted(all_codes - decided),
    }


##################################################
# 규칙 계산 결과를 평가 결과 모양으로
##################################################

def compose_summary(
    engine: dict,
    hits: list[dict],
    level: str | None,
    incomplete: bool,
    agent_level: str | None = None,
    disputed: list[dict] | None = None
) -> str:
    """
    최종 판정으로 요약을 다시 쓴다. 첫 문장은 시급과 적용 최저임금 비교다.
    """

    facts = engine["facts"]
    hourly, minimum = facts["hourly_wage"], facts["applicable_min_wage"]

    if hourly is not None and minimum is not None:
        start = facts["contract_start_date"] or str(facts["contract_start_year"] or "시작일 미상")
        comparison = f"보다 {won(minimum - hourly)} 낮습니다" if hourly < minimum else " 이상입니다"
        sentences = [f"시급 {won(hourly)}은 계약 시작일({start}) 기준 최저임금 {won(minimum)}{comparison}."]
    else:
        sentences = ["시급 또는 적용 최저임금을 확인하지 못했습니다."]

    if hits:
        sentences.append("해당한 규칙: " + ", ".join(f["title"] for f in hits) + ".")
    elif level == "safe":
        sentences.append("점검 기준서의 규칙에 해당하는 항목이 없습니다.")

    if incomplete:
        sentences.append("판단하지 못한 규칙이 있어 등급을 확정하지 않았습니다." if level is None else f"판단하지 못한 규칙이 있어 최소 '{LEVEL_LABELS[level]}'입니다.")

    if disputed:
        sentences.append(
            "평가 에이전트가 지적한 " + ", ".join(f["title"] for f in disputed)
            + " 항목은 계약서 값으로 계산하면 해당하지 않아 등급에 넣지 않았습니다."
        )

    if agent_level is not None and level is not None and agent_level != level:
        if LEVEL_SEVERITY[agent_level] < LEVEL_SEVERITY[level]:
            basis = "해당 규칙의 기준서 분류에 맞춰"
        elif hits:
            basis = "근거 규칙의 기준서 분류에 맞춰"
        elif disputed:
            basis = "근거로 든 규칙이 계약서 값으로 해당하지 않아"
        else:
            basis = "기준서 규칙에서 근거를 찾지 못해"
        sentences.append(f"평가 에이전트는 '{LEVEL_LABELS[agent_level]}'(으)로 판단했지만, {basis} '{LEVEL_LABELS[level]}'(으)로 표시합니다.")
    elif agent_level is not None and level not in (None, "safe") and not hits:
        sentences.append("해당한다고 확정한 규칙은 없지만 평가 에이전트가 확인이 필요하다고 판단했습니다.")

    return " ".join(sentences)


def engine_review(engine: dict) -> dict:
    """
    평가 에이전트를 부를 수 없을 때(데모 모드) 규칙 계산 결과로
    평가 에이전트와 같은 모양의 결과를 만든다.
    """

    hits = [f for f in engine["findings"] if f["hit"]]

    return {
        "review_level": engine["level"],
        "summary": compose_summary(engine, hits, engine["level"], incomplete=engine["level"] is None),
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

    - 지적 규칙(카드): 규칙 계산이 해당한다고 본 규칙 + 에이전트가 해당한다고 본 규칙.
      단 규칙 계산이 계약서 숫자·서명 값으로 통과를 확인한 규칙(DECISIVE_PASS_RULES)은
      에이전트가 지적해도 카드에 넣지 않고 '의견 차이'(disputed)로 따로 둔다.
    - 등급: 기준서가 정한다. 카드들의 기준서 분류 중 가장 엄격한 것이다.
      에이전트가 분류했으면 규칙 계산이 판단하지 못한 규칙은 에이전트 판단을 따르고
      (지적했으면 카드, 아니면 해당 없음), 근거 규칙 없이 더 엄격하게 분류했으면 '확인 필요'까지만 올린다.
      에이전트 분류가 없으면 규칙 계산 전체 판정을 쓰고, 그것도 없으면 확정된 지적의 최소 등급만 낸다.
      어느 경우든 확정된 지적보다 낮은 등급은 나오지 않는다.
    - incomplete: 등급을 확정할 판단(에이전트 분류 또는 규칙 계산 전체 판정)이 없음.
      교차 검증이 끝까지 됐는지는 check["status"]가 따로 알려 준다.
    - 요약: 항상 최종 구조화 결과로 다시 쓴다. 에이전트가 쓴 요약은 agent_summary로 따로 둔다.
    """

    agent_codes = set(check["agent_codes"])
    disputed_codes = {
        f["rule_code"] for f in engine["findings"]
        if f["rule_code"] in agent_codes and f["hit"] is False and f["rule_code"] in DECISIVE_PASS_RULES
    }
    final_codes = (set(engine["hit_codes"]) | agent_codes) - disputed_codes
    cards, disputed = [], []

    for f in engine["findings"]:

        if f["rule_code"] in disputed_codes:
            disputed.append({
                **f,
                "source": "agent",
                "reason": f"평가 에이전트는 해당한다고 봤지만, 계약서 값으로 계산하면 해당하지 않습니다. {f['reason']}",
            })
            continue

        if f["rule_code"] not in final_codes:
            continue

        card = dict(f)

        if f["rule_code"] in agent_codes and not f["hit"]:
            card["source"] = "agent"
            engine_note = "규칙 계산으로는 판단하지 못했습니다." if f["hit"] is None else f"규칙 계산에서는 통과로 나왔습니다({f['reason']})."
            card["reason"] = f"평가 에이전트가 이 규칙에 해당한다고 판단했습니다. {engine_note}"
        elif f["rule_code"] not in agent_codes and agent_level is not None:
            card["source"] = "engine"
        else:
            card["source"] = "both" if agent_level is not None else "engine"

        cards.append(card)

    cards.sort(key=lambda c: -LEVEL_SEVERITY.get(c["level"], 3))

    card_level = more_severe(*(c["level"] for c in cards if c["level"] in LEVEL_SEVERITY))

    if agent_level is not None:
        level = card_level or "safe"
        if level == "safe" and agent_level != "safe" and not disputed:
            # 기준서 규칙으로 근거를 대지 못한 경고는 직접 확인하도록 '확인 필요'까지만 반영한다.
            # 근거로 든 규칙이 모두 계약서 값으로 해당하지 않으면(disputed) 경고의 근거가 없다.
            level = "check_needed"
        incomplete = False
    elif engine["level"] is not None:
        level = more_severe(engine["level"], card_level)
        incomplete = False
    else:
        # 등급을 확정할 판단이 없다. 확정된 지적이 있으면 그 최소 등급만 보여 주고 보류를 알린다.
        level = card_level
        incomplete = True

    disagree = check["status"] == "mismatch" or (agent_level is not None and agent_level != level)

    # 해당 규칙이 없다고 결론 났으면 에이전트가 쓴 요청 문장은 쓰지 않는다(근거 없는 요청이 된다)
    agent_text = agent_level is not None and level != "safe"

    recommendations = list(review["recommendations"]) if (agent_text or agent_level is None) else []
    engine_actions = {f["rule_code"]: f["recommended_action"] for f in engine["findings"]}

    for code in check["engine_only"]:
        action = engine_actions.get(code)
        if action and action not in recommendations:
            recommendations.append(action)

    if disagree or agent_level is None:
        confirmed = [
            RULE_PASS_TITLES.get(f["rule_code"], f["title"] + " 통과")
            for f in engine["findings"]
            if f["hit"] is False and f["rule_code"] not in final_codes
        ]
    else:
        confirmed = list(review["confirmed_items"])

    return {
        "level": level,
        "incomplete": incomplete,
        "summary": compose_summary(engine, cards, level, incomplete=incomplete, agent_level=agent_level, disputed=disputed),
        "agent_summary": review["summary"] if agent_level is not None else "",
        "cards": cards,
        # 근로자가 할 일 (에이전트 문장 + 에이전트가 놓친 규칙의 기준서 권장 행동)
        "recommendations": recommendations,
        # 사장님께 그대로 보낼 문장. 평가 에이전트가 사업주용으로 쓴 문장만 쓴다.
        "requests": list(review["recommendations"]) if agent_text else [],
        "confirmed_items": confirmed,
        "missing_items": list(dict.fromkeys(engine["missing_items"] + review["missing_items"])),
        "pending": [f for f in engine["findings"] if f["hit"] is None and f["rule_code"] not in final_codes],
        # 에이전트는 지적했지만 규칙 계산이 계약서 값으로 통과를 확인한 규칙 (등급에 넣지 않음)
        "disputed": disputed,
        "disagree": disagree,
    }
