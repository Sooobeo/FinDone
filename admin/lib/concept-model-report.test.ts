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

  it("keeps the v2.2 Owner queue separate from the incremental reevaluation scope", () => {
    const latest = getLatestConceptExperiment();
    expect(latest).toBeDefined();
    if (!latest) return;

    const summary = getConceptExperimentSummary(latest);
    expect({
      total: latest.dataset.questionCount,
      automatedPass: latest.automatedReview.autoPassedCount,
      ownerReview: summary.ownerReviewCount,
      blocked: latest.automatedReview.blockedCount,
      reevaluated: summary.affectedQuestionCount,
      reused: summary.reusedQuestionCount,
    }).toEqual({
      total: 405,
      automatedPass: 402,
      ownerReview: 3,
      blocked: 0,
      reevaluated: 57,
      reused: 348,
    });
    expect(summary.completedEmbeddingCount).toBe(6);
    expect(summary.completedRankerRunCount).toBe(198);
    expect(summary.reasonCounts).toMatchObject({
      "candidate-never-supported": 1,
      "boundary-margin": 2,
    });
  });

  it("formats only ranking metric gates as ratios", () => {
    expect(conceptQualityGateValueKind("test-ndcg-at-4")).toBe("ratio");
    expect(conceptQualityGateValueKind("owner-exception-review")).toBe("count");
    expect(conceptQualityGateValueKind("definition-role-mismatch")).toBe("count");
  });
});
