import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";
import { getModelCopy } from "@/lib/model-copy";
import { serializeMarkdownSection } from "@/lib/sectioned-markdown";

export const introSlugs = ["overview", "today", "study", "quiz", "records", "admin"] as const;
export type IntroSlug = (typeof introSlugs)[number];

export interface IntroSection {
  slug: IntroSlug;
  navLabel: string;
  eyebrow: string | null;
  title: string;
  summary: string;
  body: string;
}

export function isIntroSlug(value: string): value is IntroSlug {
  return introSlugs.includes(value as IntroSlug);
}

async function resolveContentIncludes(source: string) {
  const token = "{{include:local-model:modeling-process}}";
  if (!source.includes(token)) return source;
  const copy = await getModelCopy();
  return source.replaceAll(token, serializeMarkdownSection(copy["modeling-process"]));
}

export async function getIntroSection(slug: IntroSlug): Promise<IntroSection> {
  const filePath = path.join(process.cwd(), "content", "app-intro", `${slug}.md`);
  const source = await readFile(filePath, "utf8");
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!match) throw new Error(`${slug}.md의 front matter 형식을 확인해 주세요.`);

  const metadata = Object.fromEntries(
    match[1]
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => {
        const separator = line.indexOf(":");
        if (separator < 0) return [line.trim(), ""];
        return [line.slice(0, separator).trim(), line.slice(separator + 1).trim()];
      }),
  );

  return {
    slug,
    navLabel: metadata.navLabel ?? slug,
    eyebrow: metadata.eyebrow?.trim() || null,
    title: metadata.title ?? "FinDone",
    summary: metadata.summary ?? "",
    body: (await resolveContentIncludes(match[2])).trim(),
  };
}

export async function getIntroNavigation() {
  return Promise.all(introSlugs.map(getIntroSection));
}
