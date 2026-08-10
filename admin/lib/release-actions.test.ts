import { describe, expect, it } from "vitest";
import { isReleaseAction, isRequestUuid } from "@/lib/release-actions";

describe("release request guards", () => {
  it("accepts only explicit release actions", () => {
    for (const action of ["create", "validate", "activate", "withdraw"]) {
      expect(isReleaseAction(action)).toBe(true);
    }
    expect(isReleaseAction("typo")).toBe(false);
    expect(isReleaseAction(null)).toBe(false);
  });

  it("accepts UUID request keys and rejects reusable labels", () => {
    expect(isRequestUuid("0262ee1c-5a77-4ad9-98d7-b93f7c9d06fd")).toBe(true);
    expect(isRequestUuid("release-v6")).toBe(false);
    expect(isRequestUuid(123)).toBe(false);
  });
});
