import conceptJson from "@/data/content-elements.generated.json";
import sourceJson from "@/data/sources.generated.json";
import { packagedContentInfo } from "@/lib/packaged-info";
import type {
  ConceptElement,
  DistractorItem,
  ReleaseItem,
  SourceItem,
  ValidationIssue,
} from "@/lib/types";

type GeneratedConcept = Omit<ConceptElement, "elementScopeNotes" | "formulaNotes"> &
  Partial<Pick<ConceptElement, "elementScopeNotes" | "formulaNotes">>;

export const conceptElements: ConceptElement[] = (conceptJson as GeneratedConcept[]).map((element) => ({
  ...element,
  elementScopeNotes: element.elementScopeNotes ?? "",
  formulaNotes: element.formulaNotes ?? element.checklist,
}));
export const sourceItems = sourceJson as SourceItem[];

export { packagedContentInfo };

/**
 * The packaged app has no curated distractor table yet. These records are intentionally
 * labelled as examples so the admin workflow can be evaluated before Supabase is connected.
 */
export const distractorItems: DistractorItem[] = [
  {
    id: "demo-dist-acc-01-01",
    elementId: "ACC-01",
    elementTitle: "회계등식과 차변·대변",
    text: "자산은 부채에서 자본을 차감한 금액과 같다.",
    rationale: "회계등식의 부호를 바꾸어 자본을 차감하는 흔한 혼동입니다.",
    confusionType: "관계식 부호 오류",
    difficulty: "기초",
    active: true,
    status: "draft",
    updatedAt: "데모 예시",
  },
  {
    id: "demo-dist-acc-02-01",
    elementId: "ACC-02",
    elementTitle: "발생주의·현금주의와 결산조정",
    text: "현금을 받은 시점에만 수익을 인식한다.",
    rationale: "현금주의 설명을 발생주의 정의로 오인한 선택지입니다.",
    confusionType: "인식 시점 혼동",
    difficulty: "기초",
    active: true,
    status: "reviewed",
    updatedAt: "데모 예시",
  },
  {
    id: "demo-dist-cf-03-01",
    elementId: "CF-03",
    elementTitle: "순현재가치(NPV)",
    text: "NPV가 0보다 작을수록 프로젝트의 경제적 가치가 크다.",
    rationale: "NPV 의사결정 기준의 방향을 반대로 적용했습니다.",
    confusionType: "판단 기준 반전",
    difficulty: "보통",
    active: true,
    status: "approved",
    updatedAt: "데모 예시",
  },
  {
    id: "demo-dist-fi-03-01",
    elementId: "FI-03",
    elementTitle: "Macaulay·Modified Duration",
    text: "수정 듀레이션은 금리 변화와 채권가격 변화가 같은 방향임을 뜻한다.",
    rationale: "가격과 수익률의 역관계를 놓친 선택지입니다.",
    confusionType: "방향성 오류",
    difficulty: "보통",
    active: false,
    status: "rejected",
    updatedAt: "데모 예시",
  },
];

export const validationIssues: ValidationIssue[] = [
  {
    id: "demo-issue-1",
    elementId: "DER-09",
    title: "Greeks·delta hedge",
    field: "수식 변수",
    severity: "warning",
    message: "수식에 등장하는 Δ의 단위 설명을 다시 확인하세요.",
    suggestion: "변수 목록에 기초자산 가격 1단위 변화당 옵션가격 변화량임을 명시합니다.",
  },
  {
    id: "demo-issue-2",
    elementId: "EQV-44",
    title: "재투자율·성장률",
    field: "출처 근거",
    severity: "info",
    message: "동일한 식을 설명하는 보조 출처가 연결되어 있습니다.",
    suggestion: "주출처와 보조출처의 우선순위를 검토합니다.",
  },
  {
    id: "demo-issue-3",
    elementId: "ACC-02",
    title: "발생주의·현금주의와 결산조정",
    field: "Markdown",
    severity: "error",
    message: "데모 수정안에 닫히지 않은 수식 구분자가 있습니다.",
    suggestion: "수식 구분자 $$가 쌍을 이루는지 확인합니다.",
  },
];

export const releaseItems: ReleaseItem[] = [
  {
    version: `content-v${packagedContentInfo.version}`,
    status: "published",
    changes: conceptElements.length,
    elements: conceptElements.length,
    size: "2.1 MB",
    checksum: packagedContentInfo.sha256,
    createdAt: "현재 APK 내장본",
    author: "패키지 가져오기",
  },
  {
    version: `content-v${packagedContentInfo.version + 1}-draft`,
    status: "draft",
    changes: 0,
    elements: conceptElements.length,
    size: "생성 전",
    checksum: "—",
    createdAt: "아직 생성되지 않음",
    author: "—",
  },
];
