import type { ConceptElement } from "@/lib/types";

export interface ConceptValidationResult {
  field: keyof ConceptElement;
  severity: "error" | "warning";
  message: string;
}

export function validateConcept(element: ConceptElement): ConceptValidationResult[] {
  const issues: ConceptValidationResult[] = [];

  if (!element.title.trim()) {
    issues.push({ field: "title", severity: "error", message: "요소명이 비어 있습니다." });
  }
  if (element.definition.trim().length < 36) {
    issues.push({
      field: "definition",
      severity: "error",
      message: "정의는 공식 없이 최소 36자 이상의 완결된 한 문장으로 작성하세요.",
    });
  }
  if (element.intuition.trim().length < 72) {
    issues.push({
      field: "intuition",
      severity: "error",
      message: "쉽게 이해하기는 구체적인 상황을 포함해 최소 72자 이상 작성하세요.",
    });
  }
  if (element.intuition.includes("이 개념을 읽는 순서")) {
    issues.push({
      field: "intuition",
      severity: "error",
      message: "일괄적인 읽는 순서 대신 이 요소 자체를 쉽게 설명하세요.",
    });
  }
  if (!/^###\s+\S/m.test(element.scopeNotes)) {
    issues.push({
      field: "scopeNotes",
      severity: "error",
      message: "### 제목으로 적용 유형을 하나 이상 나누세요. 제목 하나가 앱의 토글 하나가 됩니다.",
    });
  }
  if (!element.sourceLocator.trim()) {
    issues.push({
      field: "sourceLocator",
      severity: "error",
      message: "검증 가능한 출처 위치가 필요합니다.",
    });
  }
  if (element.formulaExpression.includes("$$") && !element.formulaAssumptions.trim()) {
    issues.push({
      field: "formulaAssumptions",
      severity: "warning",
      message: "수식이 있는 요소에는 적용 가정이 권장됩니다.",
    });
  }
  if (!element.formulaExpression.trim()) {
    issues.push({
      field: "formulaExpression",
      severity: "error",
      message: "핵심 공식이 비어 있습니다.",
    });
  }
  const formulaOutsideCard = [
    ["definition", element.definition],
    ["intuition", element.intuition],
    ["scopeNotes", element.scopeNotes],
    ["checklist", element.checklist],
  ] as const;
  formulaOutsideCard.forEach(([field, value]) => {
    if (value.includes("$$")) {
      issues.push({
        field,
        severity: "error",
        message: "공식은 ‘핵심 공식’ 영역에서만 한 번 표시하세요.",
      });
    }
  });
  const practicalUseCount = (element.checklist.match(/^\s*-\s+\S/gm) ?? []).length;
  if (practicalUseCount < 2) {
    issues.push({
      field: "checklist",
      severity: "error",
      message: "실무 사용 사례를 Markdown 목록으로 최소 2개 작성하세요.",
    });
  }

  return issues;
}

export function filterConcepts(
  elements: ConceptElement[],
  query: string,
  domainId: string,
  status: string,
): ConceptElement[] {
  const normalized = query.trim().toLocaleLowerCase("ko-KR");
  return elements.filter((element) => {
    if (domainId !== "all" && element.domainId !== domainId) return false;
    if (status !== "all" && element.status !== status) return false;
    if (!normalized) return true;
    return [element.elementId, element.title, element.coreRelation, element.definition]
      .join(" ")
      .toLocaleLowerCase("ko-KR")
      .includes(normalized);
  });
}
