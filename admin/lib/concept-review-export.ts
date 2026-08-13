import type { ConceptExperiment } from "@/lib/concept-model-report";

type QueueItem = ConceptExperiment["automatedReview"]["queue"][number];

export type ConceptReviewExportDecision = {
  decision: "approved" | "rejected";
  comment: string;
};

type ExportMetadata = {
  experimentId: string;
  generatedAt: string;
  reviewInputSha256: string;
};

type CellValue = string | number;

const QUESTION_TYPE_LABELS: Record<QueueItem["questionType"], string> = {
  term_to_definition: "용어 → 정의",
  term_to_intuition: "용어 → 직관",
  term_to_verbal_relation: "용어 → 말로 푼 관계",
};

const SEVERITY_LABELS: Record<QueueItem["severity"], string> = {
  review: "확인",
  block: "차단",
};

function xmlEscape(value: unknown): string {
  return String(value ?? "")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/gu, "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function cellReference(columnIndex: number, rowIndex: number): string {
  let column = columnIndex + 1;
  let letters = "";
  while (column > 0) {
    const remainder = (column - 1) % 26;
    letters = String.fromCharCode(65 + remainder) + letters;
    column = Math.floor((column - 1) / 26);
  }
  return `${letters}${rowIndex + 1}`;
}

function inlineStringCell(value: CellValue, reference: string, style: number): string {
  return `<c r="${reference}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${xmlEscape(value)}</t></is></c>`;
}

function worksheetXml(rows: CellValue[][], widths: number[]): string {
  const rowXml = rows.map((row, rowIndex) => {
    const cells = row.map((value, columnIndex) => (
      inlineStringCell(value, cellReference(columnIndex, rowIndex), rowIndex === 0 ? 1 : 2)
    )).join("");
    return `<row r="${rowIndex + 1}">${cells}</row>`;
  }).join("");
  const lastReference = cellReference(
    Math.max(0, (rows[0]?.length ?? 1) - 1),
    Math.max(0, rows.length - 1),
  );
  const columns = widths.map((width, index) => (
    `<col min="${index + 1}" max="${index + 1}" width="${width}" customWidth="1"/>`
  )).join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:${lastReference}"/>
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView></sheetViews>
  <cols>${columns}</cols>
  <sheetData>${rowXml}</sheetData>
  <autoFilter ref="A1:${lastReference}"/>
</worksheet>`;
}

function stylesXml(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="D9EDE8"/><bgColor indexed="64"/></patternFill></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" applyFont="1" applyFill="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;
}

function workbookXml(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="검수 문항" sheetId="1" r:id="rId1"/><sheet name="선지 상세" sheetId="2" r:id="rId2"/><sheet name="검수 안내" sheetId="3" r:id="rId3"/></sheets></workbook>`;
}

function workbookRelationshipsXml(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/><Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`;
}

function contentTypesXml(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`;
}

function packageRelationshipsXml(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`;
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xFFFFFFFF;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ ((crc & 1) ? 0xEDB88320 : 0);
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function u16(value: number): Uint8Array {
  return new Uint8Array([value & 0xFF, (value >>> 8) & 0xFF]);
}

function u32(value: number): Uint8Array {
  return new Uint8Array([value & 0xFF, (value >>> 8) & 0xFF, (value >>> 16) & 0xFF, (value >>> 24) & 0xFF]);
}

function joinBytes(parts: Uint8Array[]): Uint8Array {
  const result = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

function zipStored(files: Array<{ path: string; content: string }>): Uint8Array {
  const encoder = new TextEncoder();
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;
  for (const file of files) {
    const name = encoder.encode(file.path);
    const content = encoder.encode(file.content);
    const checksum = crc32(content);
    const local = joinBytes([
      u32(0x04034B50), u16(20), u16(0), u16(0), u16(0), u16(0), u32(checksum), u32(content.length), u32(content.length), u16(name.length), u16(0), name, content,
    ]);
    localParts.push(local);
    const central = joinBytes([
      u32(0x02014B50), u16(20), u16(20), u16(0), u16(0), u16(0), u16(0), u32(checksum), u32(content.length), u32(content.length), u16(name.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset), name,
    ]);
    centralParts.push(central);
    offset += local.length;
  }
  const centralDirectory = joinBytes(centralParts);
  const locals = joinBytes(localParts);
  const end = joinBytes([u32(0x06054B50), u16(0), u16(0), u16(files.length), u16(files.length), u32(centralDirectory.length), u32(locals.length), u16(0)]);
  return joinBytes([locals, centralDirectory, end]);
}

function reasonText(item: QueueItem): string {
  return item.reasons.map((reason) => `${reason.label} [측정 ${reason.measured} / 기준 ${reason.threshold}]`).join(" · ");
}

function choiceText(item: QueueItem, key: string): string {
  return item.choices.find((choice) => choice.key === key)?.text ?? "";
}

export function buildConceptReviewWorkbook(
  items: QueueItem[],
  decisions: Record<string, ConceptReviewExportDecision>,
  metadata: ExportMetadata,
): Uint8Array {
  const questionHeaders = [
    "문항 ID", "요소 ID", "문항 유형", "분할", "검수 등급", "문제", "문항 해설",
    "선지 A", "선지 B", "선지 C", "선지 D", "선지 E", "정답", "자동 검수 사유",
    "Top-4 합의도", "최저 오답 지지율", "경계 여유", "변경 요소 영향", "선지 구성 변경",
    "현재 결정", "검수 메모", "문항 fingerprint",
  ];
  const questionRows: CellValue[][] = [questionHeaders];
  const detailRows: CellValue[][] = [["문항 ID", "요소 ID", "문항 유형", "선지", "출처 요소 ID", "선지 설명", "선지 해설", "정답 여부"]];
  for (const item of items) {
    const decision = decisions[item.questionId];
    questionRows.push([
      item.questionId,
      item.elementId,
      QUESTION_TYPE_LABELS[item.questionType],
      item.split,
      SEVERITY_LABELS[item.severity],
      item.stem,
      item.explanation,
      ...["A", "B", "C", "D", "E"].map((key) => choiceText(item, key)),
      item.choices.find((choice) => choice.isCorrect)?.key ?? "",
      reasonText(item),
      item.metrics.meanTop4Agreement,
      item.metrics.minimumSelectedCandidateSupport,
      item.metrics.normalizedBoundaryMargin,
      item.change.affectedByChangedElement ? "예" : "아니오",
      item.change.choiceSetChanged ? "예" : "아니오",
      decision?.decision === "approved" ? "승인" : decision?.decision === "rejected" ? "반려" : "미결",
      decision?.comment ?? "",
      item.questionFingerprint,
    ]);
    for (const choice of item.choices) {
      detailRows.push([
        item.questionId,
        item.elementId,
        QUESTION_TYPE_LABELS[item.questionType],
        choice.key,
        choice.elementId,
        choice.text,
        choice.explanation,
        choice.isCorrect ? "예" : "아니오",
      ]);
    }
  }
  const infoRows: CellValue[][] = [
    ["항목", "값"],
    ["내보낸 문항 수", items.length],
    ["자동 통과 제외 검수 큐", "현재 화면의 검수 대상만 포함"],
    ["실험 ID", metadata.experimentId],
    ["검수 입력 SHA-256", metadata.reviewInputSha256],
    ["내보낸 시각", metadata.generatedAt],
    ["사용 방법", "검토 후 결정은 Admin 화면에서 저장하세요. 이 파일을 다시 가져오는 기능은 제공하지 않습니다."],
  ];
  return zipStored([
    { path: "[Content_Types].xml", content: contentTypesXml() },
    { path: "_rels/.rels", content: packageRelationshipsXml() },
    { path: "xl/workbook.xml", content: workbookXml() },
    { path: "xl/_rels/workbook.xml.rels", content: workbookRelationshipsXml() },
    { path: "xl/styles.xml", content: stylesXml() },
    { path: "xl/worksheets/sheet1.xml", content: worksheetXml(questionRows, [30, 12, 22, 12, 10, 42, 42, 42, 42, 42, 42, 42, 8, 48, 14, 16, 14, 12, 12, 12, 30, 66]) },
    { path: "xl/worksheets/sheet2.xml", content: worksheetXml(detailRows, [32, 12, 22, 8, 14, 58, 58, 10]) },
    { path: "xl/worksheets/sheet3.xml", content: worksheetXml(infoRows, [28, 100]) },
  ]);
}

export function conceptReviewWorkbookFilename(date = new Date()): string {
  const stamp = date.toISOString().slice(0, 10).replaceAll("-", "");
  return `findone-concept-review-${stamp}.xlsx`;
}
