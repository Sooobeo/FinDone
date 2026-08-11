"use client";

import {
  Check,
  ChevronRight,
  CircleAlert,
  Database,
  FileDiff,
  FileText,
  LoaderCircle,
  MessageSquareText,
  RefreshCw,
  Rocket,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { formatWorkflowDate, JobStatusBadge, roleLabel } from "@/components/workflow-status";
import type { ReviewWorkspace } from "@/lib/data";
import { packagedContentInfo } from "@/lib/packaged-info";
import type {
  AdminCapabilities,
  ContentGenerationBatch,
  ContentGenerationItem,
  ContentGenerationStatus,
} from "@/lib/types";

type GenerationAction = "create" | "approve" | "reject";

const fieldNames: Record<string, string> = {
  title: "제목",
  core_relation: "핵심 관계",
  scope_notes: "적용 범위",
  definition_markdown: "정의",
  intuition_markdown: "직관 설명",
  learning_notes_markdown: "상세 학습 설명",
  checklist_markdown: "실무 사용 사례",
  glossary_terms: "용어",
  expression_markdown: "수식",
  assumptions_markdown: "수식 가정",
  notes_markdown: "수식 사용 사례",
  variables: "변수 정의",
};

const stageLabels: Record<string, string> = {
  queued: "생성 Worker 대기 중",
  retry_queued: "자동 재시도 대기 중",
  baseline_loading: "기존 앱 DB 읽는 중",
  evidence_matching: "원문 근거와 학습 요소 연결 중",
  structured_generation: "앱용 콘텐츠 구조화 생성 중",
  automatic_repair: "검증 오류 자동 수정 중",
  final_validation: "근거·형식 최종 자동 검증 중",
  final_review_ready: "최종 검토 준비 완료",
  no_supported_changes: "근거로 뒷받침되는 변경 없음",
  release_queued: "클린 SQLite 빌드 대기 중",
  stable_released: "stable 앱 DB 공개 완료",
  release_validation_failed: "릴리스 DB 검증 실패",
  release_withdrawn: "릴리스 철회됨",
  rejected: "최종 검토에서 반려됨",
  failed: "자동 처리 실패",
};

const activeStatuses = new Set<ContentGenerationStatus>(["queued", "running", "releasing"]);

export function ReviewConsole({
  workspace,
  capabilities,
  demo,
  viewerMode = false,
}: {
  workspace: ReviewWorkspace;
  capabilities: AdminCapabilities;
  demo: boolean;
  viewerMode?: boolean;
}) {
  const router = useRouter();
  const initialBatch = workspace.batches.find((batch) => batch.status === "ready_for_review")
    ?? workspace.batches.find((batch) => activeStatuses.has(batch.status))
    ?? workspace.batches[0];
  const [selectedBatchId, setSelectedBatchId] = useState(initialBatch?.batchId ?? "");
  const selectedBatch = workspace.batches.find((batch) => batch.batchId === selectedBatchId)
    ?? workspace.batches[0]
    ?? null;
  const batchItems = useMemo(
    () => workspace.items.filter((item) => item.batchId === selectedBatch?.batchId),
    [selectedBatch?.batchId, workspace.items],
  );
  const [selectedItemId, setSelectedItemId] = useState(batchItems[0]?.generationItemId ?? "");
  const selectedItem = batchItems.find((item) => item.generationItemId === selectedItemId)
    ?? batchItems[0]
    ?? null;
  const [comment, setComment] = useState("");
  const [releaseNotes, setReleaseNotes] = useState("");
  const [submitting, setSubmitting] = useState<GenerationAction | null>(null);
  const [message, setMessage] = useState("");
  const requestKeys = useRef<Record<string, string>>({});
  const readyCount = workspace.batches.filter((batch) => batch.status === "ready_for_review").length;
  const activeCount = workspace.batches.filter((batch) => activeStatuses.has(batch.status)).length;

  useEffect(() => {
    setSelectedItemId(batchItems[0]?.generationItemId ?? "");
    setComment("");
    setMessage("");
  }, [selectedBatch?.batchId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!activeCount) return;
    const timer = window.setInterval(() => router.refresh(), 4_000);
    return () => window.clearInterval(timer);
  }, [activeCount, router]);

  async function runAction(action: GenerationAction) {
    if (action !== "create" && !selectedBatch) return;
    if (action === "reject" && !comment.trim()) {
      setMessage("반려 사유를 입력해 주세요.");
      return;
    }
    const keyTarget = action === "create" ? "create" : selectedBatch?.batchId ?? "batch";
    if (!requestKeys.current[keyTarget]) requestKeys.current[keyTarget] = crypto.randomUUID();
    setSubmitting(action);
    setMessage("");
    try {
      const response = await fetch("/api/workflow/generation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          batchId: selectedBatch?.batchId,
          requestKey: requestKeys.current[keyTarget],
          comment,
          releaseNotes,
          minimumAppVersion: 1,
        }),
      });
      const result = await response.json().catch(() => ({})) as {
        error?: string;
        message?: string;
        batchId?: string;
      };
      if (!response.ok) {
        setMessage(result.error ?? "자동 생성 작업을 처리하지 못했습니다.");
        return;
      }
      setMessage(result.message ?? "작업을 등록했습니다.");
      if (result.batchId) setSelectedBatchId(result.batchId);
      if (action === "reject") setComment("");
      if (action === "create") setReleaseNotes("");
      requestKeys.current[keyTarget] = "";
      router.refresh();
    } catch {
      setMessage("네트워크 응답을 확인하지 못했습니다. 같은 요청 키로 안전하게 다시 시도할 수 있습니다.");
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="APP CONTENT PIPELINE"
        title="앱 DB 최종 검토"
        description={viewerMode
          ? "원본 근거부터 자동 생성·검증, 최종 승인과 앱 DB 공개까지 한 화면에서 확인하는 구성을 설명합니다."
          : "원본에서 생성된 변경과 근거만 마지막으로 확인하세요. 승인 한 번이면 클린 SQLite 빌드·검증·stable 공개까지 자동 진행됩니다."}
        actions={
          <div className="workflow-header-actions">
            <span className="role-pill">{roleLabel(capabilities.role)}</span>
            <span className="count-pill">{viewerMode ? "최종 검토 구성" : `검토 대기 ${readyCount} · 처리 중 ${activeCount}`}</span>
          </div>
        }
      />

      <section className="panel generation-flow" aria-label="앱 콘텐츠 자동화 흐름">
        <div className="generation-flow-step complete"><span><FileText size={18} /></span><div><strong>원본 가공</strong><p>본문·표·수식·OCR fragment</p></div></div>
        <ChevronRight size={18} />
        <div className="generation-flow-step complete"><span><Sparkles size={18} /></span><div><strong>자동 생성·수정</strong><p>근거 연결 + 검증 통과</p></div></div>
        <ChevronRight size={18} />
        <div className="generation-flow-step current"><span><ShieldCheck size={18} /></span><div><strong>최종 검토 1회</strong><p>before/after와 원문 확인</p></div></div>
        <ChevronRight size={18} />
        <div className="generation-flow-step"><span><Database size={18} /></span><div><strong>앱 DB 릴리스</strong><p>클린 SQLite + stable 공개</p></div></div>
      </section>

      {demo ? (
        <section className="workflow-baseline panel">
          <span className="large-state-icon state-success"><ShieldCheck size={25} /></span>
          <div><p className="eyebrow">READ-ONLY PACKAGED BASELINE</p><h2>content-v{packagedContentInfo.version} · 검증된 내장 DB</h2><p>Supabase가 연결되면 실제 생성 배치와 원문 근거가 이 화면에 표시됩니다.</p></div>
        </section>
      ) : null}

      {!demo && !viewerMode && !activeCount && !readyCount ? (
        <section className="panel generation-start-panel">
          <div><p className="eyebrow">READY SOURCES</p><h2>준비된 원본을 지금 앱 콘텐츠로 변환</h2><p>자동 Worker가 새 원본을 정기적으로 가져갑니다. 즉시 시작이 필요할 때만 이 버튼을 사용하세요.</p></div>
          <div className="generation-start-actions">
            <label>릴리스 메모 <input value={releaseNotes} onChange={(event) => setReleaseNotes(event.target.value)} maxLength={4000} placeholder="비우면 자동 메모 사용" disabled={Boolean(submitting)} /></label>
            <button className="button button-primary" type="button" onClick={() => runAction("create")} disabled={!capabilities.canEdit || Boolean(submitting)}>
              {submitting === "create" ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
              {submitting === "create" ? "생성 배치 등록 중…" : "준비된 원본으로 생성 시작"}
            </button>
            {submitting === "create" ? <ActionProgress label="생성 요청 등록 중" /> : null}
          </div>
        </section>
      ) : null}

      {message ? <div className="workflow-notice" role="status">{message}</div> : null}

      {workspace.batches.length ? (
        <section className="generation-review-layout">
          <aside className="panel generation-batch-list">
            <div className="panel-heading compact-heading"><div><p className="eyebrow">GENERATION BATCHES</p><h2>자동 생성 이력</h2></div><span className="count-pill">{workspace.batches.length}</span></div>
            <div className="generation-batch-scroll">
              {workspace.batches.map((batch) => (
                <button
                  type="button"
                  className={`generation-batch-card ${selectedBatch?.batchId === batch.batchId ? "active" : ""}`}
                  onClick={() => setSelectedBatchId(batch.batchId)}
                  key={batch.batchId}
                >
                  <div><GenerationStatusBadge status={batch.status} /><small>{viewerMode ? "생성 시각" : formatWorkflowDate(batch.createdAt)}</small></div>
                  <strong>{viewerMode ? "자동 생성 배치" : `${batch.changedElementCount || "—"}개 요소 · 원본 ${batch.sourceCount}건`}</strong>
                  <p>{stageLabels[batch.processingStage] ?? batch.processingStage}</p>
                  {activeStatuses.has(batch.status) ? <MiniProgress batch={batch} /> : null}
                </button>
              ))}
            </div>
          </aside>

          <article className="panel generation-review-detail">
            {selectedBatch ? (
              <BatchDetail
                batch={selectedBatch}
                items={batchItems}
                selectedItem={selectedItem}
                onSelectItem={setSelectedItemId}
                workspace={workspace}
                comment={comment}
                onComment={setComment}
                capabilities={capabilities}
                demo={demo || viewerMode}
                viewerMode={viewerMode}
                submitting={submitting}
                onAction={runAction}
              />
            ) : null}
          </article>
        </section>
      ) : (
        <section className="panel workflow-empty-state">
          <MessageSquareText size={28} />
          <h2>{demo ? "Supabase 생성 데이터가 없습니다" : "아직 앱 콘텐츠 생성 배치가 없습니다"}</h2>
          <p>{demo ? "환경변수를 연결하면 실제 배치를 읽습니다." : "원본 가공이 완료되면 생성 Worker가 자동으로 배치를 만듭니다."}</p>
        </section>
      )}
    </div>
  );
}

function BatchDetail({
  batch,
  items,
  selectedItem,
  onSelectItem,
  workspace,
  comment,
  onComment,
  capabilities,
  demo,
  viewerMode,
  submitting,
  onAction,
}: {
  batch: ContentGenerationBatch;
  items: ContentGenerationItem[];
  selectedItem: ContentGenerationItem | null;
  onSelectItem: (id: string) => void;
  workspace: ReviewWorkspace;
  comment: string;
  onComment: (value: string) => void;
  capabilities: AdminCapabilities;
  demo: boolean;
  viewerMode: boolean;
  submitting: GenerationAction | null;
  onAction: (action: GenerationAction) => void;
}) {
  const releaseJobs = workspace.jobs.filter((job) => job.releaseId === batch.releaseId);
  const activeReleaseJob = releaseJobs.find((job) => job.status === "queued" || job.status === "running");

  if (batch.status === "queued" || batch.status === "running" || batch.status === "releasing") {
    const progress = batch.status === "releasing" && activeReleaseJob
      ? Math.max(batch.progressPercent, 96 + Math.round(activeReleaseJob.progressPercent * 0.04))
      : batch.progressPercent;
    return (
      <div className="generation-processing-state" role="status" aria-live="polite">
        <LoaderCircle className="spin" size={34} />
        <p className="eyebrow">AUTOMATED PIPELINE</p>
        <h2>{batch.status === "releasing" ? "검토 승인본으로 클린 앱 DB를 만드는 중입니다" : stageLabels[batch.processingStage] ?? "앱 콘텐츠를 자동 생성하는 중입니다"}</h2>
        <p>{batch.status === "queued" ? "Worker가 시작되면 기존 DB와 원문 근거를 읽습니다." : `${batch.modelName} · 시도 ${batch.attemptCount}/${batch.maxAttempts}`}</p>
        <div className={`generation-main-progress ${progress <= 1 ? "is-indeterminate" : ""}`} role="progressbar" aria-label="앱 콘텐츠 자동화 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress <= 1 ? undefined : progress}>
          <span style={progress <= 1 ? undefined : { width: `${progress}%` }} />
        </div>
        <strong className="generation-progress-number">{progress <= 1 ? "시작 대기" : `${progress}%`}</strong>
        <div className="generation-live-facts">
          <span><small>원본</small><strong>{batch.sourceCount}건</strong></span>
          <span><small>현재 요소</small><strong>{statText(batch, "currentElementId") || "—"}</strong></span>
          <span><small>처리 요소</small><strong>{statText(batch, "processedElementCount") || "0"}</strong></span>
          <span><small>자동 수정</small><strong>{statText(batch, "repairAttempt") || batch.autoRepairCount}</strong></span>
        </div>
        {activeReleaseJob ? <div className="generation-release-job"><JobStatusBadge status={activeReleaseJob.status} /><span>{activeReleaseJob.jobKind} · {activeReleaseJob.progressPercent}%</span></div> : null}
      </div>
    );
  }

  if (batch.status !== "ready_for_review") {
    const success = batch.status === "released" || batch.status === "no_changes";
    return (
      <div className={`generation-terminal-state ${success ? "success" : "error"}`}>
        {success ? <ShieldCheck size={34} /> : <CircleAlert size={34} />}
        <GenerationStatusBadge status={batch.status} />
        <h2>{terminalTitle(batch)}</h2>
        <p>{batch.errorMessage || stageLabels[batch.processingStage] || batch.releaseNotes || "처리가 종료되었습니다."}</p>
        {batch.status === "released" ? <Link className="button button-primary" href="/releases"><Rocket size={16} /> {batch.releaseVersionName ?? "릴리스"} 확인</Link> : null}
      </div>
    );
  }

  const evidence = selectedItem
    ? workspace.evidence.filter((row) => row.generationItemId === selectedItem.generationItemId)
    : [];
  const highRiskCount = items.filter((item) => item.riskLevel === "high").length;
  const failedElements = Array.isArray(batch.statistics.failedElements)
    ? batch.statistics.failedElements.filter(
        (value): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value),
      )
    : [];
  const failedElementIds = failedElements
    .map((value) => typeof value.elementId === "string" ? value.elementId : "")
    .filter(Boolean)
    .slice(0, 5);
  return (
    <>
      <div className="generation-review-header">
        <div><p className="eyebrow">FINAL REVIEW READY</p><h2>{viewerMode ? "근거 기반 변경 후보" : `${batch.changedElementCount}개 요소 · ${batch.itemCount}개 변경 묶음`}</h2><p>{batch.releaseNotes || "원본 근거 기반 자동 콘텐츠 생성"}</p></div>
        <GenerationStatusBadge status={batch.status} />
      </div>
      <div className="generation-integrity-strip">
        <ShieldCheck size={17} />
        <div><strong>자동 검증 완료</strong><p>모든 변경 필드에 원문 근거 연결 · {batch.evidenceCount}개 인용 · 자동 수정 {batch.autoRepairCount}회</p></div>
        <code>{batch.promptVersion}</code>
      </div>
      {highRiskCount ? <div className="generation-risk-warning"><CircleAlert size={17} /><strong>고위험 변경 {highRiskCount}건이 있습니다. 근거를 더 꼼꼼히 확인하세요.</strong></div> : null}
      {failedElements.length ? (
        <div className="generation-risk-warning">
          <CircleAlert size={17} />
          <strong>
            자동 검증을 끝내지 못한 요소 {failedElements.length}개는 이번 후보에서 제외됐습니다
            {failedElementIds.length ? ` (${failedElementIds.join(", ")}${failedElements.length > failedElementIds.length ? " 외" : ""})` : ""}.
            승인하면 화면에 표시된 변경만 릴리스됩니다.
          </strong>
        </div>
      ) : null}

      <div className="generation-item-layout">
        <aside className="generation-item-list">
          {items.map((item) => (
            <button type="button" className={selectedItem?.generationItemId === item.generationItemId ? "active" : ""} onClick={() => onSelectItem(item.generationItemId)} key={item.generationItemId}>
              <span className="mono-id">{item.elementId}</span>
              <strong>{entityLabel(item.entityType)} · {item.changedFields.length}개 필드</strong>
              <small className={`risk-${item.riskLevel}`}>{riskLabel(item.riskLevel)} · 신뢰도 {Math.round(item.confidence * 100)}%</small>
            </button>
          ))}
        </aside>

        <div className="generation-item-detail">
          {selectedItem ? (
            <>
              <div className="generation-item-heading"><div><span className="mono-id">{selectedItem.entityKey}</span><h3>{entityLabel(selectedItem.entityType)} 변경</h3></div><span>{selectedItem.changeSummary}</span></div>
              <div className="generation-diff-list">
                {selectedItem.changedFields.map((field) => {
                  const fieldEvidence = evidence.filter((row) => row.fieldPath === field);
                  return (
                    <article className="generation-diff-card" key={field}>
                      <div className="actual-diff-title"><FileDiff size={14} /><strong>{fieldNames[field] ?? field}</strong><span>근거 {fieldEvidence.length}</span></div>
                      <div className="diff-grid compact-diff-grid">
                        <section className="diff-pane diff-before"><div className="diff-label">기존 앱 DB</div><pre>{formatValue(selectedItem.baselineSnapshot[field])}</pre></section>
                        <section className="diff-pane diff-after"><div className="diff-label">자동 생성 후보</div><pre>{formatValue(selectedItem.generatedSnapshot[field])}</pre></section>
                      </div>
                      <div className="generation-evidence-list">
                        {fieldEvidence.map((row) => (
                          <details key={row.generationEvidenceId} open={fieldEvidence.length === 1}>
                            <summary><FileText size={14} /><strong>{row.sourceLabel}</strong><span>{locatorText(row.fragmentLocator)}</span></summary>
                            <blockquote>{row.contentExcerpt}</blockquote>
                            <p>{row.rationale}</p>
                            {row.sourceLocator.startsWith("http") ? <a href={row.sourceLocator} target="_blank" rel="noreferrer">원본 열기</a> : null}
                          </details>
                        ))}
                      </div>
                    </article>
                  );
                })}
              </div>
            </>
          ) : <div className="workflow-empty-inline">검토할 변경 항목이 없습니다.</div>}
        </div>
      </div>

      <label className="review-comment generation-final-comment">
        <span>최종 검토 메모 {comment.length ? `· ${comment.length}자` : ""}</span>
        <textarea rows={3} value={comment} onChange={(event) => onComment(event.target.value)} placeholder="승인 근거 또는 반려 사유를 남깁니다." disabled={demo || Boolean(submitting)} maxLength={4000} />
      </label>
      <div className="generation-final-actions">
        <div><strong>이 승인 이후 추가 수동 단계는 없습니다.</strong><p>revision 고정 → 클린 SQLite → 무결성 검증 → stable 공개가 자동으로 이어집니다.</p></div>
        <button className="button button-ghost-danger" type="button" onClick={() => onAction("reject")} disabled={demo || !capabilities.canReview || Boolean(submitting)}>
          {submitting === "reject" ? <LoaderCircle className="spin" size={16} /> : <X size={16} />}{submitting === "reject" ? "반려 저장 중…" : "배치 반려"}
        </button>
        <button className="button button-primary generation-approve-button" type="button" onClick={() => onAction("approve")} disabled={demo || !capabilities.canReview || !capabilities.canRelease || Boolean(submitting) || !items.length}>
          {submitting === "approve" ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}{submitting === "approve" ? "승인·릴리스 등록 중…" : "최종 승인하고 앱 DB 릴리스"}
        </button>
      </div>
      {submitting === "approve" || submitting === "reject" ? <ActionProgress label={submitting === "approve" ? "승인본과 릴리스를 원자적으로 고정하는 중" : "반려 결정을 저장하는 중"} /> : null}
    </>
  );
}

function ActionProgress({ label }: { label: string }) {
  return <div className="generation-action-progress" role="status"><span>{label}</span><div className="is-indeterminate" role="progressbar" aria-label={label} aria-valuetext="처리 중"><i /></div></div>;
}

function MiniProgress({ batch }: { batch: ContentGenerationBatch }) {
  const indeterminate = batch.progressPercent <= 1;
  return <div className={`generation-mini-progress ${indeterminate ? "is-indeterminate" : ""}`} role="progressbar" aria-label="배치 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={indeterminate ? undefined : batch.progressPercent}><span style={indeterminate ? undefined : { width: `${batch.progressPercent}%` }} /></div>;
}

function GenerationStatusBadge({ status }: { status: ContentGenerationStatus }) {
  const labels: Record<ContentGenerationStatus, string> = {
    queued: "대기",
    running: "자동 생성 중",
    ready_for_review: "최종 검토 대기",
    no_changes: "변경 없음",
    rejected: "반려",
    releasing: "앱 DB 생성 중",
    released: "릴리스 완료",
    failed: "실패",
  };
  return <span className={`generation-status generation-status-${status}`}>{activeStatuses.has(status) ? <LoaderCircle className="spin" size={13} /> : null}{labels[status]}</span>;
}

function terminalTitle(batch: ContentGenerationBatch) {
  if (batch.status === "released") return `${batch.releaseVersionName ?? "앱 DB"} 공개를 완료했습니다`;
  if (batch.status === "no_changes") return "근거로 확정할 새 변경이 없습니다";
  if (batch.status === "rejected") return "생성 후보를 반려했습니다";
  return "자동 처리에 실패했습니다";
}

function formatValue(value: unknown) {
  if (value == null || value === "") return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function entityLabel(type: string) {
  return ({ element: "요소", concept: "개념 카드", formula: "수식 카드" } as Record<string, string>)[type] ?? type;
}

function riskLabel(risk: ContentGenerationItem["riskLevel"]) {
  return ({ low: "낮은 위험", medium: "중간 위험", high: "높은 위험" } as const)[risk];
}

function locatorText(locator: Record<string, unknown>) {
  const values = Object.entries(locator).slice(0, 3).map(([key, value]) => `${key} ${String(value)}`);
  return values.join(" · ") || "원문 위치";
}

function statText(batch: ContentGenerationBatch, key: string) {
  const value = batch.statistics[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}
