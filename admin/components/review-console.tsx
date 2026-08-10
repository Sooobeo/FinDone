"use client";

import {
  Check,
  CheckCircle2,
  FileDiff,
  MessageSquareText,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import {
  formatWorkflowDate,
  RevisionStateBadge,
  roleLabel,
  ValidationStatusBadge,
} from "@/components/workflow-status";
import type { ReviewWorkspace } from "@/lib/data";
import { packagedContentInfo } from "@/lib/packaged-info";
import type { AdminCapabilities } from "@/lib/types";

type ReviewDecision = "approved" | "rejected" | "changes_requested";

const fieldNames: Record<string, string> = {
  title: "제목",
  core_relation: "핵심 관계",
  scope_notes: "요소 적용 범위",
  definition_markdown: "정의",
  intuition_markdown: "직관 설명",
  learning_notes_markdown: "상세 학습 설명",
  checklist_markdown: "체크리스트",
  expression_markdown: "수식",
  assumptions_markdown: "수식 가정",
  notes_markdown: "수식 설명",
  text: "오답 문구",
  explanation: "오답 해설",
  misconception_type: "혼동 유형",
  is_enabled: "사용 여부",
};

const ignoredFields = new Set([
  "created_at",
  "created_by",
  "updated_at",
  "updated_by",
  "concept_id",
  "formula_id",
  "distractor_id",
]);

export function ReviewConsole({
  workspace,
  capabilities,
  demo,
}: {
  workspace: ReviewWorkspace;
  capabilities: AdminCapabilities;
  demo: boolean;
}) {
  const router = useRouter();
  const [selectedId, setSelectedId] = useState(workspace.revisions[0]?.revisionId ?? "");
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState<ReviewDecision | null>(null);
  const [message, setMessage] = useState("");
  const selected = workspace.revisions.find((revision) => revision.revisionId === selectedId)
    ?? workspace.revisions[0]
    ?? null;
  const validation = selected
    ? workspace.runs.find((run) => run.revisionId === selected.revisionId && run.status === "passed") ?? null
    : null;
  const changes = useMemo(() => diffSnapshots(selected?.previousSnapshot ?? {}, selected?.snapshot ?? {}), [selected]);

  async function submit(decision: ReviewDecision) {
    if (!selected || !capabilities.canReview) return;
    if (decision !== "approved" && !comment.trim()) {
      setMessage("반려 또는 수정 요청 사유를 입력해 주세요.");
      return;
    }
    setSubmitting(decision);
    setMessage("");
    const response = await fetch("/api/workflow/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ revisionId: selected.revisionId, decision, comment }),
    });
    const result = (await response.json()) as { error?: string };
    setSubmitting(null);
    if (!response.ok) {
      setMessage(result.error ?? "검토 결정을 저장하지 못했습니다.");
      return;
    }
    setMessage(decision === "approved" ? "승인 결정을 기록했습니다." : "검토 결정을 기록했습니다.");
    setComment("");
    router.refresh();
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="HUMAN REVIEW"
        title="승인 검토"
        description="실제 검증을 통과해 reviewed 상태가 된 revision만 현재 내용과 비교하고 결정합니다."
        actions={<div className="workflow-header-actions"><span className="role-pill">{roleLabel(capabilities.role)}</span><span className="count-pill">검토 대기 {workspace.revisions.length}건</span></div>}
      />

      {demo ? (
        <section className="workflow-baseline panel">
          <span className="large-state-icon state-success"><ShieldCheck size={25} /></span>
          <div><p className="eyebrow">READ-ONLY PACKAGED BASELINE</p><h2>content-v{packagedContentInfo.version} · 승인된 내장본</h2><p>Supabase가 연결되지 않아 실제 검토 대기 revision은 없습니다. 예시 결정이나 가짜 diff를 표시하지 않습니다.</p></div>
        </section>
      ) : null}

      {message ? <div className="workflow-notice" role="status">{message}</div> : null}

      {workspace.revisions.length ? (
        <section className="review-layout actual-review-layout">
          <aside className="panel review-queue">
            <div className="panel-heading compact-heading"><div><p className="eyebrow">REVIEW QUEUE</p><h2>검토 대기</h2></div><span className="count-pill">{workspace.revisions.length}</span></div>
            <div className="actual-review-queue">
              {workspace.revisions.map((revision) => (
                <button
                  className={`review-queue-item ${selected?.revisionId === revision.revisionId ? "active" : ""}`}
                  type="button"
                  key={revision.revisionId}
                  onClick={() => { setSelectedId(revision.revisionId); setComment(""); setMessage(""); }}
                >
                  <div><span className="mono-id">{revision.entityKey}</span><RevisionStateBadge state={revision.state} /></div>
                  <strong>{entityLabel(revision.entityType)} revision #{revision.revisionNumber}</strong>
                  <p>{revision.changeReason || "변경 사유 없음"}</p>
                  <span>검증 통과 <Check size={13} /></span>
                </button>
              ))}
            </div>
          </aside>

          <article className="panel review-detail actual-review-detail">
            {selected ? (
              <>
                <div className="review-detail-header">
                  <div>
                    <div className="editor-id-line"><span className="mono-id">{selected.entityKey}</span><RevisionStateBadge state={selected.state} /></div>
                    <h2>{entityLabel(selected.entityType)} revision #{selected.revisionNumber}</h2>
                    <p>{selected.changeReason || "변경 사유 없음"} · {formatWorkflowDate(selected.createdAt)}</p>
                  </div>
                  {validation ? <ValidationStatusBadge status={validation.status} /> : null}
                </div>

                <div className="review-integrity-strip">
                  <CheckCircle2 size={16} />
                  <div><strong>검증 통과 revision</strong><p>{validation?.validatorName ?? "검증기"} · {validation?.checksPassed ?? 0}/{validation?.checksTotal ?? 0} checks</p></div>
                  <code>{selected.contentHash.slice(0, 14)}…</code>
                </div>

                <div className="diff-heading"><span>이전 revision</span><span>검토할 revision</span></div>
                {changes.length ? (
                  <div className="actual-diff-list">
                    {changes.map((change) => (
                      <article className="actual-diff-row" key={change.field}>
                        <div className="actual-diff-title"><FileDiff size={14} /><strong>{fieldNames[change.field] ?? change.field}</strong></div>
                        <div className="diff-grid compact-diff-grid">
                          <section className="diff-pane diff-before"><div className="diff-label">이전</div><pre>{formatValue(change.before)}</pre></section>
                          <section className="diff-pane diff-after"><div className="diff-label">수정</div><pre>{formatValue(change.after)}</pre></section>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : <div className="workflow-empty-inline">표시할 필드 변경이 없습니다.</div>}

                <label className="review-comment">
                  <span>검토 코멘트 {comment.length ? `· ${comment.length}자` : ""}</span>
                  <textarea
                    rows={4}
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                    placeholder="승인 근거 또는 수정·반려 사유를 기록합니다."
                    disabled={!capabilities.canReview || demo || Boolean(submitting)}
                  />
                </label>
                {!capabilities.canReview && !demo ? <p className="permission-note">Owner 또는 Reviewer만 검토 결정을 내릴 수 있습니다.</p> : null}
                <div className="review-actions">
                  <button className="button button-ghost-danger" type="button" onClick={() => submit("rejected")} disabled={demo || !capabilities.canReview || Boolean(submitting)}><X size={16} />{submitting === "rejected" ? "저장 중…" : "반려"}</button>
                  <button className="button button-secondary" type="button" onClick={() => submit("changes_requested")} disabled={demo || !capabilities.canReview || Boolean(submitting)}><RotateCcw size={16} />{submitting === "changes_requested" ? "저장 중…" : "수정 요청"}</button>
                  <button className="button button-primary" type="button" onClick={() => submit("approved")} disabled={demo || !capabilities.canReview || Boolean(submitting) || !validation}><Check size={16} />{submitting === "approved" ? "저장 중…" : "승인"}</button>
                </div>
              </>
            ) : null}
          </article>
        </section>
      ) : (
        <section className="panel workflow-empty-state">
          <MessageSquareText size={28} />
          <h2>{demo ? "Supabase 검토 데이터가 없습니다" : "검토 대기 revision이 없습니다"}</h2>
          <p>{demo ? "환경변수를 연결하면 실제 reviewed revision을 읽습니다." : "Worker 검증을 통과한 revision이 reviewed 상태가 되면 여기에 나타납니다."}</p>
        </section>
      )}
    </div>
  );
}

function diffSnapshots(before: Record<string, unknown>, after: Record<string, unknown>) {
  return [...new Set([...Object.keys(before), ...Object.keys(after)])]
    .filter((field) => !ignoredFields.has(field))
    .filter((field) => JSON.stringify(before[field]) !== JSON.stringify(after[field]))
    .map((field) => ({ field, before: before[field], after: after[field] }));
}

function formatValue(value: unknown) {
  if (value == null || value === "") return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function entityLabel(type: string) {
  return ({ domain: "분야", element: "요소", concept: "개념", formula: "수식", distractor: "오답 후보" } as Record<string, string>)[type] ?? type;
}
