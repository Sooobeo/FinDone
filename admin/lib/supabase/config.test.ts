import { describe, expect, it } from "vitest";
import { resolveRuntimeMode } from "@/lib/supabase/config";

describe("resolveRuntimeMode", () => {
  it("fails closed when hosted configuration is missing or partial", () => {
    expect(resolveRuntimeMode(false, false, false, "production")).toBe("misconfigured");
    expect(resolveRuntimeMode(false, true, false, "production")).toBe("misconfigured");
    expect(resolveRuntimeMode(false, false, true, "production")).toBe("misconfigured");
  });

  it("allows an explicit demo only outside production", () => {
    expect(resolveRuntimeMode(false, false, true, "development")).toBe("demo");
    expect(resolveRuntimeMode(true, false, false, "production")).toBe("supabase");
    expect(resolveRuntimeMode(true, false, true, "development")).toBe("misconfigured");
  });
});
