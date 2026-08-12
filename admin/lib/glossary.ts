import type { GlossaryTermItem } from "@/lib/types";

export const glossaryConceptTypes = [
  "INSTITUTION", "BUSINESS_FUNCTION", "ORG_UNIT", "ROLE", "ASSET_CLASS", "INSTRUMENT",
  "STRATEGY", "DEAL", "PROCESS", "ACTIVITY", "METHODOLOGY", "MODEL", "METRIC",
  "ACCOUNTING_CONCEPT", "RISK", "EVENT", "ARTIFACT", "DISCLOSURE", "REGULATION",
  "MARKET_INFRA", "DATA_SOURCE", "IDENTIFIER", "TOOL_SKILL", "SECTOR",
] as const;

export const glossaryJurisdictions = ["GLOBAL", "KR", "US", "EU", "UK", "JP", "CN", "MULTI"] as const;
const termIdPattern = /^FIN-(?:0[1-9]|1\d|2[01])-\d{3}$/;
const sourceCodePattern = /^S\d{2}$/;

export class GlossaryValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GlossaryValidationError";
  }
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new GlossaryValidationError("용어 데이터 형식이 올바르지 않습니다.");
  }
  return value as Record<string, unknown>;
}

function requiredText(
  value: Record<string, unknown>,
  key: string,
  label: string,
  minimum: number,
  maximum: number,
): string {
  const text = typeof value[key] === "string" ? value[key].trim() : "";
  if (text.length < minimum || text.length > maximum) {
    throw new GlossaryValidationError(`${label}은(는) ${minimum}~${maximum}자로 입력해 주세요.`);
  }
  if (text === "TBD" || text === "TODO" || text === "미작성" || text.includes("...")) {
    throw new GlossaryValidationError(`${label}에 임시 문구를 사용할 수 없습니다.`);
  }
  return text;
}

function optionalText(value: Record<string, unknown>, key: string, maximum: number): string {
  const text = typeof value[key] === "string" ? value[key].trim() : "";
  if (text.length > maximum) throw new GlossaryValidationError(`${key}이(가) 너무 깁니다.`);
  return text;
}

function inventoryCell(text: string, label: string): string {
  if (/[|\r\n]/.test(text)) {
    throw new GlossaryValidationError(`${label}에는 줄바꿈이나 | 문자를 사용할 수 없습니다.`);
  }
  return text;
}

function textArray(
  value: Record<string, unknown>,
  key: string,
  label: string,
  minimum: number,
  maximum: number,
): string[] {
  const items = value[key];
  if (!Array.isArray(items)) throw new GlossaryValidationError(`${label} 형식이 올바르지 않습니다.`);
  const normalized = [...new Set(items.map((item) => typeof item === "string" ? item.trim() : "").filter(Boolean))];
  if (normalized.length < minimum || normalized.length > maximum || normalized.some((item) => item.length > 500)) {
    throw new GlossaryValidationError(`${label} 항목 수 또는 길이가 허용 범위를 벗어났습니다.`);
  }
  return normalized;
}

export function validateGlossaryTerm(value: unknown, expectedTermId: string): GlossaryTermItem {
  const input = record(value);
  const termId = requiredText(input, "termId", "용어 ID", 10, 10);
  if (termId !== expectedTermId || !termIdPattern.test(termId)) {
    throw new GlossaryValidationError("용어 ID가 요청 경로와 일치하지 않습니다.");
  }
  const categoryId = requiredText(input, "categoryId", "카테고리 ID", 2, 2);
  if (termId.slice(4, 6) !== categoryId) {
    throw new GlossaryValidationError("용어 ID와 카테고리가 일치하지 않습니다.");
  }
  const displayOrder = Number(input.displayOrder);
  if (!Number.isInteger(displayOrder) || displayOrder < 0 || displayOrder > 10_000) {
    throw new GlossaryValidationError("카테고리 내 정렬 순서가 올바르지 않습니다.");
  }
  const conceptType = requiredText(input, "conceptType", "개념 유형", 2, 40);
  if (!(glossaryConceptTypes as readonly string[]).includes(conceptType)) {
    throw new GlossaryValidationError("지원하지 않는 개념 유형입니다.");
  }
  const jurisdictions = textArray(input, "jurisdictions", "적용 관할", 1, 8);
  if (jurisdictions.some((item) => !(glossaryJurisdictions as readonly string[]).includes(item))) {
    throw new GlossaryValidationError("지원하지 않는 적용 관할 코드가 있습니다.");
  }
  const sourceCodes = textArray(input, "sourceCodes", "출처", 1, 10);
  if (sourceCodes.some((item) => !sourceCodePattern.test(item))) {
    throw new GlossaryValidationError("출처 코드 형식이 올바르지 않습니다.");
  }
  const reviewStatus = requiredText(input, "reviewStatus", "검토 상태", 8, 32);
  if (reviewStatus !== "agent_reviewed" && reviewStatus !== "approved") {
    throw new GlossaryValidationError("검토 상태가 올바르지 않습니다.");
  }
  const asOfDate = requiredText(input, "asOfDate", "기준일", 10, 10);
  const parsedAsOfDate = new Date(`${asOfDate}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(asOfDate) || Number.isNaN(parsedAsOfDate.valueOf()) ||
    parsedAsOfDate.toISOString().slice(0, 10) !== asOfDate) {
    throw new GlossaryValidationError("기준일이 올바르지 않습니다.");
  }
  const relatedTermIds = textArray(input, "relatedTermIds", "관련 용어", 0, 30);
  if (relatedTermIds.some((item) => !termIdPattern.test(item) || item === termId)) {
    throw new GlossaryValidationError("관련 용어 ID가 올바르지 않습니다.");
  }
  const adminReferenceSourceIds = input.adminReferenceSourceIds === undefined
    ? []
    : textArray(input, "adminReferenceSourceIds", "Admin 원문 레퍼런스", 0, 100);

  const canonicalNameEn = inventoryCell(
    requiredText(input, "canonicalNameEn", "영문 표준명", 1, 240),
    "영문 표준명",
  );
  const canonicalNameKo = inventoryCell(
    requiredText(input, "canonicalNameKo", "한글 표준명", 1, 240),
    "한글 표준명",
  );
  const aliases = textArray(input, "aliases", "별칭", 0, 30)
    .map((alias) => inventoryCell(alias, "별칭"));

  return {
    termId,
    categoryId,
    displayOrder,
    canonicalNameEn,
    canonicalNameKo,
    aliases,
    conceptType,
    oneLineDefinitionKo: requiredText(input, "oneLineDefinitionKo", "한 문장 정의", 18, 2_000),
    coreDefinitionKo: requiredText(input, "coreDefinitionKo", "핵심 의미", 35, 8_000),
    practicalContextKo: requiredText(input, "practicalContextKo", "실무 문맥", 18, 8_000),
    whyItMattersKo: requiredText(input, "whyItMattersKo", "중요성", 12, 4_000),
    exampleKo: requiredText(input, "exampleKo", "예시", 15, 6_000),
    limitationsKo: textArray(input, "limitationsKo", "주의·한계", 1, 20),
    sourceCodes,
    jurisdictions,
    asOfDate,
    reviewStatus,
    reviewFlags: textArray(input, "reviewFlags", "검토 플래그", 0, 20),
    relatedTermIds,
    formulaLatex: optionalText(input, "formulaLatex", 20_000),
    formulaNotesKo: optionalText(input, "formulaNotesKo", 8_000),
    adminReferenceSourceIds,
    contentRevision: Number.isInteger(Number(input.contentRevision)) ? Number(input.contentRevision) : 1,
    updatedAt: typeof input.updatedAt === "string" ? input.updatedAt : "",
    isActive: input.isActive !== false,
  };
}
