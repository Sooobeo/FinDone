import type { AdminCapabilities, AdminRole } from "@/lib/types";

export function parseAdminRole(value: unknown): AdminRole | null {
  return value === "owner" || value === "viewer" ? value : null;
}

export function capabilitiesForRole(role: AdminRole | null): AdminCapabilities {
  const isOwner = role === "owner";
  return {
    role,
    canEdit: isOwner,
    canValidateRevision: isOwner,
    canReview: isOwner,
    canRelease: isOwner,
    canValidateRelease: isOwner,
  };
}
