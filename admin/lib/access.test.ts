import { describe, expect, it } from "vitest";
import { capabilitiesForRole, parseAdminRole } from "@/lib/access";

describe("viewer access", () => {
  it("keeps viewer accounts completely read-only", () => {
    expect(capabilitiesForRole("viewer")).toEqual({
      role: "viewer",
      canEdit: false,
      canValidateRevision: false,
      canReview: false,
      canRelease: false,
      canValidateRelease: false,
    });
  });

  it("gives the owner every workflow capability", () => {
    expect(capabilitiesForRole("owner")).toEqual({
      role: "owner",
      canEdit: true,
      canValidateRevision: true,
      canReview: true,
      canRelease: true,
      canValidateRelease: true,
    });
  });

  it("rejects legacy and unrecognized roles", () => {
    expect(parseAdminRole("editor")).toBeNull();
    expect(parseAdminRole("reviewer")).toBeNull();
    expect(parseAdminRole("releaser")).toBeNull();
    expect(parseAdminRole(null)).toBeNull();
  });
});
