export interface SectionedMarkdownSection {
  id: string;
  title: string;
  lead: string;
  body: string;
}

export interface MarkdownSubsection {
  title: string;
  body: string;
}

const SECTION_MARKER = /<!--\s*section:([a-z0-9-]+)\s*-->/g;

function parseSectionBlock(id: string, block: string): SectionedMarkdownSection {
  const normalized = block.trim();
  const titleMatch = normalized.match(/^##\s+(.+)$/m);
  if (!titleMatch || titleMatch.index == null) {
    throw new Error(`Markdown section "${id}" must begin with an H2 title.`);
  }

  const beforeTitle = normalized.slice(0, titleMatch.index).trim();
  if (beforeTitle) {
    throw new Error(`Markdown section "${id}" has content before its H2 title.`);
  }

  const content = normalized.slice(titleMatch.index + titleMatch[0].length).trim();
  const [lead = "", ...remainingBlocks] = content.split(/\r?\n\s*\r?\n/);
  if (!lead.trim()) {
    throw new Error(`Markdown section "${id}" must include a lead paragraph.`);
  }

  return {
    id,
    title: titleMatch[1].trim(),
    lead: lead.trim(),
    body: remainingBlocks.join("\n\n").trim(),
  };
}

export function parseSectionedMarkdown(
  source: string,
  requiredSectionIds: readonly string[] = [],
): Record<string, SectionedMarkdownSection> {
  const markers = [...source.matchAll(SECTION_MARKER)];
  if (!markers.length) throw new Error("No <!-- section:id --> markers were found in the Markdown file.");

  const sections: Record<string, SectionedMarkdownSection> = {};
  markers.forEach((marker, index) => {
    const id = marker[1];
    if (sections[id]) throw new Error(`Duplicate Markdown section id: ${id}`);
    const start = (marker.index ?? 0) + marker[0].length;
    const end = markers[index + 1]?.index ?? source.length;
    sections[id] = parseSectionBlock(id, source.slice(start, end));
  });

  const missing = requiredSectionIds.filter((id) => !sections[id]);
  if (missing.length) throw new Error(`Missing required Markdown section(s): ${missing.join(", ")}`);
  return sections;
}

export function splitMarkdownSubsections(source: string): MarkdownSubsection[] {
  const matches = [...source.matchAll(/^###\s+(.+)$/gm)];
  return matches.map((match, index) => {
    const start = (match.index ?? 0) + match[0].length;
    const end = matches[index + 1]?.index ?? source.length;
    return { title: match[1].trim(), body: source.slice(start, end).trim() };
  });
}

export function serializeMarkdownSection(section: SectionedMarkdownSection) {
  return [
    `## ${section.title}`,
    section.lead,
    section.body,
  ].filter(Boolean).join("\n\n");
}

export function markdownToPlainText(source: string) {
  return source
    .replace(/<!--.*?-->/gs, " ")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^[-*]\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}
