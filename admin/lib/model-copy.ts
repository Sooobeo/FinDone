import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";
import { modelCopySectionIds, type ModelCopy } from "@/lib/model-copy-schema";
import { parseSectionedMarkdown } from "@/lib/sectioned-markdown";

export async function getModelCopy(): Promise<ModelCopy> {
  const filePath = path.join(process.cwd(), "content", "local-model.md");
  const source = await readFile(filePath, "utf8");
  return parseSectionedMarkdown(source, modelCopySectionIds) as ModelCopy;
}
