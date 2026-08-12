import { describe, expect, it } from "vitest";
import { validateGlossaryTerm } from "@/lib/glossary";

const validTerm = {
  termId: "FIN-01-001",
  categoryId: "01",
  displayOrder: 0,
  canonicalNameEn: "Securities Firm",
  canonicalNameKo: "증권사",
  aliases: ["securities company"],
  conceptType: "INSTITUTION",
  oneLineDefinitionKo: "증권사는 증권 거래 중개와 발행 지원을 수행하는 금융기관이다.",
  coreDefinitionKo: "증권사는 고객 주문을 중개하고 증권 발행과 인수 업무를 지원한다. 인가 범위와 관할에 따라 수행할 수 있는 업무가 달라진다.",
  practicalContextKo: "기업금융, 리서치, 트레이딩과 브로커리지 업무에서 거래 상대방이나 주관사로 참여한다.",
  whyItMattersKo: "거래 실행과 자금조달의 핵심 접점이기 때문이다.",
  exampleKo: "증권사가 기업의 회사채 발행을 주관하고 투자자 주문을 배분한다.",
  limitationsKo: ["국가별 인가 체계에 따라 업무 범위가 다르다."],
  sourceCodes: ["S01"],
  jurisdictions: ["MULTI"],
  asOfDate: "2026-08-12",
  reviewStatus: "agent_reviewed",
  reviewFlags: ["human_jurisdiction_review"],
  relatedTermIds: ["FIN-01-002"],
  formulaLatex: "",
  formulaNotesKo: "",
  contentRevision: 1,
  updatedAt: "2026-08-12T00:00:00Z",
  isActive: true,
};

describe("validateGlossaryTerm", () => {
  it("normalizes a complete authored term", () => {
    const result = validateGlossaryTerm({ ...validTerm, aliases: [" securities company ", "securities company"] }, validTerm.termId);
    expect(result.aliases).toEqual(["securities company"]);
    expect(result.reviewStatus).toBe("agent_reviewed");
  });

  it("rejects path identity changes and placeholder copy", () => {
    expect(() => validateGlossaryTerm(validTerm, "FIN-01-002")).toThrow(/ID/);
    expect(() => validateGlossaryTerm({ ...validTerm, coreDefinitionKo: "TODO" }, validTerm.termId)).toThrow();
  });

  it("requires an allowed source and jurisdiction", () => {
    expect(() => validateGlossaryTerm({ ...validTerm, sourceCodes: [] }, validTerm.termId)).toThrow(/출처/);
    expect(() => validateGlossaryTerm({ ...validTerm, jurisdictions: ["CA"] }, validTerm.termId)).toThrow(/관할/);
  });

  it("rejects invalid calendar dates and release-inventory delimiters", () => {
    expect(() => validateGlossaryTerm({ ...validTerm, asOfDate: "2026-02-31" }, validTerm.termId)).toThrow(/기준일/);
    expect(() => validateGlossaryTerm({ ...validTerm, aliases: ["alpha|beta"] }, validTerm.termId)).toThrow(/별칭/);
  });
});
