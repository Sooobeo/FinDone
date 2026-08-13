import { describe, expect, it } from "vitest";
import { buildConceptReviewWorkbook, conceptReviewWorkbookFilename } from "@/lib/concept-review-export";
import type { ConceptExperiment } from "@/lib/concept-model-report";

type QueueItem = ConceptExperiment["automatedReview"]["queue"][number];

function sampleItem(): QueueItem {
  return {
    questionId: "ACC-01-term_to_definition-01",
    elementId: "ACC-01",
    questionType: "term_to_definition",
    split: "validation",
    questionFingerprint: "fingerprint-1",
    severity: "review",
    stem: "용어: 회계등식",
    explanation: "정답 해설",
    choices: ["A", "B", "C", "D", "E"].map((key, index) => ({
      key,
      elementId: `ACC-0${index + 1}`,
      text: `${key} 설명`,
      explanation: `${key} 해설`,
      isCorrect: key === "A",
    })),
    reasons: [{ id: "boundary-margin", label: "경계 불안정", measured: -0.2, threshold: -0.2 }],
    metrics: {
      meanTop4Agreement: 0.5,
      minimumSelectedCandidateSupport: 0.05,
      normalizedBoundaryMargin: -0.2,
      minimumDistractorRelevance: 2,
    },
    change: { affectedByChangedElement: false, choiceSetChanged: false },
  };
}

describe("concept review workbook export", () => {
  it("creates an XLSX zip with all review sheets and decision data", () => {
    const bytes = buildConceptReviewWorkbook(
      [sampleItem()],
      { "ACC-01-term_to_definition-01": { decision: "approved", comment: "확인" } },
      { experimentId: "cmq-v2-test", generatedAt: "2026-08-13T00:00:00.000Z", reviewInputSha256: "sha" },
    );
    expect(Array.from(bytes.slice(0, 4))).toEqual([0x50, 0x4B, 0x03, 0x04]);
    const text = new TextDecoder().decode(bytes);
    expect(text).toContain("검수 문항");
    expect(text).toContain("용어: 회계등식");
    expect(bytes.length).toBeGreaterThan(1000);
  });

  it("uses a stable Korean filename date", () => {
    expect(conceptReviewWorkbookFilename(new Date("2026-08-13T00:00:00.000Z"))).toBe("findone-concept-review-20260813.xlsx");
  });
});
