import fontkit from "@pdf-lib/fontkit";
import { PDFDocument, rgb, type PDFFont, type PDFPage } from "pdf-lib";
import { amount_candidates, as_list, is_blank, summarize_criteria, text, to_bool, to_number, won, type ExtractedData, type Facts } from "./rules";

const EMPTY = "(비어 있음)";
const CONTRACT_LABELS: readonly [string, string][] = [
  ["employer_name", "사업주"],
  ["employee_name", "근로자"],
  ["contract_start_date", "근로계약기간 시작일"],
  ["contract_end_date", "근로계약기간 종료일"],
  ["workplace", "근무장소"],
  ["job_description", "업무의 내용"],
  ["work_days", "근무일"],
  ["work_start_time", "소정근로 시작 시각"],
  ["work_end_time", "소정근로 종료 시각"],
  ["break_time", "휴게시간"],
  ["weekly_holiday", "주휴일"],
  ["wage_type", "임금 구분"],
  ["wage_amount", "임금 금액(원)"],
  ["wage_payment_date", "임금지급일"],
  ["wage_payment_method", "임금지급방법"],
  ["annual_leave_clause", "연차유급휴가"],
  ["social_insurance", "사회보험"],
  ["copy_delivery_clause", "계약서 교부 문구"],
  ["special_terms", "특약사항"],
  ["is_signed", "서명 여부(사업주·근로자 모두 서명)"],
];

function contract_value(contract: ExtractedData, key: string): string {
  const value = contract[key];
  const items = as_list(value).filter((item) => !is_blank(item));
  const raw = items.map((item) => typeof item === "boolean" ? (item ? "True" : "False") : String(item)).join(" / ");
  if (key === "is_signed") {
    const signed = to_bool(value);
    if (signed === null) return raw ? `${raw} (예/아니오로 정하지 못함)` : EMPTY;
    return signed ? "예" : "아니오";
  }
  if (key === "wage_amount") {
    const amount = to_number(value);
    const plain = items.every((item) => typeof item === "number" || typeof item === "boolean" || /^[\d,.\s]+원?$/.test(String(item)));
    if (amount !== null && plain) return amount.toFixed(0);
    if (!raw) return EMPTY;
    return amount !== null && amount_candidates(value).size <= 1 ? raw : `${raw} (금액을 하나로 정하지 못함)`;
  }
  if (key === "special_terms") return as_list(value).map(String).join(" / ") || "없음";
  return text(value) || EMPTY;
}

export function contract_rows(contract: ExtractedData): [string, string][] {
  return CONTRACT_LABELS.map(([key, label]) => [label, contract_value(contract, key)]);
}

// 글자 폭으로 줄을 나누므로 긴 단어와 여러 줄인 항목도 다음 페이지에 이어집니다.
function wrap(value: string, font: PDFFont, size: number, width: number): string[] {
  const lines: string[] = [];
  for (const paragraph of value.replace(/\r\n?/g, "\n").replace(/\t/g, "    ").split("\n")) {
    let line = "";
    for (const character of paragraph) {
      if (line && font.widthOfTextAtSize(line + character, size) > width) {
        lines.push(line);
        line = "";
      }
      line += character;
    }
    lines.push(line);
  }
  return lines;
}

export async function build_review_input(
  contract: ExtractedData,
  criteria: ExtractedData,
  facts: Facts,
  fontBytes: Uint8Array,
): Promise<Uint8Array> {
  const document = await PDFDocument.create();
  document.registerFontkit(fontkit);
  // Nanum의 마지막 공백 글리프에는 윤곽이 없습니다. fontkit이 빈 헤더를 읽을 때
  // 버퍼 끝을 넘지 않도록 메모리 복사본에 0을 붙입니다. 원본 파일은 보존합니다.
  const paddedFont = new Uint8Array(fontBytes.length + 12);
  paddedFont.set(fontBytes);
  // 부분 임베딩은 일부 Nanum 복합 글리프의 윤곽을 누락하므로 전체 폰트를 넣습니다.
  const font = await document.embedFont(paddedFont, { subset: false });
  document.setTitle("점검 입력 문서");
  document.setAuthor("FirstSign");
  const pageWidth = 595.28;
  const pageHeight = 841.89;
  const margin = 54;
  const contentWidth = pageWidth - margin * 2;
  let page: PDFPage;
  let y = 0;

  function newPage() {
    page = document.addPage([pageWidth, pageHeight]);
    y = pageHeight - margin;
  }
  function paragraph(value: string, size = 9.5, after = 5, heading = false) {
    const leading = size * 1.5;
    const lines = wrap(value, font, size, contentWidth);
    if (heading && y - leading * Math.min(lines.length + 2, 4) < margin) newPage();
    for (const line of lines) {
      if (y - leading < margin) newPage();
      page.drawText(line, { x: margin, y: y - size, size, font, color: heading ? rgb(0.1, 0.27, 0.24) : rgb(0.12, 0.16, 0.2) });
      y -= leading;
    }
    y -= after;
  }
  function heading(value: string) {
    y -= 8;
    paragraph(value, 12, 8, true);
  }

  newPage();
  paragraph("점검 입력 문서", 18, 10, true);
  heading("1부. 근로계약 정보 (계약서 추출 결과)");
  for (const [label, value] of contract_rows(contract)) paragraph(`${label}: ${value}`);

  const summary = summarize_criteria(criteria);
  const year = summary.base_year;
  heading("2부. 점검 기준 (기준서 추출 결과)");
  for (const line of [
    `기준서 이름: ${summary.name || EMPTY}`,
    `적용 버전: ${summary.version || EMPTY}`,
    `필수 기재사항: ${summary.required_items.join(", ") || EMPTY}`,
    `최저임금(${year || "기준"}년, 시간급): ${won(summary.min_wage_current)}`,
    `최저임금(${summary.min_wage_next_year || "다음 해"}년, 시간급): ${summary.min_wage_next !== null ? won(summary.min_wage_next) : "확정하지 못함"}`,
    `인용 법령: ${summary.legal_basis.join(", ") || EMPTY}`,
  ]) paragraph(line);
  heading(`점검 규칙 (${summary.rules.length}개)`);
  for (const rule of summary.rules) {
    paragraph([
      `규칙 코드: ${rule.rule_code}`,
      `점검 조건: ${rule.check_condition || EMPTY}`,
      `분류: ${rule.category || EMPTY}`,
      `법령 근거: ${rule.legal_basis || EMPTY}`,
      `권장 행동: ${rule.recommended_action || EMPTY}`,
    ].join("\n"), 9.5, 10);
  }

  heading("3부. 계산 보조값 (코드가 1부 값으로 계산한 숫자이며 판정은 하지 않음)");
  const daily = facts.daily_work_hours === null ? "계산 불가" :
    `${facts.daily_work_hours}시간 (출근부터 퇴근까지 ${(facts.daily_span_minutes ?? 0) / 60}시간, 휴게 ${facts.break_minutes ?? 0}분${facts.break_stated ? "" : "(휴게시간 미기재)"})`;
  const weekly = facts.weekly_hours === null ? "계산 불가" :
    `${facts.weekly_hours}시간 (${facts.weekly_hours >= 15 ? "15시간 이상" : "15시간 미만"})`;
  const hourly = facts.hourly_wage === null ? "계산 불가" :
    `${won(facts.hourly_wage)} (${facts.hourly_basis}, 반올림하지 않은 값)`;
  const applicable = facts.applicable_min_wage === null ? "정하지 못함" :
    `${facts.applicable_min_wage_year}년 ${won(facts.applicable_min_wage)}`;
  const continues = facts.continues_into_next_year === null ? "판단 불가" : facts.continues_into_next_year ? "예" : "아니오";
  for (const line of [
    `1일 근로시간(휴게 제외): ${daily}`,
    `1주 근무일 수: ${facts.work_days_per_week || "계산 불가"}`,
    `1주 소정근로시간: ${weekly}`,
    `시급 환산: ${hourly}`,
    `계약 시작일 기준 적용 최저임금: ${applicable}`,
    `계약이 ${facts.next_min_wage_start || "다음 해 1월 1일"} 이후까지 이어지는지: ${continues}`,
    ...facts.notes.map((note) => `참고: ${note}`),
  ]) paragraph(line);

  const pages = document.getPages();
  pages.forEach((item, index) => item.drawText(`${index + 1} / ${pages.length}`, {
    x: pageWidth - margin - 36, y: 30, size: 8, font, color: rgb(0.4, 0.45, 0.5),
  }));
  return document.save();
}
