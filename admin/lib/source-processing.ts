import type { SourceItem } from "@/lib/types";

const STAGE_LABELS: Record<string, string> = {
  starting: "가공 시작 중",
  downloading: "원본 내려받는 중",
  validating: "무결성 확인 중",
  archiving: "원본 snapshot 보관 중",
  deduplicating: "중복 확인 중",
  extracting: "본문·표·수식 추출 중",
  ocr: "OCR 인식 중",
  normalizing: "검색용 정규화 중",
  matching: "학습 요소 대조 중",
  saving: "추출 결과 저장 중",
  completed: "처리 완료",
  needs_review: "확인 필요",
  failed: "처리 실패",
};

export interface SourceStatusPresentation {
  label: string;
  detail: string;
  loading: boolean;
  progress?: number;
}

export interface SourceStatusRow {
  source_id?: unknown;
  latest_parse_status?: unknown;
  latest_job_id?: unknown;
  latest_job_status?: unknown;
  latest_job_progress_percent?: unknown;
  latest_processing_stage?: unknown;
  latest_job_error_message?: unknown;
  latest_job_updated_at?: unknown;
  linked_element_count?: unknown;
  candidate_count?: unknown;
  top_candidate_element_id?: unknown;
  top_candidate_score?: unknown;
}

export function parseSourceStatus(value: unknown): SourceItem["status"] {
  if (value === "failed") return "failed";
  if (value === "needs_review") return "needs_review";
  if (value === "ready" || value === "parsed" || value === "archived") return "ready";
  return "processing";
}

export function sourceStatusPresentation(source: SourceItem): SourceStatusPresentation {
  if (source.status === "failed" || source.jobStatus === "failed") {
    return {
      label: "처리 실패",
      detail: source.processingError || "가공 기록을 확인해 주세요",
      loading: false,
    };
  }
  if (source.jobStatus === "cancelled") {
    return { label: "처리 취소됨", detail: "다시 등록하거나 작업 기록을 확인해 주세요", loading: false };
  }
  if (source.jobStatus === "queued") {
    return {
      label: "가공 대기 중",
      detail: "자동 Worker 시작 대기",
      loading: true,
      progress: source.progressPercent ?? 0,
    };
  }
  if (source.jobStatus === "running" || source.status === "processing") {
    const stage = source.processingStage || "starting";
    return {
      label: STAGE_LABELS[stage] ?? "자동 가공 중",
      detail: source.progressPercent === undefined ? "처리 상태 확인 중" : `${source.progressPercent}% 진행`,
      loading: true,
      progress: source.progressPercent,
    };
  }
  if (source.status === "needs_review") {
    const match = source.topCandidateElementId && source.topCandidateScore !== undefined
      ? `후보 ${source.topCandidateElementId} · ${Math.round(source.topCandidateScore * 100)}%`
      : "OCR 또는 의미 연결 확인 필요";
    return { label: "확인 필요", detail: match, loading: false };
  }
  const match = source.topCandidateElementId && source.topCandidateScore !== undefined
    ? `${source.topCandidateElementId} · ${Math.round(source.topCandidateScore * 100)}%`
    : "본문·표·수식 추출 완료";
  return { label: "처리 완료", detail: match, loading: false, progress: 100 };
}

export function hasActiveSourceProcessing(source: SourceItem): boolean {
  if (source.jobStatus === "succeeded" || source.jobStatus === "failed" || source.jobStatus === "cancelled") return false;
  return source.status === "processing" || source.jobStatus === "queued" || source.jobStatus === "running";
}

export function mergeSourceStatus(source: SourceItem, row: SourceStatusRow): SourceItem {
  const numberOrUndefined = (value: unknown) => {
    if (value === null || value === undefined || value === "") return undefined;
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : undefined;
  };
  const stringOrUndefined = (value: unknown) => typeof value === "string" && value ? value : undefined;
  const jobStatus = stringOrUndefined(row.latest_job_status);
  return {
    ...source,
    linkedElements: numberOrUndefined(row.linked_element_count) ?? source.linkedElements,
    status: parseSourceStatus(row.latest_parse_status),
    jobId: stringOrUndefined(row.latest_job_id),
    jobStatus: jobStatus === "queued" || jobStatus === "running" || jobStatus === "succeeded" || jobStatus === "failed" || jobStatus === "cancelled"
      ? jobStatus
      : undefined,
    progressPercent: numberOrUndefined(row.latest_job_progress_percent),
    processingStage: stringOrUndefined(row.latest_processing_stage),
    processingError: stringOrUndefined(row.latest_job_error_message),
    processingUpdatedAt: stringOrUndefined(row.latest_job_updated_at),
    candidateCount: numberOrUndefined(row.candidate_count),
    topCandidateElementId: stringOrUndefined(row.top_candidate_element_id),
    topCandidateScore: numberOrUndefined(row.top_candidate_score),
  };
}
