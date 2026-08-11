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
  status: "bootstrap" | "release_ready" | "failed";
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
  latestExperimentId: string;
  experiments: ConceptExperiment[];
}

export const conceptModelExperiments = reportData as unknown as ConceptModelExperimentHistory;
