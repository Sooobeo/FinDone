import type { ReleaseStatus, RevisionState, ValidationRunStatus, WorkflowJob } from "@/lib/types";

const revisionLabels: Record<RevisionState, string> = {
  draft: "초안",
  validating: "검증 대기·진행",
  validation_failed: "검증 실패",
  reviewed: "검토 대기",
  approved: "승인",
  rejected: "반려",
  published: "배포됨",
  archived: "보관",
};

const validationLabels: Record<ValidationRunStatus, string> = {
  queued: "대기열",
  running: "검증 중",
  passed: "통과",
  failed: "실패",
  cancelled: "취소",
};

const releaseLabels: Record<ReleaseStatus, string> = {
  draft: "초안",
  building: "빌드 중",
  validation_failed: "검증 실패",
  ready: "배포 준비",
  published: "배포됨",
  withdrawn: "철회됨",
};

const jobLabels: Record<WorkflowJob["status"], string> = {
  queued: "작업 대기",
  running: "작업 중",
  succeeded: "완료",
  failed: "실패",
  cancelled: "취소",
};

export function RevisionStateBadge({ state }: { state: RevisionState }) {
  return <span className={`workflow-badge workflow-${state}`}><i />{revisionLabels[state]}</span>;
}

export function ValidationStatusBadge({ status }: { status: ValidationRunStatus }) {
  return <span className={`workflow-badge workflow-${status}`}><i />{validationLabels[status]}</span>;
}

export function ReleaseStatusBadge({ status }: { status: ReleaseStatus }) {
  return <span className={`workflow-badge workflow-${status}`}><i />{releaseLabels[status]}</span>;
}

export function JobStatusBadge({ status }: { status: WorkflowJob["status"] }) {
  return <span className={`workflow-badge workflow-job-${status}`}><i />{jobLabels[status]}</span>;
}

export function roleLabel(role: string | null) {
  if (role === "owner") return "Owner";
  if (role === "editor") return "Editor";
  if (role === "reviewer") return "Reviewer";
  if (role === "releaser") return "Releaser";
  return "읽기 전용";
}

export function formatWorkflowDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
