import { describe, expect, it } from "vitest";
import {
  classifySourceFiles,
  MAX_SOURCE_BYTES,
  sourceFileRejectionSummary,
  sourceMimeType,
} from "@/lib/source-files";

describe("source file staging", () => {
  it("accepts every file type advertised by the drop zone", () => {
    for (const name of ["sample.PDF", "sample.docx", "sample.xlsx", "sample.csv", "sample.md", "sample.txt"]) {
      expect(sourceMimeType({ name })).toBeTruthy();
    }
  });

  it("separates valid files from unsupported, empty, and oversized files", () => {
    const result = classifySourceFiles([
      { name: "valid.pdf", size: 10 },
      { name: "script.exe", size: 10 },
      { name: "empty.txt", size: 0 },
      { name: "large.csv", size: MAX_SOURCE_BYTES + 1 },
    ]);

    expect(result.accepted.map((file) => file.name)).toEqual(["valid.pdf"]);
    expect(result.rejected.map((item) => item.reason)).toEqual(["unsupported", "empty", "too_large"]);
    expect(sourceFileRejectionSummary(result.rejected)).toBe("지원하지 않는 형식 1개 · 빈 파일 1개 · 100MB 초과 1개");
  });

  it("accepts a file exactly at the 100MB boundary", () => {
    expect(classifySourceFiles([{ name: "limit.pdf", size: MAX_SOURCE_BYTES }]).accepted).toHaveLength(1);
  });
});
