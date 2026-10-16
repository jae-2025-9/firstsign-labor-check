"""
review_builder.py

contract.json + criteria.json → Review_Input.pdf

Studio 에이전트는 문서 파일만 입력받는다. 두 JSON을 평가 에이전트에 넘기려면
코드가 PDF 한 장으로 다시 조립해야 한다 (플레이북 1-6).

1부. 근로계약 정보 (계약서 추출 결과)
2부. 점검 기준 (기준서 추출 결과)
3부. 계산 보조값 (코드가 1부로 계산한 숫자. 판정은 평가 에이전트가 한다)
"""

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle
)

from config import (
    FONT_NAME,
    FONT_PATH
)
from file_manager import ensure_directory
from rules import (
    amount_candidates,
    as_list,
    is_blank,
    summarize_criteria,
    text,
    to_bool,
    to_number,
    won
)

##################################################
# Font
##################################################

if FONT_NAME not in pdfmetrics.getRegisteredFontNames():

    pdfmetrics.registerFont(
        TTFont(FONT_NAME, str(FONT_PATH))
    )

##################################################
# Styles
##################################################

TITLE_STYLE = ParagraphStyle("Title", fontName=FONT_NAME, fontSize=16, leading=22, spaceAfter=6)

HEADING_STYLE = ParagraphStyle("Heading", fontName=FONT_NAME, fontSize=12.5, leading=18, spaceBefore=12, spaceAfter=6)

BODY_STYLE = ParagraphStyle("Body", fontName=FONT_NAME, fontSize=9.5, leading=14)

CELL_STYLE = ParagraphStyle("Cell", fontName=FONT_NAME, fontSize=9.5, leading=13)

##################################################
# 1부 항목 (Contract Agent 스키마 순서)
##################################################

CONTRACT_LABELS = [
    ("employer_name", "사업주"),
    ("employee_name", "근로자"),
    ("contract_start_date", "근로계약기간 시작일"),
    ("contract_end_date", "근로계약기간 종료일"),
    ("workplace", "근무장소"),
    ("job_description", "업무의 내용"),
    ("work_days", "근무일"),
    ("work_start_time", "소정근로 시작 시각"),
    ("work_end_time", "소정근로 종료 시각"),
    ("break_time", "휴게시간"),
    ("weekly_holiday", "주휴일"),
    ("wage_type", "임금 구분"),
    ("wage_amount", "임금 금액(원)"),
    ("wage_payment_date", "임금지급일"),
    ("wage_payment_method", "임금지급방법"),
    ("annual_leave_clause", "연차유급휴가"),
    ("social_insurance", "사회보험"),
    ("copy_delivery_clause", "계약서 교부 문구"),
    ("special_terms", "특약사항"),
    ("is_signed", "서명 여부(사업주·근로자 모두 서명)"),
]

EMPTY = "(비어 있음)"

# 이보다 길거나 줄이 많은 값은 표 밖 문단으로 적는다. 특약은 길이와 상관없이 항상 표 밖에 적는다.
LONG_VALUE_CHARS = 300
LONG_VALUE_LINES = 6
ALWAYS_OUTSIDE = {"special_terms"}


##################################################
# Helpers
##################################################

def p(value, style=BODY_STYLE) -> Paragraph:

    return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)


def contract_value(contract: dict, key: str) -> str:
    """
    1부에 적을 값. 비어 있으면 "(비어 있음)"으로 적어 누락의 근거가 되게 한다.
    """

    value = contract.get(key)
    raw = " / ".join(str(item) for item in as_list(value) if not is_blank(item))

    if key == "is_signed":
        signed = to_bool(value)
        if signed is None:
            return f"{raw} (예/아니오로 정하지 못함)" if raw else EMPTY
        return "예" if signed else "아니오"

    if key == "wage_amount":
        # 숫자 하나로 정해질 때만 숫자로 적고, 그 밖에는 추출 원문을 그대로 적어 판단 근거를 남긴다
        number = to_number(value)
        plain = all(isinstance(item, (int, float)) or re.fullmatch(r"[\d,.\s]+원?", str(item)) for item in as_list(value) if not is_blank(item))
        if number is not None and plain:
            return f"{number:.0f}"
        if not raw:
            return EMPTY
        return raw if number is not None and len(amount_candidates(value)) <= 1 else f"{raw} (금액을 하나로 정하지 못함)"

    if key == "special_terms":
        return " / ".join(str(item) for item in as_list(value)) or "없음"

    return text(value) or EMPTY


def yes_no(value) -> str:

    return "판단 불가" if value is None else ("예" if value else "아니오")


##################################################
# Sections
##################################################

def add_contract(story: list, contract: dict):
    """
    표 셀은 페이지를 넘어 나뉘지 않는다. 긴 값(특약 등)은 표에는 안내만 적고
    표 아래에 문단으로 원문 전체를 적어, 판정 근거를 자르지 않고 PDF 생성도 실패하지 않게 한다.
    """

    story.append(p("1부. 근로계약 정보 (계약서 추출 결과)", HEADING_STYLE))

    rows, long_values = [], []

    for key, label in CONTRACT_LABELS:

        value = contract_value(contract, key)

        outside = key in ALWAYS_OUTSIDE and value not in ("없음", EMPTY)

        if outside or len(value) > LONG_VALUE_CHARS or value.count("\n") >= LONG_VALUE_LINES:
            long_values.append((label, value))
            value = "(표 아래 '긴 항목 원문'에 적음)"

        rows.append([p(label, CELL_STYLE), p(value, CELL_STYLE)])

    table = Table(rows, colWidths=[5.2 * cm, 11.8 * cm], repeatRows=0)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    story.append(table)

    if long_values:
        story.append(p("긴 항목 원문", HEADING_STYLE))
        for label, value in long_values:
            story.append(p(f"{label}:"))
            for chunk in value.split(" / "):
                for line in chunk.split("\n"):
                    story.append(p(line))
            story.append(Spacer(1, 0.2 * cm))


def add_criteria(story: list, criteria: dict):

    summary = summarize_criteria(criteria)
    year = summary["base_year"]

    story.append(p("2부. 점검 기준 (기준서 추출 결과)", HEADING_STYLE))

    lines = [
        f"기준서 이름: {summary['name'] or EMPTY}",
        f"적용 버전: {summary['version'] or EMPTY}",
        f"필수 기재사항: {', '.join(summary['required_items']) or EMPTY}",
        f"최저임금({year or '기준'}년, 시간급): {won(summary['min_wage_current'])}",
        f"최저임금({summary['min_wage_next_year'] or '다음 해'}년, 시간급): {won(summary['min_wage_next']) if summary['min_wage_next'] is not None else '확정하지 못함'}",
        f"인용 법령: {', '.join(summary['legal_basis']) or EMPTY}",
    ]

    for line in lines:
        story.append(p(line))

    story.append(Spacer(1, 0.2 * cm))
    story.append(p(f"점검 규칙 ({len(summary['rules'])}개)", HEADING_STYLE))

    for rule in summary["rules"]:
        story.append(p(
            f"규칙 코드: {rule['rule_code']}\n"
            f"점검 조건: {rule['check_condition'] or EMPTY}\n"
            f"분류: {rule['category'] or EMPTY}\n"
            f"법령 근거: {rule['legal_basis'] or EMPTY}\n"
            f"권장 행동: {rule['recommended_action'] or EMPTY}"
        ))
        story.append(Spacer(1, 0.2 * cm))


def add_facts(story: list, facts: dict):

    story.append(p("3부. 계산 보조값 (코드가 1부 값으로 계산한 숫자이며 판정은 하지 않음)", HEADING_STYLE))

    span = facts["daily_span_minutes"]
    weekly = facts["weekly_hours"]

    if facts["daily_work_hours"] is None:
        daily = "계산 불가"
    else:
        rest = f"{facts['break_minutes'] or 0}분" + ("" if facts["break_stated"] else "(휴게시간 미기재)")
        daily = f"{facts['daily_work_hours']:g}시간 (출근부터 퇴근까지 {span / 60:g}시간, 휴게 {rest})"

    if weekly is None:
        weekly_text = "계산 불가"
    else:
        weekly_text = f"{weekly:g}시간 ({'15시간 이상' if weekly >= 15 else '15시간 미만'})"

    hourly = facts["hourly_wage"]
    hourly_text = "계산 불가" if hourly is None else f"{won(hourly)} ({facts['hourly_basis']}, 반올림하지 않은 값)"

    if facts["applicable_min_wage"] is None:
        applicable = "정하지 못함"
    else:
        applicable = f"{facts['applicable_min_wage_year']}년 {won(facts['applicable_min_wage'])}"

    next_start = facts["next_min_wage_start"] or "다음 해 1월 1일"

    lines = [
        f"1일 근로시간(휴게 제외): {daily}",
        f"1주 근무일 수: {facts['work_days_per_week'] or '계산 불가'}",
        f"1주 소정근로시간: {weekly_text}",
        f"시급 환산: {hourly_text}",
        f"계약 시작일 기준 적용 최저임금: {applicable}",
        f"계약이 {next_start} 이후까지 이어지는지: {yes_no(facts['continues_into_next_year'])}",
    ]

    for line in lines:
        story.append(p(line))

    for note in facts["notes"]:
        story.append(p(f"참고: {note}"))


##################################################
# Build
##################################################

def build_review_input(
    contract: dict,
    criteria: dict,
    facts: dict,
    output_path: Path,
    title: str = "점검 입력 문서"
) -> Path:

    output_path = Path(output_path)
    ensure_directory(output_path)

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=title
    )

    story = [p(title, TITLE_STYLE)]

    add_contract(story, contract)
    add_criteria(story, criteria)
    add_facts(story, facts)

    document.build(story)

    print(f"Review Input PDF : {output_path}")

    return output_path


def contract_rows(contract: dict) -> list[tuple[str, str]]:
    """
    화면의 추출 결과 표에 쓸 (항목, 값) 목록
    """

    return [(label, contract_value(contract, key)) for key, label in CONTRACT_LABELS]

