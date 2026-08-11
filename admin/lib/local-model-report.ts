import reportData from "@/data/local-content-model-report.generated.json";

export interface LocalModelGate {
  id: string;
  label: string;
  measured: number | boolean;
  threshold: number | boolean;
  passed: boolean;
}

export interface LocalModelReport {
  reportVersion: number;
  generatedAt: string;
  status: "passed" | "failed";
  model: {
    name: string;
    version: string;
    schemaVersion: number;
    type: string;
    externalLlmApiCalls: number;
    supportedAdapters: string[];
  };
  training: {
    metricDefinition: string;
    readinessScore: number;
    reviewedContentDatabaseCount: number;
    reviewedElementCount: number;
    domainCount: number;
    structuredLearningCopyFileCount: number;
    cataloguedSourceCount: number;
    cataloguedWebSourceCount: number;
    sourceReferenceCount: number;
    corpusCoverage: number;
    requiredFieldCoverage: number;
    sourceTraceability: number;
    multipleSourceCoverage: number;
  };
  evaluation: {
    caseCount: number;
    passedCases: number;
    fieldAssertionCount: number;
    passedFieldAssertions: number;
    caseAccuracy: number;
    fieldAccuracy: number;
    caseAccuracyWilson95LowerBound: number;
    fieldAccuracyWilson95LowerBound: number;
    deterministicBuild: boolean;
    buildHashes: string[];
    failures: Array<Record<string, unknown>>;
    qualityGates: LocalModelGate[];
  };
  performance: {
    benchmarkRounds: number;
    buildDurationsMs: number[];
    medianBuildMs: number;
    minimumBuildMs: number;
    maximumBuildMs: number;
    elementsPerSecond: number;
    databaseByteSize: number;
    databaseSha256: string;
  };
  content: {
    contentDbVersion: number;
    schemaVersion: number;
    changedFromPackagedBaseline: boolean;
    previousDatabaseSha256: string | null;
    rowCounts: Record<string, number>;
    sourceTypes: Record<string, number>;
    requiredFieldCount: number;
    resolvedRequiredFieldCount: number;
    tracedElementCount: number;
    multipleSourceElementCount: number;
  };
}

export const localModelReport = reportData as unknown as LocalModelReport;
