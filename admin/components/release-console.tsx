"use client";

import {
  Check,
  ChevronRight,
  Database,
  Download,
  Fingerprint,
  Package,
  Play,
  RefreshCw,
  Rocket,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { PageHeader } from "@/components/page-header";
import {
  formatWorkflowDate,
  JobStatusBadge,
  ReleaseStatusBadge,
  roleLabel,
  ValidationStatusBadge,
} from "@/components/workflow-status";
import type { ReleaseWorkspace } from "@/lib/data";
import { packagedContentInfo } from "@/lib/packaged-info";
import type { AdminCapabilities } from "@/lib/types";

type ReleaseAction = "create" | "validate" | "activate" | "withdraw";

export function ReleaseConsole({
  workspace,
  capabilities,
  demo,
}: {
  workspace: ReleaseWorkspace;
  capabilities: AdminCapabilities;
  demo: boolean;
}) {
  const router = useRouter();
  const [selectedId, setSelectedId] = useState(workspace.releases[0]?.releaseId ?? "");
  const [channel, setChannel] = useState("stable");
  const [withdrawNote, setWithdrawNote] = useState("");
  const [newVersionName, setNewVersionName] = useState("");
  const [newReleaseNotes, setNewReleaseNotes] = useState("");
  const [minimumAppVersion, setMinimumAppVersion] = useState("1");
  const createRequestKey = useRef<string | null>(null);
  const [submitting, setSubmitting] = useState<ReleaseAction | null>(null);
  const [message, setMessage] = useState("");
  const selected = workspace.releases.find((release) => release.releaseId === selectedId)
    ?? workspace.releases[0]
    ?? null;
  const active = workspace.releases.find((release) => release.activeChannels.includes("stable"))
    ?? workspace.releases.find((release) => release.status === "published")
    ?? null;
  const validation = selected
    ? workspace.runs.find((run) => run.releaseId === selected.releaseId) ?? null
    : null;
  const jobs = selected
    ? workspace.jobs.filter((job) => job.releaseId === selected.releaseId)
    : [];
  const activeValidationJob = jobs.find(
    (job) => job.jobKind === "release_validation" && (job.status === "queued" || job.status === "running"),
  );
  const activeBuildJob = jobs.find(
    (job) => job.jobKind === "release_build" && (job.status === "queued" || job.status === "running"),
  );

  async function runAction(action: ReleaseAction) {
    if (action !== "create" && !selected) return;
    if (action === "withdraw" && !withdrawNote.trim()) {
      setMessage("철회 사유를 입력해 주세요.");
      return;
    }
    const minimumVersion = Number(minimumAppVersion);
    if (action === "create" && (!Number.isInteger(minimumVersion) || minimumVersion < 1)) {
      setMessage("최소 앱 버전은 1 이상의 정수여야 합니다.");
      return;
    }
    if (action === "create" && !createRequestKey.current) createRequestKey.current = crypto.randomUUID();
    setSubmitting(action);
    setMessage("");
    try {
      const response = await fetch("/api/workflow/releases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          releaseId: selected?.releaseId,
          action,
          channel,
          note: withdrawNote,
          versionName: newVersionName,
          releaseNotes: newReleaseNotes,
          minimumAppVersion: minimumVersion,
          requestKey: action === "create" ? createRequestKey.current : undefined,
        }),
      });
      const result = await response.json().catch(() => ({})) as { error?: string; message?: string };
      if (!response.ok) {
        setMessage(result.error ?? "릴리스 작업을 처리하지 못했습니다. 같은 요청으로 다시 시도할 수 있습니다.");
        return;
      }
      setMessage(
        result.message
          ?? (action === "activate" ? `${channel} 채널을 활성화했습니다.` : "릴리스 상태를 갱신했습니다."),
      );
      if (action === "create") {
        createRequestKey.current = null;
        setNewVersionName("");
        setNewReleaseNotes("");
      }
      if (action === "withdraw") setWithdrawNote("");
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
        eyebrow="RELEASE CENTER"
        title="앱 반영"
        description="실제 릴리스 이력, Worker 작업 큐, 검증 결과와 활성 채널을 확인합니다. 대기 중 작업을 완료로 표시하지 않습니다."
        actions={
          <div className="workflow-header-actions">
            <span className="role-pill">{roleLabel(capabilities.role)}</span>
          </div>
        }
      />

      {demo ? (
        <section className="workflow-baseline panel">
          <span className="large-state-icon state-success"><Package size={25} /></span>
          <div><p className="eyebrow">READ-ONLY PACKAGED BASELINE</p><h2>content-v{packagedContentInfo.version} · {packagedContentInfo.elementCount}개 요소 · {(packagedContentInfo.byteSize / 1024 / 1024).toFixed(1)} MB</h2><p>현재 APK에 실제 포함된 기준 DB입니다. Supabase 릴리스 이력과 Worker 작업은 연결 전이므로 비어 있습니다.</p></div>
        </section>
      ) : null}

      {!demo ? (
        <section className="panel release-creation-panel">
          <div className="panel-heading compact-heading">
            <div>
              <p className="eyebrow">FREEZE APPROVED CHANGES</p>
              <h2>새 콘텐츠 릴리스</h2>
            </div>
            <span className="panel-kicker">승인본 원자적 고정</span>
          </div>
          <div className="release-create-grid">
            <label>
              버전명 <small>비우면 자동 생성</small>
              <input
                value={newVersionName}
                onChange={(event) => setNewVersionName(event.target.value)}
                maxLength={80}
                placeholder="예: content-v6"
                disabled={!capabilities.canRelease || Boolean(submitting)}
              />
            </label>
            <label>
              최소 앱 versionCode
              <input
                type="number"
                min={1}
                step={1}
                value={minimumAppVersion}
                onChange={(event) => setMinimumAppVersion(event.target.value)}
                disabled={!capabilities.canRelease || Boolean(submitting)}
              />
            </label>
            <label className="release-notes-field">
              개선 내용
              <textarea
                value={newReleaseNotes}
                onChange={(event) => setNewReleaseNotes(event.target.value)}
                maxLength={4000}
                rows={2}
                placeholder="이번 반영 내용을 적어 두세요."
                disabled={!capabilities.canRelease || Boolean(submitting)}
              />
            </label>
            <button
              className="button button-primary"
              type="button"
              onClick={() => runAction("create")}
              disabled={!capabilities.canRelease || Boolean(submitting)}
            >
              <Rocket size={16} />{submitting === "create" ? "생성 중…" : "승인본으로 릴리스 생성"}
            </button>
          </div>
          <p className="release-create-help"><ShieldCheck size={15} />최신 승인 revision만 고정하며, Worker가 전체 135개 요소의 SQLite 산출물을 생성합니다.</p>
        </section>
      ) : null}

      {message ? <div className="workflow-notice" role="status">{message}</div> : null}

      <section className="release-hero">
        <article className="panel current-release-card">
          <div className="current-release-top"><span className="large-state-icon state-success"><Package size={25} /></span>{active ? <span className="release-live"><i />stable 사용 중</span> : <span className="example-tag">내장 기준점</span>}</div>
          <p className="eyebrow">ACTIVE CONTENT</p>
          <h2>{active?.versionName ?? `content-v${packagedContentInfo.version}`}</h2>
          <p>{active ? `${active.itemCount}개 revision · ${active.activeChannels.join(", ") || "채널 없음"}` : `${packagedContentInfo.elementCount}개 학습 요소 · APK 내장`}</p>
          <div className="checksum-box"><Fingerprint size={15} /><code>{(active?.databaseSha256 ?? packagedContentInfo.sha256).slice(0, 20)}…</code></div>
        </article>

        <article className="panel release-readiness actual-release-detail">
          <div className="panel-heading compact-heading"><div><p className="eyebrow">SELECTED RELEASE</p><h2>{selected?.versionName ?? "Supabase 릴리스 없음"}</h2></div>{selected ? <ReleaseStatusBadge status={selected.status} /> : null}</div>
          {selected ? (
            <>
              <div className="release-fact-row"><span>revision</span><strong>{selected.itemCount}</strong><span>artifacts</span><strong>{selected.artifactCount}</strong><span>schema</span><strong>v{selected.schemaVersion}</strong></div>
              <p className="selected-release-note">{selected.releaseNotes || "릴리스 노트 없음"}</p>
              <div className="selected-release-validation"><span>최근 검증</span>{validation ? <ValidationStatusBadge status={validation.status} /> : <strong>실행 전</strong>}</div>
              {activeValidationJob ? (
                <div className="queued-job-callout compact-job-callout"><RefreshCw className={activeValidationJob.status === "running" ? "spin" : ""} size={17} /><div><strong>{activeValidationJob.status === "queued" ? "릴리스 검증 Worker 대기 중" : `릴리스 검증 중 · ${activeValidationJob.progressPercent}%`}</strong><p>대기·진행 상태는 완료가 아닙니다.</p></div></div>
              ) : null}
              {activeBuildJob ? (
                <div className="queued-job-callout compact-job-callout"><RefreshCw className={activeBuildJob.status === "running" ? "spin" : ""} size={17} /><div><strong>{activeBuildJob.status === "queued" ? "SQLite 빌드 Worker 대기 중" : `SQLite 빌드 중 · ${activeBuildJob.progressPercent}%`}</strong><p>DB와 manifest 생성이 끝나야 릴리스 검증을 시작할 수 있습니다.</p></div></div>
              ) : null}
              <div className="release-action-row">
                {selected.status === "building" ? (
                  <button className="button button-secondary" type="button" onClick={() => runAction("validate")} disabled={!capabilities.canValidateRelease || Boolean(submitting) || Boolean(activeValidationJob) || Boolean(activeBuildJob) || selected.artifactCount < 2}><Play size={15} />{submitting === "validate" ? "등록 중…" : activeBuildJob ? "DB 빌드 대기" : "릴리스 검증 요청"}</button>
                ) : null}
                {selected.status === "ready" || selected.status === "published" ? (
                  <div className="channel-action"><input value={channel} onChange={(event) => setChannel(event.target.value)} aria-label="활성 채널" /><button className="button button-primary" type="button" onClick={() => runAction("activate")} disabled={!capabilities.canRelease || Boolean(submitting)}><Rocket size={15} />{submitting === "activate" ? "활성화 중…" : "채널 활성화"}</button></div>
                ) : null}
              </div>
              {selected.status !== "withdrawn" && capabilities.canRelease ? (
                <div className="withdraw-row"><input value={withdrawNote} onChange={(event) => setWithdrawNote(event.target.value)} placeholder="철회 사유" aria-label="릴리스 철회 사유" /><button className="button button-ghost-danger" type="button" onClick={() => runAction("withdraw")} disabled={Boolean(submitting)}><Trash2 size={15} />{submitting === "withdraw" ? "철회 중…" : "철회"}</button></div>
              ) : null}
            </>
          ) : <div className="workflow-empty-inline">실제 Supabase 릴리스가 생성되면 상태와 작업이 표시됩니다.</div>}
        </article>
      </section>

      <section className="release-flow panel">
        <div className="panel-heading"><div><p className="eyebrow">SAFE DELIVERY</p><h2>승인본 전달 흐름</h2></div><span className="panel-kicker">user.sqlite3 보존</span></div>
        <div className="release-flow-steps">
          <div><span><Check size={20} /></span><strong>승인 revision 고정</strong><p>요청 키로 원자적·중복 없는 생성</p></div><ChevronRight size={20} />
          <div><span><Database size={20} /></span><strong>Worker DB 생성</strong><p>queued/running/succeeded 상태 구분</p></div><ChevronRight size={20} />
          <div><span><ShieldCheck size={20} /></span><strong>릴리스 검증</strong><p>release fingerprint 기준 RPC</p></div><ChevronRight size={20} />
          <div><span><Download size={20} /></span><strong>채널 활성화</strong><p>ready 릴리스만 stable 전환</p></div>
        </div>
      </section>

      <section className="panel release-history">
        <div className="panel-heading"><div><p className="eyebrow">SUPABASE HISTORY</p><h2>콘텐츠 릴리스 이력</h2></div><span className="count-pill">{workspace.releases.length}개</span></div>
        {workspace.releases.length ? (
          <div className="release-table-scroll"><table className="data-table release-table"><thead><tr><th>버전</th><th>상태</th><th>revision</th><th>artifacts</th><th>검증/Worker</th><th>채널</th><th>생성 시각</th></tr></thead><tbody>{workspace.releases.map((release) => {
            const releaseJob = workspace.jobs.find((job) => job.releaseId === release.releaseId && (job.status === "queued" || job.status === "running")) ?? workspace.jobs.find((job) => job.releaseId === release.releaseId);
            return (
              <tr key={release.releaseId} className={selected?.releaseId === release.releaseId ? "active-row" : ""} onClick={() => { setSelectedId(release.releaseId); setMessage(""); }}>
                <td><button className="table-title-button" type="button" onClick={() => setSelectedId(release.releaseId)}>{release.versionName}</button></td>
                <td><ReleaseStatusBadge status={release.status} /></td>
                <td>{release.itemCount}</td><td>{release.artifactCount}</td>
                <td>{releaseJob ? <JobStatusBadge status={releaseJob.status} /> : "—"}</td>
                <td>{release.activeChannels.join(", ") || "—"}</td>
                <td>{formatWorkflowDate(release.createdAt)}</td>
              </tr>
            );
          })}</tbody></table></div>
        ) : <div className="workflow-empty-inline release-history-empty">Supabase에 생성된 릴리스가 없습니다.</div>}
      </section>

      {selected && jobs.length ? (
        <section className="panel release-job-panel">
          <div className="panel-heading"><div><p className="eyebrow">WORKER JOBS</p><h2>{selected.versionName} 작업 이력</h2></div></div>
          <div className="release-job-list">{jobs.map((job) => <article key={job.jobId}><span>{job.jobKind}</span><JobStatusBadge status={job.status} /><strong>{job.progressPercent}%</strong><small>{formatWorkflowDate(job.createdAt)}</small>{job.errorMessage ? <p>{job.errorMessage}</p> : null}</article>)}</div>
        </section>
      ) : null}

      <div className="release-safety-note"><ShieldCheck size={20} /><div><strong>학습 기록 DB는 릴리스 대상이 아닙니다</strong><p>오답, 북마크, 진도, 코멘트와 형광펜은 휴대폰의 user.sqlite3에 그대로 남습니다.</p></div></div>
    </div>
  );
}
