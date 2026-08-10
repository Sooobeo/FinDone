import type { ConceptElement } from "@/lib/types";

const columns: Array<[keyof ConceptElement, string]> = [
  ["domainId", "분야 ID"],
  ["domainName", "분야명"],
  ["elementId", "요소 ID"],
  ["elementNumber", "요소 번호"],
  ["title", "요소명"],
  ["mode", "모드"],
  ["coreRelation", "핵심 관계"],
  ["definition", "정의"],
  ["intuition", "직관 설명"],
  ["elementScopeNotes", "요소 적용 범위"],
  ["scopeNotes", "학습 설명"],
  ["formulaExpression", "수식"],
  ["formulaAssumptions", "수식 가정"],
  ["formulaNotes", "수식 설명"],
  ["checklist", "체크리스트"],
  ["sourceLabel", "출처명"],
  ["sourceLocator", "출처 위치"],
  ["specSectionLocator", "명세 위치"],
  ["status", "상태"],
];

const lockedKeys = new Set<keyof ConceptElement>([
  "domainId",
  "domainName",
  "elementId",
  "elementNumber",
  "mode",
  "status",
]);

const editableKeys = columns
  .map(([key]) => key)
  .filter((key) => !lockedKeys.has(key));

export interface ConceptCsvImportResult {
  changed: ConceptElement[];
  rowCount: number;
  unchangedCount: number;
}

export class ConceptCsvError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConceptCsvError";
  }
}

export function safeSpreadsheetValue(value: unknown): string {
  const text = String(value ?? "");
  return /^[=+\-@]/.test(text.trimStart()) ? `'${text}` : text;
}

function quote(value: unknown): string {
  const safe = safeSpreadsheetValue(value);
  return `"${safe.replaceAll('"', '""')}"`;
}

export function conceptsToCsv(elements: ConceptElement[]): string {
  const header = columns.map(([, label]) => quote(label)).join(",");
  const rows = elements.map((element) =>
    columns.map(([key]) => quote(element[key])).join(","),
  );
  return `\uFEFF${[header, ...rows].join("\r\n")}`;
}

/** Parse the RFC 4180 subset emitted by conceptsToCsv, including multiline Markdown cells. */
export function parseCsvRows(input: string): string[][] {
  const text = input.startsWith("\uFEFF") ? input.slice(1) : input;
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"') {
        if (text[index + 1] === '"') {
          field += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        field += character;
      }
      continue;
    }

    if (character === '"' && field.length === 0) {
      quoted = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\r" || character === "\n") {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }

  if (quoted) throw new ConceptCsvError("닫히지 않은 따옴표가 있습니다.");
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((values) => values.some((value) => value.trim().length > 0));
}

function restoreSpreadsheetValue(value: string): string {
  return /^'[=+\-@]/.test(value) ? value.slice(1) : value;
}

export function conceptsFromCsv(
  csv: string,
  currentElements: ConceptElement[],
): ConceptCsvImportResult {
  if (csv.length > 10 * 1024 * 1024) {
    throw new ConceptCsvError("CSV는 10MB 이하여야 합니다.");
  }
  const rows = parseCsvRows(csv);
  if (rows.length < 2) throw new ConceptCsvError("헤더와 한 개 이상의 요소 행이 필요합니다.");
  if (rows.length - 1 > 135) throw new ConceptCsvError("한 번에 최대 135개 요소만 가져올 수 있습니다.");

  const header = rows[0].map((value) => value.trim());
  const headerIndexes = new Map(header.map((label, index) => [label, index]));
  for (const [, label] of columns) {
    if (!headerIndexes.has(label)) throw new ConceptCsvError(`필수 열이 없습니다: ${label}`);
  }
  if (new Set(header).size !== header.length) throw new ConceptCsvError("중복된 열 이름이 있습니다.");

  const currentById = new Map(currentElements.map((element) => [element.elementId, element]));
  const seen = new Set<string>();
  const changed: ConceptElement[] = [];
  let unchangedCount = 0;

  for (const [rowIndex, values] of rows.slice(1).entries()) {
    const cell = (key: keyof ConceptElement): string => {
      const label = columns.find(([columnKey]) => columnKey === key)?.[1];
      const index = label === undefined ? undefined : headerIndexes.get(label);
      return index === undefined ? "" : restoreSpreadsheetValue(values[index] ?? "");
    };
    const elementId = cell("elementId").trim();
    if (!elementId) throw new ConceptCsvError(`${rowIndex + 2}행의 요소 ID가 비어 있습니다.`);
    if (seen.has(elementId)) throw new ConceptCsvError(`요소 ID가 중복되었습니다: ${elementId}`);
    seen.add(elementId);

    const current = currentById.get(elementId);
    if (!current) throw new ConceptCsvError(`현재 DB에 없는 요소 ID입니다: ${elementId}`);
    if (cell("domainId") !== current.domainId || cell("domainName") !== current.domainName) {
      throw new ConceptCsvError(`${elementId}: 분야 ID와 분야명은 CSV에서 바꿀 수 없습니다.`);
    }
    if (Number(cell("elementNumber")) !== current.elementNumber || cell("mode") !== current.mode) {
      throw new ConceptCsvError(`${elementId}: 요소 번호와 모드는 CSV에서 바꿀 수 없습니다.`);
    }

    const next = { ...current };
    for (const key of editableKeys) {
      // All editable values in the CSV contract are strings.
      (next as unknown as Record<string, unknown>)[key] = cell(key);
    }
    if (editableKeys.some((key) => next[key] !== current[key])) changed.push(next);
    else unchangedCount += 1;
  }

  return { changed, rowCount: rows.length - 1, unchangedCount };
}
