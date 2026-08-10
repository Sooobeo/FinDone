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
  if (element.definition.trim().length < 24) {
    issues.push({
      field: "definition",
      severity: "error",
      message: "정의는 최소 24자 이상의 완결된 설명이어야 합니다.",
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
  if (!element.checklist.includes("- ")) {
    issues.push({
      field: "checklist",
      severity: "warning",
      message: "체크리스트는 Markdown 목록 형식으로 작성하세요.",
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
