import { describe, expect, it } from "vitest";
import {
  ALL_SOURCE_DOMAINS,
  filterSources,
  sourceDomainOptions,
  UNASSIGNED_SOURCE_DOMAIN,
} from "@/lib/source-filter";
import type { SourceItem } from "@/lib/types";

const sources: SourceItem[] = [
  {
    id: "ACC-CF",
    label: "공통 원본",
    kind: "pdf",
    locator: "https://example.com/common.pdf",
    status: "ready",
    linkedElements: 2,
    domains: [
      { id: "CF", name: "기업재무", displayOrder: 2 },
      { id: "ACC", name: "회계·재무제표", displayOrder: 1 },
    ],
    createdAt: "now",
  },
  {
    id: "ACC-ONLY",
    label: "회계 원본",
    kind: "url",
    locator: "https://example.com/accounting",
    status: "ready",
    linkedElements: 1,
    domains: [{ id: "ACC", name: "회계·재무제표", displayOrder: 1 }],
    createdAt: "now",
  },
  {
    id: "NEW",
    label: "새 원본",
    kind: "document",
    locator: "private/new.txt",
    status: "processing",
    linkedElements: 0,
    domains: [],
    createdAt: "now",
  },
];

describe("source domain filters", () => {
  it("deduplicates domains, preserves display order, and counts linked sources", () => {
    expect(sourceDomainOptions(sources)).toEqual([
      { id: "ACC", name: "회계·재무제표", displayOrder: 1, sourceCount: 2 },
      { id: "CF", name: "기업재무", displayOrder: 2, sourceCount: 1 },
    ]);
  });

  it("shows multi-domain sources in every connected domain", () => {
    expect(filterSources(sources, { query: "", kind: "all", domainId: "ACC" }).map((source) => source.id))
      .toEqual(["ACC-CF", "ACC-ONLY"]);
    expect(filterSources(sources, { query: "", kind: "all", domainId: "CF" }).map((source) => source.id))
      .toEqual(["ACC-CF"]);
  });

  it("combines chapter, type, and text filters and keeps unassigned sources accessible", () => {
    expect(filterSources(sources, { query: "공통", kind: "pdf", domainId: "ACC" }).map((source) => source.id))
      .toEqual(["ACC-CF"]);
    expect(filterSources(sources, { query: "", kind: "all", domainId: UNASSIGNED_SOURCE_DOMAIN }).map((source) => source.id))
      .toEqual(["NEW"]);
    expect(filterSources(sources, { query: "", kind: "all", domainId: ALL_SOURCE_DOMAINS })).toHaveLength(3);
  });
});
