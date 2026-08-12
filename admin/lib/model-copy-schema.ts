import type { SectionedMarkdownSection } from "@/lib/sectioned-markdown";

export const modelCopySectionIds = [
  "page-intro",
  "modeling-process",
  "concept-model",
  "experiment-flow",
  "embedding-comparison",
  "quality-gates",
  "experiment-log",
  "rule-model",
  "metrics-guide",
] as const;

export type ModelCopySectionId = (typeof modelCopySectionIds)[number];
export type ModelCopy = Record<ModelCopySectionId, SectionedMarkdownSection>;
