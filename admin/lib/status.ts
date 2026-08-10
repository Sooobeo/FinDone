import type { ContentStatus } from "@/lib/types";

export const STATUS_LABELS: Record<ContentStatus, string> = {
  draft: "초안",
  validating: "검증 중",
  reviewed: "검토 완료",
  approved: "승인",
  published: "배포됨",
  rejected: "반려",
};

export const SOURCE_STATUS_LABELS = {
  ready: "처리 완료",
  processing: "가공 중",
  needs_review: "확인 필요",
  failed: "처리 실패",
} as const;
