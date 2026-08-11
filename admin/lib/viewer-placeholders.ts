import type { ReleaseWorkspace, ReviewWorkspace, ValidationWorkspace } from "@/lib/data";
import type { AdminCapabilities, ConceptElement, DistractorItem, SourceItem } from "@/lib/types";

export const viewerCapabilities: AdminCapabilities = {
  role: "viewer",
  canEdit: false,
  canValidateRevision: false,
  canReview: false,
  canRelease: false,
  canValidateRelease: false,
};

function conceptPlaceholder(
  index: number,
  title: string,
  coreRelation: string,
  definition: string,
  extras: Partial<ConceptElement> = {},
): ConceptElement {
  return {
    elementId: `FIELD-${String(index).padStart(2, "0")}`,
    domainId: "FIELD",
    domainName: "구성 항목",
    elementNumber: index,
    title,
    mode: "concept",
    coreRelation,
    definition,
    intuition: "구체적인 상황을 통해 개념을 쉽게 이해하도록 설명하는 영역입니다.",
    elementScopeNotes: "문항 생성과 원본 추적에 쓰이는 관리용 범위 메모입니다.",
    scopeNotes: "앱에서 유형별 토글로 표시될 적용 장면과 문제 유형을 관리합니다.",
    formulaExpression: "앱에서 한 번만 표시되는 Markdown/LaTeX 핵심 공식입니다.",
    formulaAssumptions: "공식 카드 안의 토글로 표시될 적용 조건입니다.",
    formulaNotes: "공식과 관련된 내부 보조 설명을 관리하는 영역입니다.",
    checklist: "이 개념이 실제 업무에서 쓰이는 구체적인 경우를 목록으로 관리합니다.",
    sourceLabel: "근거 자료의 표시 이름이 들어갑니다.",
    sourceLocator: "문서 페이지·절 또는 공개 URL 위치를 기록합니다.",
    specSectionLocator: "원본 명세에서 대응하는 위치를 기록합니다.",
    status: "published",
    issueCount: 0,
    updatedAt: "실제 수정 시각은 표시하지 않음",
    updatedBy: "실제 작성자는 표시하지 않음",
    ...extras,
  };
}

export const viewerConceptElements: ConceptElement[] = [
  conceptPlaceholder(1, "기본 식별 정보", "요소 ID와 분야로 학습 단위를 구분합니다.", "표의 ID, 분야, 표시 순서와 문제 유형이 이 영역에 들어갑니다."),
  conceptPlaceholder(2, "학습 설명", "제목·정의·직관·상세 설명을 한 요소로 묶습니다.", "사용자가 앱에서 읽는 핵심 관계와 학습 본문의 구성 방식을 설명합니다.", { status: "approved" }),
  conceptPlaceholder(3, "공식과 실무 사례", "핵심 공식·적용 조건·변수 설명을 함께 관리합니다.", "계산형 요소의 표현과 실제 업무에서 쓰이는 경우가 들어갑니다.", { mode: "calculation", status: "reviewed" }),
  conceptPlaceholder(4, "근거와 품질 상태", "출처 위치와 revision 상태를 연결합니다.", "근거 자료, 자동 검증 이슈와 승인·배포 상태를 확인하는 영역입니다.", { status: "draft", issueCount: 1 }),
];

export const viewerSources: SourceItem[] = [
  { id: "SOURCE-FIELD-01", label: "자료 식별 정보", kind: "document", locator: "자료 ID, 표시 이름과 파일 유형이 표시되는 위치", status: "ready", linkedElements: 0, domains: [{ id: "FIELD-A", name: "단원 분류 예시", displayOrder: 1 }], createdAt: "등록 시각은 표시하지 않음" },
  { id: "SOURCE-FIELD-02", label: "원본 위치", kind: "pdf", locator: "비공개 저장 경로 또는 공개 URL의 형식을 설명", status: "processing", linkedElements: 0, domains: [{ id: "FIELD-A", name: "단원 분류 예시", displayOrder: 1 }], createdAt: "등록 시각은 표시하지 않음" },
  { id: "SOURCE-FIELD-03", label: "처리 상태", kind: "spreadsheet", locator: "처리 중·검토 필요·사용 준비 상태가 표시되는 위치", status: "needs_review", linkedElements: 0, domains: [{ id: "FIELD-B", name: "공통 자료 예시", displayOrder: 2 }], createdAt: "등록 시각은 표시하지 않음" },
  { id: "SOURCE-FIELD-04", label: "콘텐츠 연결", kind: "url", locator: "근거가 연결되는 학습요소와 인용 위치를 설명", status: "ready", linkedElements: 0, domains: [], createdAt: "등록 시각은 표시하지 않음" },
];

export const viewerDistractors: DistractorItem[] = [
  { id: "VIEWER-DIST-01", elementId: "FIELD-01", elementTitle: "연결 대상", text: "오답이 사용될 학습요소를 지정하는 자리", rationale: "요소 ID와 제목, 사용 여부를 연결하는 필드입니다.", confusionType: "연결 정보", difficulty: "기초", active: true, status: "published", updatedAt: "표시하지 않음" },
  { id: "VIEWER-DIST-02", elementId: "FIELD-02", elementTitle: "오답 문구", text: "정답처럼 보이지만 한 가지 개념이 틀린 문장을 기록하는 자리", rationale: "실제 선택지 대신 오답 문구가 지켜야 할 구성 원칙을 보여줍니다.", confusionType: "선택지 구성", difficulty: "보통", active: true, status: "approved", updatedAt: "표시하지 않음" },
  { id: "VIEWER-DIST-03", elementId: "FIELD-03", elementTitle: "오답 해설", text: "학습자가 무엇을 잘못 적용했는지 설명하는 자리", rationale: "잘못된 관계와 올바른 판단 기준을 함께 기록합니다.", confusionType: "해설 정보", difficulty: "보통", active: true, status: "reviewed", updatedAt: "표시하지 않음" },
  { id: "VIEWER-DIST-04", elementId: "FIELD-04", elementTitle: "분류 정보", text: "혼동 유형과 난이도, 검수 상태를 관리하는 자리", rationale: "출제 균형과 승인 여부를 판단하기 위한 메타데이터입니다.", confusionType: "품질 상태", difficulty: "심화", active: false, status: "draft", updatedAt: "표시하지 않음" },
];

const validationRevision = {
  revisionId: "viewer-validation-revision",
  entityType: "concept" as const,
  entityKey: "검증 대상 식별 정보",
  revisionNumber: 1,
  operation: "update" as const,
  contentHash: "콘텐츠 해시는 Viewer에게 표시하지 않습니다",
  changeReason: "변경 사유와 검증 대상의 종류가 표시되는 위치입니다.",
  createdAt: "작성 시각은 표시하지 않음",
  createdBy: "작성자는 표시하지 않음",
  state: "validation_failed" as const,
  stateNote: "검증 상태 설명",
  stateChangedAt: "상태 변경 시각은 표시하지 않음",
};

export const viewerValidationWorkspace: ValidationWorkspace = {
  revisions: [
    validationRevision,
    { ...validationRevision, revisionId: "viewer-validation-structure", entityKey: "구조 검사", revisionNumber: 2, changeReason: "필수 필드, Markdown·수식 구조와 참조 무결성을 검사합니다.", state: "draft" },
    { ...validationRevision, revisionId: "viewer-validation-content", entityKey: "콘텐츠 검사", revisionNumber: 3, changeReason: "정의·수식·출처와 문제 생성 가능 여부를 검사합니다.", state: "validating" },
  ],
  runs: [{
    validationRunId: "viewer-validation-run",
    targetType: "revision",
    revisionId: validationRevision.revisionId,
    releaseId: null,
    status: "failed",
    validatorName: "검증기 이름과 버전이 표시되는 위치",
    validatorVersion: "표시 예시",
    checksTotal: 3,
    checksPassed: 2,
    checksFailed: 1,
    summary: {},
    startedAt: "실행 시각은 표시하지 않음",
    completedAt: "완료 시각은 표시하지 않음",
    createdAt: "생성 시각은 표시하지 않음",
  }],
  issues: [{
    validationIssueId: "viewer-validation-issue",
    validationRunId: "viewer-validation-run",
    severity: "error",
    code: "검사 코드",
    fieldPath: "문제가 발견된 필드 경로",
    message: "오류·경고의 내용과 수정할 위치가 이 영역에 표시됩니다.",
    details: {},
    createdAt: "발견 시각은 표시하지 않음",
  }],
  jobs: [{
    jobId: "viewer-validation-job",
    jobKind: "content_validation",
    status: "succeeded",
    revisionId: validationRevision.revisionId,
    releaseId: null,
    progressPercent: 100,
    errorMessage: null,
    createdAt: "작업 시각은 표시하지 않음",
  }],
};

const reviewRevision = {
  ...validationRevision,
  revisionId: "viewer-review-revision",
  entityKey: "변경 비교 대상",
  state: "reviewed" as const,
  changeReason: "검토자가 변경 이유와 자동 검증 근거를 확인하는 위치입니다.",
  previousSnapshot: {
    definition_markdown: "이전 revision의 필드 값이 표시됩니다.",
    checklist_markdown: "변경 전 실무 사용 사례가 표시됩니다.",
  },
  snapshot: {
    definition_markdown: "검토할 revision의 수정된 필드 값이 표시됩니다.",
    checklist_markdown: "변경 후 실무 사용 사례가 표시됩니다.",
  },
};

export const viewerReviewWorkspace: ReviewWorkspace = {
  revisions: [reviewRevision],
  runs: [{
    validationRunId: "viewer-review-run",
    targetType: "revision",
    revisionId: reviewRevision.revisionId,
    releaseId: null,
    status: "passed",
    validatorName: "자동 검증 결과",
    validatorVersion: "표시 예시",
    checksTotal: 3,
    checksPassed: 3,
    checksFailed: 0,
    summary: {},
    startedAt: "표시하지 않음",
    completedAt: "표시하지 않음",
    createdAt: "표시하지 않음",
  }],
};

export const viewerReleaseWorkspace: ReleaseWorkspace = {
  releases: [{
    releaseId: "viewer-release",
    contentVersion: 0,
    versionName: "콘텐츠 버전명",
    schemaVersion: 0,
    minimumAppVersion: 0,
    status: "published",
    releaseNotes: "승인된 변경의 요약과 앱 반영 내용을 기록하는 자리입니다.",
    manifestSha256: "manifest SHA-256 값",
    databaseSha256: "SQLite SHA-256 값",
    databaseByteSize: 0,
    publishedAt: "공개 시각은 표시하지 않음",
    createdAt: "생성 시각은 표시하지 않음",
    itemCount: 0,
    artifactCount: 0,
    activeChannels: ["stable 채널"],
  }],
  runs: [{
    validationRunId: "viewer-release-run",
    targetType: "release",
    revisionId: null,
    releaseId: "viewer-release",
    status: "passed",
    validatorName: "릴리스 무결성 검사",
    validatorVersion: "표시 예시",
    checksTotal: 3,
    checksPassed: 3,
    checksFailed: 0,
    summary: {},
    startedAt: "표시하지 않음",
    completedAt: "표시하지 않음",
    createdAt: "표시하지 않음",
  }],
  jobs: [{
    jobId: "viewer-release-job",
    jobKind: "release_build",
    status: "succeeded",
    revisionId: null,
    releaseId: "viewer-release",
    progressPercent: 100,
    errorMessage: null,
    createdAt: "작업 시각은 표시하지 않음",
  }],
};
