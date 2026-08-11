import { describe, expect, it } from "vitest";
import {
  classifySourceFiles,
  sourceFileRejectionSummary,
  sourceMimeType,
} from "@/lib/source-files";

describe("source file staging", () => {
  it("accepts every file type advertised by the drop zone", () => {
    for (const name of [
      "sample.PDF",
      "sample.docx",
      "sample.xlsx",
      "sample.pptx",
      "sample.csv",
      "sample.json",
      "sample.jsonl",
      "sample.sqlite3",
      "sample.md",
      "sample.txt",
      "sample.html",
      "sample.png",
      "sample.jpeg",
      "sample.webp",
    ]) {
      expect(sourceMimeType({ name })).toBeTruthy();
    }
  });

  it("separates valid files from unsupported and empty files", () => {
    const result = classifySourceFiles([
      { name: "valid.pdf", size: 10 },
      { name: "script.exe", size: 10 },
      { name: "empty.txt", size: 0 },
    ]);

    expect(result.accepted.map((file) => file.name)).toEqual(["valid.pdf"]);
    expect(result.rejected.map((item) => item.reason)).toEqual(["unsupported", "empty"]);
    expect(sourceFileRejectionSummary(result.rejected)).toBe("지원하지 않는 형식 1개 · 빈 파일 1개");
  });

  it("does not impose an application-level size limit", () => {
    expect(classifySourceFiles([{ name: "large.pdf", size: 5 * 1024 ** 3 }]).accepted).toHaveLength(1);
  });
});
