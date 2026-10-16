import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { PDFDocument } from "pdf-lib";
import { describe, expect, it } from "vitest";
import { build_review_input, contract_rows } from "../src/lib/review-builder";
import { compute_facts } from "../src/lib/rules";

const font = readFileSync(new URL("../public/fonts/NanumGothic-Regular.ttf", import.meta.url));
const contract = { employer_name: "검증카페", work_start_time: "09:00", work_end_time: "18:00", break_time: "1시간", work_days: "월~금", wage_type: "시급", wage_amount: 11000, is_signed: false };
const criteria = { criteria_name: "검증 기준서", criteria_version: "2026-10", min_wage_hourly: 10320, min_wage_hourly_2027: 10700 };
const hasPoppler = spawnSync("pdftotext", ["-v"]).status === 0;

function extract_pdf(bytes: Uint8Array): string {
  const directory = mkdtempSync(join(tmpdir(), "firstsign-pdf-"));
  try {
    const path = join(directory, "review.pdf");
    writeFileSync(path, bytes);
    return execFileSync("pdftotext", ["-layout", path, "-"], { encoding: "utf8" });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

describe("review PDF", () => {
  it("preserves absent values and explicit false in contract rows", () => {
    const rows = new Map(contract_rows(contract));
    expect(rows.get("서명 여부(사업주·근로자 모두 서명)")).toBe("아니오");
    expect(rows.get("근로자")).toBe("(비어 있음)");
    expect(rows.get("임금 금액(원)")).toBe("11000");
    expect(rows.get("특약사항")).toBe("없음");
  });

  it.each([
    [[10800, 9500], "10800 / 9500 (금액을 하나로 정하지 못함)"],
    ["10,800원 (수습 3개월은 9,500원)", "10,800원 (수습 3개월은 9,500원) (금액을 하나로 정하지 못함)"],
    ["10,800원 (수습기간 9천원)", "10,800원 (수습기간 9천원) (금액을 하나로 정하지 못함)"],
    ["시급 10,800원", "시급 10,800원"],
    [[10800], "10800"],
    [10319.875, "10319.875"],
    ["10,319.875원", "10319.875"],
    ["10,800원", "10800"],
    [null, "(비어 있음)"],
  ])("preserves wage evidence for %j", (wage_amount, expected) => {
    expect(new Map(contract_rows({ wage_amount })).get("임금 금액(원)")).toBe(expected);
  });

  it.each([
    [[true, false], "True / False (예/아니오로 정하지 못함)"],
    [[true], "예"],
    [[false], "아니오"],
    ["서명 확인 필요", "서명 확인 필요 (예/아니오로 정하지 못함)"],
    [null, "(비어 있음)"],
  ])("preserves signature evidence for %j", (is_signed, expected) => {
    expect(new Map(contract_rows({ is_signed })).get("서명 여부(사업주·근로자 모두 서명)")).toBe(expected);
  });

  it.skipIf(!hasPoppler)("keeps ambiguous wage and signature source text in the saved PDF", async () => {
    const ambiguous = { ...contract, wage_amount: "10,800원 (수습 3개월은 9,500원)", is_signed: [true, false] };
    const bytes = await build_review_input(ambiguous, criteria, compute_facts(ambiguous, criteria), font);
    const extracted = extract_pdf(bytes);
    expect(extracted).toContain("10,800원 (수습 3개월은 9,500원) (금액을 하나로 정하지 못함)");
    expect(extracted).toContain("True / False (예/아니오로 정하지 못함)");
  });

  it("creates a readable Korean PDF with multiple pages for long values", async () => {
    const unbroken = `${"가".repeat(800)}공백없는끝`;
    const longContract = { ...contract, special_terms: [Array.from({ length: 180 }, (_, index) => `특약 원문 ${String(index).padStart(3, "0")} 전체 보존`).join("\n"), unbroken, "마지막 원문 보존 확인"] };
    const bytes = await build_review_input(longContract, criteria, compute_facts(longContract, criteria), font);
    const document = await PDFDocument.load(bytes);
    expect(document.getTitle()).toBe("점검 입력 문서");
    expect(document.getPageCount()).toBeGreaterThan(4);
    expect(document.getPages().every((page) => Math.abs(page.getWidth() - 595.28) < 0.01)).toBe(true);

    // Poppler가 있으면 저장된 PDF에서 한국어와 마지막 원문을 다시 읽습니다.
    if (spawnSync("pdftotext", ["-v"]).status === 0) {
      const directory = mkdtempSync(join(tmpdir(), "firstsign-pdf-"));
      try {
        const path = join(directory, "review.pdf");
        writeFileSync(path, bytes);
        const extracted = execFileSync("pdftotext", ["-layout", path, "-"], { encoding: "utf8" });
        expect(extracted).toContain("1부. 근로계약 정보");
        expect(extracted).toContain("2부. 점검 기준");
        expect(extracted).toContain("3부. 계산 보조값");
        expect(extracted).toContain("마지막 원문 보존 확인");
        expect(extracted.replace(/\s/g, "")).toContain(unbroken);
        for (let index = 0; index < 180; index++) expect(extracted).toContain(`특약 원문 ${String(index).padStart(3, "0")} 전체 보존`);
      } finally {
        rmSync(directory, { recursive: true, force: true });
      }
    }
  }, 30_000);

  it("preserves many short lines in the special terms", async () => {
    const multiline = { ...contract, special_terms: ["조항\n".repeat(60)] };
    const bytes = await build_review_input(multiline, criteria, compute_facts(multiline, criteria), font);
    expect((await PDFDocument.load(bytes)).getPageCount()).toBeGreaterThan(1);
    if (hasPoppler) {
      const extracted = extract_pdf(bytes);
      expect(extracted.match(/조항/g)).toHaveLength(60);
      expect(extracted).toContain("3부. 계산 보조값");
    }
  });

  it.skipIf(!hasPoppler).each(["2025-10", "2027-10", ""])("does not reuse the fixed 2027 wage for criteria version %s", async (version) => {
    const changed = { ...criteria, criteria_version: version };
    const bytes = await build_review_input(contract, changed, compute_facts(contract, changed), font);
    const extracted = extract_pdf(bytes);
    expect(extracted).toContain("최저임금(다음 해년, 시간급): 확정하지 못함");
    expect(extracted).not.toContain("10,700원");
  });

  it.skipIf(!hasPoppler)("labels the valid next wage with its explicit year", async () => {
    const bytes = await build_review_input(contract, criteria, compute_facts(contract, criteria), font);
    expect(extract_pdf(bytes)).toContain("최저임금(2027년, 시간급): 10,700원");
  });
});


it.skipIf(!hasPoppler)("preserves the decimal wage in the saved PDF", async () => {
  const decimal = { ...contract, wage_amount: 10319.875 };
  const bytes = await build_review_input(decimal, criteria, compute_facts(decimal, criteria), font);
  expect(extract_pdf(bytes)).toContain("10319.875");
});
