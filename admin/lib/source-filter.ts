import type { SourceDomain, SourceItem } from "@/lib/types";

export const ALL_SOURCE_DOMAINS = "all";
export const UNASSIGNED_SOURCE_DOMAIN = "unassigned";

export interface SourceDomainOption extends SourceDomain {
  sourceCount: number;
}

export interface SourceFilters {
  query: string;
  kind: string;
  domainId: string;
}

export function sourceDomainOptions(sources: SourceItem[]): SourceDomainOption[] {
  const domains = new Map<string, SourceDomainOption>();

  for (const source of sources) {
    const seen = new Set<string>();
    for (const domain of source.domains) {
      if (!domain.id || seen.has(domain.id)) continue;
      seen.add(domain.id);
      const current = domains.get(domain.id);
      domains.set(domain.id, {
        ...domain,
        sourceCount: (current?.sourceCount ?? 0) + 1,
      });
    }
  }

  return [...domains.values()].sort(
    (left, right) => left.displayOrder - right.displayOrder || left.name.localeCompare(right.name, "ko-KR"),
  );
}

export function filterSources(sources: SourceItem[], filters: SourceFilters): SourceItem[] {
  const normalized = filters.query.trim().toLocaleLowerCase("ko-KR");

  return sources.filter((source) => {
    if (filters.kind !== "all" && source.kind !== filters.kind) return false;
    if (
      filters.domainId !== ALL_SOURCE_DOMAINS
      && (filters.domainId === UNASSIGNED_SOURCE_DOMAIN
        ? source.domains.length > 0
        : !source.domains.some((domain) => domain.id === filters.domainId))
    ) return false;

    if (!normalized) return true;
    const searchable = [
      source.id,
      source.label,
      source.locator,
      ...source.domains.map((domain) => domain.name),
    ].join(" ").toLocaleLowerCase("ko-KR");
    return searchable.includes(normalized);
  });
}
