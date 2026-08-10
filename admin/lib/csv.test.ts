import { describe, expect, it } from "vitest";
import {
  ConceptCsvError,
  conceptsFromCsv,
  conceptsToCsv,
  safeSpreadsheetValue,
} from "@/lib/csv";
import { conceptElements } from "@/lib/fixtures";

describe("spreadsheet export", () => {
  it("neutralizes values that spreadsheet programs could execute", () => {
    expect(safeSpreadsheetValue("=HYPERLINK(\"bad\")")).toBe("'=HYPERLINK(\"bad\")");
    expect(safeSpreadsheetValue("normal text")).toBe("normal text");
  });

  it("exports every concept row with a UTF-8 BOM", () => {
    const csv = conceptsToCsv(conceptElements);
    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv.split("\r\n")).toHaveLength(conceptElements.length + 1);
    expect(csv).toContain("ACC-01");
  });

  it("round-trips quoted multiline Markdown without reporting changes", () => {
    const result = conceptsFromCsv(conceptsToCsv(conceptElements), conceptElements);
    expect(result.rowCount).toBe(conceptElements.length);
    expect(result.changed).toEqual([]);
  });

  it("imports an edited multiline field while keeping stable IDs locked", () => {
    const edited = [{
      ...conceptElements[0],
      definition: "첫 줄, 쉼표 포함\n둘째 줄에 충분히 긴 개념 설명을 적습니다.",
    }];
    const result = conceptsFromCsv(conceptsToCsv(edited), conceptElements);
    expect(result.changed).toHaveLength(1);
    expect(result.changed[0].definition).toBe(edited[0].definition);

    const tampered = conceptsToCsv([{ ...edited[0], domainId: "BAD" }]);
    expect(() => conceptsFromCsv(tampered, conceptElements)).toThrow(ConceptCsvError);
  });
});
