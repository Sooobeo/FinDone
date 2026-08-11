export type ContentStatus =
  | "draft"
  | "validating"
  | "reviewed"
  | "approved"
  | "published"
  | "rejected";

export type Difficulty = "기초" | "보통" | "심화";

export type AdminRole = "owner" | "viewer";

export interface AdminCapabilities {
  role: AdminRole | null;
  canEdit: boolean;
  canValidateRevision: boolean;
  canReview: boolean;
  canRelease: boolean;
  canValidateRelease: boolean;
}

export type RevisionState =
  | "draft"
  | "validating"
  | "validation_failed"
  | "reviewed"
  | "approved"
  | "rejected"
  | "published"
  | "archived";

export type ValidationRunStatus = "queued" | "running" | "passed" | "failed" | "cancelled";

export interface WorkflowRevision {
  revisionId: string;
  entityType: "domain" | "element" | "concept" | "formula" | "distractor";
  entityKey: string;
  revisionNumber: number;
  operation: "insert" | "update" | "delete";
  contentHash: string;
  changeReason: string;
  createdAt: string;
  createdBy: string;
  state: RevisionState;
  stateNote: string;
  stateChangedAt: string;
  snapshot?: Record<string, unknown>;
  previousSnapshot?: Record<string, unknown>;
}

export interface ValidationRunRecord {
  validationRunId: string;
  targetType: "revision" | "release" | "system";
  revisionId: string | null;
  releaseId: string | null;
  status: ValidationRunStatus;
  validatorName: string;
  validatorVersion: string;
  checksTotal: number;
  checksPassed: number;
  checksFailed: number;
  summary: Record<string, unknown>;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
}

export interface ValidationIssueRecord {
  validationIssueId: string;
  validationRunId: string;
  severity: "info" | "warning" | "error";
  code: string;
  fieldPath: string;
  message: string;
  details: Record<string, unknown>;
  createdAt: string;
}

export type ReleaseStatus =
  | "draft"
  | "building"
  | "validation_failed"
  | "ready"
  | "published"
  | "withdrawn";

export interface ReleaseRecord {
  releaseId: string;
  contentVersion: number;
  versionName: string;
  schemaVersion: number;
  minimumAppVersion: number;
  status: ReleaseStatus;
  releaseNotes: string;
  manifestSha256: string | null;
  databaseSha256: string | null;
  databaseByteSize: number | null;
  publishedAt: string | null;
  createdAt: string;
  itemCount: number;
  artifactCount: number;
  activeChannels: string[];
}

export interface WorkflowJob {
  jobId: string;
  jobKind: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  revisionId: string | null;
  releaseId: string | null;
  progressPercent: number;
  errorMessage: string | null;
  createdAt: string;
}

export interface ConceptElement {
  elementId: string;
  domainId: string;
  domainName: string;
  elementNumber: number;
  title: string;
  mode: "calculation" | "concept";
  coreRelation: string;
  definition: string;
  intuition: string;
  elementScopeNotes: string;
  scopeNotes: string;
  formulaExpression: string;
  formulaAssumptions: string;
  formulaNotes: string;
  checklist: string;
  sourceLabel: string;
  sourceLocator: string;
  specSectionLocator: string;
  status: ContentStatus;
  issueCount: number;
  updatedAt: string;
  updatedBy: string;
}

export interface SourceItem {
  id: string;
  label: string;
  kind: "pdf" | "spreadsheet" | "document" | "url";
  locator: string;
  status: "ready" | "processing" | "needs_review" | "failed";
  linkedElements: number;
  domains: SourceDomain[];
  size?: string;
  createdAt: string;
  jobId?: string;
  jobStatus?: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progressPercent?: number;
  processingStage?: string;
  processingError?: string;
  processingUpdatedAt?: string;
  candidateCount?: number;
  topCandidateElementId?: string;
  topCandidateScore?: number;
  versionCount?: number;
  catalogOnly?: boolean;
}

export interface SourceDomain {
  id: string;
  name: string;
  displayOrder: number;
}

export interface DistractorItem {
  id: string;
  elementId: string;
  elementTitle: string;
  text: string;
  rationale: string;
  confusionType: string;
  difficulty: Difficulty;
  active: boolean;
  status: ContentStatus;
  updatedAt: string;
}

export interface ValidationIssue {
  id: string;
  elementId: string;
  title: string;
  field: string;
  severity: "error" | "warning" | "info";
  message: string;
  suggestion: string;
}

export interface ReleaseItem {
  version: string;
  status: "published" | "building" | "failed" | "draft";
  changes: number;
  elements: number;
  size: string;
  checksum: string;
  createdAt: string;
  author: string;
}

export type ContentGenerationStatus =
  | "queued"
  | "running"
  | "ready_for_review"
  | "no_changes"
  | "rejected"
  | "releasing"
  | "released"
  | "failed";

export interface ContentGenerationBatch {
  batchId: string;
  requestKey: string;
  status: ContentGenerationStatus;
  modelName: string;
  promptVersion: string;
  baselineContentVersion: number;
  releaseNotes: string;
  minimumAppVersion: number;
  progressPercent: number;
  processingStage: string;
  attemptCount: number;
  maxAttempts: number;
  itemCount: number;
  changedElementCount: number;
  evidenceCount: number;
  autoRepairCount: number;
  sourceCount: number;
  modelRunCount: number;
  statistics: Record<string, unknown>;
  errorMessage: string | null;
  releaseId: string | null;
  releaseStatus: ReleaseStatus | null;
  releaseContentVersion: number | null;
  releaseVersionName: string | null;
  createdAt: string;
  completedAt: string | null;
}

export interface ContentGenerationItem {
  generationItemId: string;
  batchId: string;
  elementId: string;
  entityType: "element" | "concept" | "formula";
  entityKey: string;
  baselineSnapshot: Record<string, unknown>;
  generatedSnapshot: Record<string, unknown>;
  changedFields: string[];
  changeSummary: string;
  confidence: number;
  riskLevel: "low" | "medium" | "high";
  validationSummary: Record<string, unknown>;
  revisionId: string | null;
}

export interface ContentGenerationEvidence {
  generationEvidenceId: string;
  generationItemId: string;
  fieldPath: string;
  sourceFragmentId: string;
  supportRole: "primary" | "corroborating" | "context";
  rationale: string;
  sourceLabel: string;
  sourceLocator: string;
  fragmentLocator: Record<string, unknown>;
  contentExcerpt: string;
}
