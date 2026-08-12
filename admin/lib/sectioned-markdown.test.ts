import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { modelCopySectionIds } from "@/lib/model-copy-schema";
import {
  parseSectionedMarkdown,
  markdownToPlainText,
  serializeMarkdownSection,
  splitMarkdownSubsections,
} from "@/lib/sectioned-markdown";

describe("sectioned Markdown", () => {
  it("loads every required local-model copy section", async () => {
    const filePath = fileURLToPath(new URL("../content/local-model.md", import.meta.url));
    const source = await readFile(filePath, "utf8");
    const sections = parseSectionedMarkdown(source, modelCopySectionIds);

    expect(Object.keys(sections)).toEqual(expect.arrayContaining([...modelCopySectionIds]));
    expect(splitMarkdownSubsections(sections["modeling-process"].body)).toHaveLength(5);
    expect(serializeMarkdownSection(sections["modeling-process"])).toContain("## 모델링 과정");
    expect(markdownToPlainText("### 단계\n\n`release_ready` **승인**")).toBe("단계 release_ready 승인");
  });

  it("rejects a missing required section", () => {
    expect(() => parseSectionedMarkdown(
      "<!-- section:only -->\n## 제목\n\n설명",
      ["only", "missing"],
    )).toThrow("Missing required Markdown section(s): missing");
  });
});
