import { describe, expect, it } from "vitest";
import {
  conceptModelExperiments,
  conceptQualityGateValueKind,
  getConceptExperimentSummary,
  getLatestConceptExperiment,
  type ConceptModelExperimentHistory,
} from "@/lib/concept-model-report";

describe("concept model report", () => {
  it("selects the authoritative latest experiment by ID, regardless of array order", () => {
    const reversedHistory: ConceptModelExperimentHistory = {
      ...conceptModelExperiments,
      experiments: [...conceptModelExperiments.experiments].reverse(),
    };

    expect(getLatestConceptExperiment(reversedHistory)?.experimentId)
      .toBe(conceptModelExperiments.latestExperimentId);
  });

  it("rejects a report whose latest experiment ID is missing", () => {
    expect(() => getLatestConceptExperiment({
      ...conceptModelExperiments,
      latestExperimentId: "missing-experiment",
    })).toThrow(/missing from the report history/u);
  });

  it("keeps the Owner queue separate from the incremental reevaluation scope", () => {
    const latest = getLatestConceptExperiment();
    expect(latest).toBeDefined();
    if (!latest) return;

    const summary = getConceptExperimentSummary({
      ...latest,
      automatedReview: {
        ...latest.automatedReview,
        needsOwnerReviewCount: 3,
        affectedQuestionCount: 57,
        reusedQuestionCount: 348,
      },
    });
    expect({
      ownerReview: summary.ownerReviewCount,
      reevaluated: summary.affectedQuestionCount,
      reused: summary.reusedQuestionCount,
    }).toEqual({
      ownerReview: 3,
      reevaluated: 57,
      reused: 348,
    });
    expect(summary.completedEmbeddingCount)
      .toBe(latest.embeddings.filter((embedding) => embedding.status === "completed").length);
    expect(summary.completedRankerRunCount)
      .toBe(latest.rankerRuns.filter((run) => run.status === "completed").length);
  });

  it("formats only ranking metric gates as ratios", () => {
    expect(conceptQualityGateValueKind("test-ndcg-at-4")).toBe("ratio");
    expect(conceptQualityGateValueKind("owner-exception-review")).toBe("count");
    expect(conceptQualityGateValueKind("definition-role-mismatch")).toBe("count");
  });
});
