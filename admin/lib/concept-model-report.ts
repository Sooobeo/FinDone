import reportData from "@/data/concept-model-experiments.generated.json";

export interface RankingMetrics {
  questionCount: number;
  retrievalRecallAt20: number;
  ndcgAt4: number;
  precisionAt4: number;
  mrr: number;
  labelSource: string;
}

export interface ConceptQualityGate {
  id: string;
  label: string;
  measured: number | boolean;
  threshold: number | boolean;
  passed: boolean;
}

export interface ConceptRankerRun {
  embeddingId: string;
  retrievalProfileId: string;
  rankerFamily: string;
  rankerId: string;
  hyperparameters: Record<string, unknown>;
  status: "completed" | "failed";
  trainingSeconds: number;
  validation: RankingMetrics | null;
  test: RankingMetrics | null;
  testEvaluated: boolean;
  modelBytes: number | null;
  error: string | null;
}

export interface ConceptExperiment {
  experimentId: string;
  startedAt: string;
  finishedAt: string;
  durationSeconds: number;
  status: "bootstrap" | "candidate" | "release_ready" | "failed";
  releaseReady: boolean;
  releaseBlockReason: string | null;
  dataset: {
    elementCount: number;
    factCount: number;
    questionCount: number;
    candidateCount: number;
    elementSplits: Record<string, number>;
    questionSplits: Record<string, number>;
  };
  labels: {
    weakLabelCount: number;
    humanLabelCount: number;
    humanLabelCompletion: number;
    humanTestCoverage: number;
    coveredTestQuestionCount: number;
    testQuestionCount: number;
    humanApprovalRate: number;
    metricWarning: string | null;
  };
  automatedReview: {
    policyVersion: string;
    selectedProfileId: string;
    selectionReason: string;
    reviewInputSha256: string;
    policyConfigSha256: string;
    baselineMode: "initial" | "incremental";
    changedElementCount: number;
    changedElementIds: string[];
    changedQuestionCount: number;
    affectedQuestionCount: number;
    reusedQuestionCount: number;
    autoPassedCount: number;
    ownerApprovedCount: number;
    needsOwnerReviewCount: number;
    blockedCount: number;
    staleOwnerDecisionCount: number;
    ownerBatchApproved: boolean;
    ownerReviewComplete: boolean;
    profileExperiments: Array<{
      profileId: string;
      thresholds: Record<string, number>;
      provenance: string;
      validationQuestionCount: number;
      validationReviewCount: number;
      validationReviewRate: number;
      validationBlockedCount: number;
      distanceFromTargetReviewRate: number;
    }>;
    queue: Array<{
      questionId: string;
      elementId: string;
      questionType: "term_to_definition" | "term_to_intuition" | "term_to_verbal_relation";
      split: string;
      questionFingerprint: string;
      severity: "review" | "block";
      stem: string;
      explanation: string;
      choices: Array<{
        key: string;
        elementId: string;
        factId?: string;
        text: string;
        explanation: string;
        isCorrect: boolean;
      }>;
      reasons: Array<{
        id: string;
        label: string;
        measured: number | boolean | string;
        threshold: number | boolean | string;
      }>;
      metrics: {
        meanTop4Agreement: number;
        minimumSelectedCandidateSupport: number;
        normalizedBoundaryMargin: number;
        minimumDistractorRelevance: number;
      };
      change: {
        affectedByChangedElement: boolean;
        choiceSetChanged: boolean;
      };
    }>;
  };
  embeddings: Array<{
    candidateId: string;
    modelId: string;
    status: "completed" | "failed";
    revisionResolved: string | null;
    dimensions: number | null;
    encodeSeconds: number | null;
    artifactBytes: number | null;
    cacheHit?: boolean;
    matrixCacheSha256?: string | null;
    error: string | null;
  }>;
  rankerRuns: ConceptRankerRun[];
  selection: {
    embeddingId: string;
    retrievalProfileId: string;
    rankerId: string;
    rankerFamily: string;
    hyperparameters: Record<string, unknown>;
    validationNdcgAt4: number;
    selectionTolerance: number;
    reason: string;
    modelBytes: number;
  };
  evaluation: {
    labelSource: string;
    validation: RankingMetrics;
    test: RankingMetrics;
  };
  safety: {
    answerLeakCount: number;
    termLeakCount: number;
    formulaChoiceCount: number;
    duplicateChoiceCount: number;
    ambiguousQuestionCount: number;
  };
  qualityGates: ConceptQualityGate[];
  artifacts: {
    markdownReport: string;
    questionBank: string;
    questionBankSha256: string;
  };
  environment: {
    externalLlmApiCalls: number;
    appRuntimeModelCalls: number;
  };
}

export interface ConceptModelExperimentHistory {
  reportVersion: number;
  contractVersion?: string;
  resetAt?: string;
  latestExperimentId: string | null;
  experiments: ConceptExperiment[];
}

export const conceptModelExperiments = reportData as unknown as ConceptModelExperimentHistory;
