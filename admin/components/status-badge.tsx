import type { ContentStatus } from "@/lib/types";
import { STATUS_LABELS } from "@/lib/status";

interface StatusBadgeProps {
  status: ContentStatus;
  showDot?: boolean;
}

export function StatusBadge({ status, showDot = true }: StatusBadgeProps) {
  return (
    <span className={`status-badge status-${status}`}>
      {showDot ? <span className="status-dot" aria-hidden="true" /> : null}
      {STATUS_LABELS[status]}
    </span>
  );
}
