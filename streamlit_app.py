"""
streamlit_app.py

첫사인 알바 안심 체크 - Streamlit 화면

실행
    streamlit run streamlit_app.py
"""

import html
import json

import streamlit as st

from config import CRITERIA_FILE, SAMPLES, SAMPLE_DIR, is_live_ready, missing_settings
from rules import LEVEL_LABELS, RULE_TITLES, won
from service import ServiceError, run_review_service

##################################################
# Page
##################################################

st.set_page_config(
    page_title="첫사인 · 알바 안심 체크",
    layout="centered"
)

LEVEL_STYLE = {
    "safe": {"dot": "#22c55e", "bg": "#dcfce7", "fg": "#166534", "border": "#bbf7d0", "line": "#22c55e"},
    "check_needed": {"dot": "#f59e0b", "bg": "#fef3c7", "fg": "#92400e", "border": "#fde68a", "line": "#f59e0b"},
    "risky": {"dot": "#ef4444", "bg": "#fee2e2", "fg": "#991b1b", "border": "#fecaca", "line": "#ef4444"},
}

st.markdown(
    """
    <style>
    .fs-hero h1 {font-size: 1.9rem; margin: 0 0 .2rem 0;}
    .fs-hero p {color: #475569; margin: 0;}
    .fs-tags {margin-top: .5rem;}
    .fs-tag {display: inline-block; font-size: .78rem; color: #475569; background: #f1f5f9;
             border: 1px solid #e2e8f0; border-radius: 999px; padding: .1rem .55rem; margin: 0 .25rem .25rem 0;}
    .fs-badge {display: inline-flex; align-items: center; gap: .45rem; border-radius: 999px; border: 1px solid;
               font-weight: 700; padding: .3rem .8rem; font-size: 1rem; white-space: nowrap;}
    .fs-badge.sm {font-size: .78rem; padding: .12rem .55rem; gap: .35rem;}
    .fs-dot {width: .62rem; height: .62rem; border-radius: 999px; display: inline-block;}
    .fs-card {border: 1px solid #e2e8f0; border-radius: 14px; padding: 1.1rem 1.2rem; background: #fff;
              box-shadow: 0 1px 2px rgba(15, 23, 42, .05); margin-bottom: .8rem;}
    .fs-card-head {display: flex; justify-content: space-between; align-items: center; gap: .8rem;}
    .fs-card h3 {font-size: 1.1rem; margin: 0;}
    .fs-sub {color: #64748b; font-size: .85rem; margin-top: .15rem;}
    .fs-summary {color: #334155; margin: .7rem 0 0 0; line-height: 1.6;}
    .fs-clause {border: 1px solid #e2e8f0; border-left: 4px solid; border-radius: 10px; padding: .9rem 1rem;
                background: #fff; margin-bottom: .7rem;}
    .fs-clause h4 {font-size: 1rem; margin: 0;}
    .fs-quote {background: #f8fafc; border-radius: 8px; padding: .5rem .7rem; color: #475569; font-style: italic;
               margin: .6rem 0 0 0; font-size: .9rem;}
    .fs-reason {color: #334155; font-size: .92rem; margin: .6rem 0 0 0; line-height: 1.55;}
    .fs-dl {display: grid; grid-template-columns: 5.5rem 1fr; gap: .25rem .6rem; margin: .6rem 0 0 0; font-size: .88rem;}
    .fs-dl dt {color: #64748b; font-weight: 600;}
    .fs-dl dd {margin: 0; color: #334155;}
    .fs-code {text-align: right; color: #94a3b8; font-size: .75rem; margin-top: .4rem;}
    .fs-chip {display: inline-block; border: 1px solid #fcd34d; background: #fff; color: #92400e; border-radius: 999px;
              padding: .15rem .6rem; margin: 0 .3rem .3rem 0; font-size: .85rem;}
    .fs-box {border-radius: 12px; padding: .8rem 1rem; margin-bottom: .8rem; font-size: .92rem;}
    .fs-box.amber {background: #fffbeb; border: 1px solid #fde68a;}
    .fs-box.green {background: #f0fdf4; border: 1px solid #bbf7d0; color: #166534;}
    .fs-box.slate {background: #f8fafc; border: 1px solid #e2e8f0; color: #334155;}
    .fs-box b {display: block; margin-bottom: .35rem;}
    </style>
    """,
    unsafe_allow_html=True
)


##################################################
# HTML helpers
##################################################

def esc(value) -> str:
    """
    계약서 원문은 사용자가 올린 내용이라 항상 이스케이프해서 넣는다.
    """

    return html.escape(str(value), quote=True)


def badge(level: str | None, small: bool = False) -> str:

    if level not in LEVEL_STYLE:
        return '<span class="fs-badge sm" style="background:#f1f5f9;color:#475569;border-color:#e2e8f0">판정 보류</span>'

    s = LEVEL_STYLE[level]
    size = " sm" if small else ""

    return (
        f'<span class="fs-badge{size}" style="background:{s["bg"]};color:{s["fg"]};border-color:{s["border"]}">'
        f'<span class="fs-dot" style="background:{s["dot"]}"></span>{LEVEL_LABELS[level]}</span>'
    )


def html_block(markup: str):

    st.markdown(markup, unsafe_allow_html=True)


##################################################
# Header
##################################################

html_block(
    """
    <div class="fs-hero">
      <h1>첫사인 · 알바 안심 체크</h1>
      <p>사인하기 전 30초, 알바 근로계약서의 빠진 항목과 불리한 조항을 기준서대로 짚어 드려요.</p>
      <div class="fs-tags">
        <span class="fs-tag">Upstage Studio 에이전트 3개</span>
        <span class="fs-tag">점검 기준서 v2 · 규칙 7개</span>
        <span class="fs-tag">모든 지적에 법령 근거</span>
      </div>
    </div>
    """
)

st.caption("참고용 점검 도구이며 법률 자문이 아닙니다. 중요한 계약은 노무사나 고용노동부 상담(국번 없이 1350)으로 꼭 확인하세요.")

live = is_live_ready()

if not live:
    reason = "FORCE_DEMO=1" if not missing_settings() else "에이전트 연결 정보(.env)가 없어"
    st.info(f"데모 모드입니다. {reason} 체험용 샘플 계약서만 점검할 수 있습니다.")


##################################################
# Input
##################################################

st.subheader("1. 근로계약서 선택")

input_mode = st.radio(
    "입력 방법",
    ["샘플로 체험하기", "내 계약서 올리기"],
    horizontal=True,
    label_visibility="collapsed",
    index=0
)

uploaded = None
sample_id = None

if input_mode == "샘플로 체험하기":

    sample_id = st.selectbox(
        "가상 근로계약서 (실존 인물·사업장과 무관)",
        options=list(SAMPLES),
        format_func=lambda key: SAMPLES[key]["label"]
    )

    sample_path = SAMPLE_DIR / SAMPLES[sample_id]["file"]

    st.download_button(
        "샘플 계약서 PDF 보기",
        data=sample_path.read_bytes(),
        file_name=f"근로계약서_{SAMPLES[sample_id]['file']}",
        mime="application/pdf"
    )

else:

    uploaded = st.file_uploader(
        "근로계약서 PDF (10MB 이하). 실제 개인정보가 담긴 계약서는 올리지 마세요.",
        type=["pdf"],
        disabled=not live
    )

    if not live:
        st.caption("데모 모드에서는 업로드를 받지 않습니다.")

run = st.button("점검하기", type="primary", use_container_width=True)

# 입력을 바꾸면 이전 결과를 지워 다른 계약서의 결과로 오해하지 않게 한다
current_input = ("sample", sample_id) if input_mode == "샘플로 체험하기" else ("upload", uploaded.file_id if uploaded else None)

if st.session_state.get("result_input") != current_input:
    st.session_state.pop("result", None)


##################################################
# Execute
##################################################

STEPS = {
    1: "계약서 항목 추출",
    2: "점검 기준서 불러오기",
    3: "평가 입력 문서 조립",
    4: "평가 에이전트 분류",
    5: "규칙 계산 교차 검증",
}

if run:

    if input_mode == "내 계약서 올리기" and uploaded is None:
        st.error("근로계약서 PDF를 올려 주세요.")
        st.stop()

    st.session_state.pop("result", None)

    with st.status("계약서를 점검하고 있습니다...", expanded=True) as status:

        def progress(step: int, message: str):
            status.write(f"**{step}. {STEPS.get(step, '')}** · {message}")

        try:
            result = run_review_service(
                pdf_bytes=uploaded.getvalue() if uploaded is not None else None,
                sample_id=sample_id if uploaded is None else None,
                progress=progress
            )
        except ServiceError as error:
            status.update(label="점검하지 못했습니다", state="error")
            st.error(str(error))
            st.stop()
        except Exception as error:  # 예상하지 못한 오류도 화면이 멈추지 않게 한다
            status.update(label="점검하지 못했습니다", state="error")
            st.error("예상하지 못한 오류가 났습니다. 잠시 뒤 다시 시도해 주세요.")
            print(f"[streamlit] unexpected error: {error!r}")
            st.stop()

        status.update(label="점검을 마쳤습니다", state="complete", expanded=False)

    st.session_state["result"] = result
    st.session_state["result_input"] = current_input


##################################################
# Result
##################################################

def render_not_contract(result: dict):

    st.warning(
        "임금·근로시간 같은 핵심 항목이 대부분 비어 있습니다. "
        "근로계약서가 아니거나 읽을 수 없는 파일일 수 있어 판정을 표시하지 않습니다."
    )

    render_details(result)


SOURCE_NOTES = {
    "agent": "Upstage Studio 평가 에이전트 + 규칙 계산 교차 검증",
    "recorded": "Upstage Studio 평가 에이전트 저장 결과 재생 + 규칙 계산 교차 검증",
    "rules": "데모: 규칙 계산 결과 (평가 에이전트 미연결)",
}


def render_summary(result: dict):

    final, facts, engine = result["final"], result["facts"], result["engine"]

    html_block(
        f"""
        <div class="fs-card">
          <div class="fs-card-head">
            <div><h3>종합 진단</h3><div class="fs-sub">{esc(SOURCE_NOTES[result["source"]])}</div></div>
            {badge(final["level"])}
          </div>
          <p class="fs-summary">{esc(final["summary"] or "요약이 없습니다.")}</p>
        </div>
        """
    )

    if engine["criteria_problems"]:
        st.warning("점검 기준서 추출 결과에 문제가 있어 규칙 계산 등급을 내지 않았습니다: " + ", ".join(engine["criteria_problems"]))

    if final["level"] is None:
        st.info("일부 규칙을 판단하지 못해 등급을 정하지 않았습니다. 아래 '판단 보류' 항목을 계약서 원문으로 확인하세요.")
    elif final["incomplete"]:
        st.info(f"판단하지 못한 규칙이 있어 최소 '{LEVEL_LABELS[final['level']]}' 등급입니다. 아래 '판단 보류' 항목을 계약서 원문으로 확인하세요.")

    col1, col2, col3 = st.columns(3)

    hourly, minimum = facts["hourly_wage"], facts["applicable_min_wage"]

    col1.metric("시급", won(hourly))

    if hourly is not None and minimum is not None:
        gap = hourly - minimum
        col1.caption(f"{facts['applicable_min_wage_year']}년 최저 {won(minimum)} 대비 {'+' if gap >= 0 else '-'}{won(abs(gap))}")
    else:
        col1.caption("적용 최저임금을 정하지 못함")

    weekly = facts["weekly_hours"]
    col2.metric(
        "1주 소정근로시간",
        "계산 불가" if weekly is None else f"{weekly:g}시간",
        help="15시간 이상이면 주휴일·연차유급휴가 대상입니다."
    )
    col2.caption("근무일을 읽지 못함" if weekly is None else ("주휴 대상 (15시간 이상)" if weekly >= 15 else "15시간 미만"))

    col3.metric("해당한 점검 규칙", f"{len(final['cards'])}개")
    col3.caption(f"기준서 규칙 {len(engine['findings'])}개 중")


def render_cross_check(result: dict):

    check, review = result["cross_check"], result["review"]

    if result["source"] == "rules":
        return

    agent, engine = check["agent_level"], check["engine_level"]

    if review.get("level_conflict"):
        html_block(
            '<div class="fs-box amber"><b>평가 에이전트 내부 결과가 다릅니다</b>'
            f"Classify 분류는 {esc(LEVEL_LABELS[review['classify_level']])}, "
            f"결과 스키마의 review_level은 {esc(LEVEL_LABELS[review['schema_level']])}입니다. 더 엄격한 쪽을 썼습니다.</div>"
        )

    if agent is None:
        html_block(
            '<div class="fs-box amber"><b>평가 에이전트의 분류를 찾지 못했습니다</b>'
            "응답에서 Classify 결과와 review_level을 찾지 못해 규칙 계산 결과만으로 등급을 표시합니다.</div>"
        )
        return

    if not result["final"]["disagree"]:
        html_block(
            f'<div class="fs-box green"><b>교차 검증 일치</b>평가 에이전트({esc(LEVEL_LABELS[agent])})와 '
            f'규칙 계산({esc(LEVEL_LABELS.get(engine, "판정 보류"))})의 등급과 해당 규칙이 같습니다.</div>'
        )
        return

    lines = [
        f"평가 에이전트: <b style='display:inline'>{esc(LEVEL_LABELS[agent])}</b> · "
        f"규칙 계산: <b style='display:inline'>{esc(LEVEL_LABELS.get(engine, '판정 보류'))}</b>"
    ]

    if check["agent_only"]:
        lines.append("에이전트만 지적: " + ", ".join(esc(RULE_TITLES.get(c, c)) for c in check["agent_only"]))

    if check["engine_only"]:
        lines.append("규칙 계산만 지적: " + ", ".join(esc(RULE_TITLES.get(c, c)) for c in check["engine_only"]))

    lines.append("사용자 보호를 위해 둘 중 더 엄격한 등급과 두 쪽의 지적을 모두 표시합니다. 해당 항목은 계약서 원문으로 직접 확인하세요.")

    html_block('<div class="fs-box amber"><b>교차 검증 결과가 다릅니다</b>' + "<br>".join(lines) + "</div>")


def render_missing(result: dict):

    items = result["final"]["missing_items"]

    if not items:
        return

    chips = "".join(f'<span class="fs-chip">{esc(item)}</span>' for item in items)
    html_block(f'<div class="fs-box amber"><b>계약서에 없는 항목</b>{chips}</div>')


SOURCE_LABELS = {
    "both": "평가 에이전트 · 규칙 계산 모두 지적",
    "agent": "평가 에이전트만 지적",
    "engine": "규칙 계산만 지적",
}


def render_rules(result: dict):

    final = result["final"]
    cards = final["cards"]

    st.subheader(f"2. 점검 규칙에 해당한 항목 ({len(cards)}건)")

    if not cards:
        if final["level"] == "safe":
            html_block('<div class="fs-box green">점검 기준서의 규칙에 해당하는 항목이 없습니다.</div>')
        else:
            st.write("해당한다고 확정한 규칙은 없습니다.")

    for f in cards:

        style = LEVEL_STYLE.get(f["level"])
        line = style["line"] if style else "#94a3b8"
        quote = f'<p class="fs-quote">“{esc(f["clause"])}”</p>' if f["clause"] else ""
        origin = f'<div class="fs-sub">{esc(SOURCE_LABELS[f["source"]])}</div>' if result["source"] != "rules" else ""

        html_block(
            f"""
            <div class="fs-clause" style="border-left-color:{line}">
              <div class="fs-card-head"><h4>{esc(f["title"])}</h4>{badge(f["level"], small=True)}</div>
              {origin}
              {quote}
              <p class="fs-reason">{esc(f["reason"])}</p>
              <dl class="fs-dl">
                <dt>계약서</dt><dd>{esc(f["contract_value"])}</dd>
                <dt>기준</dt><dd>{esc(f["criteria_value"])}</dd>
                <dt>법령 근거</dt><dd>{esc(f["legal_basis"] or "-")}</dd>
                <dt>권장 행동</dt><dd>{esc(f["recommended_action"] or "-")}</dd>
              </dl>
              <div class="fs-code">규칙 {esc(f["rule_code"])} · 기준서 분류 {esc(f["category"] or "-")}</div>
            </div>
            """
        )

    if final["pending"]:
        names = "<br>".join(f"{esc(f['title'])}: {esc(f['reason'])}" for f in final["pending"])
        html_block(f'<div class="fs-box slate"><b>판단 보류 ({len(final["pending"])}건)</b>{names}</div>')

    clauses = result["review"]["risky_clauses"]

    if clauses and result["source"] != "rules":
        with st.expander(f"평가 에이전트가 지적한 조항 원문 ({len(clauses)}건)"):
            for clause in clauses:
                st.text(clause)


def render_actions(result: dict):

    actions = result["final"]["recommendations"]

    st.subheader("3. 다음에 할 일")

    if not actions:
        if result["final"]["level"] == "safe":
            st.write("따로 요청할 내용이 없습니다. 서명한 계약서 사본 1부를 꼭 받아 두세요.")
        else:
            st.write("판단 보류 항목을 계약서 원문으로 확인하고, 애매하면 고용노동부 상담(국번 없이 1350)에 물어보세요.")
        return

    for action in actions:
        st.text(f"• {action}")

    requests = result["final"]["requests"]

    if not requests:
        return

    message = "사장님, 근로계약서 관련해서 몇 가지 확인 부탁드립니다.\n\n"
    message += "\n".join(f"{i}. {request}" for i, request in enumerate(requests, start=1))
    message += "\n\n확인 후 수정된 계약서를 받을 수 있을까요? 감사합니다."
    st.caption("사장님께 보낼 메시지 초안 · 평가 에이전트 작성 (오른쪽 위 아이콘으로 복사)")
    st.code(message, language=None, wrap_lines=True)


def render_details(result: dict):

    st.subheader("4. 상세 보기")

    with st.expander("추출된 계약 정보 (Contract Agent)"):
        st.table({"항목": [r[0] for r in result["contract_rows"]], "값": [r[1] for r in result["contract_rows"]]})

    facts = result["facts"]

    with st.expander("계산 보조값과 기준서 (평가 입력 문서 2·3부)"):
        criteria = result["engine"]["criteria"]
        applicable = "정하지 못함" if facts["applicable_min_wage"] is None else f"{facts['applicable_min_wage_year']}년 {won(facts['applicable_min_wage'])}"
        daily = "계산 불가" if facts["daily_work_hours"] is None else f"{facts['daily_work_hours']:g}시간"
        st.markdown(
            f"- 기준서: {criteria['name'] or CRITERIA_FILE.name} ({criteria['version'] or '버전 미상'})\n"
            f"- 최저임금: {criteria['base_year'] or '기준'}년 {won(criteria['min_wage_current'])}, 다음 해 {won(criteria['min_wage_next'])}\n"
            f"- 1일 근로시간(휴게 제외): {daily}\n"
            f"- 1주 근무일: {facts['work_days_per_week'] or '계산 불가'}\n"
            f"- 시급 환산: {won(facts['hourly_wage'])} {facts['hourly_basis']}\n"
            f"- 적용 최저임금: {applicable}"
        )
        for note in facts["notes"] + result["engine"]["criteria_problems"]:
            st.caption(f"참고: {note}")

    final = result["final"]

    if final and final["agent_summary"] and final["agent_summary"] != final["summary"]:
        with st.expander("평가 에이전트 원문 요약"):
            st.text(final["agent_summary"])

    if final and final["confirmed_items"]:
        with st.expander("기준을 충족한 항목"):
            for item in final["confirmed_items"]:
                st.text(f"• {item}")

    export = {
        "mode": result["mode"],
        "source": result["source"],
        "final_level": result["final_level"],
        "agent_level": result["agent_level"],
        "engine_level": result["engine_level"],
        "final": {k: v for k, v in (final or {}).items() if k not in ("cards", "pending")},
        "final_rule_codes": [card["rule_code"] for card in final["cards"]] if final else [],
        "review": result["review"],
        "contract": result["contract"],
        "facts": facts,
        "rule_findings": result["engine"]["findings"],
    }

    col1, col2 = st.columns(2)

    col1.download_button(
        "결과 JSON 내려받기",
        data=json.dumps(export, ensure_ascii=False, indent=2),
        file_name="review_result.json",
        mime="application/json",
        use_container_width=True
    )

    if result["review_pdf_bytes"]:
        col2.download_button(
            "평가 입력 PDF 내려받기",
            data=result["review_pdf_bytes"],
            file_name="Review_Input.pdf",
            mime="application/pdf",
            use_container_width=True
        )


def render_limits():

    st.caption(
        "점검하지 않는 항목: 5인 미만 사업장 여부, 만 18세 미만 근로자, 수습 기간 감액은 계약서만으로 판단할 수 없어 점검하지 않습니다. "
        "기준서는 법령 기준일 2026-10-14 기준이며, AI의 판단은 틀릴 수 있습니다."
    )


result = st.session_state.get("result")

if result:

    st.divider()

    if result["final"] is None:
        render_not_contract(result)
    else:
        render_summary(result)
        render_cross_check(result)
        render_missing(result)
        render_rules(result)
        render_actions(result)
        render_details(result)

    render_limits()
