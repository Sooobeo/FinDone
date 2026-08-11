import "server-only";

import { capabilitiesForRole, parseAdminRole } from "@/lib/access";
import { getServerSupabase } from "@/lib/supabase/server";
import { runtimeMode } from "@/lib/supabase/config";
import type {
  AdminCapabilities,
  ConceptElement,
  DistractorItem,
  ReleaseRecord,
  SourceItem,
  ValidationIssueRecord,
  ValidationRunRecord,
  WorkflowJob,
  WorkflowRevision,
} from "@/lib/types";

type Row = Record<string, unknown>;

function text(row: Row, ...keys: string[]): string {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === "string") return value;
    if (typeof value === "number") return String(value);
  }
  return "";
}

function number(row: Row, key: string, fallback = 0): number {
  const value = row[key];
  if (typeof value === "number") return value;
  const parsed = typeof value === "string" ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : fallback;
}

function nullableText(row: Row, key: string): string | null {
  const value = row[key];
  return typeof value === "string" && value ? value : null;
}

function object(row: Row, key: string): Record<string, unknown> {
  const value = row[key];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export interface ValidationWorkspace {
  revisions: WorkflowRevision[];
  runs: ValidationRunRecord[];
  issues: ValidationIssueRecord[];
  jobs: WorkflowJob[];
}

export interface ReviewWorkspace {
  revisions: WorkflowRevision[];
  runs: ValidationRunRecord[];
}

export interface ReleaseWorkspace {
  releases: ReleaseRecord[];
  runs: ValidationRunRecord[];
  jobs: WorkflowJob[];
}

export async function getAdminCapabilities(): Promise<AdminCapabilities> {
  const supabase = await getServerSupabase();
  if (!supabase) return capabilitiesForRole(null);

  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) return capabilitiesForRole(null);
  const { data, error } = await supabase
    .from("admin_users")
    .select("role,is_active")
    .eq("user_id", auth.user.id)
    .maybeSingle();
  if (error || !data?.is_active) return capabilitiesForRole(null);
  return capabilitiesForRole(parseAdminRole(data.role));
}

export async function getConceptElements(): Promise<ConceptElement[]> {
  const supabase = await getServerSupabase();
  if (!supabase) {
    if (runtimeMode() !== "demo" || process.env.NODE_ENV === "production") return [];
    return (await import("@/lib/fixtures")).conceptElements;
  }

  const { data, error } = await supabase
    .from("admin_content_grid")
    .select("*")
    .order("display_order", { ascending: true });
  if (error) throw new Error(`개념 DB를 불러오지 못했습니다: ${error.message}`);

  return ((data ?? []) as Row[]).map((row) => {
    const rawMode = text(row, "mode").toLocaleLowerCase("en-US");
    return {
    elementId: text(row, "element_id"),
    domainId: text(row, "domain_id"),
    domainName: text(row, "domain_name"),
    elementNumber: number(row, "element_number"),
    title: text(row, "title"),
    mode: rawMode === "concept" || rawMode === "c/n" ? "concept" : "calculation",
    coreRelation: text(row, "core_relation"),
    definition: text(row, "definition_markdown"),
    intuition: text(row, "intuition_markdown"),
    elementScopeNotes: text(row, "element_scope_notes"),
    scopeNotes: text(row, "learning_notes_markdown"),
    formulaExpression: text(row, "expression_markdown"),
    formulaAssumptions: text(row, "assumptions_markdown"),
    formulaNotes: text(row, "notes_markdown"),
    checklist: text(row, "checklist_markdown"),
    sourceLabel: text(row, "source_label"),
    sourceLocator: text(row, "source_locator"),
    specSectionLocator: text(row, "spec_section_locator"),
    status: (text(row, "revision_status", "status") || "published") as ConceptElement["status"],
    issueCount: number(row, "issue_count"),
    updatedAt: text(row, "updated_at") || "—",
    updatedBy: text(row, "updated_by") || "—",
    };
  });
}

export async function getSources(): Promise<SourceItem[]> {
  const supabase = await getServerSupabase();
  if (!supabase) {
    if (runtimeMode() !== "demo" || process.env.NODE_ENV === "production") return [];
    return (await import("@/lib/fixtures")).sourceItems;
  }

  const { data, error } = await supabase
    .from("source_catalog_overview")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) throw new Error(`출처 목록을 불러오지 못했습니다: ${error.message}`);

  return ((data ?? []) as Row[]).map((row) => {
    const sourceType = text(row, "kind", "source_type").toLocaleLowerCase("en-US");
    const locator = text(row, "locator");
    const kind: SourceItem["kind"] = sourceType.includes("pdf")
      ? "pdf"
      : sourceType.includes("sheet")
        ? "spreadsheet"
        : sourceType === "file"
          ? "document"
        : /^https?:\/\//.test(locator)
          ? "url"
          : "document";
    return {
      id: text(row, "source_id"),
      label: text(row, "label"),
      kind,
      locator,
      status: parseSourceStatus(text(row, "latest_parse_status")),
      linkedElements: number(row, "linked_element_count"),
      createdAt: text(row, "created_at") || "—",
    };
  });
}

export async function getDistractors(): Promise<DistractorItem[]> {
  const supabase = await getServerSupabase();
  if (!supabase) {
    if (runtimeMode() !== "demo" || process.env.NODE_ENV === "production") return [];
    return (await import("@/lib/fixtures")).distractorItems;
  }

  const { data, error } = await supabase
    .from("distractors")
    .select("distractor_id,element_id,text,explanation,misconception_type,difficulty,is_enabled,updated_at,elements(title)")
    .order("element_id", { ascending: true });
  if (error) throw new Error(`오답 후보를 불러오지 못했습니다: ${error.message}`);

  return ((data ?? []) as Row[]).map((row) => {
    const joined = row.elements as { title?: string } | null;
    return {
      id: text(row, "distractor_id"),
      elementId: text(row, "element_id"),
      elementTitle: joined?.title ?? "",
      text: text(row, "text"),
      rationale: text(row, "explanation"),
      confusionType: text(row, "misconception_type"),
      difficulty: parseDifficulty(row.difficulty),
      active: Boolean(row.is_enabled),
      status: (text(row, "status") || "draft") as DistractorItem["status"],
      updatedAt: text(row, "updated_at") || "—",
    };
  });
}

export async function getValidationWorkspace(): Promise<ValidationWorkspace> {
  const supabase = await getServerSupabase();
  if (!supabase) return { revisions: [], runs: [], issues: [], jobs: [] };

  const { data: revisionRows, error: revisionError } = await supabase
    .from("content_revision_status")
    .select("*")
    .in("state", ["draft", "validating", "validation_failed"])
    .order("created_at", { ascending: false })
    .limit(150);
  if (revisionError) throw new Error(`검증 대상 revision을 불러오지 못했습니다: ${revisionError.message}`);
  const revisions = ((revisionRows ?? []) as Row[]).map(mapRevision);
  const revisionIds = revisions.map((revision) => revision.revisionId);
  if (!revisionIds.length) return { revisions, runs: [], issues: [], jobs: [] };

  const [{ data: runRows, error: runError }, { data: jobRows, error: jobError }] = await Promise.all([
    supabase
      .from("validation_runs")
      .select("*")
      .in("revision_id", revisionIds)
      .order("created_at", { ascending: false }),
    supabase
      .from("ingestion_jobs")
      .select("*")
      .in("revision_id", revisionIds)
      .order("created_at", { ascending: false }),
  ]);
  if (runError) throw new Error(`검증 실행 이력을 불러오지 못했습니다: ${runError.message}`);
  if (jobError) throw new Error(`검증 작업 큐를 불러오지 못했습니다: ${jobError.message}`);
  const runs = ((runRows ?? []) as Row[]).map(mapValidationRun);
  const runIds = runs.map((run) => run.validationRunId);
  let issues: ValidationIssueRecord[] = [];
  if (runIds.length) {
    const { data: issueRows, error: issueError } = await supabase
      .from("validation_issues")
      .select("*")
      .in("validation_run_id", runIds)
      .order("created_at", { ascending: false });
    if (issueError) throw new Error(`검증 이슈를 불러오지 못했습니다: ${issueError.message}`);
    issues = ((issueRows ?? []) as Row[]).map(mapValidationIssue);
  }

  return {
    revisions,
    runs,
    issues,
    jobs: ((jobRows ?? []) as Row[]).map(mapWorkflowJob),
  };
}

export async function getReviewWorkspace(): Promise<ReviewWorkspace> {
  const supabase = await getServerSupabase();
  if (!supabase) return { revisions: [], runs: [] };

  const { data: statusRows, error: statusError } = await supabase
    .from("content_revision_status")
    .select("*")
    .eq("state", "reviewed")
    .order("state_changed_at", { ascending: true })
    .limit(100);
  if (statusError) throw new Error(`검토 대기 목록을 불러오지 못했습니다: ${statusError.message}`);
  const baseRevisions = ((statusRows ?? []) as Row[]).map(mapRevision);
  if (!baseRevisions.length) return { revisions: [], runs: [] };

  const entityKeys = [...new Set(baseRevisions.map((revision) => revision.entityKey))];
  const revisionIds = baseRevisions.map((revision) => revision.revisionId);
  const [{ data: snapshotRows, error: snapshotError }, { data: runRows, error: runError }] = await Promise.all([
    supabase
      .from("content_revisions")
      .select("revision_id,entity_type,entity_key,revision_number,snapshot")
      .in("entity_key", entityKeys)
      .order("revision_number", { ascending: true })
      .limit(500),
    supabase
      .from("validation_runs")
      .select("*")
      .in("revision_id", revisionIds)
      .order("created_at", { ascending: false }),
  ]);
  if (snapshotError) throw new Error(`revision 내용을 불러오지 못했습니다: ${snapshotError.message}`);
  if (runError) throw new Error(`검증 근거를 불러오지 못했습니다: ${runError.message}`);
  const snapshots = (snapshotRows ?? []) as Row[];
  const revisions = baseRevisions.map((revision) => {
    const sameEntity = snapshots
      .filter(
        (row) =>
          text(row, "entity_type") === revision.entityType &&
          text(row, "entity_key") === revision.entityKey,
      )
      .sort((left, right) => number(left, "revision_number") - number(right, "revision_number"));
    const currentIndex = sameEntity.findIndex((row) => text(row, "revision_id") === revision.revisionId);
    return {
      ...revision,
      snapshot: currentIndex >= 0 ? object(sameEntity[currentIndex], "snapshot") : {},
      previousSnapshot: currentIndex > 0 ? object(sameEntity[currentIndex - 1], "snapshot") : {},
    };
  });

  return { revisions, runs: ((runRows ?? []) as Row[]).map(mapValidationRun) };
}

export async function getReleaseWorkspace(): Promise<ReleaseWorkspace> {
  const supabase = await getServerSupabase();
  if (!supabase) return { releases: [], runs: [], jobs: [] };

  const { data: releaseRows, error: releaseError } = await supabase
    .from("release_overview")
    .select("*")
    .order("content_version", { ascending: false })
    .limit(100);
  if (releaseError) throw new Error(`릴리스 이력을 불러오지 못했습니다: ${releaseError.message}`);
  const releases = ((releaseRows ?? []) as Row[]).map(mapRelease);
  const releaseIds = releases.map((release) => release.releaseId);
  if (!releaseIds.length) return { releases, runs: [], jobs: [] };

  const [{ data: runRows, error: runError }, { data: jobRows, error: jobError }] = await Promise.all([
    supabase
      .from("validation_runs")
      .select("*")
      .in("release_id", releaseIds)
      .order("created_at", { ascending: false }),
    supabase
      .from("ingestion_jobs")
      .select("*")
      .in("release_id", releaseIds)
      .order("created_at", { ascending: false }),
  ]);
  if (runError) throw new Error(`릴리스 검증 이력을 불러오지 못했습니다: ${runError.message}`);
  if (jobError) throw new Error(`릴리스 작업 큐를 불러오지 못했습니다: ${jobError.message}`);
  return {
    releases,
    runs: ((runRows ?? []) as Row[]).map(mapValidationRun),
    jobs: ((jobRows ?? []) as Row[]).map(mapWorkflowJob),
  };
}

function mapRevision(row: Row): WorkflowRevision {
  return {
    revisionId: text(row, "revision_id"),
    entityType: text(row, "entity_type") as WorkflowRevision["entityType"],
    entityKey: text(row, "entity_key"),
    revisionNumber: number(row, "revision_number"),
    operation: text(row, "operation") as WorkflowRevision["operation"],
    contentHash: text(row, "content_hash"),
    changeReason: text(row, "change_reason"),
    createdAt: text(row, "created_at"),
    createdBy: text(row, "created_by"),
    state: (text(row, "state") || "draft") as WorkflowRevision["state"],
    stateNote: text(row, "state_note"),
    stateChangedAt: text(row, "state_changed_at"),
  };
}

function mapValidationRun(row: Row): ValidationRunRecord {
  return {
    validationRunId: text(row, "validation_run_id"),
    targetType: text(row, "target_type") as ValidationRunRecord["targetType"],
    revisionId: nullableText(row, "revision_id"),
    releaseId: nullableText(row, "release_id"),
    status: text(row, "status") as ValidationRunRecord["status"],
    validatorName: text(row, "validator_name"),
    validatorVersion: text(row, "validator_version"),
    checksTotal: number(row, "checks_total"),
    checksPassed: number(row, "checks_passed"),
    checksFailed: number(row, "checks_failed"),
    summary: object(row, "summary"),
    startedAt: nullableText(row, "started_at"),
    completedAt: nullableText(row, "completed_at"),
    createdAt: text(row, "created_at"),
  };
}

function mapValidationIssue(row: Row): ValidationIssueRecord {
  return {
    validationIssueId: text(row, "validation_issue_id"),
    validationRunId: text(row, "validation_run_id"),
    severity: text(row, "severity") as ValidationIssueRecord["severity"],
    code: text(row, "code"),
    fieldPath: text(row, "field_path"),
    message: text(row, "message"),
    details: object(row, "details"),
    createdAt: text(row, "created_at"),
  };
}

function mapWorkflowJob(row: Row): WorkflowJob {
  return {
    jobId: text(row, "job_id"),
    jobKind: text(row, "job_kind"),
    status: text(row, "status") as WorkflowJob["status"],
    revisionId: nullableText(row, "revision_id"),
    releaseId: nullableText(row, "release_id"),
    progressPercent: number(row, "progress_percent"),
    errorMessage: nullableText(row, "error_message"),
    createdAt: text(row, "created_at"),
  };
}

function mapRelease(row: Row): ReleaseRecord {
  return {
    releaseId: text(row, "release_id"),
    contentVersion: number(row, "content_version"),
    versionName: text(row, "version_name"),
    schemaVersion: number(row, "schema_version"),
    minimumAppVersion: number(row, "minimum_app_version"),
    status: text(row, "status") as ReleaseRecord["status"],
    releaseNotes: text(row, "release_notes"),
    manifestSha256: nullableText(row, "manifest_sha256"),
    databaseSha256: nullableText(row, "database_sha256"),
    databaseByteSize: row.database_byte_size == null ? null : number(row, "database_byte_size"),
    publishedAt: nullableText(row, "published_at"),
    createdAt: text(row, "created_at"),
    itemCount: number(row, "item_count"),
    artifactCount: number(row, "artifact_count"),
    activeChannels: Array.isArray(row.active_channels)
      ? row.active_channels.filter((value): value is string => typeof value === "string")
      : [],
  };
}

function parseSourceStatus(value: string): SourceItem["status"] {
  if (value === "failed") return "failed";
  if (value === "needs_review") return "needs_review";
  if (value === "ready" || value === "parsed") return "ready";
  return "processing";
}

function parseDifficulty(value: unknown): DistractorItem["difficulty"] {
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numeric)) {
    if (numeric <= 2) return "기초";
    if (numeric >= 4) return "심화";
  }
  return "보통";
}
