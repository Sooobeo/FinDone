"use client";

import {
  AlertTriangle,
  CheckCircle2,
  CircleDotDashed,
  Clock3,
  FileCheck2,
  Play,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import {
  formatWorkflowDate,
  JobStatusBadge,
  RevisionStateBadge,
  roleLabel,
  ValidationStatusBadge,
} from "@/components/workflow-status";
import type { ValidationWorkspace } from "@/lib/data";
import { packagedContentInfo } from "@/lib/packaged-info";
import type { AdminCapabilities } from "@/lib/types";

export function ValidationConsole({
  workspace,
  capabilities,
  demo,
}: {
  workspace: ValidationWorkspace;
  capabilities: AdminCapabilities;
  demo: boolean;
}) {
  const router = useRouter();
  const [selectedId, setSelectedId] = useState(workspace.revisions[0]?.revisionId ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const selected = workspace.revisions.find((revision) => revision.revisionId === selectedId)
    ?? workspace.revisions[0]
    ?? null;
  const selectedRun = selected
    ? workspace.runs.find((run) => run.revisionId === selected.revisionId) ?? null
    : null;
  const selectedJob = selected
    ? workspace.jobs.find((job) => job.revisionId === selected.revisionId && job.jobKind === "content_validation") ?? null
    : null;
  const selectedIssues = selectedRun
    ? workspace.issues.filter((issue) => issue.validationRunId === selectedRun.validationRunId)
    : [];
  const eligible = selected?.state === "draft" || selected?.state === "validation_failed";

  const counts = useMemo(() => ({
    ready: workspace.revisions.filter((revision) => revision.state === "draft" || revision.state === "validation_failed").length,
    queued: workspace.jobs.filter((job) => job.status === "queued" || job.status === "running").length,
    errors: workspace.issues.filter((issue) => issue.severity === "error").length,
  }), [workspace]);

  async function startValidation() {
    if (!selected || !eligible || !capabilities.canValidateRevision) return;
    setSubmitting(true);
    setMessage("");
    const response = await fetch("/api/workflow/validation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ revisionId: selected.revisionId }),
    });
    const result = (await response.json()) as { error?: string; message?: string };
    setSubmitting(false);
    if (!response.ok) {
      setMessage(result.error ?? "검증 작업을 등록하지 못했습니다.");
      return;
    }
    setMessage(result.message ?? "검증 작업을 대기열에 등록했습니다.");
    router.refresh();
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="QUALITY GATE"
        title="자동 검증"
        description="검증 결과는 Worker만 기록합니다. Admin에서는 대상 revision을 선택해 작업을 대기열에 넣고 결과를 확인합니다."
        actions={
          <div className="workflow-header-actions">
            <span className="role-pill">{roleLabel(capabilities.role)}</span>
            <button
              className="button button-primary"
              type="button"
              onClick={startValidation}
              disabled={demo || !selected || !eligible || !capabilities.canValidateRevision || submitting}
              title={!capabilities.canValidateRevision ? "Owner, Editor, Reviewer만 검증을 요청할 수 있습니다" : undefined}
            >
              {submitting ? <RefreshCw className="spin" size={16} /> : <Play size={16} />}
              {selected?.state === "validation_failed" ? "재검증 요청" : "검증 요청"}
            </button>
          </div>
        }
      />

      {demo ? (
        <section className="workflow-baseline panel">
          <span className="large-state-icon state-success"><ShieldCheck size={25} /></span>
          <div>
            <p className="eyebrow">READ-ONLY PACKAGED BASELINE</p>
            <h2>content-v{packagedContentInfo.version} · {packagedContentInfo.elementCount}개 요소</h2>
            <p>현재 APK 내장 DB의 실제 기준점입니다. Supabase가 연결되지 않아 검증 대기 revision과 실행 결과는 없습니다.</p>
          </div>
        </section>
      ) : null}

      <section className="workflow-metrics" aria-label="검증 현황">
        <article><span className="metric-mini-icon"><FileCheck2 size={18} /></span><div><strong>{counts.ready}</strong><p>검증 요청 가능</p></div></article>
        <article><span className="metric-mini-icon icon-blue"><Clock3 size={18} /></span><div><strong>{counts.queued}</strong><p>대기·진행 작업</p></div></article>
        <article><span className="metric-mini-icon icon-coral"><AlertTriangle size={18} /></span><div><strong>{counts.errors}</strong><p>실제 오류 이슈</p></div></article>
      </section>

      {message ? <div className="workflow-notice" role="status">{message}</div> : null}

      {workspace.revisions.length ? (
        <section className="workflow-split">
          <aside className="panel workflow-queue-pane">
            <div className="workflow-pane-heading">
              <div><p className="eyebrow">REVISION QUEUE</p><h2>검증 대상</h2></div>
              <span>{workspace.revisions.length}</span>
            </div>
            <div className="workflow-queue-list">
              {workspace.revisions.map((revision) => {
                const run = workspace.runs.find((item) => item.revisionId === revision.revisionId);
                return (
                  <button
                    className={`workflow-queue-card ${selected?.revisionId === revision.revisionId ? "active" : ""}`}
                    type="button"
                    key={revision.revisionId}
                    onClick={() => { setSelectedId(revision.revisionId); setMessage(""); }}
                  >
                    <div><span className="mono-id">{revision.entityKey}</span><RevisionStateBadge state={revision.state} /></div>
                    <strong>{entityLabel(revision.entityType)} revision #{revision.revisionNumber}</strong>
                    <p>{revision.changeReason || "변경 사유 없음"}</p>
                    <small>{run ? `최근 검증: ${run.status}` : "검증 실행 전"} · {formatWorkflowDate(revision.createdAt)}</small>
                  </button>
                );
              })}
            </div>
          </aside>

          <article className="panel workflow-detail-pane">
            {selected ? (
              <>
                <div className="workflow-detail-heading">
                  <div>
                    <div className="editor-id-line"><span className="mono-id">{selected.entityKey}</span><RevisionStateBadge state={selected.state} /></div>
                    <h2>{entityLabel(selected.entityType)} revision #{selected.revisionNumber}</h2>
                    <p>{selected.changeReason || "변경 사유가 기록되지 않았습니다."}</p>
                  </div>
                  <code>{selected.contentHash.slice(0, 12)}…</code>
                </div>

                <div className="workflow-fact-grid">
                  <div><span>작성 시각</span><strong>{formatWorkflowDate(selected.createdAt)}</strong></div>
                  <div><span>작업 유형</span><strong>{selected.operation}</strong></div>
                  <div><span>검증 실행</span>{selectedRun ? <ValidationStatusBadge status={selectedRun.status} /> : <strong>실행 전</strong>}</div>
                  <div><span>Worker 작업</span>{selectedJob ? <JobStatusBadge status={selectedJob.status} /> : <strong>없음</strong>}</div>
                </div>

                {selectedJob && (selectedJob.status === "queued" || selectedJob.status === "running") ? (
                  <div className="queued-job-callout">
                    <CircleDotDashed size={18} />
                    <div><strong>{selectedJob.status === "queued" ? "Worker 실행 대기 중" : `Worker 처리 중 · ${selectedJob.progressPercent}%`}</strong><p>대기 상태는 완료가 아닙니다. Worker가 검증 결과를 기록할 때까지 승인 단계로 이동하지 않습니다.</p></div>
                  </div>
                ) : null}

                <section className="workflow-section">
                  <div className="workflow-section-heading"><div><p className="eyebrow">VALIDATION RESULT</p><h3>검사 결과</h3></div>{selectedRun ? <span>{selectedRun.checksPassed}/{selectedRun.checksTotal} 통과</span> : null}</div>
                  {selectedRun ? (
                    <div className="validation-progress-row">
                      <div className="readiness-track"><span style={{ width: selectedRun.checksTotal ? `${(selectedRun.checksPassed / selectedRun.checksTotal) * 100}%` : "0%" }} /></div>
                      <p>실패 {selectedRun.checksFailed}건</p>
                    </div>
                  ) : <div className="workflow-empty-inline">검증 요청 전입니다.</div>}
                </section>

                <section className="workflow-section">
                  <div className="workflow-section-heading"><div><p className="eyebrow">ISSUES</p><h3>검증 이슈</h3></div><span>{selectedIssues.length}건</span></div>
                  {selectedIssues.length ? (
                    <div className="actual-issue-list">
                      {selectedIssues.map((issue) => (
                        <article className={`actual-issue severity-${issue.severity}`} key={issue.validationIssueId}>
                          <span>{issue.severity === "error" ? "!" : issue.severity === "warning" ? "△" : "i"}</span>
                          <div><div><code>{issue.code}</code>{issue.fieldPath ? <small>{issue.fieldPath}</small> : null}</div><p>{issue.message}</p></div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="workflow-empty-inline">{selectedRun?.status === "passed" ? <><CheckCircle2 size={16} /> 기록된 이슈가 없습니다.</> : "아직 기록된 이슈가 없습니다."}</div>
                  )}
                </section>
              </>
            ) : null}
          </article>
        </section>
      ) : (
        <section className="panel workflow-empty-state">
          <CheckCircle2 size={28} />
          <h2>{demo ? "Supabase 검증 데이터가 없습니다" : "검증할 revision이 없습니다"}</h2>
          <p>{demo ? "환경변수를 연결하면 실제 revision과 작업 상태를 읽습니다." : "개념 DB에서 변경사항을 저장하면 초안 revision이 여기에 나타납니다."}</p>
        </section>
      )}
    </div>
  );
}

function entityLabel(type: string) {
  return ({ domain: "분야", element: "요소", concept: "개념", formula: "수식", distractor: "오답 후보" } as Record<string, string>)[type] ?? type;
}
