import { describe, expect, it } from "vitest";
import { conceptElements } from "@/lib/fixtures";
import { filterConcepts, validateConcept } from "@/lib/validation";

describe("filterConcepts", () => {
  it("filters by Korean search text and domain", () => {
    const result = filterConcepts(conceptElements, "현금흐름", "ACC", "all");
    expect(result.length).toBeGreaterThan(0);
    expect(result.every((item) => item.domainId === "ACC")).toBe(true);
  });

  it("filters by workflow status", () => {
    const result = filterConcepts(conceptElements, "", "all", "approved");
    expect(result.every((item) => item.status === "approved")).toBe(true);
  });
});

describe("validateConcept", () => {
  it("accepts the packaged fixture content", () => {
    expect(validateConcept(conceptElements[0]).filter((issue) => issue.severity === "error")).toEqual([]);
  });

  it("rejects missing definition and source", () => {
    const invalid = { ...conceptElements[0], definition: "짧음", sourceLocator: "" };
    const fields = validateConcept(invalid).map((issue) => issue.field);
    expect(fields).toContain("definition");
    expect(fields).toContain("sourceLocator");
  });
});
