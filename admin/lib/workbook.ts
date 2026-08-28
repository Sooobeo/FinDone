import "server-only";

import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { cache } from "react";
import type { WorkbookIndex, WorkbookUnit } from "@/lib/workbook-types";

function adminProjectRoot() {
  const current = process.cwd();
  if (existsSync(join(current, "content", "workbook", "index.json"))) return current;
  const nestedAdmin = join(current, "admin");
  return existsSync(join(nestedAdmin, "content", "workbook", "index.json")) ? nestedAdmin : current;
}

const workbookRoot = join(adminProjectRoot(), "content", "workbook");

async function readJson<T>(path: string): Promise<T> {
  return JSON.parse(await readFile(path, "utf8")) as T;
}

export const getWorkbookIndex = cache(async (): Promise<WorkbookIndex> => {
  const index = await readJson<WorkbookIndex>(join(workbookRoot, "index.json"));
  if (index.schemaVersion !== 1) throw new Error(`Unsupported workbook schema: ${index.schemaVersion}`);
  return index;
});

export const getWorkbookUnit = cache(async (unitId: string): Promise<WorkbookUnit | null> => {
  if (!/^[A-Z0-9-]+$/.test(unitId)) return null;
  const index = await getWorkbookIndex();
  const known = index.subjects.some((subject) => subject.units.some((unit) => unit.id === unitId));
  if (!known) return null;

  const unit = await readJson<WorkbookUnit>(join(workbookRoot, "units", `${unitId}.json`));
  if (unit.schemaVersion !== index.schemaVersion || unit.sourceSha256 !== index.source.sha256 || unit.id !== unitId) {
    throw new Error(`Workbook unit ${unitId} does not match the index`);
  }
  return unit;
});
