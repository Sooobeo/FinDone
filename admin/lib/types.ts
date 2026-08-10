export type ContentStatus =
  | "draft"
  | "validating"
  | "reviewed"
  | "approved"
  | "published"
  | "rejected";

export type Difficulty = "기초" | "보통" | "심화";

export type AdminRole = "owner" | "editor" | "reviewer" | "releaser";

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
  size?: string;
  createdAt: string;
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
