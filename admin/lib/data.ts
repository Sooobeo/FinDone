import "server-only";

import { capabilitiesForRole, parseAdminRole } from "@/lib/access";
import { mergeSourceStatus, parseSourceStatus, type SourceStatusRow } from "@/lib/source-processing";
import { getServerSupabase } from "@/lib/supabase/server";
import { runtimeMode } from "@/lib/supabase/config";
import type {
  AdminCapabilities,
  ContentGenerationBatch,
  ContentGenerationEvidence,
  ContentGenerationItem,
  ConceptElement,
  DistractorItem,
  GlossaryCategoryItem,
  GlossaryAdminReferenceSource,
  GlossaryCompileJobItem,
  GlossaryReleaseItem,
  GlossarySourceItem,
  GlossaryTermItem,
  ReleaseRecord,
  SourceDomain,
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

function relation(value: unknown): Row {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate && typeof candidate === "object" && !Array.isArray(candidate)
    ? candidate as Row
    : {};
}

function nullableNumber(row: Row, key: string): number | null {
  const value = row[key];
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export interface ValidationWorkspace {
  revisions: WorkflowRevision[];
  runs: ValidationRunRecord[];
  issues: ValidationIssueRecord[];
  jobs: WorkflowJob[];
}

export interface ReviewWorkspace {
  batches: ContentGenerationBatch[];
  items: ContentGenerationItem[];
  evidence: ContentGenerationEvidence[];
  jobs: WorkflowJob[];
}

export interface ReleaseWorkspace {
  releases: ReleaseRecord[];
  runs: ValidationRunRecord[];
  jobs: WorkflowJob[];
}

export interface GlossaryWorkspace {
  categories: GlossaryCategoryItem[];
  sources: GlossarySourceItem[];
  adminReferenceSources: GlossaryAdminReferenceSource[];
  terms: GlossaryTermItem[];
  releases: GlossaryReleaseItem[];
  jobs: GlossaryCompileJobItem[];
}

function stringArray(row: Row, key: string): string[] {
  const value = row[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

export async function getGlossaryWorkspace(): Promise<GlossaryWorkspace> {
  const empty: GlossaryWorkspace = {
    categories: [], sources: [], adminReferenceSources: [], terms: [], releases: [], jobs: [],
  };
  const supabase = await getServerSupabase();
  if (!supabase) return empty;

  const [
    categoryResult,
    sourceResult,
    adminSourceResult,
    referenceResult,
    releaseResult,
    jobResult,
    channelResult,
  ] = await Promise.all([
    supabase.from("glossary_categories").select("*").order("display_order"),
    supabase.from("glossary_sources").select("source_code,title,public_url").order("source_code"),
    supabase.from("sources").select("source_id,label,kind,source_type").eq("is_active", true).order("label"),
    supabase.from("glossary_term_admin_references").select("term_id,source_id"),
    supabase.from("glossary_releases").select("*").order("glossary_version", { ascending: false }).limit(20),
    supabase.from("glossary_compile_jobs").select("*").order("created_at", { ascending: false }).limit(20),
    supabase.from("glossary_release_channels").select("release_id").eq("channel", "stable").maybeSingle(),
  ]);
  const firstError = categoryResult.error ?? sourceResult.error ?? adminSourceResult.error ??
    referenceResult.error ?? releaseResult.error ?? jobResult.error ?? channelResult.error;
  if (firstError) throw new Error(`용어집 작업 공간을 불러오지 못했습니다: ${firstError.message}`);

  const termRows: Row[] = [];
  const pageSize = 500;
  for (let offset = 0; ; offset += pageSize) {
    const { data, error } = await supabase
      .from("glossary_terms")
      .select("*")
      .eq("is_active", true)
      .order("category_id")
      .order("display_order")
      .range(offset, offset + pageSize - 1);
    if (error) throw new Error(`용어집 용어를 불러오지 못했습니다: ${error.message}`);
    const page = (data ?? []) as Row[];
    termRows.push(...page);
    if (page.length < pageSize) break;
  }

  const categoryCounts = new Map<string, number>();
  const adminReferencesByTerm = new Map<string, string[]>();
  ((referenceResult.data ?? []) as Row[]).forEach((row) => {
    const termId = text(row, "term_id");
    adminReferencesByTerm.set(termId, [
      ...(adminReferencesByTerm.get(termId) ?? []),
      text(row, "source_id"),
    ]);
  });
  termRows.forEach((row) => {
    const id = text(row, "category_id");
    categoryCounts.set(id, (categoryCounts.get(id) ?? 0) + 1);
  });
  const stableReleaseId = channelResult.data?.release_id ?? null;
  return {
    categories: ((categoryResult.data ?? []) as Row[]).map((row) => ({
      categoryId: text(row, "category_id"),
      name: text(row, "name"),
      displayOrder: number(row, "display_order"),
      termCount: categoryCounts.get(text(row, "category_id")) ?? 0,
    })),
    sources: ((sourceResult.data ?? []) as Row[]).map((row) => ({
      sourceCode: text(row, "source_code"),
      title: text(row, "title"),
      url: text(row, "public_url"),
    })),
    adminReferenceSources: ((adminSourceResult.data ?? []) as Row[]).map((row) => ({
      sourceId: text(row, "source_id"),
      label: text(row, "label"),
      kind: text(row, "kind"),
      sourceType: text(row, "source_type"),
    })),
    terms: termRows.map((row) => mapGlossaryTerm(row, adminReferencesByTerm.get(text(row, "term_id")) ?? [])),
    releases: ((releaseResult.data ?? []) as Row[]).map((row) => ({
      releaseId: text(row, "release_id"),
      glossaryDbVersion: number(row, "glossary_version"),
      versionName: text(row, "version_name"),
      status: text(row, "status") as GlossaryReleaseItem["status"],
      termCount: number(row, "term_count"),
      releaseNotes: text(row, "release_notes"),
      databaseByteSize: nullableNumber(row, "database_byte_size"),
      publishedAt: nullableText(row, "published_at"),
      createdAt: text(row, "created_at"),
      stable: text(row, "release_id") === stableReleaseId,
    })),
    jobs: ((jobResult.data ?? []) as Row[]).map((row) => ({
      jobId: text(row, "job_id"),
      releaseId: text(row, "release_id"),
      status: text(row, "status") as GlossaryCompileJobItem["status"],
      progressPercent: number(row, "progress_percent"),
      attemptCount: number(row, "attempt_count"),
      errorMessage: nullableText(row, "error_message"),
      createdAt: text(row, "created_at"),
      updatedAt: text(row, "updated_at"),
    })),
  };
}

function mapGlossaryTerm(row: Row, adminReferenceSourceIds: string[]): GlossaryTermItem {
  return {
    termId: text(row, "term_id"),
    categoryId: text(row, "category_id"),
    displayOrder: number(row, "display_order"),
    canonicalNameEn: text(row, "canonical_name_en"),
    canonicalNameKo: text(row, "canonical_name_ko"),
    aliases: stringArray(row, "aliases"),
    conceptType: text(row, "concept_type"),
    oneLineDefinitionKo: text(row, "one_line_definition_ko"),
    coreDefinitionKo: text(row, "core_definition_ko"),
    practicalContextKo: text(row, "practical_context_ko"),
    whyItMattersKo: text(row, "why_it_matters_ko"),
    exampleKo: text(row, "example_ko"),
    limitationsKo: stringArray(row, "limitations_ko"),
    sourceCodes: stringArray(row, "source_codes"),
    jurisdictions: stringArray(row, "jurisdictions"),
    asOfDate: text(row, "as_of_date"),
    reviewStatus: text(row, "review_status") as GlossaryTermItem["reviewStatus"],
    reviewFlags: stringArray(row, "review_flags"),
    relatedTermIds: stringArray(row, "related_term_ids"),
    formulaLatex: text(row, "formula_latex"),
    formulaNotesKo: text(row, "formula_notes_ko"),
    adminReferenceSourceIds,
    contentRevision: number(row, "content_revision"),
    updatedAt: text(row, "updated_at"),
    isActive: row.is_active === true,
  };
}

export interface LocalModelOperationalMetrics {
  connected: boolean;
  measurementAvailable: boolean;
  structuredSourceFileCount: number;
  processedBatchCount: number;
  transformedItemCount: number;
  approvedFeedbackCount: number;
  localExecutionCount: number;
}

export async function getLocalModelOperationalMetrics(): Promise<LocalModelOperationalMetrics> {
  const empty: LocalModelOperationalMetrics = {
    connected: false,
    measurementAvailable: false,
    structuredSourceFileCount: 0,
    processedBatchCount: 0,
    transformedItemCount: 0,
    approvedFeedbackCount: 0,
    localExecutionCount: 0,
  };
  const supabase = await getServerSupabase();
  if (!supabase) return empty;

  const [files, batches, items, approved, runs] = await Promise.all([
    supabase
      .from("source_files")
      .select("source_version_id,original_filename,file_role")
      .eq("file_role", "original")
      .limit(5000),
    supabase
      .from("content_generation_batches")
      .select("batch_id", { count: "exact", head: true })
      .eq("model_name", "findone-local-content-v1"),
    supabase
      .from("content_generation_items")
      .select("generation_item_id", { count: "exact", head: true }),
    supabase
      .from("content_generation_items")
      .select("generation_item_id", { count: "exact", head: true })
      .not("revision_id", "is", null),
    supabase
      .from("content_model_runs")
      .select("model_run_id", { count: "exact", head: true }),
  ]);
  const failed = [files.error, batches.error, items.error, approved.error, runs.error].some(Boolean);
  const structuredExtension = /\.(?:csv|json|jsonl|ndjson|xlsx|db|sqlite|sqlite3)$/i;
  const structuredSourceFileCount = (files.data ?? []).filter((row) =>
    structuredExtension.test(typeof row.original_filename === "string" ? row.original_filename : "")
  ).length;
  return {
    connected: true,
    measurementAvailable: !failed,
    structuredSourceFileCount,
    processedBatchCount: batches.count ?? 0,
    transformedItemCount: items.count ?? 0,
    approvedFeedbackCount: approved.count ?? 0,
    localExecutionCount: runs.count ?? 0,
  };
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

  const [sourceResult, linkResult, elementResult, domainResult] = await Promise.all([
    supabase.from("source_catalog_overview").select("*").order("created_at", { ascending: false }),
    supabase.from("element_sources").select("source_id,element_id"),
    supabase.from("elements").select("element_id,domain_id"),
    supabase.from("domains").select("domain_id,name,display_order"),
  ]);
  const firstError = sourceResult.error ?? linkResult.error ?? elementResult.error ?? domainResult.error;
  if (firstError) throw new Error(`출처 목록을 불러오지 못했습니다: ${firstError.message}`);

  const domainsById = new Map<string, SourceDomain>();
  for (const row of (domainResult.data ?? []) as Row[]) {
    const id = text(row, "domain_id");
    if (!id) continue;
    domainsById.set(id, {
      id,
      name: text(row, "name") || id,
      displayOrder: number(row, "display_order", Number.MAX_SAFE_INTEGER),
    });
  }

  const domainByElement = new Map<string, string>();
  for (const row of (elementResult.data ?? []) as Row[]) {
    domainByElement.set(text(row, "element_id"), text(row, "domain_id"));
  }

  const domainIdsBySource = new Map<string, Set<string>>();
  for (const row of (linkResult.data ?? []) as Row[]) {
    const sourceId = text(row, "source_id");
    const domainId = domainByElement.get(text(row, "element_id"));
    if (!sourceId || !domainId) continue;
    const sourceDomains = domainIdsBySource.get(sourceId) ?? new Set<string>();
    sourceDomains.add(domainId);
    domainIdsBySource.set(sourceId, sourceDomains);
  }

  return ((sourceResult.data ?? []) as Row[]).map((row) => {
    const sourceType = text(row, "source_type", "kind").toLocaleLowerCase("en-US");
    const sourceKind = text(row, "kind").toLocaleLowerCase("en-US");
    const locator = text(row, "locator");
    const kind: SourceItem["kind"] = sourceType.includes("pdf")
      ? "pdf"
      : sourceType.includes("sheet") || sourceType.includes("excel") || sourceType.includes("csv")
        ? "spreadsheet"
        : sourceKind === "url" || /^https?:\/\//.test(locator)
          ? "url"
          : "document";
    const source: SourceItem = {
      id: text(row, "source_id"),
      label: text(row, "label"),
      kind,
      locator,
      status: parseSourceStatus(text(row, "latest_parse_status")),
      linkedElements: number(row, "linked_element_count"),
      domains: [...(domainIdsBySource.get(text(row, "source_id")) ?? [])]
        .map((domainId) => domainsById.get(domainId))
        .filter((domain): domain is SourceDomain => Boolean(domain))
        .sort((left, right) => left.displayOrder - right.displayOrder || left.name.localeCompare(right.name, "ko-KR")),
      createdAt: text(row, "created_at") || "—",
      versionCount: number(row, "version_count"),
      catalogOnly: number(row, "version_count") === 0,
    };
    return mergeSourceStatus(source, row as SourceStatusRow);
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
  if (!supabase) return { batches: [], items: [], evidence: [], jobs: [] };

  const { data: batchRows, error: batchError } = await supabase
    .from("content_generation_overview")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(30);
  if (batchError) throw new Error(`로컬 콘텐츠 변환 배치를 불러오지 못했습니다: ${batchError.message}`);
  const batches = ((batchRows ?? []) as Row[]).map(mapGenerationBatch);
  const batchIds = batches.map((batch) => batch.batchId);
  if (!batchIds.length) return { batches, items: [], evidence: [], jobs: [] };

  const { data: itemRows, error: itemError } = await supabase
    .from("content_generation_items")
    .select("*")
    .in("batch_id", batchIds)
    .order("element_id", { ascending: true })
    .limit(1500);
  if (itemError) throw new Error(`생성 후보를 불러오지 못했습니다: ${itemError.message}`);
  const items = ((itemRows ?? []) as Row[]).map(mapGenerationItem);
  const itemIds = items.map((item) => item.generationItemId);

  let evidence: ContentGenerationEvidence[] = [];
  if (itemIds.length) {
    const { data: evidenceRows, error: evidenceError } = await supabase
      .from("content_generation_evidence")
      .select("generation_evidence_id,generation_item_id,field_path,source_fragment_id,support_role,rationale,source_fragments(locator,content_text,source_versions(source_id,sources(label,locator)))")
      .in("generation_item_id", itemIds)
      .order("created_at", { ascending: true })
      .limit(6000);
    if (evidenceError) throw new Error(`생성 근거를 불러오지 못했습니다: ${evidenceError.message}`);
    evidence = ((evidenceRows ?? []) as Row[]).map(mapGenerationEvidence);
  }

  const releaseIds = batches
    .map((batch) => batch.releaseId)
    .filter((releaseId): releaseId is string => Boolean(releaseId));
  let jobs: WorkflowJob[] = [];
  if (releaseIds.length) {
    const { data: jobRows, error: jobError } = await supabase
      .from("ingestion_jobs")
      .select("*")
      .in("release_id", releaseIds)
      .order("created_at", { ascending: false });
    if (jobError) throw new Error(`릴리스 작업 상태를 불러오지 못했습니다: ${jobError.message}`);
    jobs = ((jobRows ?? []) as Row[]).map(mapWorkflowJob);
  }
  return { batches, items, evidence, jobs };
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

function mapGenerationBatch(row: Row): ContentGenerationBatch {
  const releaseStatus = nullableText(row, "release_status");
  return {
    batchId: text(row, "batch_id"),
    requestKey: text(row, "request_key"),
    status: text(row, "status") as ContentGenerationBatch["status"],
    modelName: text(row, "model_name"),
    promptVersion: text(row, "prompt_version"),
    baselineContentVersion: number(row, "baseline_content_version"),
    releaseNotes: text(row, "release_notes"),
    minimumAppVersion: number(row, "minimum_app_version", 1),
    progressPercent: number(row, "progress_percent"),
    processingStage: text(row, "processing_stage"),
    attemptCount: number(row, "attempt_count"),
    maxAttempts: number(row, "max_attempts", 3),
    itemCount: number(row, "persisted_item_count", number(row, "item_count")),
    changedElementCount: number(row, "persisted_changed_element_count", number(row, "changed_element_count")),
    evidenceCount: number(row, "persisted_evidence_count", number(row, "evidence_count")),
    autoRepairCount: number(row, "auto_repair_count"),
    sourceCount: number(row, "source_count"),
    modelRunCount: number(row, "model_run_count"),
    statistics: object(row, "statistics"),
    errorMessage: nullableText(row, "error_message"),
    releaseId: nullableText(row, "release_id"),
    releaseStatus: releaseStatus as ContentGenerationBatch["releaseStatus"],
    releaseContentVersion: nullableNumber(row, "release_content_version"),
    releaseVersionName: nullableText(row, "release_version_name"),
    createdAt: text(row, "created_at"),
    completedAt: nullableText(row, "completed_at"),
  };
}

function mapGenerationItem(row: Row): ContentGenerationItem {
  const changedFields = Array.isArray(row.changed_fields)
    ? row.changed_fields.filter((value): value is string => typeof value === "string")
    : [];
  return {
    generationItemId: text(row, "generation_item_id"),
    batchId: text(row, "batch_id"),
    elementId: text(row, "element_id"),
    entityType: text(row, "entity_type") as ContentGenerationItem["entityType"],
    entityKey: text(row, "entity_key"),
    baselineSnapshot: object(row, "baseline_snapshot"),
    generatedSnapshot: object(row, "generated_snapshot"),
    changedFields,
    changeSummary: text(row, "change_summary"),
    confidence: number(row, "confidence"),
    riskLevel: text(row, "risk_level") as ContentGenerationItem["riskLevel"],
    validationSummary: object(row, "validation_summary"),
    revisionId: nullableText(row, "revision_id"),
  };
}

function mapGenerationEvidence(row: Row): ContentGenerationEvidence {
  const fragment = relation(row.source_fragments);
  const version = relation(fragment.source_versions);
  const source = relation(version.sources);
  return {
    generationEvidenceId: text(row, "generation_evidence_id"),
    generationItemId: text(row, "generation_item_id"),
    fieldPath: text(row, "field_path"),
    sourceFragmentId: text(row, "source_fragment_id"),
    supportRole: text(row, "support_role") as ContentGenerationEvidence["supportRole"],
    rationale: text(row, "rationale"),
    sourceLabel: text(source, "label") || text(version, "source_id"),
    sourceLocator: text(source, "locator"),
    fragmentLocator: object(fragment, "locator"),
    contentExcerpt: text(fragment, "content_text").slice(0, 4000),
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

function parseDifficulty(value: unknown): DistractorItem["difficulty"] {
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numeric)) {
    if (numeric <= 2) return "기초";
    if (numeric >= 4) return "심화";
  }
  return "보통";
}
