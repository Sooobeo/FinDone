import type { ContentStatus } from "@/lib/types";

export const STATUS_LABELS: Record<ContentStatus, string> = {
  draft: "초안",
  validating: "검증 중",
  reviewed: "검토 완료",
  approved: "승인",
  published: "배포됨",
  rejected: "반려",
};
