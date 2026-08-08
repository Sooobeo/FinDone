---
title: Finance Interview 개념·계산 퀴즈 앱 — 최종 콘텐츠 자료집 및 구현 설계서
version: 2.2.0
date: 2026-08-08
language: ko-KR
status: implementation-ready
deployment: single-user-android-sideload
---

# Finance Interview 개념·계산 퀴즈 앱

## 0. 문서의 목적

이 문서는 주식 리서치, 투자운용, 회계, 기업재무, 채권, 파생상품, 투자은행(IB), 시장 및 대체투자 분야의 **Finance Interview 대비 앱**을 구현하기 위한 최종 콘텐츠 자료집이자 기능 설계서다.

앱은 다음 다섯 가지를 반드시 제공한다.

1. 분야·요소별 개념 카드와 수식 카드
2. 개념 퀴즈와 계산 퀴즈, 그리고 관련 개념·수식·대입과정·해석이 포함된 정답 해설
3. 오답 이력과 문제 인스턴스 북마크
4. 일반화된 문제 템플릿에 허용 범위의 숫자를 넣어 문제를 무작위 생성하되, **계산기 없이 암산할 수 있고 최종 답은 항상 정수**가 되도록 하는 생성 규칙
5. 분야·요소별로 고정된 지식 범위와 검증된 근거 안에서, **로컬 지식 DB의 claim을 검색하고 seed 기반 renderer로 조립하는 개념문제**. 출처·renderer 버전·정답 근거를 문제 snapshot에 보존하며 로컬 LLM은 PC 제작의 선택 기능으로만 둔다.

### 0.1 명칭 일반화

학회 고유명은 출제범위의 조사 근거로만 사용하고 앱의 사용자-facing 분류에는 사용하지 않는다.

| 기존 준비표 명칭 | 앱의 최종 명칭 | 코드 접두사 | 의미 |
|---|---|---:|---|
| 회계 | 회계·재무제표 | `ACC` | 거래 기록부터 세 재무제표와 비율 분석까지 |
| 재무 | 기업재무 | `CF` | 자금의 시간가치, 투자안, 자본비용과 현금흐름 가치평가 |
| 투자운용 | 투자·포트폴리오 | `INV` | 수익률·위험·분산투자·성과평가 |
| 채권 | 채권·금리 | `FI` | 채권가격, 수익률곡선, 듀레이션, 헤지와 신용 |
| 파생 | 파생상품 | `DER` | 선도·선물·옵션·스왑의 가격과 헤지 |
| YIG | **주식 리서치·기업가치평가** | `EQV` | 실적추정, 멀티플, DCF, 목표주가와 시나리오 |
| YFL Tech | **IB·시장·대체투자 실무** | `IBT` | 마켓, M&A, IPO, 부동산 및 딜 계산 |

### 0.2 범위와 비범위

- 본 문서는 면접에 적합한 **학부 전공기초부터 주니어 실무 수준**을 목표로 한다.
- 확률미분방정식, 확률변동성 모형, 복잡한 구조화상품, CPA 2차 수준의 장문 회계처리는 기본 문제은행에서 제외한다.
- 개념형 문제는 단일선택·복수선택·참거짓·순서배열·30~60초 구술형을 허용한다. 구술형 자동채점은 선택 기능이며, 기본값은 검수된 rubric에 따른 자기검토다.
- 계산형 문제는 **계산기·엑셀·수식표 없이 암산으로 푸는 상황**을 가정한다. 사용자가 입력하는 최종값은 정수인 `integer`, 여러 정수인 `integer_tuple`, 또는 정수 객관식인 `integer_mcq`만 허용한다.
- 개념 중심으로만 의미가 있는 요소는 계산 템플릿을 강제로 만들지 않는다. 계산형이 정의된 모든 템플릿은 정수답 생성 규칙, 별도 reference solver, 암산 복잡도 검사를 가져야 한다. 암산 기준을 만족시키기 어려운 고급 계산은 수치문제로 출제하지 않고 개념형으로 전환하거나 필요한 할인계수·정규분포값을 지문에 제공한다.
- 금액은 원칙적으로 `백만원`, 금리는 `bp` 또는 `정수 %`, 주가는 `원`, 수량은 `주/계약`을 사용한다.
- 이 버전의 배포 전제는 **1인·비상업·본인 Android 전용 사이드로드**다. Play Store나 다른 앱스토어에 올리지 않고, PC에서 만든 서명 APK를 개인 OneDrive로 옮겨 본인 휴대폰에만 설치한다.
- 자료 파싱·문항 검증·콘텐츠 DB 빌드는 PC에서 수행하고, Android 앱은 패키지에 포함된 검증 DB로 오프라인 실행한다. OneDrive는 APK·선택적 백업 파일의 개인 전송수단일 뿐 런타임 서버나 자동 동기화 계층이 아니다.
- 기본 실행 프로필은 `offline_strict`다. 퀴즈를 푸는 동안 네트워크를 쓰지 않고 원격 API·Hosted File Search·클라우드 embedding을 모두 끈다.
- 계산형, 객관식, 참거짓, 순서배열은 모델 없이 생성·채점한다. 구술형은 claim rubric과 자기검토가 기본이며 로컬 모델 채점은 선택 사항이다.
- 공개 URL은 한 번 받아 로컬에 캐시하고 이후에는 SHA-256이 달라진 자료만 다시 파싱한다. 사용자가 직접 보유한 PDF·HTML·TXT·XLSX도 로컬 파일로 가져올 수 있다.
- 로그인·유료벽·CAPTCHA·비공개 토큰 등 접근통제는 우회하지 않는다. `401/403/429` 또는 명시적 차단을 만나면 자동수집을 멈추고, 사용자가 정상적으로 확보한 로컬 파일만 수동으로 가져온다.

## 1. 콘텐츠 정보구조

### 1.1 계층

```text
SourceRef(링크·서지 식별자)
└─ CorpusDocument(특정 시점의 로컬 수집본)
   └─ EvidenceChunk(페이지·절 위치가 보존된 근거 조각)
      └─ ConceptClaim(사람이 승인한 최소 지식 단위)

Domain(분야)
└─ Element(번호가 부여된 학습요소)
   ├─ ConceptCard(개념)
   ├─ FormulaCard(수식)
   ├─ ElementConceptScope(허용·제외 범위)
   ├─ ConceptQuestionBlueprint(개념 출제 골격)
   │  └─ GeneratedConceptQuestion(근거·검증결과가 고정된 실제 문제)
   └─ QuestionTemplate(계산 문제의 일반화 유형)
      └─ GeneratedQuestion(난수와 seed가 고정된 실제 계산 문제)
```

### 1.2 고유 ID 규칙

| 객체 | 형식 | 예시 |
|---|---|---|
| 분야 | 접두사 | `ACC`, `CF`, `INV`, `FI`, `DER`, `EQV`, `IBT` |
| 학습요소 | `{DOMAIN}-{NN}` | `CF-07` |
| 개념 | `{ELEMENT}-C{NN}` | `CF-07-C01` |
| 수식 | `{ELEMENT}-F{NN}` | `CF-07-F01` |
| 문제 템플릿 | `{ELEMENT}-Q{NN}` | `CF-07-Q02` |
| 생성 문제 | `{TEMPLATE}:g{generatorVersion}:{seed}` | `CF-07-Q02:g1:420319` |
| 원문 문서 | `DOC-{SOURCE}-{NN}-V{NN}` | `DOC-SEC-NONGAAP-01-V02` |
| 근거 조각 | `{DOCUMENT}-CH{NNNN}` | `DOC-SEC-NONGAAP-01-V02-CH0042` |
| 검증 주장 | `{ELEMENT}-CL{NN}` | `EQV-34-CL03` |
| 개념문제 blueprint | `{ELEMENT}-CQ{NN}` | `EQV-34-CQ05` |
| 개념문제 인스턴스 | `{BLUEPRINT}:b{blueprintVersion}:c{corpusVersion}:s{scopeVersion}:r{rendererVersion}:{seed}` | `EQV-34-CQ05:b2:c3:s4:r2:49302` |

- ID는 한 번 배포한 뒤 재사용하거나 다른 의미로 바꾸지 않는다.
- 문구 수정은 `contentVersion`, 생성규칙 수정은 `generatorVersion`을 올린다.
- 북마크와 오답노트는 템플릿뿐 아니라 `seed`, 실제 파라미터, 생성 당시 버전을 저장한다.
- 상세 명세에서 독립 계산식이 하나씩인 `유형 A`, `유형 B`는 각각 `Q01`, `Q02`로 매핑한다.
- 한 유형 안에 `또는`, 슬래시(`/`)로 서로 다른 계산식이 병기되면 A/B 표시는 묶음명일 뿐이다. 구현 시 왼쪽부터 모든 독립 prompt를 `Q01`, `Q02`, `Q03` 순서로 펼친다. `EQV`·`IBT` 표의 기본 prompt는 `Q01`, 별도로 난수 선택되는 변형 prompt는 `Q02`부터 부여한다.
- 단순 문구·산업명만 바뀌고 `computeAnswer`가 같은 경우에는 같은 Q ID의 `contextVariant`로 저장한다. `computeAnswer`, 정답 단위 또는 난수 제약이 달라지면 반드시 별도 Q ID를 쓴다.
- `sourceRefId`는 URL·서지의 논리 식별자이고 `documentId`는 특정 시점의 실제 수집본이다. 원문이 바뀌면 기존 수집본을 덮어쓰지 않고 새 버전을 만든다.
- 선택적 로컬·원격 모델은 URL이나 페이지 번호를 직접 쓰지 않고 허용된 `chunkId`만 반환한다. 기본 renderer와 모델 변형 모두 화면의 링크·문서명·페이지를 로컬 출처 레지스트리에서 조립한다.

## 2. 구현 데이터 모델

아래 스키마는 TypeScript 예시다. 다른 언어로 구현하더라도 필드 의미와 불변조건은 유지한다.

```ts
type DomainId = "ACC" | "CF" | "INV" | "FI" | "DER" | "EQV" | "IBT";
type Difficulty = 1 | 2 | 3;
type AnswerKind =
  | "integer"
  | "integer_tuple"
  | "integer_mcq"
  | "concept_mcq"
  | "true_false"
  | "ordered_list";
type GenerationMode =
  | "direct"              // 독립 파라미터 생성 후 정확히 계산
  | "answer_first"        // 정수 정답을 먼저 뽑고 입력값 역산
  | "divisible_sampling"  // 분자가 분모로 나누어떨어지도록 생성
  | "perfect_power"       // 제곱근·기하평균 등이 정수가 되도록 생성
  | "validated_lookup"    // 사전 검증된 튜플 중 하나 선택
  | "rejection_sampling"; // 검증 통과 시에만 채택

interface MentalMathPolicy {
  calculatorAllowed: false;
  targetSeconds: 30 | 60 | 90;
  maxWeightedOperationScore: 2 | 4 | 6; // 난이도 1/2/3의 상한
  maxDisplayedNumericInputs: 4 | 6 | 8;
  maxSignificantDigitsPerInput: 3;       // 끝의 0은 유효숫자에서 제외
  exactIntermediateRequired: true;
  scoreOneDivisors: number[];            // 기본 [2, 4, 5, 8, 10, 20, 25, 50, 100]
  scoreTwoDivisors: number[];            // 기본 [3, 6, 7, 9]
  providedConstants?: string[];          // 할인계수, N(d), 환산계수 등
  mentalStrategyTemplate: string;        // 검수 가능한 최단 암산 경로
}

interface MentalMathAudit {
  weightedOperationScore: number;
  forbiddenOperationCount: number;
  displayedNumericInputs: number;
  maximumSignificantDigits: number;
  allIntermediatesExact: boolean;
  estimatedSeconds: number;
  strategy: string;
  passed: boolean;
}

interface SourceRef {
  id: string;
  label: string;
  url?: string;
  localPath?: string;
  kind:
    | "pdf" | "image" | "course" | "problem_set" | "exam" | "book"
    | "official_scope" | "regulation" | "filing" | "api" | "license"
    | "local_file" | "manual_note";
  accessNote?: string;
  // url 또는 localPath 중 적어도 하나가 있어야 한다.
}

interface ConceptCard {
  id: string;
  elementId: string;
  title: string;
  definition: string;
  intuition: string;
  interviewPoints: string[];
  commonTraps: string[];
  sourceRefIds: string[];
}

interface FormulaCard {
  id: string;
  elementId: string;
  latex: string;
  variables: Record<string, string>;
  assumptions: string[];
  unitRule: string;
  sourceRefIds: string[];
}

interface IntegerRange {
  min: number;
  max: number;
  step: number;
  exclude?: number[];
}

interface ParamSpec {
  name: string;
  symbol?: string;
  unit: string;
  range?: IntegerRange;
  allowedValues?: number[];
  derivedFrom?: string;
  constraint?: string;
}

interface ChoiceSpec {
  id: string;
  textTemplate: string;
  misconceptionTag?: string;
  explanation: string;
}

interface RenderedChoice {
  id: string;
  text: string;
  explanation: string;
}

interface QuestionTemplate {
  id: string;
  elementId: string;
  contentVersion: number;
  generatorVersion: number;
  difficulty: Difficulty;
  promptTemplate: string;
  answerKind: AnswerKind;
  answerUnit: string;
  generationMode: GenerationMode;
  mentalMathPolicy: MentalMathPolicy;
  contextVariants?: string[];
  params: ParamSpec[];
  choices?: ChoiceSpec[];       // 객관식은 검수된 선택지 또는 숫자 오답식 사용
  correctChoiceIds?: string[];  // 단일정답도 길이 1 배열; ordered_list는 정답 순서대로 저장
  shuffleChoices?: boolean;
  computeAnswer: string;       // 순수함수 또는 식별 가능한 함수명
  integerGuarantee: string;    // 반드시 기계검증 가능한 규칙
  explanationTemplate: string;
  conceptIds: string[];
  formulaIds: string[];
  sourceRefIds: string[];
  tags: string[];
}

interface GeneratedQuestion {
  instanceId: string;
  templateId: string;
  answerKind: AnswerKind;
  difficulty: Difficulty;
  contentVersion: number;
  generatorVersion: number;
  seed: number;
  contextVariant?: string;
  params: Record<string, number | number[]>;
  renderedPrompt: string;
  renderedChoices?: RenderedChoice[];
  correctChoiceIds?: string[];
  canonicalAnswer: number | number[] | string | string[] | boolean;
  answerUnit: string;
  explanationSteps: string[];
  mentalMathAudit: MentalMathAudit;
  generatedAt: string;
}

type AuthorityTier = 1 | 2 | 3;
// 1: 규제기관·회계기준·거래소·기업공시 등 1차 자료
// 2: 대학 OER·표준 교재·검증된 교육자료
// 3: 학회·인터뷰 가이드·블로그 등 면접 문맥 보조자료

type DeploymentMode = "personal_android_sideload" | "distributable";
type LocalIngestMode =
  | "fetch_once" | "refresh_if_changed" | "api_sync"
  | "local_file" | "manual_paste" | "disabled";
type ParserId =
  | "html_readability" | "pdf_text" | "pdf_ocr" | "image_ocr"
  | "json_api" | "xlsx" | "plain_text";

interface LocalSourceConfig {
  sourceRefId: string;
  canonicalUrl?: string;
  localPath?: string;
  authorityTier: AuthorityTier;
  ingestMode: LocalIngestMode;
  parserId: ParserId;
  enabled: boolean;
  crawlScope: "single_document" | "same_path" | "same_domain";
  maxDepth: number;                 // 기본 0; 사이트 전체 미러링 금지
  rateLimitRps: number;             // 기본 0.5
  refreshPolicy: "manual" | "if_changed" | "never";
  language: "ko" | "en";
  elementHints?: string[];
  termsUrl?: string;                // provenance용 선택 메타데이터
  redistributionNote?: string;      // personal_android_sideload에서는 런타임 gate가 아님
  notes?: string;
  // fetch/api 모드는 canonicalUrl, local_file 모드는 localPath가 필수다.
}

interface PcAuthoringRuntimeConfig {
  retrievalMode: "element_direct" | "fts5" | "hybrid_local";
  semanticSearchEnabled: boolean;   // 초기값 false
  localLlmEnabled: boolean;         // 초기값 false
  remoteApiEnabled: boolean;        // PC 제작 단계의 명시적 opt-in; 초기값 false
  maxRemoteCallsPerDay: number;     // 초기값 0
  maxRemoteTokensPerDay: number;    // 초기값 0
}

interface AndroidRuntimeConfig {
  deploymentMode: "personal_android_sideload";
  networkDuringQuiz: false;
  retrievalMode: "element_direct" | "fts5";
  semanticSearchEnabled: false;
  localLlmEnabled: false;
  remoteApiEnabled: false;
  maxRemoteCallsPerDay: 0;
  maxRemoteTokensPerDay: 0;
  calculatorFeatureEnabled: false;
  scratchpadFeatureEnabled: false;
}

interface EmbeddedContentManifest { // APK asset; APK 서명으로 함께 보호됨
  contentDbVersion: number;
  contentDbSchemaVersion: number;
  contentDbSha256: string;
  rowCountInvariants: Record<string, number>;
}

interface AndroidReleaseManifest {  // PC-side 외부 배포 manifest; APK/content DB에 넣지 않음
  distributionChannel: "private_onedrive_sideload";
  publicStoreRelease: false;
  targetUser: "self_only";
  internetPermission: false;
  oneDriveRuntimeSync: false;
  applicationId: string;
  versionCode: number;
  versionName: string;
  contentDbVersion: number;
  contentDbSha256: string;
  userDbSchemaVersion: number;
  signingCertificateSha256: string;
  releaseApkSha256: string;
}

interface CorpusDocument {
  id: string;
  sourceRefId: string;
  sourceVersion: number;
  canonicalUrl?: string;
  title: string;
  language: "ko" | "en";
  mimeType: "html" | "pdf" | "image" | "text" | "json" | "xlsx";
  retrievedAt: string;
  publishedAt?: string;
  asOfDate?: string;
  contentHash: string;
  localBlobPath: string;
  extractedTextPath?: string;
  extractorConfigHash: string;
  parserVersion: number;
  ocrVersion?: number;
  corpusVersion: number;
  status: "active" | "superseded" | "parse_failed" | "disabled";
}

interface EvidenceChunk {
  id: string;
  documentId: string;
  ordinal: number;
  elementIds: string[];
  headingPath: string[];
  page?: number;
  paragraph?: number;
  text: string;
  normalizedText: string;
  tokenCount: number;
  contentHash: string;
  authorityTier: AuthorityTier;
  ftsRowId?: number;
  embeddingRef?: string;
  embeddingVersion?: string;
  asOfDate?: string;
}

type ClaimKind =
  | "definition" | "relationship" | "formula_meaning" | "directionality"
  | "assumption" | "limitation" | "classification" | "interview_interpretation";

interface EvidenceAnchor {
  sourceRefId: string;
  documentId: string;
  chunkId: string;
  page?: number;
  section?: string;
  startOffset?: number;
  endOffset?: number;
  evidenceHash: string;
  supportRole: "supports" | "contradicts" | "qualifies";
}

interface ConceptClaim {
  id: string;
  elementId: string;
  statement: string;             // 출처 문장 복제가 아닌 검수된 독립 서술
  claimKind: ClaimKind;
  assumptions: string[];
  formulaIds: string[];
  relatedClaimIds: string[];
  contradictsClaimIds: string[];
  misconceptionTags: string[];
  evidence: EvidenceAnchor[];
  contentVersion: number;
  reviewStatus: "draft" | "approved" | "retired";
}

type ConceptIntent =
  | "definition" | "comparison" | "causal_direction" | "formula_interpretation"
  | "assumption_limit" | "error_spotting" | "scenario_application" | "oral_short_answer";

type ConceptAnswerKind =
  | "single_choice" | "multi_select" | "true_false" | "ordered_list" | "short_answer";

interface ElementConceptScope {
  elementId: string;
  scopeVersion: number;
  requiredClaimIds: string[];
  optionalClaimIds: string[];
  excludedClaimIds: string[];
  excludedTopics: string[];
  prerequisiteElementIds: string[];
  allowedRelatedElementIds: string[];
  allowedSourceRefIds: string[];
  allowedIntents: ConceptIntent[];
  allowedAnswerKinds: ConceptAnswerKind[];
  maximumAllowedTier: AuthorityTier; // tier <= 이 값만 허용; 1이 가장 강한 근거다.
  maxClaimsPerQuestion: number;
  maxInferenceHops: 0 | 1 | 2;
  generationPolicy: "deterministic_only" | "local_model_optional" | "remote_opt_in";
}

type MisconceptionMutation =
  | "reverse_direction" | "swap_numerator_denominator" | "swap_ev_equity"
  | "swap_stock_flow" | "swap_cash_accrual" | "swap_pre_post_tax"
  | "swap_price_yield" | "drop_assumption" | "wrong_sign" | "wrong_timing";

interface MisconceptionRule {
  id: string;
  elementId: string;
  tag: string;
  mutation: MisconceptionMutation;
  applicableClaimKinds: ClaimKind[];
  renderFunction: string;
  whyWrongTemplate: string;
  reviewStatus: "draft" | "approved" | "retired";
}

interface ConceptQuestionBlueprint {
  id: string;
  elementId: string;
  blueprintVersion: number;
  intent: ConceptIntent;
  answerKind: ConceptAnswerKind;
  difficulty: Difficulty;
  requiredClaimKinds: ClaimKind[];
  claimCount: IntegerRange;
  inferenceHops: 0 | 1 | 2;
  needsRelatedClaims: boolean;
  scenarioFamilies: string[];
  allowedMisconceptionRuleIds: string[];
  choiceCount?: 2 | 4 | 5;
  promptRules: string[];
  explanationRules: string[];
}

interface ConceptChoiceSnapshot {
  id: string;
  text: string;
  supportingClaimIds: string[];
  misconceptionRuleId?: string;
  explanation: string;
}

interface ConceptRubric {
  requiredClaimIds: string[];
  optionalClaimIds: string[];
  contradictoryClaimIds: string[];
  acceptedAliases: string[];
  requiredKeywords: string[];
  minimumRequiredMatches: number;
  modelAnswer: string;
}

interface RetrievalTrace {
  queryText: string;
  queryHash: string;
  retrievalMode: "element_direct" | "fts5" | "hybrid_local";
  elementFilter: string[];
  sourceFilter: string[];
  candidateChunkIds: string[];
  selectedChunkIds: string[];
  selectedClaimIds: string[];
  indexVersion: number;
  retrievalVersion: string;
  rerankerVersion?: string;
}

interface ConceptValidationReport {
  id: string;
  schemaValid: boolean;
  scopeValid: boolean;
  citationCoverage: number;
  answerGrounded: boolean;
  answerUnique: boolean;
  distractorsInvalidUnderAssumptions: boolean;
  promptAnswerLeak: boolean;
  unsupportedClaimIds: string[];
  invalidCitationIds: string[];
  maximumDuplicateSimilarity: number;
  decision: "approved" | "rejected" | "human_review";
  rejectionReasons: string[];
  validatorVersions: string[];
}

interface GeneratedConceptQuestion {
  instanceId: string;
  elementId: string;
  blueprintId: string;
  blueprintVersion: number;
  answerKind: ConceptAnswerKind;
  difficulty: Difficulty;
  contentVersion: number;
  corpusVersion: number;
  scopeVersion: number;
  rendererVersion: number;
  promptVersion?: number;           // 로컬/원격 모델을 쓴 경우에만 필요
  generatorVersion?: number;        // 로컬/원격 모델을 쓴 경우에만 필요
  rendererId: string;               // 기본 "deterministic-v1"
  modelGeneratorId?: string;
  modelRevision?: string;
  seed: number;
  generationMode:
    | "deterministic_assembly" | "local_llm_paraphrase" | "remote_opt_in";
  remoteApiUsed: boolean;
  remoteTokenUsage?: { input: number; output: number };
  renderedPrompt: string;
  choices?: ConceptChoiceSnapshot[];
  correctChoiceIds?: string[];
  rubric?: ConceptRubric;
  explanation: string;
  claimIds: string[];
  citations: EvidenceAnchor[];
  retrieval: RetrievalTrace;
  validationReportId: string;
  itemSignature: string;
  createdAt: string;
  approvedAt?: string;
}

type QuestionSnapshot = GeneratedQuestion | GeneratedConceptQuestion;

interface Attempt {
  id: string;
  userId: string;
  questionInstanceId: string;
  submittedAnswer: number | number[] | string | string[] | boolean;
  correct: boolean;
  elapsedMs: number;
  attemptedAt: string;
}

interface Bookmark {
  id: string;
  userId: string;
  snapshotKind: "calculation" | "concept";
  questionSnapshot: QuestionSnapshot;
  reason: "manual" | "incorrect" | "review_later";
  note?: string;
  resolved: boolean;
  createdAt: string;
  resolvedAt?: string;
}

interface ConceptAttemptEvaluation {
  attemptId: string;
  gradingMode: "exact" | "rubric_local" | "local_llm_judge" | "remote_opt_in" | "self_review";
  matchedClaimIds: string[];
  missingRequiredClaimIds: string[];
  contradictedClaimIds: string[];
  score: number;       // 0..1
  confidence: number;  // 0..1
  feedback: string;
  graderVersion: string;
}

interface LocalInferenceCache {
  cacheKey: string;
  modelId: string;
  modelHash: string;
  promptHash: string;
  inputHash: string;
  outputJson: string;
  validationState: "approved" | "rejected" | "pending";
  createdAt: string;
}
```

## 3. 정수답·암산 보장형 난수 생성 규칙

### 3.1 공통 불변조건

모든 계산 문제는 저장 전 **정수 정답**과 **계산기 없는 암산 가능성**을 함께 통과해야 한다.

```ts
function validateGeneratedQuestion(q: GeneratedQuestion): void {
  if (["integer_mcq", "concept_mcq"].includes(q.answerKind)) {
    const choiceIds = new Set((q.renderedChoices ?? []).map(c => c.id));
    if (choiceIds.size < 2 || !(q.correctChoiceIds ?? []).length) {
      throw new Error("INVALID_CHOICES");
    }
    if (!(q.correctChoiceIds ?? []).every(id => choiceIds.has(id))) {
      throw new Error("UNKNOWN_CORRECT_CHOICE");
    }
  }
  if (q.answerKind === "true_false" && typeof q.canonicalAnswer !== "boolean") {
    throw new Error("ANSWER_SHAPE_MISMATCH");
  }
  if (
    q.answerKind === "ordered_list" &&
    (!Array.isArray(q.canonicalAnswer) || !q.canonicalAnswer.every(v => typeof v === "string"))
  ) {
    throw new Error("ANSWER_SHAPE_MISMATCH");
  }
  if (!(["integer", "integer_tuple", "integer_mcq"] as AnswerKind[]).includes(q.answerKind)) {
    return;
  }

  if (q.answerKind === "integer_tuple" && !Array.isArray(q.canonicalAnswer)) {
    throw new Error("ANSWER_SHAPE_MISMATCH");
  }
  if (q.answerKind !== "integer_tuple" && Array.isArray(q.canonicalAnswer)) {
    throw new Error("ANSWER_SHAPE_MISMATCH");
  }

  const values = Array.isArray(q.canonicalAnswer)
    ? q.canonicalAnswer
    : [q.canonicalAnswer];

  if (!values.every(v => typeof v === "number" && Number.isSafeInteger(v))) {
    throw new Error("NON_INTEGER_ANSWER");
  }
  if (!values.every(v => typeof v === "number" && Number.isFinite(v))) {
    throw new Error("NON_FINITE_ANSWER");
  }
  if (!values.every(v => typeof v === "number" && Math.abs(v) <= 1_000_000_000)) {
    throw new Error("ANSWER_OUT_OF_RANGE");
  }

  const limits = {
    1: { score: 2, inputs: 4, seconds: 30 },
    2: { score: 4, inputs: 6, seconds: 60 },
    3: { score: 6, inputs: 8, seconds: 90 },
  }[q.difficulty];
  const template = loadQuestionTemplate(q.templateId);
  const m = auditMentalMath({
    calculationAst: loadCalculationAst(template.computeAnswer),
    params: q.params,
    renderedPrompt: q.renderedPrompt,
    difficulty: q.difficulty,
    policy: template.mentalMathPolicy,
  });
  if (stableJson(m) !== stableJson(q.mentalMathAudit)) {
    throw new Error("MENTAL_AUDIT_MISMATCH");
  }
  if (
    !m.passed || m.forbiddenOperationCount !== 0 || !m.allIntermediatesExact ||
    m.weightedOperationScore > limits.score ||
    m.displayedNumericInputs > limits.inputs ||
    m.maximumSignificantDigits > 3 ||
    m.estimatedSeconds > limits.seconds
  ) {
    throw new Error("NOT_MENTAL_MATH_SAFE");
  }
}
```

`mentalMathAudit`는 generator가 선언한 값을 신뢰하지 않는다. reference solver와 분리된 `auditMentalMath`가 실제 표시 지문, 파라미터, 정규화된 계산 AST에서 다시 계산하고 snapshot 값과 byte 단위로 비교한다. `estimatedSeconds`도 주관적으로 입력하지 않고 `4 + 8×weightedOperationScore + 4×max(0, displayedNumericInputs−2)`로 산출한다. `passed`는 아래 난이도 cap과 금지연산 여부에서 파생되는 값이다.

난이도별 cap과 divisor 집합은 전역 고정값이며 template이 바꿀 수 없다. `difficulty=1/2/3`은 각각 `targetSeconds=30/60/90`, `maxWeightedOperationScore=2/4/6`, `maxDisplayedNumericInputs=4/6/8`과 정확히 일치해야 한다. template별로 달라지는 필드는 `providedConstants`와 `mentalStrategyTemplate`뿐이며, `auditMentalMath`가 실제 template policy를 명시적으로 받아 독립 검증한다.

- 부동소수점 오차를 피하기 위해 금리와 비율은 각각 `bp` 또는 `basisPoints`, 금액은 최소 화폐단위의 정수로 저장한다.
- 내부 계산은 가능하면 정수 분수(`numerator`, `denominator`) 또는 `BigInt` 기반 유리수로 처리한다.
- 화면 표시에서 `%`를 쓰더라도 내부값 `500`은 `5.00% = 500bp`를 의미하도록 단위를 명시한다.
- 답을 반올림해야만 정수가 되는 문제는 Android 배포 문제은행에서 금지한다. `explicit_rounding` 템플릿은 authoring 실험용으로만 남기고 release build에서 제외한다.

#### 암산 복잡도 점수

generator는 실제로 표시될 숫자와 `computeAnswer`의 연산 AST에서 가장 짧은 검수된 암산 경로를 만들고 아래 점수를 합산한다.

| 연산 | 점수 | 허용 예시 |
|---|---:|---|
| 정수 덧셈·뺄셈, 부호 반전 | 1 | `800−300`, `−20+50` |
| 10의 거듭제곱 이동, 2·4·5·8·10·20·25·50·100으로 정확히 나누기 | 1 | `2,400÷20`, `500×10%` |
| 한 자리 수 곱셈, 3·6·7·9의 정확 나눗셈, round-number 간단 곱셈 | 2 | `24×6`, `84÷7`, `4,000×12` |
| 완전제곱·완전제곱근 또는 지문이 제공한 계수 1회 적용 | 2 | `15²`, `√144`, `현가계수 0.8×500` |
| 일반 로그·지수·정규분포 계산, 반복법, 비정수 중간값의 연쇄 계산 | 금지 | 지문에 필요한 값을 제공하거나 개념형으로 전환 |

- 끝의 0은 유효숫자에서 제외한다. 따라서 `120,000÷10`은 큰 수여도 쉬운 암산으로 본다.
- round-number 곱셈은 끝의 0을 제거한 두 인수 중 하나가 12 이하이고 다른 하나가 25 이하일 때만 2점으로 허용한다. `4,000×12`는 허용하지만 `7,300×17` 같은 일반 곱셈은 폐기한다.
- 모든 중간값은 정수 또는 지문에 명시된 단순 계수로 정확히 계산되어야 한다. 숨은 반올림, 보간, 계산기식 소수 연산은 허용하지 않는다.
- 정수 %는 기준금액을 100의 배수로, `12.5%`는 8의 배수로 역생성한다. 분수·비율은 먼저 약분하고 허용 divisor로 정확히 나누어지게 만든다.
- 각 template은 `mentalStrategyTemplate`을 가져야 하고, 생성 instance에는 실제 숫자를 넣은 `MentalMathAudit.strategy`를 저장한다.
- 표에 적힌 파라미터 범위는 후보 pool의 바깥 경계다. 범위 안 숫자라도 암산 audit를 통과하지 못하면 rejection sampling으로 폐기한다.

### 3.2 생성 패턴

#### A. 나누어떨어지는 표본추출

비율·단가·주당가치 문제는 분모 `d`와 목표 정수답 `a`를 먼저 뽑고 분자 `n = a × d`를 만든다.

```ts
const denominator = pick([2, 4, 5, 10, 20, 25, 50, 100], rng);
const answer = int(2, 200, rng);
const numerator = answer * denominator;
```

적용: EPS, PER 목표주가, P/B, EV/EBITDA, cap rate, LTV, DSCR, margin, 세율.

#### B. 목표수익률 역생성

IRR·YTM처럼 해를 수치적으로 찾아야 하는 문제는 정수 목표수익률 `r`을 먼저 뽑고 현금흐름 또는 가격을 역산한다.

```text
1기간 IRR: 초기투자 I를 생성 → 목표 IRR r% 생성 → 회수액 C = I × (100+r)/100
0쿠폰 YTM: 액면 F와 목표 YTM r% 생성 → 가격 P = F/(1+r)^T가 정수가 되는 검증 튜플만 채택
```

#### C. 완전제곱·완전거듭제곱

표준편차와 기하평균 문제는 목표 정수답을 먼저 선택한다.

```text
표준편차: 목표 σ를 선택하고 분산을 σ²로 생성
2기간 기하수익: 목표 성장배수 g를 선택하고 총 성장배수를 g²로 생성
```

#### D. 검증 룩업

BSM, 다기간 채권가격, 복수 현금흐름 IRR처럼 임의 난수로 정수답을 보장하기 어려운 유형은 빌드 시 생성·검증한 튜플만 배포한다.

```ts
interface ValidatedTuple {
  params: Record<string, number | number[]>;
  exactAnswer: number;
  proof: string;
}
```

- 룩업 파일은 원본 수식 재계산과 `MentalMathAudit`를 모두 통과해야 한다. 정수답이어도 암산 과정이 복잡하면 배포하지 않는다.
- BSM은 `N(d1)`, `N(d2)`, 할인계수를 지문에 제공하고 남은 계산이 암산 점수 상한 안에 드는 튜플만 사용한다. `d1`, `d2`, 누적정규분포를 직접 계산시키지 않는다.
- 다기간 IRR은 후보 IRR과 필요한 현가계수를 지문에 주고 NPV 확인이 암산 가능한 경우만 허용한다. 그렇지 않으면 IRR의 방향·해석을 묻는 개념형으로 전환한다.

#### E. 거부 표본추출

최대 100회 생성 후 아래 조건을 모두 통과한 인스턴스만 채택한다.

```text
분모 ≠ 0
금리 > 성장률(영구성장식)
확률 합 = 100%
상관계수 ∈ [-100%, 100%]
옵션·차익거래 가격이 경제적으로 유효
답이 안전한 정수이며 허용 답 범위 안에 있음
문제 지문에 필요한 정보가 모두 존재
```

100회 안에 실패하면 해당 템플릿은 `generation_error`를 기록하고 다른 템플릿으로 대체한다.

### 3.3 난수 재현성과 중복 방지

- PRNG는 고정 알고리즘(예: `xoshiro128**`)과 32비트 seed를 사용한다.
- 동일한 `templateId + generatorVersion + seed`는 항상 같은 파라미터와 문제를 생성해야 한다.
- 세션 안에서는 `SHA-256(templateId + canonicalizedParams)` 해시가 중복되면 재생성한다.
- 최근 100개 인스턴스와 같은 파라미터 조합은 기본 출제에서 제외한다.
- 북마크 문제는 snapshot을 우선 사용하므로 향후 템플릿 변경에도 원문과 해설이 보존된다.

### 3.4 완성 템플릿 예시

```json
{
  "id": "EQV-07-Q01",
  "elementId": "EQV-07",
  "contentVersion": 1,
  "generatorVersion": 1,
  "difficulty": 1,
  "promptTemplate": "내년 예상 EPS가 {{eps}}원이고 목표 PER이 {{per}}배라면 목표주가는 얼마인가?",
  "answerKind": "integer",
  "answerUnit": "원",
  "generationMode": "direct",
  "mentalMathPolicy": {
    "calculatorAllowed": false,
    "targetSeconds": 30,
    "maxWeightedOperationScore": 2,
    "maxDisplayedNumericInputs": 4,
    "maxSignificantDigitsPerInput": 3,
    "exactIntermediateRequired": true,
    "scoreOneDivisors": [2, 4, 5, 8, 10, 20, 25, 50, 100],
    "scoreTwoDivisors": [3, 6, 7, 9],
    "mentalStrategyTemplate": "EPS의 끝자리 0을 분리하고 유효숫자와 PER을 곱한 뒤 0을 복원"
  },
  "params": [
    { "name": "eps", "unit": "원/주", "range": { "min": 500, "max": 10000, "step": 100 } },
    { "name": "per", "unit": "배", "range": { "min": 5, "max": 25, "step": 1 } }
  ],
  "computeAnswer": "eps * per",
  "integerGuarantee": "eps와 per가 모두 정수이므로 곱도 정수",
  "explanationTemplate": "목표주가 = EPS × 목표 PER = {{eps}} × {{per}} = {{answer}}원",
  "conceptIds": ["EQV-07-C01"],
  "formulaIds": ["EQV-07-F01"],
  "sourceRefIds": ["KO-EQV-02", "EN-DAMO-VAL-01"],
  "tags": ["equity", "relative_valuation", "per"]
}
```

예를 들어 seed가 `420319`이고 `eps=4,000`, `per=12`가 생성되면 정답 snapshot은 `48,000원`이다. 이 instance의 audit는 `score=2`, `forbiddenOperationCount=0`, `inputs=2`, `maximumSignificantDigits=2`, `allIntermediatesExact=true`, `estimatedSeconds=20`, `strategy="4×12=48 후 0 세 개 복원"`, `passed=true`다. 반면 같은 후보 범위의 `7,300×17`은 정수답이어도 암산 audit에서 탈락한다. 해설은 대입·암산 경로·정확한 중간값·최종값을 생성 시점에 함께 저장한다.

## 4. 퀴즈·정답·오답·북마크 UX

### 4.1 퀴즈 모드

| 모드 | 동작 |
|---|---|
| 분야별 학습 | 선택 분야 안에서 요소별 균등 출제 |
| 약점 집중 | 정답률이 낮고 최근 오답이 많은 요소에 가중치 부여 |
| 면접 스프린트 | 계산기 없이 30·60·90초 암산형과 2~4분 설명형을 혼합 |
| 개념 랜덤 | 선택 요소의 로컬 claim·blueprint·오개념 규칙을 seed로 결정론적 조립; 선택 시에만 캐시된 로컬 모델 문장 변형 사용 |
| 구술 연습 | 30~60초 답변 후 필수 claim rubric·모범답안과 비교; 선택적으로 자동채점 |
| 통합 케이스 | 여러 요소가 연결된 고정 데이터셋 기반 문제 |
| 북마크 복습 | 저장된 동일 snapshot, 계산형 새 숫자, 개념형 같은 scope의 새 문제 중 선택 |

모든 계산형 화면에는 `암산 · 계산기 사용 안 함 · 권장시간 NN초` badge를 표시한다. 앱 내부 계산기·스프레드시트·수식 계산기·메모장·scratchpad는 제공하지 않으며, 숫자 입력 keypad와 단위만 보여준다. 권장시간은 난이도 1/2/3에 각각 30/60/90초이고 시간 초과가 오답을 뜻하지는 않지만 `elapsedMs`로 약점 분석에 반영한다. 제출 전에는 풀이 힌트를 노출하지 않고, 제출 후 해설의 첫 계산 단계로 가장 짧은 `mentalStrategy`를 보여준다.

### 4.2 출제 가중치

```text
elementWeight = 1
  + incorrectRate × 2
  + daysSinceLastSeen / 30
  + bookmarkedUnresolved × 1.5

templateWeight = elementWeight × difficultyFit × noveltyFactor
conceptBlueprintWeight = elementWeight × difficultyFit × claimNovelty × intentCoverage
```

- 한 세션에서 특정 요소가 전체의 25%를 넘지 않게 한다.
- 첫 학습자는 난이도 1을 60%, 2를 35%, 3을 5%로 시작한다.
- 최근 20회 정답률이 80% 이상이면 다음 난이도의 비중을 높인다.

### 4.3 개념 퀴즈 — 로컬 지식 DB 기반 결정론적 조립

개념문제의 기본 경로는 **모델 없는 retrieval-constrained assembly**다. 선택된 요소의 `ElementConceptScope`에서 claim ID를 직접 조회하고, `ConceptQuestionBlueprint`, 승인 문장 frame, `MisconceptionRule`, scenario family를 seed로 고른 뒤 로컬에서 문항을 조립한다. 여기서 retrieval은 SQLite 조회이므로 토큰을 쓰지 않는다. FTS5/BM25는 인접 claim 탐색이나 사용자의 corpus 검색에만 필요하며, 벡터 검색도 필수가 아니다.

문장 다양성은 blueprint마다 검수된 prompt frame 3~8개, 동의 표현 집합, 선택지 순서, 사례 family, claim·오개념 조합으로 만든다. 선택적 로컬 LLM은 PC 제작 단계에서 이미 완성된 구조화 문항의 말투만 바꿀 수 있고 정답·claim·수식·인용을 바꾸지 못한다. 원격 API도 PC authoring의 명시적 opt-in일 뿐이며, Android release APK에는 모델 호출 코드·API key·`INTERNET` 권한을 넣지 않는다.

각 135개 학습요소는 독립된 scope manifest를 가지며, 요소당 최소 다음 claim을 승인한다.

| claim 묶음 | 일반 요소 최소 | `EQV`·`IBT` 최소 | 예시 |
|---|---:|---:|---|
| 정의·핵심 관계 | 1 | 2 | 듀레이션이 무엇을 측정하는가 |
| 수식의 경제적 의미 | 1 | 2 | WACC 각 항의 청구권과 세후 처리 |
| 방향성·비교 | 2 | 2 | 금리 상승 시 채권가격 하락 |
| 가정·한계 | 2 | 2 | 영구성장률은 할인율보다 작아야 함 |
| 흔한 함정·오개념 | 2 | 2 | EV 배수와 equity 배수 혼동 |
| 실무·면접 해석 | 1 | 2 | 숫자를 30초 답변으로 연결 |
| **합계** | **9개 이상** | **12개 이상** | 출시 전 사람이 승인 |

전체 최소 승인 claim 수는 `53개 일반 요소×9 + 82개 EQV·IBT 요소×12 = 1,461개`다. 각 요소의 `requiredClaimIds`, `optionalClaimIds`, `excludedTopics`, 허용 인접요소와 추론단계를 고정한다.

모든 요소는 다음 blueprint를 기본으로 가진다.

```text
CQ01: 정의·핵심 관계 식별
CQ02: 변수 변화와 결과 방향
CQ03: 인접 개념 비교
CQ04: 모형의 가정·한계
CQ05: 잘못된 면접 답변 또는 풀이 오류 찾기
CQ06: 짧은 사례에 개념 적용
CQ07(선택): 30~60초 구술형 답변
```

출시 권장 최소치는 요소당 **검증된 서로 다른 결정론적 signature 18개**, 총 `135×18=2,430개`를 생성할 수 있는 상태다. 이를 미리 API로 생성할 필요는 없다. 최초 노출 때 로컬 조립해 snapshot으로 materialize하고 캐시한다. 난이도 구성은 쉬움 6·보통 8·어려움 4로 시작하며, 허용 claim, 판정근거, 오개념 규칙, 출처 chunk, 난이도·추론단계와 제외범위는 고정한다.

#### 생성·검증 파이프라인

```text
elementId·difficulty·seed 선택
→ scope와 blueprint 로드
→ required claim ID를 SQLite에서 직접 로드
→ 선택적 관련 claim만 FTS5 또는 local hybrid search
→ 호환되는 오개념 규칙·문장 frame·scenario를 seed로 선택
→ 구조화 문항을 deterministic renderer로 조립
→ schema·scope·인용·정답유일성·오답유효성·중복 검사
→ 통과한 결과를 immutable snapshot으로 로컬 저장
→ 실패 시 다른 검수 frame을 선택하고, 끝내 실패하면 고정 fallback 문항 제공
```

```ts
function buildConceptQuestion(req: {
  elementId: string;
  difficulty: Difficulty;
  seed: number;
}): GeneratedConceptQuestion {
  const scope = loadScope(req.elementId);
  const blueprint = seededSelect(loadBlueprints(scope, req.difficulty), req.seed);
  const evidence = localRetrieve({
    mode: blueprint.needsRelatedClaims ? runtime.retrievalMode : "element_direct",
    requiredClaimIds: scope.requiredClaimIds,
    optionalClaimIds: scope.optionalClaimIds,
    allowedElementIds: [scope.elementId, ...scope.allowedRelatedElementIds],
    limit: 6,
  });

  if (!hasRequiredCoverage(evidence, blueprint)) return loadApprovedFallback(req);
  const candidate = deterministicAssemble({
    blueprint,
    evidence,
    frame: seededSelect(loadApprovedFrames(blueprint.id), req.seed + 1),
    misconceptionRules: loadCompatibleMisconceptions(blueprint, evidence),
    scenario: seededSelect(loadScenarioFrames(blueprint.scenarioFamilies), req.seed + 2),
    seed: req.seed,
  });

  const report = validateConceptCandidate(candidate, blueprint, scope, evidence);
  if (report.decision !== "approved") return loadApprovedFallback(req);
  return persistImmutableSnapshot(candidate, report, req.seed);
}
```

PC authoring의 선택적 로컬 LLM은 `deterministicAssemble` 뒤에만 붙는다. 구조화 문항을 한국어로 자연스럽게 바꾸되 숫자·부호·수식·`claimId`·정답·선택지 의미를 동결하고, 결과를 `LocalInferenceCache`에 저장한다. 검증 실패·모델 미설치·시간 초과 시 결정론적 문장을 승인 후보로 유지한다. 모델은 URL·문헌명·페이지를 만들지 않으며, build pipeline이 로컬 `chunkId`에서 링크와 locator를 붙인다. Android에는 승인된 결과만 들어간다.

#### 통제된 오답 생성

오답은 자유 작문하지 않고 승인된 `MisconceptionRule` 하나를 claim에 적용한다. 기본 변형은 방향 반전, 분자·분모 교환, EV·equity 교환, stock·flow 혼동, 현금·발생주의 혼동, 세전·세후 혼동, 가격·수익률 반전, 부호 오류, 시점 한 기간 이동, 필수 가정 삭제다.

- 같은 가정에서 정답은 정확히 하나여야 한다.
- 모든 오답은 `misconceptionRuleId`와 왜 틀렸는지를 가진다.
- 예외상황에서 맞을 수 있는 오답은 지문이 그 예외를 배제하지 않으면 폐기한다.
- 정답만 유난히 길거나 “항상·절대” 같은 힌트를 주는 표현을 금지한다.

#### snapshot·다양성·난이도

결정론적 renderer는 같은 corpus·scope·renderer version·seed에서 항상 같은 문항을 만든다. PC에서 만든 로컬 LLM 변형은 같은 seed라도 모델 revision에 따라 달라질 수 있으므로 결과 전체를 snapshot으로 저장하고, Android에서는 저장본만 재생한다.

```text
cacheKey = SHA256(corpusVersion + scopeVersion + blueprintId + blueprintVersion
                  + sortedClaimIds + seed + rendererVersion + generatorConfigHash)

itemSignature = SHA256(elementId + sortedClaimIds + intent + difficulty
                        + sortedMisconceptionTags + scenarioFamily)
```

- 같은 문제 다시 풀기: snapshot 그대로 재생한다.
- 같은 요소 새 문제: 아직 보지 않은 결정론적 signature를 먼저 조립하고 저장한다.
- 최근 20문항의 claim 조합에는 novelty penalty를 주며 같은 signature를 반복하지 않는다.
- 난이도 1은 claim 1개·추론 0~1단계, 난이도 2는 claim 2개 또는 조건반전, 난이도 3은 claim 2~4개·추론 최대 2단계로 정의한다.
- Android 구술형은 alias·keyword와 rubric의 필수 claim 누락·모순을 로컬에서 표시하고 자기검토를 제공한다. local LLM·원격 judge는 APK에 없으며, PC authoring에서 rubric을 시험할 때만 선택적으로 사용할 수 있다.

#### 요소별 scope manifest 작성 규칙

5장의 **각 ID 하나가 곧 하나의 로컬 생성 scope**다. 상세 명세의 제목·개념·수식·가정·해설 필수사항·주 참고를 빌드 단계에서 claim 후보로 변환하고, 검수한 뒤 `ElementConceptScope`에 넣는다. ID만 있고 manifest가 없거나, manifest의 `requiredClaimIds`가 승인 상태가 아니면 CI를 실패시킨다.

| 분야 | 모든 요소에서 허용할 핵심 관점 | 분야 공통 오개념 | 기본 제외범위 |
|---|---|---|---|
| `ACC` | 인식·측정·분류, 차변/대변, 세 재무제표 연결, 비율 해석 | 현금=수익, 비용=현금유출, stock=flow | CPA 2차 장문 처리·기준서 예외 암기 |
| `CF` | 시간가치, 증분 현금흐름, 자본비용, 기업/지분 청구권 | 장부가=시장가, sunk cost 포함, 세전/세후 혼동 | 확률미분·복잡한 실물옵션 |
| `INV` | 기대수익·위험·분산효과·요인·성과측정 | 산술=기하, 변동성=손실, alpha=총수익 | 고급 계량추정·고차 모멘트 |
| `FI` | 가격–수익률, 기간구조, duration/convexity, 신용·헤지 | coupon=YTM, price와 yield 같은 방향 | 복잡한 금리모형 calibration |
| `DER` | payoff/profit, 무차익가격, long/short, Greeks·헤지 | payoff=profit, 부호 반전, 만기와 현재가치 혼동 | exotic 구조·확률변동성 |
| `EQV` | 운영 driver→재무제표→이익의 질→ROIC/재투자→가치→투자논리 | 성장=가치, 낮은 배수=저평가, 비표준 KPI 직접비교 | 근거 없는 종목추천·실시간 가격예측 |
| `IBT` | 시장 transmission, 거래 bridge, 희석·시너지, 부동산·대체투자 | EV/equity, primary/secondary, NOI/현금흐름 혼동 | 특정 거래의 미공개정보·법률자문 |

예시 manifest:

```yaml
elementId: EQV-41
title: ROIC
requiredClaims:
  - ROIC = NOPAT / AverageInvestedCapital
  - 분자와 분모에는 같은 회계조정을 적용한다
directionalRelations:
  - incremental ROIC가 자본비용보다 높을수록 재투자는 일반적으로 가치를 만든다
caveats:
  - 인수, 손상, FX, 초과현금은 invested capital 비교를 왜곡할 수 있다
comparisons:
  - ROIC vs WACC
  - existing ROIC vs incremental ROIC
allowedIntents:
  - definition
  - formula_interpretation
  - causal_direction
  - scenario_application
  - error_spotting
excludedTopics:
  - 근거 없이 특정 상장사의 미래 ROIC 단정
sourceRefs:
  - ER-DAMO-TOOLKIT
```

개념형 해설도 `정답 이유 → 오답별 틀린 이유 → 연결 수식 → 근거 링크·페이지 → 계산형 연습 바로가기`를 포함한다. 개념 퀴즈를 틀리면 같은 요소의 난이도 1 계산문제 또는 개념카드를 추천한다.

### 4.4 정답 해설의 필수 구조

계산형 정답은 반드시 다음 순서로 표시한다.

1. **관련 개념**: 무엇을 계산하는지 한 문장
2. **수식**: 기호식
3. **숫자 대입**: 지문의 숫자를 대입한 식
4. **암산 경로**: 30~90초 안에 계산할 수 있는 묶기·약분·0 처리 순서
5. **계산 단계**: 정확한 중간값을 포함한 1~4단계
6. **정답**: 정수와 단위
7. **해석**: 면접에서 말할 경제적 의미
8. **자주 하는 실수**: 부호·단위·시점 등
9. **참고자료**: 연결된 출처 링크

예시:

```md
관련 개념: 목표 PER은 예상 EPS 1원당 시장이 지불하는 가격이다.

수식: 목표주가 = 예상 EPS × 목표 PER

대입: 4,000원 × 12배

암산 경로: `4×12=48`을 먼저 계산하고 `4,000`의 0 세 개를 붙인다.

계산: 48,000원

정답: **48,000원**

해석: 예상 EPS가 유지되고 시장이 12배를 부여하면 정당화되는 가격이다.

자주 하는 실수: 과거 EPS와 예상 EPS를 혼용하지 않는다.
```

### 4.5 오답과 북마크

- 오답 발생 시 `Attempt.correct = false`를 저장하고 `오답노트에 추가` 버튼을 즉시 노출한다.
- 사용자 설정으로 모든 오답을 자동 북마크할 수 있다.
- 북마크에는 다음 두 복습 버튼을 제공한다.
  - `같은 문제 다시 풀기`: 저장된 snapshot 재생
  - 계산형 `같은 유형 새 숫자로 풀기`: 같은 template의 새 seed 생성
  - 개념형 `같은 요소 새 문제`: 미노출 deterministic signature → PC에서 미리 검수·캐시해 release DB에 넣은 문장 변형 순서로 새 snapshot 제공; Android는 모델·원격 API를 호출하지 않음
- 사용자가 두 번 연속 정답을 맞히면 `resolved` 제안을 표시하지만 자동 삭제하지 않는다.
- 오답률 통계는 문제 인스턴스가 아니라 학습요소 ID와 템플릿 ID에 각각 집계한다.

## 5. 분야별 번호 체계와 콘텐츠 사양

> 아래 모든 계산형 템플릿은 **계산기 없이 암산**하는 문제다. 정답은 별도 언급이 없으면 정확한 정수이며, `%` 답은 정수 퍼센트포인트, 금리 미세단위는 정수 bp, 금액은 지문에 표시된 단위의 정수로 입력한다. 표의 파라미터 범위는 후보 pool이고, 실제 문항은 `MentalMathAudit`까지 통과한 숫자 조합만 사용한다.

### 5.1 학습요소·계산문제 준비범위 — 최종 재정리

기존 표의 학회 고유 행은 앱에서 통용되는 일반 분야명으로 변경했다. 아래 ID는 이어지는 상세 명세의 ID와 일치한다.

| 분야 | ID·요소 | 개수 |
|---|---|---:|
| **회계·재무제표** | `ACC-01` 회계등식·차변/대변 · `ACC-02` 발생주의·결산조정 · `ACC-03` 매출채권·대손 · `ACC-04` 재고·매출원가 · `ACC-05` 유형자산·감가상각·처분 · `ACC-06` 사채 회계 · `ACC-07` 기본 EPS · `ACC-08` 운전자본 · `ACC-09` 현금흐름표 · `ACC-10` 세 재무제표 연결 · `ACC-11` 수익성·효율성·레버리지 비율 · `ACC-12` ROA·ROE·DuPont | 12 |
| **기업재무** | `CF-01` 일시금 PV/FV · `CF-02` 연금·영구연금 · `CF-03` NPV · `CF-04` IRR · `CF-05` DDM · `CF-06` CAPM·베타 · `CF-07` WACC · `CF-08` 레버리지·자본구조 · `CF-09` 증분 프로젝트 현금흐름 · `CF-10` FCFF·FCFE · `CF-11` 계속가치 · `CF-12` EV·지분가치·주당가치 | 12 |
| **투자·포트폴리오** | `INV-01` 보유기간·로그·산술·기하수익률 · `INV-02` 기대수익·분산·표준편차 · `INV-03` 공분산·상관계수 · `INV-04` 2자산 포트폴리오 · `INV-05` 베타 · `INV-06` CAPM·알파 · `INV-07` APT · `INV-08` Sharpe·Treynor·Jensen · `INV-09` Tracking Error·Information Ratio | 9 |
| **채권·금리** | `FI-01` 채권가격·YTM · `FI-02` 현물·선도금리 · `FI-03` Macaulay·Modified Duration · `FI-04` DV01·Convexity · `FI-05` 면역전략 · `FI-06` 금리헤지 계약수 · `FI-07` Repo·Haircut · `FI-08` 선물 Basis·CTD · `FI-09` 금리스왑 · `FI-10` 신용스프레드·기대손실 | 10 |
| **파생상품** | `DER-01` 선도·선물 이론가격 · `DER-02` 무차익거래 · `DER-03` 최소분산 헤지비율·계약수 · `DER-04` 옵션 payoff · `DER-05` 옵션 profit·전략 · `DER-06` put-call parity · `DER-07` 이항모형 · `DER-08` BSM · `DER-09` Greeks·delta hedge · `DER-10` swap cash flow·netting | 10 |
| **주식 리서치·기업가치평가** | `EQV-01~19` 기초 실적추정·재무제표·배수·DCF·목표가 · `EQV-20~28` 매출 드라이버·단위경제성 · `EQV-29~40` 이익의 질·회계조정 · `EQV-41~47` ROIC·성장·재투자 · `EQV-48~54` 실무 가치평가 · `EQV-55~60` 산업 모듈 · `EQV-61~64` 투자논리·촉매·위험·자본배분 | 64 |
| **IB·시장·대체투자 실무** | `IBT-01` 명목·실질금리 · `IBT-02` FX 환산손익 · `IBT-03` 신용스프레드 가격민감도 · `IBT-04` 통화정책·이자수익 · `IBT-05` EV–Equity bridge · `IBT-06` M&A 시너지 · `IBT-07` EPS accretion/dilution · `IBT-08` 주식교환비율 · `IBT-09` IPO primary/secondary · `IBT-10` IPO 희석 · `IBT-11` IPO 배수 · `IBT-12` NOI · `IBT-13` cap rate · `IBT-14` LTV · `IBT-15` DSCR · `IBT-16` levered IRR · `IBT-17` 리서치 촉매 · `IBT-18` 리서치 위험·기대하방 | 18 |
| **합계** | 고유 학습요소 135개. 각 요소별 개념·수식·출제범위와, 계산 가능한 요소의 일반화 문제·파라미터·정수답 규칙을 아래에 정의한다. | **135** |

## A. 회계 계산 문제 (`ACC`)

### ACC-01. 회계등식과 차변·대변

- **개념·수식:** `자산(A)=부채(L)+자본(E)`. 모든 거래는 차변 합계와 대변 합계를 같게 유지한다.
- **유형 A — 거래 후 잔액:** “기초 자산 `A0`, 부채 `L0`인 회사가 유상증자 `S`, 차입 `B`를 하고 현금으로 설비 `P`를 샀다. 기말 자본은?”
  - 파라미터: `A0=randInt(500,5000,100)`, `L0=randInt(100,A0-100,100)`, `S=randInt(50,500,10)`, `B=randInt(50,500,10)`, `P=randInt(50,500,10)`.
  - 정답: `E1=A0-L0+S`. 설비 매입은 자산 내 현금→설비 대체라 총자본에 영향이 없다.
  - 해설식: `E0=A0-L0`, `E1=E0+S`.
- **유형 B — 분개 누락금액:** “설비 `P`를 취득하며 현금 `C`를 지급하고 나머지는 장기미지급금으로 기록했다. 대변의 장기미지급금은?”
  - 파라미터: `P=randInt(100,5000,100)`, 현금비율 `h∈{20,25,40,50}`, `C=P×h/100`.
  - 정수 보장: `P`를 100의 배수로 뽑는다.
  - 정답/해설식: `장기미지급금=P-C`; `차변 설비 P = 대변 현금 C + 대변 장기미지급금`.
- **참고자료:** [OpenStax 회계순환·거래기록](https://openstax.org/books/principles-financial-accounting/pages/3-3-define-and-describe-the-initial-steps-in-the-accounting-cycle), [OpenStax 재무제표 연결](https://openstax.org/books/principles-financial-accounting/pages/2-1-describe-the-income-statement-statement-of-owners-equity-balance-sheet-and-statement-of-cash-flows-and-how-they-interrelate), [MIT 15.501 과제·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/assignments/)

### ACC-02. 발생주의·현금주의와 결산조정

- **개념·수식:** 현금 수취/지급 시점이 아니라 수익을 획득하고 비용이 발생한 기간에 인식한다. 단순 매출채권 모형에서 `발생주의 매출=현금회수+기말 매출채권-기초 매출채권`.
- **유형 A — 발생주의 매출:** “현금회수액 `C`, 기초·기말 매출채권 `AR0`,`AR1`이 주어질 때 당기 매출은?” 단, 대손·선수금은 없다.
  - 파라미터: `C=randInt(500,5000,10)`, `AR0,AR1=randInt(0,1000,10)`; `C+AR1-AR0>0`만 허용.
  - 정답/해설식: `Revenue=C+AR1-AR0`.
- **유형 B — 발생주의 비용:** “현금지급 `C`, 기초·기말 미지급비용 `AP0`,`AP1`, 기초·기말 선급비용 `PP0`,`PP1`일 때 당기 비용은?”
  - 파라미터: `C=randInt(300,4000,10)`, `AP0,AP1,PP0,PP1=randInt(0,500,10)`; 결과가 양수일 때만 출제.
  - 정답/해설식: `Expense=C+(AP1-AP0)+(PP0-PP1)`.
- **참고자료:** [OpenStax 결산조정 개념](https://openstax.org/books/principles-financial-accounting/pages/4-1-explain-the-concepts-and-guidelines-affecting-adjusting-entries), [OpenStax 결산조정 예제](https://openstax.org/books/principles-financial-accounting/pages/4-2-discuss-the-adjustment-process-and-illustrate-common-types-of-adjusting-entries), [OpenStax 조정분개](https://openstax.org/books/principles-financial-accounting/pages/4-3-record-and-post-the-common-types-of-adjusting-entries), [MIT 15.501 시험·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/exams/)

### ACC-03. 매출채권·대손충당금

- **개념·수식:** `기말 충당금=기초 충당금+대손상각비-대손확정`. 순매출채권은 `총매출채권-대손충당금`이다.
- **유형 A — 대손상각비:** “기초 충당금 `AL0`, 당기 대손확정 `W`, 목표 기말 충당금 `AL1`일 때 대손상각비는?”
  - 파라미터: `AL0=randInt(10,200,5)`, `W=randInt(0,150,5)`, `AL1=randInt(10,250,5)`; `AL1-AL0+W≥0` 조건.
  - 정답/해설식: `BDE=AL1-AL0+W`.
- **유형 B — 순매출채권:** “총매출채권 `GAR`, 예상손실률 `p%`일 때 순매출채권은?”
  - 파라미터: `GAR=randInt(100,5000,100)`, `p=randInt(1,10,1)`.
  - 정수 보장: `GAR`가 100의 배수이므로 `Allowance=GAR×p/100`이 정수.
  - 정답/해설식: `NetAR=GAR-GAR×p/100`.
- **참고자료:** [OpenStax 매출채권·충당금 핵심용어](https://openstax.org/books/principles-financial-accounting/pages/9-key-terms), [MIT 15.501 과제·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/assignments/), [MIT Problem Set 4 공식해설 PDF](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/resources/ps4_sol/)

### ACC-04. 재고자산·매출원가

- **개념·수식:** `판매가능재고=기초재고+순매입`, `매출원가=판매가능재고-기말재고`. 원가흐름 가정에 따라 FIFO·가중평균의 매출원가가 달라진다.
- **유형 A — 재고등식:** “기초재고 `BI`, 당기매입 `PUR`, 기말재고 `EI`일 때 매출원가는?”
  - 파라미터: `BI=randInt(100,2000,10)`, `PUR=randInt(500,5000,10)`, `EI=randInt(50,BI+PUR-50,10)`.
  - 정답/해설식: `COGS=BI+PUR-EI`.
- **유형 B — FIFO 또는 가중평균:** “기초 `q`개(개당 `c1`), 추가매입 `q`개(개당 `c2`) 중 `s`개를 판매했다. 지정된 방법의 매출원가는?”
  - 파라미터: `q=randInt(20,100,10)`, `c1=randInt(2,20,2)`, `c2=randInt(c1+2,c1+12,2)`, `s=randInt(q+10,2q,10)`.
  - FIFO 정답: `q×c1+(s-q)×c2`.
  - 가중평균 정답: `s×(c1+c2)/2`; `c1,c2`를 둘 다 짝수로 뽑아 단위원가와 답을 정수화한다.
- **참고자료:** [OpenStax 재고평가방법](https://openstax.org/books/principles-financial-accounting/pages/10-1-describe-and-demonstrate-the-basic-inventory-valuation-methods-and-their-cost-flow-assumptions), [OpenStax 재고 챕터 요약](https://openstax.org/books/principles-financial-accounting/pages/10-summary), [MIT 15.501 과제·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/assignments/)

### ACC-05. 유형자산·감가상각·처분손익

- **개념·수식:** 정액법 `연간 감가상각비=(취득원가-잔존가치)/내용연수`, `장부가=취득원가-누적감가상각`, `처분손익=매각대금-처분시 장부가`.
- **유형 A — 정액법 장부가:** “취득원가 `C`, 잔존가치 `R`, 내용연수 `N`, 사용기간 `t`가 주어질 때 기말 장부가는?”
  - answer-first 파라미터: 연간상각액 `D=randInt(10,500,10)`, `R=randInt(0,500,10)`, `N=randInt(3,10,1)`, `t=randInt(1,N,1)`, `C=R+D×N`.
  - 정답/해설식: `BV=C-D×t`.
- **유형 B — 처분손익:** 위 자산을 `t`년 말 `SP`에 팔았을 때 처분손익을 부호 있는 정수로 답한다(이익 `+`, 손실 `-`).
  - 파라미터: 위 `C,R,D,N,t`; 목표손익 `G=randInt(-200,200,10)`, `G≠0`; `SP=(C-D×t)+G`, `SP≥0` 조건.
  - 정답/해설식: `GainLoss=SP-(C-D×t)=G`.
- **참고자료:** [OpenStax 감가상각 방법과 예제](https://openstax.org/books/principles-financial-accounting/pages/11-3-explain-and-apply-depreciation-methods-to-allocate-capitalized-costs), [MIT 15.501 과제·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/assignments/), [MIT 15.501 시험·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/exams/)

### ACC-06. 사채 회계·유효이자율법

- **개념·수식:** `현금이자=액면금액×표면이율`, `이자비용=기초 장부금액×유효이율`, `기말 장부금액=기초 장부금액+이자비용-현금이자`.
- **유형 A — 이자비용:** “액면 `F`, 표면이율 `rc%`, 기초 장부금액 `CA0`, 유효이율 `re%`인 사채의 당기 이자비용은?”
  - 파라미터: `F=randInt(1000,10000,100)`, `CA0=randInt(500,F-100,100)`인 할인발행, `rc=randInt(2,6,1)`, `re=randInt(rc+1,12,1)`.
  - 정수 보장: `CA0`가 100의 배수.
  - 정답/해설식: `InterestExpense=CA0×re/100`.
- **유형 B — 기말 장부금액:** 같은 조건에서 첫 이자지급 직후 장부금액은?
  - 정답/해설식: `CashCoupon=F×rc/100`; `CA1=CA0+CA0×re/100-F×rc/100`.
  - 프리미엄 변형: `CA0>F`, `re<rc`로 바꾸되 같은 식을 사용한다.
- **참고자료:** [OpenStax 장기부채·사채 가격](https://openstax.org/books/principles-financial-accounting/pages/13-1-explain-the-pricing-of-long-term-liabilities), [OpenStax 사채 분개](https://openstax.org/books/principles-financial-accounting/pages/13-3-prepare-journal-entries-to-reflect-the-life-cycle-of-bonds), [MIT 15.501 시험·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/exams/)

### ACC-07. 기본주당이익(EPS)·가중평균주식수

- **개념·수식:** `기본 EPS=(당기순이익-우선주배당)/가중평균 유통보통주식수`.
- **유형 A — 기본 EPS:** “순이익 `NI`, 우선주배당 `PD`, 가중평균 주식수 `S`일 때 EPS는?”
  - answer-first 파라미터: 목표 `eps=randInt(100,5000,10)`원, `S=randInt(10,500,10)`백만 주, `PD=randInt(0,50000,100)`백만원, `NI=PD+eps×S`백만원.
  - 정답/해설식: `EPS=(NI-PD)/S=eps`원.
- **유형 B — 중도 신주발행:** “연초 `S0`백만 주, 7월 1일 `I`백만 주 발행, 순이익 `NI`, 우선주배당 `PD`일 때 EPS는?”
  - 파라미터: `S0=randInt(10,500,10)`, `I=randInt(2,200,2)`, 목표 `eps=randInt(100,5000,10)`, `WA=S0+I/2`, `PD=randInt(0,50000,100)`, `NI=PD+eps×WA`.
  - 정수 보장: `I`를 짝수로 뽑고 `NI`를 역산한다.
  - 정답/해설식: `WA=S0+I×6/12`; `EPS=(NI-PD)/WA`.
- **참고자료:** [OpenStax EPS와 가중평균주식수](https://openstax.org/books/principles-financial-accounting/pages/14-5-discuss-the-applicability-of-earnings-per-share-as-a-method-to-measure-performance), [OpenStax 시장가치비율](https://openstax.org/books/principles-finance/pages/6-5-market-value-ratios), [MIT 15.501 시험·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/exams/)

### ACC-08. 운전자본과 순운전자본 증감

- **개념·수식:** `NWC=유동자산-유동부채`. 현금·차입금을 제외한 영업순운전자본을 별도로 사용할 때는 문항에 포함 계정을 명시한다. `현금흐름 영향=-ΔNWC`.
- **유형 A — NWC:** “현금 `Cash`, 매출채권 `AR`, 재고 `Inv`, 매입채무 `AP`, 기타 유동부채 `OCL`일 때 NWC는?”
  - 파라미터: `Cash,AR,Inv=randInt(50,1000,10)`, `AP,OCL=randInt(20,800,10)`; 결과 양수 조건.
  - 정답/해설식: `NWC=Cash+AR+Inv-AP-OCL`.
- **유형 B — FCF에 미치는 영향:** “기초 `CA0,CL0`, 기말 `CA1,CL1`일 때 NWC 변화가 당기 현금흐름에 미친 영향을 부호 있는 정수로 답하라.”
  - 파라미터: 각 값 `randInt(100,3000,10)`, 각 시점 `CA>CL`; `ΔNWC≠0`.
  - 정답/해설식: `CashImpact=-[(CA1-CL1)-(CA0-CL0)]`.
- **참고자료:** [OpenStax 유동부채와 현금흐름 효과](https://openstax.org/books/principles-financial-accounting/pages/12-1-identify-and-describe-current-liabilities), [Damodaran 투자수익 문제·해설](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/invret.htm), [MIT 15.501 과제·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/assignments/)

### ACC-09. 현금흐름표(CFO·CFI·CFF)

- **개념·수식:** 간접법 `CFO=순이익+비현금비용-비현금이익-영업자산 증가+영업부채 증가`. `현금증감=CFO+CFI+CFF`.
- **유형 A — 간접법 CFO:** “순이익 `NI`, 감가상각 `DA`, 자산처분이익 `G`, 매출채권·재고·매입채무 증감 `dAR,dInv,dAP`가 주어질 때 CFO는?” 증가를 `+`, 감소를 `-`로 표시한다.
  - 파라미터: `NI=randInt(200,3000,10)`, `DA=randInt(10,500,10)`, `G=randInt(0,200,10)`, `dAR,dInv,dAP=randInt(-200,300,10)`; CFO 양수 조건.
  - 정답/해설식: `CFO=NI+DA-G-dAR-dInv+dAP`.
- **유형 B — 총 현금증감:** “CFO `O`, 설비취득 `Capex`, 설비매각대금 `Sale`, 신규차입 `Debt`, 배당 `Div`가 주어질 때 현금증감은?”
  - 파라미터: `O=randInt(100,3000,10)`, `Capex=randInt(50,1000,10)`, `Sale=randInt(0,500,10)`, `Debt=randInt(0,1000,10)`, `Div=randInt(0,500,10)`.
  - 정답/해설식: `CFI=Sale-Capex`, `CFF=Debt-Div`, `ΔCash=O+CFI+CFF`.
- **참고자료:** [OpenStax 간접법 현금흐름표](https://openstax.org/books/principles-financial-accounting/pages/16-3-prepare-the-statement-of-cash-flows-using-the-indirect-method), [MIT 15.501 과제·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/assignments/), [MIT 15.501 시험·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/exams/)

### ACC-10. 손익계산서·재무상태표·현금흐름표 연결

- **개념·수식:** 순이익은 이익잉여금을 늘리고 CFO의 출발점이 된다. 감가상각은 손익을 줄이지만 비현금비용이라 CFO에서 가산하며, 설비투자는 CFI와 유형자산에 반영된다.
- **유형 A — 3표 통합 현금 브리지:** “기초현금 `C0`, 매출 `R`, 현금영업비용 `OC`, 감가상각 `DA`, 이자 `Int`, 세율 `T%`, NWC 증가 `dNWC`, 설비투자 `Capex`, 신규차입 `Debt`일 때 기말현금은?”
  - 파라미터: `C0=randInt(100,2000,100)`, `R=randInt(1000,10000,100)`, `OC=randInt(500,R-300,100)`, `DA=randInt(100,500,100)`, `Int=randInt(0,300,100)`; `EBT=R-OC-DA-Int>0`; `T=randInt(10,30,5)`, `dNWC=randInt(-200,500,10)`, `Capex=randInt(100,1000,10)`, `Debt=randInt(0,1000,10)`.
  - 정수 보장: `EBT`가 100의 배수여서 세금 `EBT×T/100`이 정수.
  - 정답/해설식: `NI=EBT×(100-T)/100`; `CFO=NI+DA-dNWC`; `C1=C0+CFO-Capex+Debt`.
- **유형 B — 외상매출의 3표 영향:** “세금이 없고 원가 `COGS`인 상품을 `Revenue`에 전액 외상판매했다. 즉시 총자산은 얼마 증가하는가?”
  - 파라미터: `COGS=randInt(100,2000,10)`, 매출총이익 `GP=randInt(50,1000,10)`, `Revenue=COGS+GP`.
  - 정답/해설식: `매출채권 +Revenue`, `재고 -COGS`, `순이익·이익잉여금 +GP`, 따라서 `ΔAssets=Revenue-COGS=GP`; 현금 변화는 0.
- **참고자료:** [OpenStax 재무제표 상호연결](https://openstax.org/books/principles-financial-accounting/pages/2-1-describe-the-income-statement-statement-of-owners-equity-balance-sheet-and-statement-of-cash-flows-and-how-they-interrelate), [OpenStax 간접법](https://openstax.org/books/principles-financial-accounting/pages/16-3-prepare-the-statement-of-cash-flows-using-the-indirect-method), [MIT 15.514 샘플 중간고사 PDF](https://ocw.mit.edu/courses/15-514-financial-and-managerial-accounting-summer-2003/19734bb3c6872e3d0934f40febb2ec21_samplemidterm.pdf), [MIT 15.514 공식풀이 PDF](https://ocw.mit.edu/courses/15-514-financial-and-managerial-accounting-summer-2003/c8d4748deabadc72a8fac83de99d6878_samplesolutions.pdf)

### ACC-11. 수익성·효율성·레버리지 비율

- **개념·수식:** `영업이익률=영업이익/매출`, `총자산회전율=매출/평균총자산`, `재고회전율=매출원가/평균재고`, `부채비율=부채/자본`.
- **유형 A — 이익률:** “매출 `Sales`, 목표 영업이익률 `m%`로부터 생성된 영업이익 `EBIT`가 주어질 때 영업이익률은?”
  - 파라미터: `Sales=randInt(500,10000,100)`, `m=randInt(2,30,1)`, `EBIT=Sales×m/100`.
  - 정답/해설식: `EBIT/Sales×100=m%`.
- **유형 B — 회전율/레버리지:** 무작위로 하나를 선택한다.
  - 자산회전율: `AvgAssets=randInt(100,3000,10)`, 목표 `t=randInt(1,5,1)`, `Sales=t×AvgAssets`; 답 `t`배.
  - 부채비율: `Equity=randInt(100,3000,10)`, 목표 `d=randInt(1,4,1)`, `Debt=d×Equity`; 답 `d×100%` 즉 `100d`.
- **참고자료:** [OpenStax 재무비율 핵심용어](https://openstax.org/books/principles-finance/pages/6-key-terms), [OpenStax 재고관리·재고회전율](https://openstax.org/books/principles-financial-accounting/pages/10-5-examine-the-efficiency-of-inventory-management-using-financial-ratios), [MIT 15.501 시험·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/exams/)

### ACC-12. ROA·ROE·DuPont 분해

- **개념·수식:** `ROA=순이익률×총자산회전율`; 3단계 DuPont은 `ROE=순이익률×총자산회전율×자기자본승수`, `자기자본승수=평균자산/평균자본`.
- **유형 A — DuPont ROE:** “순이익률 `m%`, 자산회전율 `t`배, 자기자본승수 `e`배일 때 ROE는?”
  - 파라미터: `m=randInt(2,15,1)`, `t=randInt(1,3,1)`, `e=randInt(1,4,1)`; `m×t×e≤100` 조건.
  - 정답/해설식: `ROA=m×t%`; `ROE=m×t×e%`.
- **유형 B — 누락 구성요소:** “ROE `roe%`, 순이익률 `m%`, 자산회전율 `t`배일 때 자기자본승수는?”
  - answer-first 파라미터: `m=randInt(2,15,1)`, `t=randInt(1,3,1)`, 목표 `e=randInt(1,4,1)`, `roe=m×t×e`.
  - 정답/해설식: `EquityMultiplier=roe/(m×t)=e`배.
- **참고자료:** [OpenStax 재무비율·DuPont 핵심용어](https://openstax.org/books/principles-finance/pages/6-key-terms), [OpenStax Principles of Finance 무료 전체 PDF](https://assets.openstax.org/oscms-prodcms/media/documents/PrinciplesofFinance-WEB.pdf), [MIT 15.501 시험·공식해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/exams/)

---

## B. 기업재무 계산 문제 (`CF`)

### CF-01. 화폐의 시간가치 — 일시금 PV·FV

- **개념·수식:** `FV_n=PV_0(1+r)^n`, `PV_0=FV_n/(1+r)^n`.
- **유형 A — 미래가치 / 유형 B — 현재가치:** 같은 생성 데이터로 질문 방향만 바꾼다.
  - 파라미터: `r∈{5,10,20,25}%`, `n=randInt(1,4,1)`. `g=gcd(100+r,100)`, `p=(100+r)/g`, `q=100/g`. `k=randInt(1,Kmax,1)`, `PV=k×q^n`, `FV=k×p^n`.
  - 범위 제한: `Kmax=min(50,floor(1,000,000/q^n),floor(1,500,000/p^n))`; `Kmax≥1`인 조합만 선택.
  - 정수 보장: `(1+r)=p/q`로 기약하고 입력을 `q^n`의 배수로 구성한다.
  - 정답/해설식: FV형 `PV×(p/q)^n=FV`; PV형 `FV×(q/p)^n=PV`.
- **참고자료:** [원광대 화폐의 시간가치 교안 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/03.pdf), [MIT 15.401 PV·채권·주식 문제와 해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/resources/mit15_401f08_problem_sets/), [Damodaran 현재가치 문제](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/pvpr.htm), [Damodaran 현재가치 공식풀이 PDF](https://www.stern.nyu.edu/~adamodar/pdfiles/pvsol.pdf)

### CF-02. 연금·영구연금·성장영구연금

- **개념·수식:** 보통연금 `PV=C[1-(1+r)^(-n)]/r`; 영구연금 `PV=C/r`; 성장영구연금 `PV=C1/(r-g)`, 단 `r>g`.
- **유형 A — 성장영구연금:** “내년 현금흐름 `C1`, 할인율 `r%`, 영구성장률 `g%`일 때 현재가치는?”
  - answer-first 파라미터: 스프레드 `s=randInt(2,10,1)`, `g=randInt(0,6,1)`, `r=g+s≤20`, `k=randInt(1,500,1)`, `C1=k×s`.
  - 정답/해설식: `PV=C1/[(r-g)/100]=100k`.
- **유형 B — 보통연금:** “매년 말 `C`를 `n`년 받으며 할인율이 `r%`일 때 PV는?”
  - 파라미터: `r∈{10,20,25}%`, `n=randInt(2,4,1)`. 유리수 엔진으로 `AF=Σ(t=1..n)(q/p)^t=N/D`를 기약한다. `k=randInt(1,min(30,floor(1,000,000/D)),1)`, `C=kD`.
  - 정수 보장: 연금현가계수의 기약분모 `D`를 현금흐름의 인수로 넣는다.
  - 정답/해설식: `PV=C×N/D=kN`.
- **참고자료:** [원광대 화폐의 시간가치 교안 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/03.pdf), [MIT 15.401 PV 문제·해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/resources/mit15_401f08_problem_sets/), [Damodaran 현재가치 문제](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/pvpr.htm)

### CF-03. NPV와 투자안 채택

- **개념·수식:** `NPV=-I0+Σ CF_t/(1+r)^t`. 독립 투자안은 `NPV>0`이면 채택한다.
- **유형 A — 다기간 NPV:** “초기투자 `I0`, 연도별 현금흐름 `CF_t`, 할인율 `r%`일 때 NPV는?”
  - 파라미터: `r∈{10,20,25}%`, `n=randInt(1,3,1)`, 위와 같이 `p/q=(100+r)/100` 기약. 각 `K_t=randInt(1,20,1)`, `CF_t=K_t×p^t`, 할인현재가치 `PV_t=K_t×q^t`. 목표 NPV `N=randInt(-500,500,10)`, `N≠0`; `I0=ΣPV_t-N`, `I0>0` 및 표시상한 조건.
  - 정수 보장: 각 `CF_t`를 `p^t`의 배수로 만들고 `I0`를 목표답에서 역산한다.
  - 정답/해설식: `NPV=-I0+ΣK_tq^t=N`.
- **유형 B — 투자안 채택 최소 현금흐름:** “현재 `I0`를 투자하고 1년 뒤 현금흐름을 받을 때, NPV가 0이 되기 위한 최소 현금흐름은?”
  - 파라미터: `r=randInt(5,20,5)`, `I0=randInt(100,5000,100)`.
  - 정답/해설식: `CF1=I0×(100+r)/100`; `I0`가 100의 배수라 정수.
- **참고자료:** [원광대 자본예산 교안 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/12.pdf), [MIT 15.401 시험·공식해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/exams/), [Damodaran 투자수익 문제](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/invret.htm), [Damodaran 기업재무 문제·해설 허브](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/cfprset.htm)

### CF-04. IRR

- **개념·수식:** IRR은 `0=-I0+ΣCF_t/(1+IRR)^t`를 만족하는 할인율이다. 비정상 현금흐름의 복수 IRR 문제는 이 기본 모듈에서 제외하고 개념 퀴즈로 다룬다.
- **유형 A — 1기간 IRR:** “현재 `I0`를 투자해 1년 뒤 `CF1`을 받을 때 IRR은 몇 %인가?”
  - answer-first 파라미터: 목표 `irr=randInt(5,50,5)%`, `I0=randInt(100,5000,100)`, `CF1=I0×(100+irr)/100`.
  - 정답/해설식: `IRR=(CF1/I0-1)×100=irr%`.
- **유형 B — 만기일시 현금흐름:** “현재 `I0`, `n`년 뒤 `CFn`만 있는 투자안의 IRR은?”
  - 파라미터: `irr∈{5,10,20,25}%`, `n=randInt(2,4,1)`, `p/q=(100+irr)/100` 기약. `Kmax=min(50,floor(1,000,000/q^n),floor(1,500,000/p^n))`로 정의하고 `Kmax≥1`일 때 `k=randInt(1,Kmax,1)`, `I0=kq^n`, `CFn=kp^n`으로 생성한다.
  - 정수 보장: CF-01과 같은 기약분수 구성.
  - 정답/해설식: `(CFn/I0)^(1/n)-1=p/q-1=irr%`.
- **참고자료:** [원광대 자본예산 교안 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/12.pdf), [MIT 15.401 시험·공식해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/exams/), [Damodaran 투자수익 문제](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/invret.htm)

### CF-05. 배당할인모형(DDM)

- **개념·수식:** Gordon 성장모형 `P0=D1/(ke-g)`, `ke=D1/P0+g`, 단 `ke>g`.
- **유형 A — 주식가치:** “내년 배당 `D1`, 요구수익률 `ke%`, 성장률 `g%`일 때 주가는?”
  - answer-first 파라미터: `g=randInt(0,8,1)`, 스프레드 `s=randInt(2,10,1)`, `ke=g+s≤25`, `k=randInt(1,500,1)`, `D1=k×s`원.
  - 정답/해설식: `P0=D1/(s/100)=100k`원.
- **유형 B — 요구수익률:** “현재주가 `P0`, 내년 배당 `D1`, 성장률 `g%`일 때 요구수익률은?”
  - 파라미터: 배당수익률 `y=randInt(1,10,1)%`, `g=randInt(0,8,1)%`, `k=randInt(1,500,1)`, `P0=100k`, `D1=ky`.
  - 정답/해설식: `ke=D1/P0+g=y+g%`.
- **참고자료:** [원광대 주식가치평가 교안 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/06.pdf), [MIT 15.401 주식 문제·해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/resources/mit15_401f08_problem_sets/), [Damodaran DCF·DDM 문제와 해설](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/dcfprob.htm), [Damodaran 가치평가 공식풀이 PDF](https://pages.stern.nyu.edu/~adamodar/pdfiles/valpr.pdf)

### CF-06. CAPM·베타

- **개념·수식:** `ke=rf+β[E(Rm)-rf]`. 베타는 시장위험 노출이며 총위험과 동일하지 않다.
- **유형 A — CAPM 요구수익률:** “무위험수익률 `rf%`, 시장위험프리미엄 `MRP%`, 베타 `b10/10`일 때 요구수익률은?”
  - 파라미터: `rf=randInt(1,5,1)`, `MRP=randInt(4,10,1)`, `b10=randInt(5,20,1)`; `(b10×MRP) mod 10=0` 조건.
  - 정답/해설식: `ke=rf+b10×MRP/10` 정수 `%`.
- **유형 B — 내재 베타:** “요구수익률 `ke%`, 무위험수익률 `rf%`, 시장위험프리미엄 `MRP%`로부터 베타×10을 구하라.”
  - answer-first 파라미터: 위와 같이 `b10,rf,MRP`를 뽑아 `ke=rf+b10×MRP/10` 역산.
  - 정답/해설식: `β×10=(ke-rf)/MRP×10=b10`.
- **참고자료:** [원광대 CAPM 교안 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/10.pdf), [MIT 15.401 시험·공식해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/exams/), [Damodaran 위험·수익률 문제](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/riskprac.htm), [Damodaran 기업재무 문제·해설 허브](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/cfprset.htm)

### CF-07. WACC

- **개념·수식:** `WACC=wE×ke+wD×kd×(1-T)`. 장부가가 아니라 시장가치 가중치를 기본으로 한다.
- **유형 A — WACC(bp):** “부채비중 `wD%`, 자기자본비중 `wE%`, 자기자본비용 `ke%`, 세전부채비용 `kd%`, 세율 `T%`일 때 WACC는 몇 bp인가?”
  - 파라미터: `wD∈{20,25,40,50,60}`, `wE=100-wD`, `ke=randInt(8,20,1)`, `kd=randInt(3,12,1)`, `T∈{0,20,25,30}`; `(wD×kd×(100-T)) mod 100=0` 조건.
  - 정답/해설식: `WACC_bp=wE×ke + wD×kd×(100-T)/100`.
- **유형 B — 세후부채비용(bp):** “세전부채비용 `kd%`, 세율 `T%`일 때 세후부채비용은 몇 bp인가?”
  - 파라미터: `kd=randInt(3,12,1)`, `T∈{0,20,25,30,40}`.
  - 정답/해설식: `AfterTaxKd_bp=kd×(100-T)`; 예: `8%×75%=6%=600bp`.
- **참고자료:** [Damodaran 위험·수익률·허들레이트 문제](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/riskprac.htm), [Damodaran 기업재무 문제·공식해설](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/cfprset.htm), [MIT 15.401 시험·공식해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/exams/)

### CF-08. 레버리지·자본구조

- **개념·수식:** 법인세가 있는 단순 MM에서 `VL=VU+T×D`. Hamada 형태는 `βL=βU[1+(1-T)D/E]`이며 부채베타 0을 가정한다.
- **유형 A — 이자절세가치:** “무차입기업가치 `VU`, 영구부채 `D`, 세율 `T%`일 때 차입기업가치는?”
  - 파라미터: `VU=randInt(1000,20000,100)`, `D=randInt(100,10000,100)`, `T=randInt(10,30,5)`.
  - 정수 보장: `D`가 100의 배수.
  - 정답/해설식: `TaxShield=T×D/100`; `VL=VU+TaxShield`.
- **유형 B — 레버드 베타(β×100):** “언레버드 베타 `b10/10`, 부채/자본 `d`배, 세율 `T%`일 때 레버드 베타×100은?”
  - 파라미터: `b10=randInt(5,15,1)`, `d=randInt(1,3,1)`, `T∈{0,20,25,40,50}`; `[b10×(100+(100-T)d)] mod 10=0` 조건.
  - 정답/해설식: `βL×100=b10×[100+(100-T)d]/10`.
- **참고자료:** [Damodaran 자본구조 문제·해설 허브](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/cfprset.htm), [Damodaran 위험·수익률 문제](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/riskprac.htm), [Damodaran 과거 기업재무 시험·해설](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/cfprob0.html)

### CF-09. 증분 프로젝트 현금흐름

- **개념·수식:** `OCF=EBIT(1-T)+감가상각`; `Project FCF=OCF-Capex-ΔNWC`. 매몰원가는 제외하고 기회비용·부수효과는 포함한다.
- **유형 A — 1년 프로젝트 FCF:** “매출 `Sales`, 현금영업비용 `CashCost`, 감가상각 `DA`, 세율 `T%`, 설비투자 `Capex`, NWC 증가 `dNWC`일 때 FCF는?”
  - 파라미터: `Sales=randInt(1000,10000,100)`, `CashCost=randInt(500,Sales-300,100)`, `DA=randInt(100,500,100)`, `EBIT=Sales-CashCost-DA>0`, `T=randInt(10,30,5)`, `Capex=randInt(0,1000,10)`, `dNWC=randInt(-200,500,10)`.
  - 정수 보장: `EBIT`가 100의 배수.
  - 정답/해설식: `OCF=EBIT×(100-T)/100+DA`; `FCF=OCF-Capex-dNWC`.
- **유형 B — 감가상각 절세효과:** “다른 조건이 같을 때 감가상각 `DA`, 세율 `T%`가 만드는 연간 세금절감은?”
  - 파라미터: `DA=randInt(100,2000,100)`, `T=randInt(10,30,5)`.
  - 정답/해설식: `DepTaxShield=DA×T/100`.
- **참고자료:** [원광대 자본예산 교안 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/12.pdf), [Damodaran 투자수익 문제](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/invret.htm), [MIT 15.401 시험·공식해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/exams/)

### CF-10. FCFF·FCFE

- **개념·수식:** `FCFF=EBIT(1-T)+D&A-Capex-ΔNWC`; `FCFE=NI+D&A-Capex-ΔNWC+순차입`. FCFF는 WACC, FCFE는 자기자본비용으로 할인한다.
- **유형 A — FCFF:** “EBIT `E`, 세율 `T%`, 감가상각 `DA`, 설비투자 `Capex`, NWC 증가 `dNWC`일 때 FCFF는?”
  - 파라미터: `E=randInt(500,10000,100)`, `T=randInt(10,30,5)`, `DA=randInt(0,1000,10)`, `Capex=randInt(0,2000,10)`, `dNWC=randInt(-500,1000,10)`; 결과 양수 조건.
  - 정답/해설식: `FCFF=E×(100-T)/100+DA-Capex-dNWC`.
- **유형 B — FCFE:** “순이익 `NI`, 감가상각 `DA`, 설비투자 `Capex`, NWC 증가 `dNWC`, 순차입 `NetDebt`일 때 FCFE는?”
  - 파라미터: `NI=randInt(200,8000,10)`, `DA=randInt(0,1000,10)`, `Capex=randInt(0,2000,10)`, `dNWC=randInt(-500,1000,10)`, `NetDebt=randInt(-500,1500,10)`; 결과 양수 조건.
  - 정답/해설식: `FCFE=NI+DA-Capex-dNWC+NetDebt`.
- **참고자료:** [Damodaran DCF 문제·공식해설](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/dcfprob.htm), [Damodaran 기업재무 문제·해설 허브](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/cfprset.htm), [Damodaran 가치평가 문제 허브](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/eqprob.html)

### CF-11. 계속가치(Terminal Value)

- **개념·수식:** 영구성장법 `TV_n=FCF_(n+1)/(WACC-g)`, 단 `WACC>g`; 출구배수법 `TV_n=기준지표_n×Exit Multiple`.
- **유형 A — 영구성장 계속가치:** “예측종료 다음 해 FCF `F1`, WACC `w%`, 영구성장률 `g%`일 때 종료시점 계속가치는?”
  - answer-first 파라미터: `g=randInt(0,5,1)`, 스프레드 `s=randInt(3,10,1)`, `w=g+s≤20`, `k=randInt(10,1000,1)`, `F1=k×s`.
  - 정답/해설식: `TV=F1/(s/100)=100k`.
- **유형 B — 출구배수:** “종료연도 EBITDA `E`, Exit EV/EBITDA 배수 `m`일 때 TV는?”
  - 파라미터: `E=randInt(100,10000,10)`, `m=randInt(3,15,1)`.
  - 정답/해설식: `TV=E×m`.
- **참고자료:** [Damodaran DCF 문제·공식해설](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/dcfprob.htm), [Damodaran 가치평가 문제 허브](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/eqprob.html), [Damodaran 가치평가 공식풀이 PDF](https://pages.stern.nyu.edu/~adamodar/pdfiles/valpr.pdf)

### CF-12. 기업가치(EV)·지분가치·주당가치 연결

- **개념·수식:** 단순화한 브리지는 `지분가치=EV-이자부부채+현금`, `주당가치=지분가치/희석주식수`. 비영업자산·비지배지분·우선주가 있으면 문항에 명시해 조정한다.
- **유형 A — EV에서 주당가치:** “EV `EV`, 부채 `D`, 현금 `C`, 희석주식수 `S`일 때 주당가치는?”
  - answer-first 파라미터: 목표주가 `P=randInt(1000,50000,100)`, `S=randInt(10,500,10)`, `D=randInt(0,10000,100)`, `C=randInt(0,5000,100)`, `Equity=P×S`, `EV=Equity+D-C`; `EV>0`.
  - 정답/해설식: `Equity=EV-D+C`; `Price=Equity/S=P`.
- **유형 B — 배수부터 주당가치:** “EBITDA `EB`, EV/EBITDA 배수 `m`, 부채 `D`, 현금 `C`, 주식수 `S`일 때 주당가치는?”
  - 생성: `EB=randInt(100,5000,10)`, `m=randInt(3,15,1)`, `D=randInt(0,5000,10)`, `C=randInt(0,3000,10)`, `S=randInt(10,500,10)`; `Equity=EB×m-D+C>0`이고 `Equity mod S=0`일 때만 출제.
  - 정수 보장 개선안: 목표 `P,S,D,C,m`을 먼저 뽑고 `EV=P×S+D-C`; `EV mod m=0`이고 `100≤EV/m≤5,000`이면 `EB=EV/m`으로 역산한다.
  - 정답/해설식: `EV=EB×m`; `Equity=EV-D+C`; `Price=Equity/S`.
- **참고자료:** [원광대 상대가치평가 교안 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/07.pdf), [Damodaran DCF 문제·공식해설](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/dcfprob.htm), [Damodaran 가치평가 문제 허브](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/eqprob.html)

## C. 투자·포트폴리오 계산 문제 (`INV`)

### INV-01. 보유기간수익률·로그수익률·산술평균·기하평균

- **개념·수식**
  - 단순 보유기간수익률: `HPR=(P1-P0+D)/P0`
  - 로그수익률: `r_log=ln((P1+D*)/P0)`; 배당을 재투자하지 않는 단순 문항에서는 `D*=0`으로 제한한다.
  - 산술평균: `r_A=(Σr_t)/n`
  - 기하평균/CAGR: `r_G=[Π(1+r_t)]^(1/n)-1=(Pn/P0)^(1/n)-1`
- **유형 A — 총수익률과 산술평균 (`L1`)**: “주가가 `P0`원에서 `P1`원으로 변하고 배당 `D`원을 받았다. HPR은 몇 %인가?” 또는 “`n`개 연 수익률의 산술평균은 몇 %인가?”
  - 파라미터: 목표 HPR `h=−20..40%`, `P0=1,000..50,000`원(100원 단위), `D=0..P0×5%`; `P1=P0×(100+h)/100−D`. 평균형은 `n=2..5`, 목표 평균 `m=−10..25%`, 앞 `n−1`개 수익률 `−30..50%`, 마지막 값 `n×m−Σ앞값`.
  - 정수 보장: `P0`를 100의 배수로 뽑고 역산한 `P1`이 양수일 때만 채택한다. 평균형 마지막 수익률이 범위 안일 때만 채택한다.
- **유형 B — CAGR·로그수익률 (`L2`)**: “`n`년간 `P0`원이 `Pn`원이 되었다. CAGR은 몇 %인가?” 또는 “계산된 `ln(가격비)`가 `0.08`로 주어질 때 로그수익률은 몇 bp인가?” 로그함수 자체는 계산시키지 않는다.
  - CAGR 파라미터: 목표 `g=1..25%`, `n=2..4`; `d=gcd(100+g,100)`, `p=(100+g)/d`, `q=100/d`. `Kmin=max(1,ceil(1,000/q^n))`, `Kmax=min(100,floor(1,000,000/q^n),floor(2,000,000/p^n))`로 두고 `Kmin≤Kmax`일 때 `k=Kmin..Kmax`, `P0=kq^n`, `Pn=kp^n`으로 생성한다.
  - 로그 파라미터: `logReturnBp=−3,000..4,000 / step 100`(`0` 제외), 화면에는 정확한 값 `logReturnBp/10,000`을 소수로 제공한다. 답은 소수점을 네 칸 옮긴 `logReturnBp` bp다.
  - 정수·암산 보장: CAGR 정답은 먼저 뽑은 `g`; 로그형은 지문이 제공한 로그값의 단위 변환만 수행하므로 숨은 근사나 반올림이 없다.
- **참고**: [MIT 15.433 Investments 강의노트](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/lecture-notes/), [MIT 15.433 과제·일부 해설](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/), [OpenStax Principles of Finance](https://openstax.org/books/principles-finance/pages/15-summary)

### INV-02. 기대수익률·분산·표준편차

- **개념·수식**: `E(R)=Σp_sR_s`, 모집단 분산 `σ²=Σp_s(R_s−E(R))²`, 표준편차 `σ=√σ²`. 앱에서는 별도 표기가 없으면 확률분포의 **모집단** 분산을 쓴다.
- **유형 A — 상태별 기대수익률 (`L1`)**: “호황·보통·불황의 확률과 수익률이 주어질 때 기대수익률은 몇 %인가?”
  - 파라미터: 확률 `p_s`는 10% 단위, 상태 `n=2..4`, 합계 100%; 수익률 `−30..50%`.
  - 정수 보장: 앞 상태들을 뽑은 뒤 목표 기대수익률 `μ=−10..25%`가 되도록 마지막 수익률을 역산하거나, `Σp_sR_s`가 100으로 나누어떨어지는 조합만 채택한다.
- **유형 B — 대칭분포의 분산·표준편차 (`L1`)**: “두 상태가 각각 50% 확률이고 수익률이 `μ−d`, `μ+d`다. 기대수익률, 분산(%²), 표준편차(%)를 구하라.”
  - 파라미터: `μ=−5..20`, `d=2..25`; 두 수익률 모두 `−40..60%`.
  - 정수 보장: 정답이 각각 `μ`, `d²`, `d`이므로 항상 정수다. 일반 4상태형은 편차 `[-d,-d,+d,+d]`를 사용한다.
- **참고**: [MIT 15.401 Risk and Return](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/risk-and-return), [MIT 15.433 과제·해설](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/), [원광대 포트폴리오 교안 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/08.pdf)

### INV-03. 공분산·상관계수

- **개념·수식**: `Cov(A,B)=Σp_s(R_As−μ_A)(R_Bs−μ_B)`, `ρ_AB=Cov(A,B)/(σ_Aσ_B)`, `−1≤ρ≤1`.
- **유형 A — 공분산 계산 (`L1`)**: “`σ_A`, `σ_B`, `ρ`가 주어질 때 공분산은 몇 `%²`인가?”
  - 파라미터: `σ_A,σ_B=5..40%`의 5% 단위, `ρ×100∈{−100,−80,−60,−50,−40,−20,0,20,40,50,60,80,100}`.
  - 정수 보장: `σ_A×σ_B×ρ100`이 100으로 나누어떨어지는 조합만 채택한다. 정답 `Cov=σ_Aσ_Bρ100/100`.
- **유형 B — 상관계수 역산 (`L2`)**: “공분산과 두 표준편차로 상관계수를 `ρ×100` 정수로 답하라.”
  - 파라미터: 위와 동일하되 `ρ100`을 먼저 뽑고 `Cov=σ_Aσ_Bρ100/100`으로 생성한다.
  - 정수 보장: 정답 필드가 `ρ×100`이며 생성 시 선택한 정수 그대로다. 부호가 분산효과에 미치는 의미를 해설한다.
- **참고**: [MIT 15.401 Portfolio Theory](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/portfolio-theory), [MIT 15.433 Capital Market Theory 문제](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/), [원광대 포트폴리오 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/08.pdf)

### INV-04. 2자산 포트폴리오

- **개념·수식**: `E(R_p)=wR_A+(1−w)R_B`; `σ_p²=w²σ_A²+(1−w)²σ_B²+2w(1−w)Cov_AB`.
- **유형 A — 포트폴리오 기대수익률 (`L1`)**: “A 비중 `w%`, B 비중 `100−w%`일 때 기대수익률은 몇 %인가?”
  - 파라미터: `w=10..90%`의 10% 단위, `R_A,R_B=−10..30%`.
  - 정수 보장: 목표 `R_p`를 먼저 뽑고 `R_B=(100R_p−wR_A)/(100−w)`를 역산해 정수·범위 조건을 만족할 때 채택한다.
- **유형 B — 분산 또는 완전 음의 상관에서 표준편차 (`L2`)**: 일반형은 `σ_p²`를 `%²` 정수로, 특수형은 비중을 정수 `%`인 `w`로 둘 때 `σ_A=σ_B=s`, `ρ=−1`에서 `σ_p=|2w/100−1|s`를 %로 묻는다.
  - 파라미터: 일반형 `w=10..90% / step 10`, `σ_A,σ_B=10..40% / step 10`, `ρ100∈{−100,−75,−50,−25,0,25,50,75,100}`, `Cov=σ_Aσ_Bρ100/100`; 특수형 `s=10..40% / step 10`.
  - 정수 보장: 상관계수를 먼저 생성하므로 자동으로 `|Cov|≤σ_Aσ_B`가 성립한다. 일반형은 계산 분자 `w²σ_A²+(100−w)²σ_B²+2w(100−w)Cov`가 10,000으로 나누어떨어지고 분산이 양수인 조합만 채택한다. 특수형은 항상 정수다.
- **참고**: [MIT 15.401 Portfolio Theory](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/portfolio-theory), [MIT 15.433 강의노트](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/lecture-notes/), [원광대 포트폴리오 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/08.pdf)

### INV-05. 베타

- **개념·수식**: `β_i=Cov(R_i,R_m)/Var(R_m)`. 베타는 총위험이 아니라 시장수익률에 대한 민감도다.
- **유형 A — 공분산으로 베타 계산 (`L1`)**: “시장수익률 분산과 종목·시장 공분산으로 `β×100`을 구하라.”
  - 파라미터: 목표 `β100=40..220`의 10 단위, `Var_m=25..400%²`의 25 단위, `Cov=β100×Var_m/100`.
  - 정수 보장: `β100×Var_m`가 100으로 나누어떨어지는 조합만 사용한다.
- **유형 B — 두 시나리오 민감도 (`L1`)**: 시장이 `−m%`, `+m%`일 때 종목 초과수익이 각각 `−βm%`, `+βm%`라면 베타를 `×100`으로 답하게 한다.
  - 파라미터: `m=2..10%`, `β100=50..200`의 25 단위.
  - 정수 보장: `m×β100`이 100으로 나누어떨어질 때만 채택한다.
- **참고**: [MIT 15.401 CAPM·APT 강의와 PDF](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/the-capm-and-apt), [원광대 CAPM PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/10.pdf), [OpenStax CAPM](https://openstax.org/books/principles-finance/pages/15-3-the-capital-asset-pricing-model-capm)

### INV-06. CAPM 요구수익률·알파

- **개념·수식**: `E(R_i)=R_f+β_i[E(R_m)−R_f]`; CAPM 알파 `α=R_actual−[R_f+β(R_m−R_f)]`.
- **유형 A — 요구수익률 (`L1`)**: “무위험수익률, 시장위험프리미엄, 베타가 주어질 때 요구수익률은 몇 bp인가?”
  - 파라미터: `R_f=1..6%`, 시장위험프리미엄 `MRP=4..12%`의 2% 단위, `β100=50..200`의 25 단위.
  - 정수 보장: 답 단위를 bp로 두면 `100R_f+β100×MRP`가 항상 정수다.
- **유형 B — Jensen alpha의 기초 (`L2`)**: 실현수익률과 CAPM 기대수익률의 차이를 bp로 계산하고 과대/과소성과를 판단한다.
  - 파라미터: 위 CAPM 변수와 실제수익률 `−10..35%`.
  - 정수 보장: 모든 금리를 정수 %로 생성하고 답을 bp로 저장한다.
- **참고**: [MIT 15.401 CAPM·APT](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/the-capm-and-apt), [MIT 15.401 문제세트·해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/problem-sets/), [원광대 CAPM PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/10.pdf)

### INV-07. APT 다요인 기대수익률

- **개념·수식**: `E(R_i)=R_f+Σ_k β_ikλ_k`; `λ_k`는 요인 위험프리미엄이다. 문제에서는 요인의 정의와 부호를 반드시 명시한다.
- **유형 A — 2요인 APT (`L1`)**: “금리요인·성장요인 베타와 각 위험프리미엄으로 요구수익률을 bp로 구하라.”
  - 파라미터: `R_f=1..6%`, `β_k×100=−150..200`의 25 단위, `λ_k=−4..8%`의 2% 단위, 요인 수 `2`.
  - 정수 보장: `E(R)bp=100R_f+Σβ100_kλ_k`이므로 정수다. 결과가 `−10..35%` 범위일 때만 채택한다.
- **유형 B — APT mispricing/alpha (`L2`)**: 실제 기대수익률과 모형 요구수익률 차이를 bp로 구하고, 양(+)의 알파인지 판정한다.
  - 파라미터: 유형 A와 동일, 실제 기대수익률 `−10..40%`.
  - 정수 보장: bp 단위 차감으로 항상 정수다.
- **참고**: [MIT 15.401 CAPM·APT](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/the-capm-and-apt), [MIT 15.433 CAPM·APT 강의노트](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/lecture-notes/)

### INV-08. Sharpe·Treynor·Jensen 성과평가

- **개념·수식**: `Sharpe=(R_p−R_f)/σ_p`; `Treynor=(R_p−R_f)/β_p`; `Jensen α=R_p−[R_f+β_p(R_m−R_f)]`.
- **유형 A — Sharpe 또는 Treynor (`L1`)**: 비율은 `ratio×100` 정수로 답한다.
  - 파라미터: Sharpe 목표 `S100=25..200`의 25 단위, `σ=4..32%`의 4 단위, `R_f=1..6%`, `R_p=R_f+S100×σ/100`; Treynor는 목표 Treynor 수익률 `T=1..20%`, `β100=50..200`의 25 단위, `R_p=R_f+T×β100/100`.
  - 정수 보장: 목표 비율을 먼저 뽑아 `R_p`를 역산하며, 역산 수익률이 정수·범위 안일 때 채택한다. Treynor 정답은 `%` 정수로 저장한다.
- **유형 B — Jensen alpha (`L2`)**: “펀드 수익률, 시장수익률, 무위험수익률, 베타로 Jensen alpha를 몇 bp인지 구하라.”
  - 파라미터: `R_p=−10..35%`, `R_m=−10..30%`, `R_f=1..6%`, `β100=50..200`의 25 단위.
  - 정수 보장: `αbp=100(R_p−R_f)−β100(R_m−R_f)`로 직접 계산한다.
- **참고**: [CFA Institute Risk-Adjusted Performance Measures](https://rpc.cfainstitute.org/topics/performance-attribution/risk-adjusted-performance), [CFA 성과측정 PDF](https://rpc.cfainstitute.org/-/media/documents/code/gips/measures-risk-adjusted-return.pdf), [MIT 15.433 Performance Attribution 문제·해설](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/)

### INV-09. Tracking Error·Information Ratio

- **개념·수식**: 액티브수익률 `AR_t=R_pt−R_bt`; `TE=SD(AR_t)`; `IR=mean(AR_t)/TE`. 앱에서는 별도 언급이 없으면 주어진 상태의 모집단 표준편차를 쓴다.
- **유형 A — Tracking Error (`L1`)**: 액티브수익률이 동일확률로 `a−d`, `a+d`일 때 TE를 %로 구한다.
  - 파라미터: 평균 액티브수익률 `a=−5..10%`, `d=1..15%`; 각 값 `−25..25%`.
  - 정수 보장: 대칭분포 모집단 표준편차가 정확히 `d`다.
- **유형 B — Information Ratio (`L1`)**: 평균 액티브수익률과 TE로 `IR×100`을 계산한다.
  - 파라미터: 목표 `IR100=−200..200`의 25 단위(0 제외 가능), `TE=4..20%`의 4 단위, `AR=IR100×TE/100`.
  - 정수 보장: 목표 IR을 먼저 뽑아 평균 액티브수익률을 역산하고 정수·`−15..15%` 범위일 때만 채택한다.
- **참고**: [CFA Institute Risk-Adjusted Performance Measures](https://rpc.cfainstitute.org/topics/performance-attribution/risk-adjusted-performance), [CFA Investment Risk and Performance 사례 PDF](https://rpc.cfainstitute.org/-/media/documents/code/gips/case-study-risk-adjusted-performance-measures.pdf), [MIT 15.433 Performance Attribution](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/)

## D. 채권·금리 계산 문제 (`FI`)

### FI-01. 채권가격·YTM

- **개념·수식**: 쿠폰채 `P=Σ_{t=1}^n C/(1+y)^t+F/(1+y)^n`; 무이표채 `P=F/(1+y)^n`. 가격과 YTM은 다른 조건이 같으면 반대로 움직인다.
- **유형 A — 무이표채 가격 또는 YTM (`L1`)**: “만기 `n`년, 액면 `F`, 연복리 YTM `y%`인 무이표채 가격은 몇 원인가?” 또는 가격·액면으로 YTM을 역산한다.
  - 파라미터: 목표 YTM `y=1..12%`, `n=1..3`, 가격배수 `k=1..50`; `P=k×100^n`, `F=k×(100+y)^n`원.
  - 정수 보장: `y`와 `P`를 먼저 정하고 `F`를 역산한다. 가격형 정답은 정확히 `P`, YTM형은 정확히 `y`다. 액면 범위 `1,000..5,000,000원` 밖이면 재생성한다.
- **유형 B — 1기간 쿠폰채 (`L1`)**: “1년 뒤 쿠폰 `C`와 액면 `F`를 받는 채권의 현재가격 또는 YTM은?”
  - 파라미터: `y=1..12%`, 목표 가격 `P=1,000..100,000원`의 100원 단위, 총 만기현금흐름 `T=P(100+y)/100`; 액면비율 `a=88..99%`, `F=aT/100`, `C=T−F`.
  - 정수 보장: `P`를 100원 단위로 생성해 T를 정수화하고, `aT`가 100으로 나누어떨어지는 조합만 채택한다. `C>0`이고 암묵 쿠폰율 `C/F≤15%`인지도 검사한다.
- **참고**: [MIT 15.401 Fixed-Income Securities 강의·PDF](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/fixed-income-securities), [MIT 15.401 문제세트·해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/problem-sets/), [원광대 채권 가치평가 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/05.pdf), [OpenStax Bond Valuation](https://openstax.org/books/principles-finance/pages/10-2-bond-valuation)

### FI-02. 현물이자율·선도금리

- **개념·수식**: 연복리 기준 `(1+s_2)^2=(1+s_1)(1+f_{1,2})`; 일반형 `(1+s_n)^n=(1+s_m)^m(1+f_{m,n})^(n−m)`.
- **유형 A — 1년 후 1년 선도금리 (`L2`)**: “1년 현물금리 `s1`과 2년 현물금리 `s2`가 주어질 때 `f1,2`는 몇 bp인가?”
  - 파라미터 생성: 서로 다른 정수 `x,y∈{100,101,…,109}`를 뽑아 `1+s1=x²/10,000`, `1+f=y²/10,000`, `1+s2=xy/10,000`으로 둔다. 화면에는 `s1=x²−10,000 bp`, `s2=xy−10,000 bp`를 제시한다.
  - 정수 보장: 공식 대입 시 `1+f=y²/10,000`, 따라서 정답은 정확히 `y²−10,000 bp`다. `s1,s2,f`가 `0..2,000bp` 안인 경우만 사용한다.
- **유형 B — 2년 현물금리 역산 (`L2`)**: `s1`과 `f1,2`를 주고 `s2`를 bp로 묻는다.
  - 파라미터: 유형 A와 같은 `x,y` 생성기.
  - 정수 보장: `sqrt(x²y²)=xy`이므로 `s2=xy−10,000bp`가 정확한 정수다.
- **참고**: [MIT 15.401 Fixed-Income Securities](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/fixed-income-securities), [Tuckman·Serrat, Fixed Income Securities 4e](https://onlinelibrary.wiley.com/doi/book/10.1002/9781119835622), [MIT 15.433 강의노트](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/lecture-notes/)

### FI-03. Macaulay Duration·Modified Duration

- **개념·수식**: `D_Mac=Σ[t×PV(CF_t)]/P`; 연 1회 복리에서 `D_Mod=D_Mac/(1+y)`. Modified duration은 작은 수익률 변화에 대한 가격 민감도다.
- **유형 A — PV 현금흐름표로 Macaulay duration (`L1`)**: 각 시점별 현금흐름의 **현재가치** 표를 주고 duration을 `centiyear(0.01년)`로 답하게 한다.
  - 파라미터: 만기 `n=2..10`, 시점 `t=1..n`, 총가격 `P=10,000원`, 각 `PV_t`는 100원 단위 양의 정수이고 합계 10,000원.
  - 정수 보장: `D_Mac×100=Σt×(PV_t/100)`이므로 항상 정수다. 최종 원금 PV 비중이 가장 크도록 제약한다.
- **유형 B — Modified duration (`L2`)**: “Macaulay duration과 YTM으로 modified duration을 centiyear로 구하라.”
  - 파라미터: 만기 `n=2..15년`, `y=1..12%`, 목표 `D_Mod,100=100..1,200`; `D_Mac,100=D_Mod,100×(100+y)/100`.
  - 정수 보장: `D_Mod,100`을 `100/gcd(100,100+y)`의 배수로 뽑고, 역산한 `D_Mac,100`이 정수이며 `D_Mac,100≤100n`일 때 채택한다.
- **참고**: [MIT 15.401 Fixed-Income Securities](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/fixed-income-securities), [OpenStax Interest Rate Risk](https://openstax.org/books/principles-finance/pages/20-4-interest-rate-risk), [Tuckman·Serrat 4e](https://onlinelibrary.wiley.com/doi/book/10.1002/9781119835622)

### FI-04. DV01·Convexity 가격변화

- **개념·수식**: `DV01≈D_Mod×MV×0.0001`; `ΔP/P≈−D_ModΔy+0.5×Convexity×(Δy)²`. 수익률 상승이면 duration 항에 의해 가격이 하락한다.
- **유형 A — DV01 (`L1`)**: “시장가치 `MV`, modified duration `D`인 채권 포지션의 DV01은 몇 원인가?”
  - 파라미터: `D=1..15년` 정수, `MV=1,000,000..100,000,000원`의 10,000원 단위.
  - 정수 보장: `DV01=D×MV/10,000`; MV를 10,000의 배수로 제한한다.
- **유형 B — duration+convexity 근사 (`L2`)**: “수익률이 `k%p` 상승할 때 근사 가격변화액은 몇 원인가?”
  - 파라미터: `P=100,000..20,000,000원`의 20,000원 단위, `D=1..12`, convexity `C=2..120`의 짝수, `k∈{−3,−2,−1,1,2,3}`.
  - 정수 보장: `ΔP=P[−Dk/100+0.5Ck²/10,000]`. P를 20,000의 배수, C를 짝수로 두면 각 항이 정수다. 근사변화 후 가격이 양수인 경우만 채택한다.
- **참고**: [CME Calculating the Dollar Value of a Basis Point PDF](https://www.cmegroup.com/trading/interest-rates/files/Calculating_the_Dollar_Value_of_a_Basis_Point_Final_Dec_4.pdf), [CME Treasury Hedging and Risk Management](https://www.cmegroup.com/education/courses/introduction-to-treasuries/treasuries-hedging-and-risk-management.hideSubnav.html.educationIframe.html?hideAddThisExt=y&hideFooter=y&hideHeader=y&hideRightRail=y), [OpenStax Interest Rate Risk](https://openstax.org/books/principles-finance/pages/20-4-interest-rate-risk)

### FI-05. Duration Immunization

- **개념·수식**: 1차 면역화는 보통 `PV(자산)=PV(부채)`와 `D_A=D_L`을 동시에 맞춘다. 두 자산이면 `wD_1+(1−w)D_2=D_L`, `w=(D_2−D_L)/(D_2−D_1)`.
- **유형 A — 두 채권으로 부채 면역 (`L2`)**: “부채 PV `V`와 duration `D_L`을 duration `D_1,D_2` 채권으로 면역화할 때 각 투자액은?”
  - 파라미터: `D_1=1..6`, `D_2=7..15`, `D_L`은 두 값 사이 정수; `den=D_2−D_1`, `V=den×k`, `k=100,000..5,000,000원`의 100,000원 단위.
  - 정수 보장: `V_1=V(D_2−D_L)/den`, `V_2=V(D_L−D_1)/den`; V를 den의 배수로 만든다.
- **유형 B — 목표 duration 맞추기 (`L1`)**: 총자산 `V`, 두 채권 duration과 한 채권 투자액을 주고 포트폴리오 duration 또는 필요한 반대편 투자액을 구한다.
  - 파라미터: 유형 A에서 완성된 정수 포지션을 일부 가려서 제시한다.
  - 정수 보장: 완성된 면역 포트폴리오를 먼저 생성한 뒤 미지수를 숨기는 역문제 방식이다.
- **참고**: [MIT 15.401 Fixed-Income Securities](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/fixed-income-securities), [Tuckman·Serrat 4e](https://onlinelibrary.wiley.com/doi/book/10.1002/9781119835622), [CME Treasury Hedging](https://www.cmegroup.com/education/courses/introduction-to-treasuries/treasuries-hedging-and-risk-management.hideSubnav.html.educationIframe.html?hideAddThisExt=y&hideFooter=y&hideHeader=y&hideRightRail=y)

### FI-06. 금리위험 헤징·계약수

- **개념·수식**: DV01 중립 헤지계약수 `N=DV01_portfolio/DV01_futures`; 일반 duration hedge `N=(V_PD_P)/(V_FD_F)`. 롱 채권의 금리상승 위험은 보통 금리선물을 매도해 헤지한다.
- **유형 A — DV01 hedge (`L1`)**: “채권 포트폴리오 DV01을 선물로 100% 헤지하려면 몇 계약을 매수/매도해야 하는가?”
  - 파라미터: 선물 1계약 DV01 `d_f=10..500원`, 목표 계약수 `N=1..500`, 포트폴리오 DV01 `d_p=N×d_f`.
  - 정수 보장: 계약수를 먼저 뽑아 포트폴리오 DV01을 역산한다. 포지션 방향은 별도 선택지로 채점한다.
- **유형 B — 목표 DV01로 조정 (`L2`)**: 현재 DV01 `d_current`를 목표 `d_target`으로 바꿀 때 `N=(d_current−d_target)/d_f`를 구한다.
  - 파라미터: `d_f=10..500원`, signed `N=−500..500`, `d_current=1,000..200,000원`, `d_target=d_current−N×d_f`.
  - 정수 보장: signed N을 먼저 생성한다. `N>0`은 선물 매도, `N<0`은 매수라는 앱 부호 규약을 고정한다.
- **참고**: [CME DV01 PDF](https://www.cmegroup.com/trading/interest-rates/files/Calculating_the_Dollar_Value_of_a_Basis_Point_Final_Dec_4.pdf), [CME Using Treasury Futures to Replace Swap Exposure PDF](https://www.cmegroup.com/content/dam/cmegroup/education/files/using-treasury-futures-to-replace-swap-exposure.pdf), [CME Treasury Hedging](https://www.cmegroup.com/education/courses/introduction-to-treasuries/treasuries-hedging-and-risk-management.hideSubnav.html.educationIframe.html?hideAddThisExt=y&hideFooter=y&hideHeader=y&hideRightRail=y)

### FI-07. Repo·Haircut

- **개념·수식**: 현금대출액 `Cash=Collateral×(1−h)`; repo 이자 `I=Cash×r×days/B`, `B=360` 또는 `365`; 재매입가격 `RP=Cash+I`.
- **유형 A — haircut과 현금대출액 (`L1`)**: “담보 시가와 haircut으로 조달 가능한 현금은 몇 원인가?”
  - 파라미터: 담보가치 `V=100,000..100,000,000원`의 100원 단위, haircut `h=0..20%` 정수.
  - 정수 보장: V를 100의 배수로 제한해 `V(100−h)/100`을 정수로 만든다.
- **유형 B — repo 이자·재매입가격 (`L1`)**: “현금 `Cash`, repo rate `r%`, 기간 `d일`, Actual/360일 때 이자와 재매입가격은?”
  - 파라미터: `r=1..12%`, `d∈{1,7,10,15,30,45,60,90,120,180}`, `Cash=100,000..100,000,000원`.
  - 정수 보장: `m=36,000/gcd(r×d,36,000)`을 계산하고 Cash를 m의 배수로만 생성한다. 그러면 `I=Cash×r×d/36,000`, `RP=Cash+I`가 모두 정수다.
- **참고**: [뉴욕연은 Tri-Party Repo Mechanics PDF](https://www.newyorkfed.org/medialibrary/media/research/epr/2012/1210cope.pdf), [뉴욕연은 Repo·Reverse Repo 설명](https://www.newyorkfed.org/markets/domestic-market-operations/monetary-policy-implementation/repo-reverse-repo-agreements), [CME Repo Exposure Hedging PDF](https://www.cmegroup.com/content/dam/cmegroup/education/files/hedging-repo-exposure-in-the-treasury-basis-web.pdf)

### FI-08. 채권선물 Basis·CTD

- **개념·수식**: 단순화한 conversion-factor-adjusted basis `Basis=P_cash−F_futures×CF`; 여러 인도가능채권 중 조정 basis가 가장 작은 채권을 CTD 후보로 본다. 실제 거래의 accrued interest·carry·delivery option은 심화 카드에서 분리한다.
- **유형 A — 조정 basis (`L2`)**: 현물과 선물가격을 `1/32 point` 단위 tick으로 주고 basis도 tick으로 답한다.
  - 파라미터: 현물 `P_tick=2,560..4,800`, 선물 `F_tick=2,560..4,800`; `CF∈{0.50,0.60,0.625,0.75,0.80,0.875,1.00}`.
  - 정수 보장: CF를 기약분수 `a/b`로 저장하고 `F_tick`을 b의 배수로 생성한다. `Basis_tick=P_tick−F_tick×a/b`가 정수다.
- **유형 B — CTD 선택 (`L2`)**: 동일 선물에 인도 가능한 채권 2~4개의 현물가격·CF를 제시하고 최소 basis의 채권 번호를 고른다.
  - 파라미터: 유형 A의 완성쌍을 2~4개 생성, basis 범위 `−200..300 tick`.
  - 정수 보장: 모든 basis가 정수이며 동점이 없는 세트만 채택한다. 정답은 채권 번호 정수다.
- **참고**: [CME Treasury Futures DV01 PDF](https://www.cmegroup.com/trading/interest-rates/files/Calculating_the_Dollar_Value_of_a_Basis_Point_Final_Dec_4.pdf), [CME Treasury Hedging and Risk Management](https://www.cmegroup.com/education/courses/introduction-to-treasuries/treasuries-hedging-and-risk-management.hideSubnav.html.educationIframe.html?hideAddThisExt=y&hideFooter=y&hideHeader=y&hideRightRail=y), [MIT 15.433 Futures 과제·해설](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/)

### FI-09. 금리스왑 고정금리·현금흐름

- **개념·수식**: 단일통화 plain-vanilla swap의 순지급액은 결제일 기준 `Net=N×(L_prev−K)×d/B`(고정금리 수취자 기준 부호는 반대). 할인계수 `D_i`가 있을 때 par fixed rate `K=(1−D_n)/(ΣD_i×accrual_i)`.
- **유형 A — 순이자 현금흐름 (`L1`)**: “명목원금, 직전 fixing 금리, 고정금리, 일수로 다음 순지급액을 구하고 누가 지불하는지 판단하라.”
  - 파라미터: `N=1,000,000..1,000,000,000원`, `L,K=1..12%` 정수, `d∈{30,60,90,180}`, `B=360`.
  - 정수 보장: `N`을 `100×360/gcd(|L−K|×d,36,000)`의 배수로 만든다. 금리차 0은 제외한다.
- **유형 B — par swap rate (`L2`)**: 할인계수 합인 swap annuity `A`와 마지막 할인계수 `D_n`을 주고 고정금리를 bp로 답한다.
  - 파라미터: 목표 `K_bp=100..1,200 / step 25`; `stepA=10,000/gcd(K_bp,10,000)`, `kMin=ceil(10,000/stepA)`, `kMax=floor(50,000/stepA)`, `A_scaled=stepA×k`(`kMin..kMax`), 실제 `A=A_scaled/10,000`; `D_n=1−(K_bp/10,000)A`.
  - 정수 보장: `A_scaled`를 위 배수로 직접 생성하므로 `D_n×10,000=10,000−K_bp×A_scaled/10,000`이 항상 정수다. `0.50≤D_n≤0.99`인 경우만 채택하며 화면에는 A와 Dn을 소수 4자리로 제공한다.
- **참고**: [MIT 15.433 강의노트—Forwards, Futures & Swaps](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/lecture-notes/), [Hull 11e 공식 목차·교재](https://www.pearson.com/en-us/subject-catalog/p/options-futures-and-other-derivatives/P200000005938/9780136939917), [CME Treasury Futures and Swap Exposure PDF](https://www.cmegroup.com/content/dam/cmegroup/education/files/using-treasury-futures-to-replace-swap-exposure.pdf)

### FI-10. 신용위험·Credit Spread·Expected Loss

- **개념·수식**: `LGD=1−Recovery`; 1기간 기대손실 `EL=EAD×PD×LGD`; 단순화한 위험중립 근사 spread `s≈PD×LGD`. 실제 spread에는 유동성·위험프리미엄·만기구조가 포함된다.
- **유형 A — 기대손실 (`L1`)**: “EAD, PD, recovery rate로 예상손실은 몇 원인가?”
  - 파라미터: `EAD=100,000..100,000,000원`의 10,000원 단위, `PD=1..20%`, recovery `R=0..80%`의 10% 단위.
  - 정수 보장: `EL=EAD×PD×(100−R)/10,000`; EAD를 10,000의 배수로 제한한다.
- **유형 B — 손실보전 break-even spread (`L1`)**: “PD와 recovery만 반영한 단순 1년 break-even spread는 몇 bp인가?”
  - 파라미터: `PD=1..15%`, `LGD=20..100%`의 10% 단위.
  - 정수 보장: `spread_bp=PD_percent×LGD_percent`; 예컨대 2%×60%=120bp로 항상 정수다.
- **참고**: [FINRA Bond Spreads 설명](https://www.finra.org/investors/insights/spread-word-what-you-need-know-about-bond-spreads), [OpenStax Interest Rate and Default Risk](https://openstax.org/books/principles-finance/pages/10-4-risks-of-interest-rates-and-default), [MIT 15.433 커리큘럼—Credit Market](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/calendar/), [Tuckman·Serrat 4e](https://onlinelibrary.wiley.com/doi/book/10.1002/9781119835622)

## E. 파생상품 계산 문제 (`DER`)

### DER-01. Forward·Futures 이론가격

- **개념·수식**: 단순금리·알려진 현금수익에서 `F_0=(S_0−I)(1+rT)`; 무수익 자산의 연복리 1년형 `F_0=S_0(1+r)`. 통화선도 1년형 `F_0=S_0(1+r_d)/(1+r_f)`. 동일 만기·무중간 현금흐름이라는 가정에서 선도와 선물가격을 같게 취급한다.
- **유형 A — 현금수익이 있는 주식/지수의 선도가격 (`L1`)**: “현물가격, 만기 전 배당의 현재가치, 단순 조달금리, 만기로 이론선도가격을 구하라.”
  - 파라미터: `S_0=1,000..100,000원`, `I=0..S_0×10%`, `r=1..12%`, `m∈{3,6,12}개월`, `T=m/12`.
  - 정수 보장: 순현물 `X=S_0−I`를 `1,200/gcd(rm,1,200)`의 배수로 생성한다. `F=X(1+rm/1,200)`가 정수다.
- **유형 B — FX forward (`L2`)**: “현물환율 `S`, 국내금리 `r_d`, 해외금리 `r_f`로 1년 선도환율을 원 단위로 구하라.”
  - 파라미터: `r_d,r_f=0..12%`, 서로 다르게 생성; 목표 현물환율 `S=500..2,000원`.
  - 정수 보장: `S`를 `(100+r_f)/gcd(100+r_d,100+r_f)`의 배수로 생성한다. `F=S(100+r_d)/(100+r_f)`가 정수이고 `500..2,500원`일 때 채택한다.
- **참고**: [MIT 15.401 Forward and Futures 강의·PDF](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/forward-and-futures-contracts), [중앙대 선물 무차익가격 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/02.pdf), [Hull 11e 공식 교재 페이지](https://www.pearson.com/en-us/subject-catalog/p/options-futures-and-other-derivatives/P200000005938/9780136939917)

### DER-02. Forward·Futures 무차익거래

- **개념·수식**: 시장선도가격 `K_mkt`가 이론가격 `F*`보다 높으면 현물 매수·선도 매도(cash-and-carry), 낮으면 가능한 경우 현물 공매도·선도 매수(reverse cash-and-carry). 만기 단위당 확정이익은 단순 조건에서 `|K_mkt−F*|`다.
- **유형 A — arbitrage profit (`L2`)**: “이론가격, 시장가격, 계약수량으로 만기 차익거래이익과 방향을 구하라.”
  - 파라미터: `F*=1,000..100,000원`, 괴리 `δ=10..5,000원`, 부호 `z∈{−1,+1}`, `K_mkt=F*+zδ`, 수량 `Q=1..1,000`.
  - 정수 보장: `Profit=δQ`로 항상 정수다. 이론가격은 DER-01 생성기로 먼저 만든다.
- **유형 B — 현금흐름표 완성 (`L3`)**: 현재의 현물매매·차입/대출·선도 포지션 중 빠진 금액 하나 또는 만기 순현금흐름을 구한다.
  - 파라미터: DER-01의 무배당 1년 데이터, `δ=10..2,000원`, `Q=1..100`.
  - 정수 보장: 모든 현재·만기 현금흐름을 이론가격 생성기에서 확정한 뒤 한 셀만 가리는 역문제 방식이다.
- **참고**: [중앙대 선물 무차익가격 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/02.pdf), [MIT 15.401 문제세트·해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/problem-sets/), [MIT 15.401 Forward and Futures](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/forward-and-futures-contracts)

### DER-03. 최소분산 Hedge Ratio·선물계약수

- **개념·수식**: 최소분산 헤지비율 `h*=ρσ_S/σ_F`; 계약수 `N*=h*Q_A/Q_F`. 주가지수선물 베타헤지는 `N*=βV_P/(F_0×multiplier)`.
- **유형 A — 최소분산 헤지비율 (`L1`)**: “상관계수와 현물·선물 가격변화 표준편차로 `h×100`을 구하라.”
  - 파라미터: 목표 `h100=20..150`의 10 단위, `σ_S,σ_F=5..40`의 5 단위; `ρ100=h100×σ_F/σ_S`.
  - 정수 보장: h를 먼저 뽑아 `ρ100`을 역산하고, 정수이면서 `−100..100`인 조합만 채택한다.
- **유형 B — 계약수 (`L2`)**: “헤지할 현물 수량 `Q_A`, 선물 1계약 단위 `Q_F`, h로 몇 계약을 매수/매도해야 하는가?”
  - 파라미터: 목표 계약수 `N=1..500`, `h100=20..150`의 10 단위, `Q_F=10..1,000`; `Q_A=N×Q_F×100/h100`.
  - 정수 보장: N을 먼저 뽑아 QA를 역산하며 QA가 정수일 때만 채택한다. 롱 현물 헤지는 일반적으로 선물 매도임을 별도 채점한다.
- **참고**: [중앙대 선물 헤징 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/04.pdf), [MIT 15.433 Futures 문제·해설](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/), [CME A Trader's Guide to Futures PDF](https://www.cmegroup.com/education/files/a-traders-guide-to-futures.pdf)

### DER-04. Call·Put Payoff

- **개념·수식**: 만기 콜 payoff `max(S_T−K,0)`, 풋 payoff `max(K−S_T,0)`; 매도 포지션 payoff는 부호가 반대다. Payoff에는 최초 프리미엄을 넣지 않는다.
- **유형 A — 단일 옵션 payoff (`L1`)**: “행사가, 만기주가, 계약승수, 계약수로 롱/숏 콜·풋 만기 payoff를 구하라.”
  - 파라미터: `K=1,000..100,000원`의 100원 단위, `S_T=0.5K..1.5K`의 100원 단위, 승수 `M∈{1,10,100}`, 계약수 `N=1..20`, 포지션 부호 `±1`.
  - 정수 보장: 모든 금액·수량이 정수이므로 `±N×M×max(...)`도 정수다. ATM과 ITM/OTM을 균등 표집한다.
- **유형 B — 보호적 풋·커버드콜 payoff (`L2`)**: 주식 1단위와 옵션 1단위 결합 포지션의 만기가치를 묻는다.
  - 파라미터: 유형 A 가격 범위, `S_0`은 payoff 계산에서 제외하고 `K,S_T`만 사용; 주식·옵션 수량비 1:1.
  - 정수 보장: `protective put=max(S_T,K)`, `covered call=min(S_T,K)`의 정수 성질을 이용한다.
- **참고**: [MIT 15.401 Options 강의·PDF](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/options), [Yale Financial Markets Options 강의](https://oyc.yale.edu/economics/econ-252-11/lecture-17), [Hull 11e](https://www.pearson.com/en-us/subject-catalog/p/options-futures-and-other-derivatives/P200000005938/9780136939917)

### DER-05. 옵션 Profit·손익분기점·전략손익

- **개념·수식**: 롱 콜 profit `max(S_T−K,0)−c`; 롱 풋 `max(K−S_T,0)−p`; 콜 손익분기점 `K+c`, 풋 손익분기점 `K−p`. 복합전략은 각 leg의 profit을 합한다.
- **유형 A — 단일 옵션 profit·BEP (`L1`)**: “프리미엄까지 포함한 만기손익 또는 손익분기 주가를 구하라.”
  - 파라미터: `K=1,000..100,000원`의 100원 단위, 프리미엄 `c,p=10..10,000원`의 10원 단위이며 `≤20%K`, `S_T=0.5K..1.5K`, `M∈{1,10,100}`, `N=1..20`.
  - 정수 보장: 정수 입력의 덧셈·max 연산만 사용한다.
- **유형 B — Long straddle 또는 bull call spread (`L2`)**: 같은 행사가 콜·풋을 매수한 straddle 손익, 또는 `K_1<K_2`인 콜스프레드 손익을 계산한다.
  - 파라미터: `K_1,K_2,S_T=1,000..100,000원`의 100원 단위, 각 프리미엄 10원 단위, 총 순프리미엄이 스프레드 폭보다 작도록 제한.
  - 정수 보장: 완성된 leg별 정수 손익을 합산한다. 무위험 차익이 생기는 비정상 프리미엄 조합은 거절한다.
- **참고**: [MIT 15.401 Options](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/options), [Yale Options 강의·문제](https://oyc.yale.edu/economics/econ-252-11/lecture-17), [중앙대 CPA 파생 문제·해설 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/10.pdf)

### DER-06. Put–Call Parity·차익거래

- **개념·수식**: 무배당 유럽형 옵션에서 `C+PV(K)=P+S_0`, 즉 `C−P=S_0−PV(K)`. 만기와 행사가가 같은 콜·풋이어야 한다.
- **유형 A — 빠진 옵션가격/행사가 PV (`L1`)**: 네 항 중 하나를 가리고 parity로 계산한다.
  - 파라미터: `S_0=1,000..100,000원`, `PV(K)=0.7S_0..1.2S_0`, 풋 `P=10..20,000원`; `C=P+S_0−PV(K)`.
  - 정수 보장: 세 정수를 먼저 뽑아 네 번째를 역산하며 `0<C≤S_0`, `0<P≤PV(K)`일 때 채택한다.
- **유형 B — parity 위반 차익 (`L2`)**: 시장 콜 또는 풋 가격을 공정가보다 `δ`만큼 틀리게 제시하고 무차익 이익과 거래 방향을 묻는다.
  - 파라미터: 유형 A 공정가격, `δ=10..5,000원`, 과대/과소 부호 무작위.
  - 정수 보장: 초기 확정이익은 정확히 δ다. `C+PV(K)>P+S`이면 좌변을 매도하고 우변을 매수하며, 반대면 역거래한다.
- **참고**: [MIT 15.401 Options](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/options), [중앙대 CPA 파생 문제·완전해설 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/10.pdf), [Hull 11e](https://www.pearson.com/en-us/subject-catalog/p/options-futures-and-other-derivatives/P200000005938/9780136939917)

### DER-07. Binomial Option Pricing

- **개념·수식**: 1기간 주식가 `S_u=uS_0`, `S_d=dS_0`; 무차익 조건 `d<R<u`; 위험중립확률 `q=(R−d)/(u−d)=(RS_0−S_d)/(S_u−S_d)`; 옵션가 `V_0=[qV_u+(1−q)V_d]/R`; 복제 델타 `Δ=(V_u−V_d)/(S_u−S_d)`.
- **유형 A — 1기간 콜/풋 가격 (`L2`)**: `S_0,S_u,S_d,K,r`를 주고 q와 옵션가격을 계산한다.
  - 파라미터: `q_num∈{25,50,75}`, `r∈{0,5,10}%`, `S_d=20..150`, `S_u=S_d+20..200`, `K=S_d..S_u`. 후보별로 `S_0=[q_numS_u+(100−q_num)S_d]/(100+r)`, `V_0=[q_numV_u+(100−q_num)V_d]/(100+r)`를 계산한다.
  - 정수 보장: `S_0`와 `V_0`가 모두 정수이고 `S_d<(1+r/100)S_0<S_u`인 후보만 채택한다. q 답은 `q×100` 정수다.
- **유형 B — 복제 delta (`L2`)**: 주가 트리와 옵션 만기 payoff로 `Delta×100`을 구한다.
  - 파라미터: 유형 A의 채택 트리, `Δ100=100(V_u−V_d)/(S_u−S_d)`.
  - 정수 보장: terminal price spread가 payoff 차이의 `100`배를 나누어떨어뜨리는 트리만 채택한다.
- **참고**: [중앙대 이항모형 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/06.pdf), [중앙대 CPA 파생 문제·완전해설 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/07.pdf), [MIT 15.401 Options](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/options)

### DER-08. Black–Scholes–Merton

- **개념·수식**: 무배당 유럽형 콜 `C=S_0N(d_1)−Ke^(−rT)N(d_2)`; 풋 `P=Ke^(−rT)N(−d_2)−S_0N(−d_1)`; `d_1=[ln(S_0/K)+(r+σ²/2)T]/(σ√T)`, `d_2=d_1−σ√T`.
- **중요 생성 원칙**: Android 계산형에서는 `ln`, `e`, 정규 CDF를 직접 계산시키지 않는다. 문제에 암산 친화적인 `N(d)` 값을 정수 %로 제공하고 BSM 구조에 대입하게 하며, 근사·반올림이 필요한 tuple은 전부 폐기한다.
- **유형 A — 제공 CDF 대입형 (`L2`)**: `S_0`, `PV(K)=Ke^(−rT)`, `N(d1)`, `N(d2)`를 주고 콜 가격을 구한다.
  - 파라미터: `S_0,PV(K)=10,000..200,000원`의 10,000원 단위, `N1Pct,N2Pct∈{25,50,75}`, `N1Pct>N2Pct`. 지문은 해당 lookup 값을 이미 계산된 값으로 제공한다.
  - 정수·암산 보장: `C=S_0×N1Pct/100−PV(K)×N2Pct/100`. 두 정확한 % 계산과 한 번의 뺄셈이 score 4 이하이고 `0<C<S_0`인 tuple만 저장한다.
- **유형 B — ATM-forward BSM (`L2`)**: `S_0=PV(K)`이고 지문이 `N(d1)−N(d2)`를 제공할 때 `C=S_0[N(d1)−N(d2)]`를 계산한다.
  - 파라미터: `S_0=10,000..200,000원`의 10,000원 단위, `cdfGapPct∈{5,10,20,25}`.
  - 정수·암산 보장: `C=S_0×cdfGapPct/100`이 정확한 정수이고 audit를 통과한 tuple만 사용한다. 반올림형 fallback은 없다.
- **참고**: [Hull 11e 공식 교재 페이지](https://www.pearson.com/en-us/subject-catalog/p/options-futures-and-other-derivatives/P200000005938/9780136939917), [MIT 15.401 Options](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/video-lectures-and-slides/options), [중앙대 Greeks·옵션헤징 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/08.pdf)

### DER-09. Greeks·Delta Hedge·근사 P&L

- **개념·수식**: `Delta=∂V/∂S`, `Gamma=∂²V/∂S²`, `Vega=∂V/∂σ`, `Theta=∂V/∂t`, `Rho=∂V/∂r`; 2차 근사 `ΔV≈DeltaΔS+0.5Gamma(ΔS)²+VegaΔσ+ThetaΔt+RhoΔr`.
- **유형 A — Delta-neutral 주식 수 (`L1`)**: “옵션 delta와 계약승수·계약수로 중립화를 위해 거래할 주식 수와 방향을 구하라.”
  - 파라미터: `Delta×100=10..90`(콜) 또는 `−90..−10`(풋), 승수 `M=100`, 계약수 `N=1..500`, 옵션 포지션 부호 `±1`.
  - 정수 보장: 필요 주식수 `−position×Delta100×N`주로 정확한 정수다.
- **유형 B — Greek risk report P&L (`L2`)**: 표준화된 Greek 금액민감도를 제공해 `Delta+Gamma`, 또는 `Vega+Theta+Rho` 기여를 합산한다. 예: Delta exposure는 기초자산 1% 변화당 원, Gamma exposure는 `(1%p)²`당 원으로 정의한다.
  - 파라미터: `D,V,Theta,Rho=−100,000..100,000원/단위`의 100원 단위, `Gamma=−100,000..100,000`의 짝수, 기초자산 변화 `x=−5..5%`(0 제외), 변동성 변화 `v=−10..10%p`, 일수 `t=1..10`, 금리변화 `r=−3..3%p`.
  - 정수 보장: `P&L=D×x+0.5Gamma×x²+V×v+Theta×t+Rho×r`; Gamma를 짝수로 생성한다. 문제마다 사용하지 않는 shock은 0으로 명시한다.
- **참고**: [중앙대 Greeks와 옵션헤징 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/08.pdf), [Hull 11e](https://www.pearson.com/en-us/subject-catalog/p/options-futures-and-other-derivatives/P200000005938/9780136939917), [MIT 15.433 Simulation Based Option Problem](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/)

### DER-10. Swap Cash Flows·Netting

- **개념·수식**: 이자율스왑에서 기간 초 확정된 변동금리 `L_{t−1}`를 기간 말에 지급한다. 고정금리 지급·변동금리 수취자의 순현금흐름은 `CF_t=N(L_{t−1}−K)α_t`, `α_t=days/B`. 동일 통화 plain-vanilla swap은 원금을 교환하지 않는다.
- **유형 A — 단일 결제일 순현금흐름 (`L1`)**: “명목원금, 고정금리, 직전 reset 변동금리, day-count로 순수취/지급액을 구하라.”
  - 파라미터: `N=1,000,000..1,000,000,000원`, `K,L=1..12%` 정수, `days∈{30,60,90,180}`, `B=360`, `L≠K`.
  - 정수 보장: N을 `36,000/gcd(|L−K|×days,36,000)`의 배수로 만든다. 고정지급자 기준 `CF=N(L−K)days/36,000`이 정수다.
- **유형 B — 2~4회 reset 누적 net cash flow (`L2`)**: 여러 기간의 `L_t` 표를 주고 각 기간 순현금흐름 또는 누적합을 계산한다.
  - 파라미터: `n=2..4`, 각 `L_t=0..15%`, `K=1..12%`, 동일 `days∈{90,180}`, N은 모든 기간 분모 조건의 최소공배수로 생성.
  - 정수 보장: 각 기간 현금흐름이 정수가 되도록 필요한 N의 최소배수를 계산해 그 배수만 표집한다. 문제는 반드시 어느 쪽의 관점인지 명시한다.
- **참고**: [MIT 15.433 Forwards, Futures & Swaps 강의노트](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/lecture-notes/), [Hull 11e](https://www.pearson.com/en-us/subject-catalog/p/options-futures-and-other-derivatives/P200000005938/9780136939917), [중앙대 CPA 파생 문제·해설 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/10.pdf)

## F. 주식 리서치·기업가치평가 (`EQV`)

### F.1 개념·문제 유형·난수 명세

| ID | 요소와 핵심 수식 | 생성할 문제 유형(1개 이상) | 파라미터 범위와 정수답 보장 | 주 참고 |
|---|---|---|---|---|
| **EQV-01** | P×Q 매출 추정: `Revenue = Price × Quantity` | “제품 평균단가가 `P억원/천개`, 판매량이 `Q천개`일 때 매출은?” 산업별로 제품/점포/가입자/객실 등 드라이버 명칭을 교체한다. | `P: 1…20`, `Q: 10…200`; 답 `P×Q`억원. 성장형 변형은 `Q1=Q0×(100+g)/100`이 정수가 되도록 `Q0=(100/gcd(100,g))×k`, `g: 5…50`로 생성한다. | R-YIG, R-DCF |
| **EQV-02** | 마진과 영업이익: `EBIT = Revenue × (grossMargin − sgaMargin)` | “매출, 매출총이익률, 판관비율이 주어졌을 때 영업이익과 영업이익률 중 하나를 계산하라.” | `Revenue=100k`, `k: 5…100`; `grossMarginPct: 30…75`, `sgaPct: 5…35`, 제약 `grossMarginPct−sgaPct≥5`. 답 EBIT=`k×(grossMarginPct−sgaPct)`억원. | R-YIG, R-DCF |
| **EQV-03** | 현금세율·NOPAT: `NOPAT = EBIT×(1−t)` | “영업이익과 현금세율이 주어질 때 NOPAT은?” 세율 상승 전후 차이를 묻는 변형도 허용한다. | `EBIT=100k`, `k: 2…100`; `taxPct: 10…35`. 답 `k×(100−taxPct)`억원. 세율차 변형은 `ΔtaxPct: 1…10`, 답 `−k×ΔtaxPct`. | R-DCF, R-CF |
| **EQV-04** | 운전자본: `NWC = Revenue×nwcRatio`, `ΔNWC=NWC1−NWC0` | “매출 증가액과 매출 대비 NWC 비율이 주어질 때 추가 운전자본 투자액은?” | `Revenue0=100k0`, `ΔRevenue=100kg`; `k0: 5…100`, `kg: 1…30`, `nwcPct: 5…30`. 답 `kg×nwcPct`억원. | R-DCF |
| **EQV-05** | 설비투자·감가상각: `Net Capex = Capex−D&A` | “CAPEX와 감가상각비가 주어질 때 순설비투자 및 FCFF 감소액은?” | `Capex: 50…1500 / step 10`, `D&A: 20…1000 / step 10`, 제약 `Capex>D&A`; 답 `Capex−D&A`억원. 유지보수/성장 CAPEX 명칭 변형을 둔다. | R-DCF, R-YIG |
| **EQV-06** | 3개 재무제표 연결: `CFO=NI+D&A−ΔNWC`; `EndCash=BeginCash+CFO−Capex+DebtIssued−Dividend` | “당기순이익에서 현금흐름표를 거쳐 기말 현금까지 연결하라.” 해설에서 NI→이익잉여금, D&A의 손익/현금/자산 효과를 함께 설명한다. | `BeginCash: 100…2000`, `NI: 50…1000`, `D&A: 10…300`, `ΔNWC: −100…300 / step 10`, `Capex: 20…500`, `DebtIssued: 0…500 / step 10`, `Dividend: 0…200 / step 10`; `EndCash≥0`인 조합만 채택. 답은 위 정수식. | R-ACC, R-DCF |
| **EQV-07** | 기본 EPS: `EPS=(NI−PreferredDividend)/WeightedAvgDilutedShares` | “순이익, 우선주배당, 가중평균 희석주식수로 EPS를 계산하라.” | 잠재 답 `eps: 500…5000 / step 100`; `shares: 10…300`백만주; `prefDiv: 0…1000 / step 100`; `NI=eps×shares+prefDiv`백만원으로 derived. 답 `eps`원. | R-ACC, R-MITFIN |
| **EQV-08** | PER: `PER=Price/EPS` | “주가와 선행 EPS로 선행 PER을 계산하라.” 또는 목표 PER로 목표주가를 계산한다. | `eps: 500…8000 / step 100`; 잠재 `per: 5…35`; `price=eps×per` derived. PER 질문 답 `per`x, 목표가 질문 답 `price`원. | R-REL, R-YIG |
| **EQV-09** | ROE: `ROE=NI/AverageEquity` | “평균 자기자본과 순이익으로 ROE를 계산하라.” | `AverageEquity=100k`, `k: 5…200`; 잠재 `roePct: 5…35`; `NI=k×roePct`억원 derived. 답 `roePct`%. | R-REL, R-ACC |
| **EQV-10** | PBR: `PBR=Price/BPS`, 보조관계 `PBR≈PER×ROE` | “주가와 주당순자산으로 PBR을 계산하라.” | `bps: 5,000…50,000 / step 1,000`; 잠재 `pbr: 1…6`; `price=bps×pbr` derived. 답 `pbr`x. `PBR=PER×ROE` 변형은 `PER: 5…25`, `ROE%: choice{10,20,30,40}`, 곱을 %로 환산해 정수 PBR이 되는 조합만 채택한다. | R-REL |
| **EQV-11** | EV와 EV/EBITDA: `EV=MarketCap+Debt+Preferred+Minority−Cash`; `EV/EBITDA=EV/EBITDA` | “시가총액·순부채로 EV를 구하고 EV/EBITDA를 계산하라.” 한 문제에서는 최종 배수 하나만 답하게 한다. | `EBITDA: 100…3000 / step 50`, 잠재 `multiple: 4…20`, `EV=EBITDA×multiple`; `Debt: 0…5000 / step 50`, `Preferred, Minority: 0…500 / step 50`, `Cash: 0…2000 / step 50`; `MarketCap=EV−Debt−Preferred−Minority+Cash>0` derived. 답 `multiple`x. | R-REL, R-DCF |
| **EQV-12** | FCFF: `FCFF=EBIT(1−t)+D&A−Capex−ΔNWC = NOPAT+D&A−Capex−ΔNWC` | “NOPAT, 감가상각, CAPEX, ΔNWC로 FCFF를 계산하라.” | `NOPAT: 100…3000 / step 10`, `D&A: 10…500 / step 10`, `Capex: 20…800 / step 10`, `ΔNWC: −100…400 / step 10`; `FCFF>0`인 조합만 채택. 답 위 정수식. | R-DCF, R-CF |
| **EQV-13** | WACC: `wE×kE + wD×kD×(1−t)`; 문제에는 세후부채비용을 직접 줄 수도 있다. | “시가가중 자기자본비용과 세후부채비용으로 WACC를 계산하라.” | `wE: 40…90 / step 10`, `wD=100−wE`; `kE: 8…20`, `kDafterTax: 2…10`, 제약 `kE>kDafterTax` 및 `(wE×kE+wD×kDafterTax)%100=0`. 가능한 조합 카탈로그에서 추출. 답 정수 %. | R-DCF, R-CF |
| **EQV-14** | 명시기간 DCF: `EVexplicit=Σ FCFF_t/(1+WACC)^t` | “2~3년 FCFF를 WACC로 할인한 명시기간 가치 합계를 계산하라.” | `rPct: choice{10,20,25}`. `(100+r)/100=p/q`를 기약분수로 만들고 `n: choice{2,3}`, `k_t: 1…20`; `FCFF_t=p^t×k_t` derived. 각 PV=`q^t×k_t`, 답 `Σq^t×k_t`억원으로 정확한 정수. | R-MITFIN, R-DCF |
| **EQV-15** | 계속가치: `TV=FCFF_(n+1)/(WACC−g)` | “다음 해 FCFF, WACC, 영구성장률로 n년 말 TV를 계산하라.” | `WACCpct: 8…15`, `gPct: 1…5`, 제약 `WACC−g≥3`; `k: 10…500`; `FCFFnext=k×(WACCpct−gPct)` derived. 답 `TV=100k`억원. `g<WACC`를 개념 체크에도 사용한다. | R-DCF, R-DCF25 |
| **EQV-16** | Peer multiple: `ImpliedEV=PeerMedianMultiple×TargetMetric` | “5개 비교기업 배수의 중앙값을 적용해 목표기업의 내재 EV를 구하라.” | 서로 다른 `peerMultiple[5]: 4…25` 정수, 극단치 1개를 선택적으로 포함; `metric: 100…3000 / step 50`. 중앙값이 정수이므로 답 `median×metric`억원. 산업·배수(PER/EV-EBITDA)를 stem에서 교체하되 분모는 일치시킨다. | R-REL, R-YIG |
| **EQV-17** | 목표주가·상승여력: `Upside=(Target/Current−1)×100` | “현재가와 목표가로 상승여력을 계산하라.” 또는 상승여력으로 목표가를 역산한다. | 잠재 `upsidePct: 5…60`; `base=100/gcd(100,upsidePct)`, `current=base×k`, `k: 10…300`; `target=current×(100+upsidePct)/100` derived. 답 `upsidePct`% 또는 정수 target원. | R-YIG, R-REL |
| **EQV-18** | 민감도: `ΔEV=EBITDA×ΔMultiple`; `ΔPrice=ΔEV/Shares` | “동일 EBITDA에서 적용배수가 1~2턴 변할 때 주당가치 변화는?” | 이 유형만 `EBITDA`는 백만원, `shares`는 백만주로 표시한다. `shares: 10…300`, `k: 10…300`, `EBITDA=shares×k`백만원; `Δmultiple: choice{−2,−1,1,2}`. `백만원/백만주=원/주`이므로 답 `k×Δmultiple`원. 숫자뿐 아니라 `WACC↑ → DCF↓` 방향성 꼬리질문을 붙인다. | R-REL, R-DCF |
| **EQV-19** | 시나리오 가중가치: `ExpectedPrice=Σp_s×Price_s` | “Bear/Base/Bull 확률과 목표주가로 확률가중 목표가를 계산하라.” | `pBear,pBase,pBull: 10…70 / step 10`, 합 100, 각 ≥10; `priceBear,priceBase,priceBull: 10…500 / step 10`, `Bear<Base<Bull`. 각 곱이 100의 배수이므로 답 정수원. | R-DCF, R-YIG |

### F.2 EQV 해설에 반드시 포함할 개념

- 추정치와 가치평가를 분리한다. `P×Q → 매출 → 마진 → EBIT/NOPAT → 재투자 → FCFF → 할인 → EV → 순부채 차감 → 지분가치 → 주당가치`의 연결 경로를 모든 관련 해설에 표시한다.
- PER·PBR·EV/EBITDA는 분자와 분모의 청구권을 일치시킨다. `EV`에는 채권자·우선주·비지배주주 몫이 포함되므로 `EBITDA/EBIT`과 대응하고, 보통주 시가총액은 `EPS/순이익/BPS`와 대응한다.
- 목표가 해설은 숫자 하나로 끝내지 않고 `핵심 가정`, `촉매`, `하방 위험`, `가정이 틀렸을 때 가장 민감한 입력` 한 줄씩을 붙인다. 이 네 항목은 채점 대상이 아닌 면접 꼬리질문이다.
- DCF에서 `g≥WACC`, 음의 주식수, 음의 EV처럼 경제적으로 무의미한 조합은 생성 단계에서 금지한다.

### F.3 실무 기업 리서치 확장 요소 (`EQV-20~64`)

아래 요소는 학회 공개자료의 범위를 넘어 실제 기업 리서치에 필요한 운영 KPI, 이익의 질, 자본효율성, 회계조정, 산업별 분석과 투자논리를 보강한다. `C/N`은 개념형과 정수답 계산형을 모두 만들고, `C`는 개념·사례판단 중심이라는 뜻이다. 계산형 열의 `답`은 별도 표시가 없으면 정수이며, 해당 요소의 `Q01`로 등록한다.

#### F.3.1 매출 드라이버와 단위경제성

| ID·모드 | 핵심 공식·관계 | 개념형 scope | 계산형 일반화 문제·파라미터·정수 보장 | 주 참고 |
|---|---|---|---|---|
| **EQV-20 C/N** | 매출 브리지: `ΔRevenue = Organic + FX + M&A + Divestiture + ScopeChange` | 보고 성장과 organic·constant-currency 성장, 인수성장과 기존사업 성장, 성장률 단순 가감의 한계 | 각 증감액 `Organic: 50…1,000`, `FX: −300…300`, `M&A: 0…800`, `Divestiture: −500…0`, `Scope: −200…200`억원/step 10. 답은 다섯 항의 정수합. | ER-SEC-EDGAR, ER-DART-API |
| **EQV-21 C/N** | 제품별 `R=ΣP_iQ_i`; 순차 P/Q 브리지 `ΔR=(P1−P0)Q0 + P1(Q1−Q0)` | ASP 상승이 순수 가격인지 mix인지, 분해 순서에 따른 교호항 귀속, 제품별 드라이버 | `P0,P1: 1…30`억원/천개, `Q0,Q1: 10…300`천개, 각 변화 0 제외. 가격효과와 물량효과를 `integer_tuple`로 답한다. | ER-DAMO-TOOLKIT |
| **EQV-22 C/N** | `M=Σw_i m_i`; 연결 EBIT=`Σ SegmentEBIT−CorporateCost−Elimination` | 저마진 사업 mix 상승 시 연결마진 하락, segment와 연결 수치, 공통비 배부 | 사업부 2~4개, `Revenue_i=100k_i`, `k_i: 1…50`, `margin_i: 5…40%`, `corporateCost: 0…500`억원. 답 EBIT=`Σk_i×margin_i−cost`가 양수인 조합만 채택. | ER-SEC-EDGAR, ER-DART-API |
| **EQV-23 C/N** | `ARR_end=ARR_begin+New+Expansion−Contraction−Churn`; `NRR=(Begin+Expansion−Contraction−Churn)/Begin`; `GRR=(Begin−Contraction−Churn)/Begin` | NRR 100% 초과와 고객수 감소의 공존, ARR·매출·billings·계약부채 차이, 회사별 KPI 정의 | `BeginARR=100k`, `k: 10…200`, `expansionPct: 0…40`, `contractionPct: 0…20`, `churnPct: 0…30`, 합리적 범위 `50≤NRR≤150`. 금액은 각각 `k×pct`로 생성해 답 NRR가 정수 %. | ER-IFRS15, ER-SEC-NONGAAP |
| **EQV-24 C/N** | `CAC=AcquisitionS&M/NewCustomers`; 단순 `LTV≈ARPU×GrossMargin/Churn`; `Payback=CAC/MonthlyCustomerGrossProfit` | cohort 선택편향, 선불·장기계약의 현금효과, 높은 LTV/CAC가 항상 좋은 사업은 아닌 이유 | 잠재 `paybackMonths: 3…36`, `monthlyGrossProfit: 10…500`천원; `CAC=payback×monthlyGrossProfit` derived. 답 payback 개월. LTV는 churn 0일 때 생성 금지. | ER-SEC-NONGAAP |
| **EQV-25 C/N** | `Sales=Stores×SalesPerStore`; `SalesPerStore=Traffic×Conversion×AverageTicket` | same-store sales와 신규점 효과, cannibalization, 트래픽·전환율·객단가 연결 | `stores: 10…500`, `traffic: 100…2,000`명, `conversionPct: 10…80`. `traffic=100k` 형태로 표집하고 `averageTicket: 1…20`만원; 점포당 매출=`k×conversionPct×ticket`만원, 총매출은 여기에 stores를 곱한 정수. | ER-SEC-EDGAR |
| **EQV-26 C/N** | `NetRevenue=GMV×TakeRate`; `ContributionProfit=NetRevenue−VariableCosts` | GMV와 회계상 매출, principal-agent gross/net 판단, take rate 상승의 생태계 영향 | `GMV=100k`억원, `k: 10…500`, `takeRatePct: 1…30`, `variableCost: 0…takeRevenue / step 10`. 답 net revenue 또는 contribution profit 정수억원. | ER-IFRS15, ER-SEC-NONGAAP |
| **EQV-27 C/N** | `Revenue=Capacity×Utilization×Yield`; `UnitContribution=Price−VariableCost`; `BreakEvenUnits=FixedCost/UnitContribution` | 가동률·영업레버리지, 가격·물량 변화의 비대칭, 호텔 `RevPAR=ADR×Occupancy` 등 산업 치환 | 손익분기형은 `unitContribution: 1…50`만원, `breakEvenUnits: 10…5,000`, `fixedCost=contribution×units` derived. 답 units. 가동률형은 `capacity=100k`와 정수 이용률을 사용. | ER-SEC-EDGAR |
| **EQV-28 C/N** | `Backlog_end=Backlog_begin+Bookings−RevenueRecognized−Cancellations±FX`; `BookToBill=Bookings/Revenue` | backlog·RPO·수주·계약부채 차이, book-to-bill 1배 초과의 의미와 한계, 고정가 수주의 원가위험 | `begin: 0…5,000`, `bookings: 100…3,000`, `revenue: 100…3,000`, `cancellations: 0…500`, `FX: −200…200`억원/step 10, ending≥0만 채택. Book-to-bill형은 `ratio100: 50…200`, `revenue=100k`, `bookings=k×ratio100`; 정수답은 **배수×100**인 `ratio100`(예: 120=`1.20x`)이고 UI는 `ratio100/100`배로 표시한다. | ER-IFRS15, ER-SEC-EDGAR |

비표준 KPI인 ARR·NRR·GMV·backlog·RPO는 회사마다 정의가 다르다. DB에 `metricDefinition`, `inclusionRules`, `periodBasis`, `issuerSource`, `asOfDate`를 저장하고, 서로 다른 회사의 KPI를 정의 확인 없이 직접 비교하는 문항은 금지한다.

#### F.3.2 이익의 질과 회계 조정

| ID·모드 | 핵심 공식·관계 | 개념형 scope | 계산형 일반화 문제·파라미터·정수 보장 | 주 참고 |
|---|---|---|---|---|
| **EQV-29 C/N** | `AccrualRatio=(NI−CFO)/AverageAssets`; `CashConversion=CFO/NI` | NI 증가·CFO 감소, 적자 또는 일회성 운전자본 변동에서 비율의 한계, 현금전환의 지속성 | `AverageAssets=100k`, `k: 10…500`, 잠재 `accrualPct: −20…30`, `NI: 100…3,000`; `CFO=NI−k×accrualPct` derived. 답 accrual ratio 정수 %. | ER-SEC-FRM, ER-CFA-QUALITY |
| **EQV-30 C/N** | `DSO=AvgAR/Revenue×Days`; `DIO=AvgInventory/COGS×Days`; `DPO=AvgAP/Purchases×Days`; `CCC=DSO+DIO−DPO` | 음의 운전자본, 성장 둔화 시 현금효과 반전, DPO에 purchases가 더 적합한 이유 | `days∈{360,365}`, 잠재 `DSO,DIO,DPO: 5…120`. 각 분모를 `days×k`로 만들고 평균잔액=`k×targetDays` derived. 답 CCC 정수일. | ER-SEC-FRM, ER-DART-API |
| **EQV-31 C/N** | 근사 `Billings=Revenue−ΔContractAsset+ΔContractLiability` | IFRS 15의 5단계, 계약자산·매출채권·계약부채, principal-agent, 계약부채 증가와 이익의 차이 | `Revenue: 100…5,000`, `ΔContractAsset, ΔContractLiability: −500…500`억원/step 10. billings≥0만 채택하고 답은 정수합. | ER-IFRS15 |
| **EQV-32 C/N** | `InventoryTurnover=COGS/AvgInventory`; `AllowanceRatio=Allowance/GrossReceivables` | AR·재고가 매출보다 빨리 증가하는 정상 원인과 적신호, 반품·대손·재고평가충당 | 잠재 `turnover: 1…15`, `AvgInventory: 10…500`억원, `COGS=turnover×inventory` derived. 충당률형은 `GrossAR=100k`, `Allowance=k×ratioPct`. | ER-SEC-FRM, ER-DART-API |
| **EQV-33 C/N** | R&D 자산화 조정 `AdjustedEBIT=ReportedEBIT+CurrentR&D−ResearchAmortization`; `NetCapex=Capex−D&A` | 비용 자산화가 이익·ROIC에 미치는 효과, maintenance/growth capex, 개발비와 R&D | `ReportedEBIT: 100…3,000`, `CurrentR&D: 10…1,000`, `Amortization: 0…800`억원/step 10, 조정 EBIT>0만 채택. 답은 정수억원. | ER-DAMO-TOOLKIT, ER-SEC-FRM |
| **EQV-34 C/N** | `NormalizedEBIT=ReportedEBIT−NonOperatingGains+TrueOneOffLosses±PolicyAdjustments` | 매년 반복되는 “일회성” 비용, adjusted EBITDA 조정의 대칭성·일관성·현금성 | `ReportedEBIT: 100…5,000`, `gains: 0…1,000`, `oneOffLoss: 0…1,000`, `policyAdj: −500…500`억원/step 10. 답 normalized EBIT>0인 조합. | ER-SEC-NONGAAP, ER-CFA-QUALITY |
| **EQV-35 C/N** | Treasury-stock method `IncrementalShares=Options×max(P−K,0)/P`; `FD Shares=Basic+Incremental+RSU+Convertibles` | SBC의 비현금성과 경제적 비용, FCF 가산과 희석 무시의 이중 오류, 자사주와 희석 | `P: 10…100`, `K: 1…P−1`천원, `m: 1…50`, `Options=P×m`만주 derived. 답 incremental shares=`m×(P−K)`만주. OTM 옵션은 0. | ER-SEC-SBC, ER-IFRS2 |
| **EQV-36 C/N** | `LeaseAdjustedNetDebt=Debt+LeaseLiabilities−Cash` | IFRS 16 이후 EBITDA·CFO가 높아 보이는 이유, 리스부채와 pre/post-lease 배수 일치 | `Debt: 0…10,000`, `LeaseLiability: 0…5,000`, `Cash: 0…5,000`억원/step 50. 답 lease-adjusted net debt; 음수도 허용. | ER-IFRS16 |
| **EQV-37 C/N** | `FundedStatus=PlanAssets−DBO`; debt-like deficit=`max(DBO−PlanAssets,0)` | 할인율 민감도, service cost와 finance component, 미적립 연금의 debt-like 성격 | `PlanAssets, DBO: 100…10,000`억원/step 50. 답 funded status 또는 deficit 정수억원. | ER-IAS19 |
| **EQV-38 C/N** | `BookETR=TaxExpense/PBT`; 진단용 `CashTaxRate=CashTaxesPaid/PBT`; `NOLShield=UsableNOL×TaxRate` | 낮은 세율의 지속가능성, DTA·DTL·valuation allowance, 현금세율과 회계세율 | `PBT=100k`, `k: 10…500`, `taxPct: 0…40`, `TaxExpense=k×taxPct`. 답 ETR 정수 %. NOL형은 `NOL=100k`로 shield가 정수. | ER-SEC-FRM |
| **EQV-39 C/N** | `Goodwill=Consideration+NCI+FVPreviousInterest−FVIdentifiableNetAssets` | 인수성장과 organic growth, 무형자산 상각·goodwill impairment, 손상의 신호 | 각 항 `0…20,000`억원/step 100, consideration>0, goodwill≥0인 조합만 채택. 답 goodwill 정수억원. | ER-SEC-FRM |
| **EQV-40 C/N** | `CommonEquityValue=OperatingEV+NonOperatingAssets−Debt−Preferred−NCI−OtherDebtLikeClaims` | 연결 EBITDA 100%와 NCI, 지분법투자, 리스·연금·supplier finance·factoring 분류 | `OperatingEV: 1,000…50,000`, 나머지 항 `0…10,000`억원/step 100, equity>0만 채택. 답 common equity value. | ER-DAMO-TOOLKIT, ER-SEC-FRM |

#### F.3.3 ROIC·ROE·성장·재투자

| ID·모드 | 핵심 공식·관계 | 개념형 scope | 계산형 일반화 문제·파라미터·정수 보장 | 주 참고 |
|---|---|---|---|---|
| **EQV-41 C/N** | `ROIC=NOPAT/AverageInvestedCapital`; `IC=OperatingAssets−NonInterestBearingOperatingLiabilities` | 분자·분모 조정 일치, 초과현금 제외, 리스·R&D 조정의 양면 적용 | `AverageIC=100k`, `k: 10…500`, 잠재 `roicPct: 1…40`, `NOPAT=k×roicPct` derived. 답 ROIC 정수 %. | ER-DAMO-TOOLKIT |
| **EQV-42 C/N** | `ROIC=NOPATMargin×InvestedCapitalTurnover` | 고마진·저회전과 저마진·고회전 비교, ROIC 개선 원인 분해 | `marginPct: 2…30`, `turnover: 1…5`; 답 `marginPct×turnover`%. 비교형은 두 회사의 정수 ROIC를 계산한다. | ER-DAMO-TOOLKIT |
| **EQV-43 C/N** | `IncrementalROIC=ΔNOPAT/ΔInvestedCapital`; 실무는 3~5년 누적값 권장 | 기존 ROIC와 신규투자 수익률, 인수·FX·손상의 단년도 왜곡 | `ΔIC=100k`, `k: 5…300`, `incrementalRoicPct: −10…40`, `ΔNOPAT=k×rate`. 답 정수 %, ΔIC>0. | ER-DAMO-TOOLKIT |
| **EQV-44 C/N** | 5단계 DuPont `ROE=(NI/EBT)×(EBT/EBIT)×(EBIT/Sales)×(Sales/AvgAssets)×(AvgAssets/AvgEquity)` | 영업개선과 레버리지 증가, 자사주로 장부자본 감소, 기간·평균잔액 일치 | 세 부담·이자 부담·EBIT margin은 `10…100% / step 5`, asset turnover `1…4`, equity multiplier `1…5`. 전체 곱/`10000`이 정수인 검증 카탈로그만 사용. | ER-SEC-FRM, ER-DAMO-TOOLKIT |
| **EQV-45 C/N** | 기업 성장 `g≈ReinvestmentRate×IncrementalROIC`; 주주이익 `g≈RetentionRatio×ROE` | `ROIC<WACC` 성장의 가치파괴, 안정기 `ReinvestmentRate=g/ROIC`, 성장률보다 재투자수익률 | `reinvestmentPct, incrementalRoicPct: 0…100 / step 5` 중 곱이 100으로 나누어지는 pair만 채택. 답 `g=product/100` 정수 %. | ER-DAMO-TOOLKIT |
| **EQV-46 C/N** | `EVA=NOPAT−WACC×IC=(ROIC−WACC)×IC` | 이익 성장과 가치창출의 차이, incremental spread와 기존 자산 spread | `IC=100k`억원, `k: 10…500`, `ROIC: 0…40%`, `WACC: 1…20%`. 답 `k×(ROIC−WACC)`억원; 음수 허용. | ER-DAMO-TOOLKIT |
| **EQV-47 C/N** | `FCFF=NOPAT−Reinvestment`; `FCFE=NI−(Capex−D&A)−ΔNWC+NetBorrowing`; `RI=NI−r_e×BeginningBVE` | FCFF·FCFE·DDM·residual income 선택, 은행에서 FCFF의 한계, 현금흐름과 할인율 청구권 일치 | FCFE 각 항 `−500…5,000`억원/step 10, 답 정수. RI형은 `BVE=100k`, `kePct: 5…20`, `NI: 100…5,000`으로 equity charge=`k×ke`. | ER-DAMO-VAL, ER-DAMO-TOOLKIT |

#### F.3.4 실무 가치평가

| ID·모드 | 핵심 공식·관계 | 개념형 scope | 계산형 일반화 문제·파라미터·정수 보장 | 주 참고 |
|---|---|---|---|---|
| **EQV-48 C/N** | `EndPP&E=BeginPP&E+Capex−D&A−Disposals±FX`; `EndRE=BeginRE+NI−Dividends` | 대차대조표와 DCF 연결, capex·감가상각·운전자본·차입 상호작용 | 모든 항 `0…10,000`억원/step 10, FX `−500…500`; ending≥0만 채택. 답 EndPP&E 또는 EndRE. | ER-SEC-FRM, ER-DART-API |
| **EQV-49 C/N** | `TV=FCFF_(n+1)/(WACC−g)`; `StableReinvestmentRate=g/ROIC`; `ImpliedTerminalMultiple=TV/TerminalMetric` | TV 비중 점검, `g<WACC`, 장기성장·ROIC·마진·재투자의 일관성 | 재투자율형은 `g: 1…6%`, `ROIC: 5…30%` 중 `100g/ROIC`가 정수인 pair만 채택. 답 정수 %. TV형은 EQV-15 생성기를 재사용. | ER-DAMO-DCF-CHECK, ER-DAMO-TOOLKIT |
| **EQV-50 C/N** | Mid-year `PV=FCF_t/(1+r)^(t−0.5)`; stub은 실제 가치평가일 기준 지수 | year-end보다 가치가 높은 이유, LTM·NTM·회계연도·가치평가일 불일치 | 미리 계산·검수한 `{r, t, discountFactorBp}` lookup을 사용하고 `FCF=10000k`억원으로 표집한다. 답 `FCF×factorBp/10000` 정수; 임의 부동소수 생성 금지. | ER-DAMO-DCF-CHECK |
| **EQV-51 C/N** | Reverse DCF: 현재 EV가 되게 성장·마진·ROIC를 역산 | 목표가 모델이 아닌 시장기대 추출 도구, 단일 입력만 역산할 때의 위험 | 단순 영구형 `EV=FCFFnext/(WACC−g)`. `EV=100k`, `spreadPct: 2…10`, `FCFFnext=k×spreadPct`, `WACC: spread+1…20`; 답 `g=WACC−spread` 정수 %. | ER-DAMO-VAL, ER-DAMO-TOOLKIT |
| **EQV-52 C/N** | `EV/EBITDA`, `EV/EBIT`, `P/E`, `P/B`, `EV/Sales`의 청구권·시점·회계정책 일치 | LTM/NTM, IFRS 16·SBC·R&D·연금, 경기정점의 낮은 PER, 저배수 함정 | 잠재 `multiple: 2…30`, `metric: 100…5,000`억원/step 50, `numerator=multiple×metric` derived. 문항은 numerator/denominator 청구권을 일치시킨 경우만 승인. | ER-DAMO-TOOLKIT, ER-DAMO-CYCLICAL |
| **EQV-53 C/N** | `SOTPEquity=ΣSegmentEV−PV(CorporateCosts)+NonOperatingAssets−NetDebt−NCI−OtherClaims` | 사업부별 peer·배수, 본사비용·세금누수·교차지분, 현금 이중계상 | 사업부 2~5개 `EV_i: 500…20,000`, 조정항 `0…10,000`억원/step 100. equity>0만 채택하고 답 정수억원. | ER-DAMO-SOTP |
| **EQV-54 C/N** | `ExpectedValue=Σp_sV_s`; 민감도 `ΔValue/ΔDriver` 또는 탄력성 | 독립된 bull/base/bear 서사, WACC·g만 바꾸는 가짜 시나리오, 상관·tail risk | `p_s: 10…70% / step 10`, 합 100; `V_s: 10…500 / step 10`, Bear<Base<Bull. 답 확률가중 가치 정수. | ER-DAMO-DCF-CHECK |

#### F.3.5 선택형 산업 모듈

| ID·모드 | 핵심 공식·관계 | 개념형 scope | 계산형 일반화 문제·파라미터·정수 보장 | 주 참고 |
|---|---|---|---|---|
| **EQV-55 C/N** | 은행 `NII=InterestIncome−InterestExpense`; `NIM=NII/AvgEarningAssets`; `DepositBeta=ΔDepositCost/ΔBenchmarkRate`; `PPNR=NII+NoninterestIncome−Opex` | 금리 상승이 항상 NIM에 유리하지 않은 이유, repricing 속도, 예금 mix·beta·유동성 | `AvgEarningAssets=100k`억원, `nimPct: 1…8`, `NII=k×nimPct`. 답 NIM 정수 %. Deposit beta형은 `benchmarkChangeBp∈{25,50,100,200}`, `betaPct: 0…100 / step 5` 중 `(benchmarkChangeBp×betaPct)%100=0`인 조합만 쓰고 `depositCostChangeBp=product/100`으로 derived. | ER-FED-BHCPR, ER-FDIC-QBP |
| **EQV-56 C/N** | `EndAllowance=BeginAllowance+Provision−ChargeOffs+Recoveries±Other`; `CET1Ratio=CET1/RWA`; `ROTCE=CommonNI/AvgTCE` | provision·NCO·NPL, reserve release 이익, P/TBV·ROTCE·residual income | allowance 각 항 `0…5,000`억원/step 10, ending≥0. CET1형은 `RWA=100k`, `CET1=k×ratioPct`, `ratio: 5…20%`. | ER-IFRS9, ER-BIS-BASEL, ER-FED-BHCPR |
| **EQV-57 C/N** | 손해보험 `LossRatio=IncurredLosses/EarnedPremium`; `CombinedRatio=LossRatio+ExpenseRatio(+DividendRatio)` | combined ratio 100 미만, reserve development, 가격 인상과 손해율의 시차, 분모 정의 | `lossRatio: 40…100%`, `expenseRatio: 10…50%`, 선택 `dividendRatio: 0…10%`. 답 combined ratio 정수 %. | ER-NAIC-PC |
| **EQV-58 C/N** | 생명보험 개념 브리지 `ClosingCSM=OpeningCSM+NewBusiness+Interest+FutureServiceChanges−CSMRelease±FX`; `SolvencyRatio=AvailableCapital/RequiredCapital` | IFRS 17 CSM과 현금·장부자본의 차이, 신계약가치·보험서비스손익, RBC의 한계 | CSM 각 항 `0…5,000`억원/step 10, FX `−500…500`, closing≥0. 지급여력형은 `Required=100k`, `Available=k×ratioPct`, `ratio: 100…300%`. | ER-IFRS17, ER-NAIC-RBC |
| **EQV-59 C/N** | 경기민감 `NormalizedEBIT=CurrentScaleRevenue×ThroughCycleMargin`; 원자재 `Revenue≈Price×Volume`; `CashMargin=RealizedPrice−CashCost` | 경기정점의 낮은 PER, 평균 이익 대신 현재 규모×평균마진, 선도곡선·헤지·운영레버리지 | `CurrentRevenue=100k`억원, `marginPct: −10…30`, 답 `k×marginPct`억원. 원자재형은 정수 price·cost·volume을 사용. | ER-DAMO-CYCLICAL, ER-EIA-API |
| **EQV-60 C/N** | `NAV=ΣPV(AssetAfterTaxFCF)+OtherAssets−NetDebt−Closure/ARO`; `ReserveLife=RecoverableReserves/AnnualProduction` | 유한자산과 영구성장, proved/probable 확실성, 개발 capex·폐쇄비용·자산별 할인율 | 자산가치 2~5개 `100…20,000`, 조정항 `0…10,000`억원/step 100, NAV>0. Reserve-life형은 `production: 1…100`, `years: 2…40`, `reserves=production×years`. | ER-SEC-OILGAS, ER-EIA-API |

#### F.3.6 투자논리·촉매·위험·자본배분

| ID·모드 | 핵심 공식·관계 | 개념형 scope | 계산형 일반화 문제·파라미터·정수 보장 | 주 참고 |
|---|---|---|---|---|
| **EQV-61 C/N** | `EstimateGap=OurEstimate/Consensus−1`; `Surprise=Actual/Consensus−1`; 목표가 변화는 EPS·배수·순부채로 분해 | 좋은 실적에도 주가 하락, consensus와 whisper, 핵심 driver의 variant perception | `Consensus=100k`, `gapPct: −30…50`, `OurEstimate=k×(100+gapPct)`, 값>0. 답 estimate gap 정수 %. Surprise도 같은 생성기. | ER-SEC-EDGAR, ER-DART-API |
| **EQV-62 C/N** | `ExpectedTSR=(TargetPrice−CurrentPrice+ExpectedDividends)/CurrentPrice` | 촉매의 사건·시점·시장기대·관측지표, 좋은 뉴스와 예상보다 좋은 뉴스, 목표가 roll-forward | `Current=100k`원, `k: 100…2,000`, `tsrPct: −30…80`, `Dividend: 0…20k`; `Target=Current+k×tsrPct−Dividend` derived, Target>0. 답 TSR 정수 %. | ER-DAMO-VAL |
| **EQV-63 C/N** | `ExpectedLoss=Probability×Impact`; `LiquidityRunway=(Cash+UndrawnFacilities−NearTermObligations)/CashBurn` | thesis breaker와 변동성, covenant·refinancing·희석, 기대손실이 tail correlation을 놓치는 이유 | `probPct: 10…80 / step 10`, `impact: 10…500 / step 10`원으로 답 정수. Runway형은 `monthlyBurn: 10…500`억원, `months: 1…36`, 순가용유동성=`burn×months` derived. | ER-SEC-EDGAR, ER-DART-API |
| **EQV-64 C/N** | `ShareholderYield=(Dividends+NetBuybacks+NetDebtRepayment)/MarketCap` | EPS가 늘어도 가치파괴인 자사주, 배당·부채상환·M&A·재투자 우선순위, 보상 KPI 왜곡 | `MarketCap=100k`억원, `k: 10…500`, `yieldPct: −10…20`, `Dividends: 0…2,000`, `NetBuybacks: −5,000…5,000`억원/step 10. `NetDebtRepayment=k×yieldPct−Dividends−NetBuybacks`로만 역산하고 `−5,000…5,000` 범위를 벗어나면 재표집한다. 배당은 항상 0 이상이며, 순매입·순상환은 양수, 순발행·순차입은 음수다. 답 shareholder yield 정수 %. | ER-DAMO-TOOLKIT, ER-SEC-EDGAR |

#### F.3.7 기존 기초 요소와의 연결·보정

- `EQV-10`의 `PBR≈PER×ROE`는 같은 기간·같은 지분기준이면 `P/B=(P/E)×(E/B)`라는 항등식이다. EPS는 기간값, BPS는 시점값이고 평균자본 ROE를 쓰면 정확히 일치하지 않을 수 있음을 해설에 붙인다.
- `EQV-16` peer multiple은 LTM/NTM, 리스, SBC, R&D, 연금, 회계기준과 경기국면을 정규화한 뒤 비교한다.
- `EQV-18~19`의 계산형은 유지하되 시나리오의 질·상관·tail risk는 `EQV-54`에 연결한다.
- `IBT-17`은 `EQV-61~62`, `IBT-18`은 `EQV-63`과 `relatedElementIds`로 연결해 지식 청크를 중복 저장하지 않는다.
- ARR·NRR·GMV·backlog·adjusted EBITDA·AFFO처럼 표준화되지 않은 지표는 `canonicalFormula`와 `issuerSpecificDefinition`을 분리한다.
- 모든 EQV scope는 `정의 → 공식 → 방향성 → 회계상 왜곡 → 가치평가 영향 → 예외·반례 → 면접 발화` 순서의 claim을 가져야 한다.

## G. IB·시장·대체투자 실무 (`IBT`)

### G.1 개념·문제 유형·난수 명세

| ID | 요소와 핵심 수식 | 생성할 문제 유형(1개 이상) | 파라미터 범위와 정수답 보장 | 주 참고 |
|---|---|---|---|---|
| **IBT-01** | 시장금리·실질금리: 근사 `RealRate≈NominalRate−Inflation`; `100bp=1%p` | “명목 정책금리와 기대인플레이션이 주어졌을 때 사전 실질금리를 bp로 계산하라.” 기준금리 변경 전후 bp 차이 변형도 둔다. | `nominalBp: 0…800 / step 25`, `inflationBp: 0…600 / step 25`; 답 `nominalBp−inflationBp`bp. 음수 허용. | R-FED, R-FEDPDF |
| **IBT-02** | FX 환산손익: 원화표시 수취액 `USDNotional×KRW/USD`; `FX P&L=N×(S1−S0)` | “달러 매출채권 보유자가 환율 변화로 얻는 원화 환산손익은?” | `N: 1…100`백만달러; `S0: 1,000…1,500 / step 10`; `ΔS: −150…150 / step 10`, 0 제외, `S1=S0+ΔS>0`. 답 `N×ΔS`백만원. 수입업체는 부호를 반대로 한다. | R-MITINV, R-FED |
| **IBT-03** | 신용스프레드·가격민감도: `ΔP/P≈−ModifiedDuration×ΔSpread`; bp 표현 시 `priceChangeBp≈−D×spreadChangeBp` | “국채금리는 불변이고 회사채 스프레드가 확대될 때 듀레이션 근사 가격변화는?” | `D: 2…10`, `ΔspreadBp: −200…200 / step 10`, 0 제외. 답 `−D×ΔspreadBp` 가격 bp. 금리하락과 스프레드확대가 동시에 주어지는 상쇄 변형은 두 yield 변화를 먼저 합산한다. | R-MITFIN, R-CF |
| **IBT-04** | 통화정책·이자수익 전이: `ΔAnnualInterest=B×ΔrBp/10,000` | “변동금리 대출자산이 정책금리 변화를 100% 반영할 때 연간 이자수익 변화는?” | `ΔrBp: choice{−100,−75,−50,−25,25,50,75,100,125}`; `base=10000/gcd(abs(ΔrBp),10000)`, `B=base×k`, `k: 1…200`억원. 답 `B×ΔrBp/10000`억원 정수. | R-FED, R-FEDPDF |
| **IBT-05** | EV–Equity bridge: `EquityValue=EV−Debt−Preferred−Minority+Cash` | “거래 EV에서 순부채·우선주·비지배지분을 조정해 보통주 지분가치를 구하라.” 역방향으로 EV를 묻는 변형도 둔다. | `EV: 1,000…30,000 / step 100`; `Debt: 0…10,000 / step 100`, `Preferred,Minority: 0…2,000 / step 100`, `Cash: 0…5,000 / step 100`; Equity>0인 조합만 채택. 답 위 정수식. | R-DCF, R-REL |
| **IBT-06** | M&A 시너지: 무성장 영구 시너지 `SynergyPV=AfterTaxAnnualSynergy/r`; `NetValueCreated=SynergyPV−IntegrationCost` | “세후 연간 비용절감이 영구히 지속될 때 시너지 PV와 일회성 통합비용 차감 후 가치창출액을 계산하라.” | `rPct: 5…15`; `k: 10…300`; `afterTaxSynergy=rPct×k` derived, 따라서 `SynergyPV=100k`; `integrationCost: 0…10,000 / step 100`, 제약 `integrationCost<SynergyPV`. 답 `100k−integrationCost`억원. | R-ACQ, R-ACQPDF |
| **IBT-07** | EPS accretion/dilution: `ProFormaEPS=CombinedNI/ProFormaShares`; `A/D%=(ProFormaEPS/BuyerEPS−1)×100` | “주식대가 인수 후 합산순이익과 신주를 반영해 EPS 증감률을 계산하라.” | 잠재 `buyerEPS: 500…5,000 / step 100`, `adPct: −20…30`, 0 제외; 정수 post EPS를 위해 `buyerEPS`가 `100/gcd(100,100+adPct)`의 배수인 조합만 허용. `buyerShares: 50…500`, `newShares: 10…200`; `buyerNI=buyerEPS×buyerShares`, `combinedNI=postEPS×(buyerShares+newShares)`, `targetNI=combinedNI−buyerNI>0` derived. 답 `adPct`%. | R-ACQ, R-BIWS |
| **IBT-08** | 주식교환비율: `ExchangeRatio=OfferPriceTarget/BuyerSharePrice`; `NewShares=TargetShares×ExchangeRatio` | “목표주주 1주당 인수회사 주식 몇 %를 지급하는가?” 또는 발행 신주 수를 묻는다. | `buyerPrice: 1,000…100,000 / step 1,000`; 잠재 `ratioPct: 25…200 / step 25`; `offerPrice=buyerPrice×ratioPct/100` derived. 답 `ratioPct`(exchange ratio×100). 신주 변형은 `targetShares: 4…400 / step 4`백만주로 두어 0.25 단위 비율에서도 정수. | R-ACQ, R-ACQPDF |
| **IBT-09** | IPO primary/secondary: `PrimaryProceeds=OfferPrice×NewShares`; `DealSize=Price×(New+Secondary)` | “신주·구주매출 중 회사로 유입되는 gross proceeds는?” 총 공모규모와 혼동시키는 선택지를 만든다. | 주가 `P: 1…20`만원/주, `newShares: 100…5,000`만주, `secondaryShares: 0…5,000`만주. `1만원×1만주=1억원`이므로 답 `P×newShares`억원. | R-SECIPO, R-SECPDF, R-IPO |
| **IBT-10** | IPO 지분희석: `Dilution%=NewShares/PostMoneyShares×100` | “기존주식과 신주가 주어졌을 때 기존주주의 경제적 지분 희석률은?” 가격 희석과 소유비율 희석을 구분한다. | 잠재 `dilutionPct: 5…40`; `k: 1…100`; `postShares=100k`, `newShares=dilutionPct×k`, `oldShares=(100−dilutionPct)×k` derived. 답 `dilutionPct`%. | R-SECIPO, R-SECPDF |
| **IBT-11** | IPO 밸류에이션 배수: `PostMoneyMarketCap=OfferPrice×PostShares`; `PER=MarketCap/NI` | “공모가 기준 post-money PER을 계산하라.” | 잠재 `per: 5…40`, `eps: 500…5,000 / step 100`, `postShares: 10…500`백만주; `offerPrice=eps×per`, `NI=eps×postShares`백만원 derived. 답 `per`x. EV/Sales 변형은 EQV-11의 EV bridge 생성기를 재사용한다. | R-IPO, R-REL |
| **IBT-12** | 부동산 NOI: `NOI=GrossPotentialRent−VacancyLoss−OperatingExpenses` | “잠재총임대료, 공실률, 운영비로 NOI를 계산하라.” 금융비용·감가상각은 NOI에서 제외한다. | `GPR=100k`, `k: 2…100`; `vacancyPct: 0…20`; `opex: 10…3000 / step 10`, 제약 `NOI=k×(100−vacancyPct)−opex>0`. 답 NOI억원. | R-RE, R-REEXAM |
| **IBT-13** | Cap rate 가치: `PropertyValue=NOI/CapRate` | “안정화 NOI와 시장 cap rate로 부동산 가치를 계산하라.” | `capRatePct: 3…10`; `k: 10…500`; `NOI=capRatePct×k` derived; 답 `PropertyValue=100k`억원. cap rate 상승 전후 가치방향 꼬리질문을 붙인다. | R-RE, R-REEXAM |
| **IBT-14** | LTV: `LTV=Loan/PropertyValue×100` | “담보가치와 대출잔액으로 LTV를 계산하라.” 또는 허용 LTV로 최대 대출액을 계산한다. | 잠재 `ltvPct: 40…80`; `k: 10…500`; `propertyValue=100k`, `loan=ltvPct×k` derived. 답 `ltvPct`% 또는 loan억원. | R-RE |
| **IBT-15** | DSCR: `DSCR=NOI/AnnualDebtService` | “NOI와 연간 원리금상환액으로 DSCR을 계산하라.” | `debtService: 10…500 / step 10`; 잠재 `dscr100: 110…250 / step 10`; `NOI=debtService×dscr100/100` derived. 답 `dscr100`(예: 150은 1.50x). 해설은 100 미만이면 상환재원이 부족하다고 해석한다. | R-RE, R-REEXAM |
| **IBT-16** | 단순 보유기간 IRR: 1년이면 `IRR=(Distribution/InitialEquity−1)×100` | “초기 자기자본 투자액과 1년 뒤 순분배액으로 levered equity IRR을 계산하라.” 다기간 IRR은 정수답 원칙 때문에 별도 고급 템플릿으로만 제공한다. | 잠재 `irrPct: −20…50`, `k: 10…500`; `initialEquity=100k`, `distribution=k×(100+irrPct)` derived, 양수 제약. 답 `irrPct`%. | R-RE, R-REEXAM |
| **IBT-17** | 리서치 촉매·실적서프라이즈: `RevisedEPS=ConsensusEPS×(1+Surprise%)`; `ΔTarget=ΔEPS×TargetPER` | “실적 촉매로 EPS가 예상보다 상향될 때 동일 PER 기준 목표주가 상승분은?” | `surprisePct: 5…30`; `base=100/gcd(100,surprisePct)`; `consensusEPS=base×k`, `k: 100…2000`; `targetPER: 5…30`. `revisedEPS`와 답 `ΔEPS×targetPER` 모두 정수원. | R-YIG, R-REL |
| **IBT-18** | 리서치 위험·기대 하방: `ExpectedDownside=Probability×LossIfEvent` | “규제/원가/임상 실패 위험의 발생확률과 발생 시 목표가 하락액으로 기대 하방을 계산하라.” 이는 확률가중 보조지표이지 완전한 가치평가가 아님을 밝힌다. | `probPct: 10…70 / step 10`; `lossIfEvent: 10…300 / step 10`; 답 `probPct×lossIfEvent/100`원 정수. 위험 없음 시 손실 0을 전제로 한다. | R-DCF, R-YIG |

### G.2 IBT 해설에 반드시 포함할 개념

- 금리·FX·신용 문제는 계산 후 반드시 **누가 long/short인지**를 한 문장으로 해석한다. 같은 환율 상승도 달러 수취자는 이익, 달러 지급자는 손실이다.
- M&A에서 “시너지의 존재”와 “인수자 주주가 얻는 가치”를 구분한다. 지급 프리미엄과 통합비용이 시너지보다 크면 합산가치가 늘어도 인수자 주주가 손해를 볼 수 있다.
- IPO에서 primary는 회사의 신주발행, secondary는 기존주주의 구주매출이다. 총 공모규모 전체가 회사 현금으로 들어간다고 설명하면 오답이다.
- 부동산 NOI에는 이자·법인세·감가상각·원금상환을 넣지 않는다. DSCR 및 levered IRR 단계에서 금융구조를 반영한다.
- 리서치 촉매/위험 문항은 숫자를 근거로 한 면접 발화 훈련이다. 답 아래에 “가정이 이미 주가에 반영됐는가?”, “일회성인가 구조적인가?” 꼬리질문을 자동 표시한다.

## 6. 통합 케이스 설계

단일 요소 문제와 별도로 동일 데이터셋을 여러 문항이 공유하는 케이스를 둔다. 통합 케이스는 무작위 생성보다 **검증된 데이터셋 룩업**을 우선한다.

### 6.1 주식 리서치 통합 케이스

```text
P×Q 매출 → 영업이익 → 세후영업이익 → 운전자본·CAPEX → FCFF
→ WACC 할인 → terminal value → EV → 순차입금 차감 → 주당가치
→ 현재주가 대비 상승여력 → bull/base/bear 민감도
```

- 최소 8문항, 최대 15문항
- 앞 문제를 틀려도 뒤 문제를 풀 수 있도록 각 문항에는 필요한 중간값을 다시 제공하거나 `이전 정답과 무관한 기준값`을 제공한다.
- 면접 모드에서는 계산 후 “이 가정이 가장 민감한 이유”를 객관식 또는 구두 체크리스트로 묻는다.

### 6.2 M&A·IPO 통합 케이스

```text
독립가치 → 제안 프리미엄 → 거래대금 → 현금/주식 조달
→ 시너지 → pro forma 순이익·주식수 → EPS accretion/dilution
→ EV/EBITDA 및 교환비율
```

- 현금거래와 주식교환 거래를 분리한다.
- 세금·거래비용을 넣는 난이도 3 문제에서도 모든 값은 정수답 역생성 규칙을 따른다.

### 6.3 부동산 인수 통합 케이스

```text
임대수입·공실·비용 → NOI → cap rate 가치 → LTV 대출
→ 이자·원금상환 → DSCR → equity cash flow → exit value → levered IRR
```

- IRR은 목표 정수 IRR을 먼저 고르고 exit proceeds를 역산한 검증 데이터셋만 사용한다.

## 7. 품질보증 및 자동 테스트

### 7.1 템플릿 단위 테스트

각 템플릿은 최소 다음 테스트를 가진다.

```text
✓ 10,000개 seed에서 생성 성공률 ≥ 99.9%
✓ 모든 canonicalAnswer가 safe integer
✓ 표시 단위와 내부 단위가 일치
✓ 해설의 대입식으로 동일 답 재현
✓ 분모 0, 음의 주식수, 확률합 오류 등 금지상태 없음
✓ 난이도별 답 범위 초과 없음
✓ 10,000개 release instance 모두 calculatorAllowed=false
✓ 독립 재계산한 MentalMathAudit가 snapshot과 동일
✓ 난이도 1/2/3의 score≤2/4/6, inputs≤4/6/8, estimatedSeconds≤30/60/90
✓ maximumSignificantDigits≤3, allIntermediatesExact=true, forbiddenOperationCount=0
✓ explicit_rounding 태그 instance가 release corpus에 0개
✓ 같은 seed의 결정론적 재현
✓ sourceRefIds가 모두 실제 출처 레지스트리에 존재
```

### 7.2 독립 정답검증

- 생성 함수와 별도의 reference solver를 둔다.
- CI에서 `generatorAnswer === referenceSolver(params)`를 검사한다.
- 문제 generator와 별도의 AST 기반 `auditMentalMath`를 두고, `storedMentalMathAudit === recomputedMentalMathAudit`를 검사한다.
- DCF·채권·옵션은 스프레드시트 또는 검증 라이브러리 결과와 golden test를 둔다.
- 해설 문자열에서 추출한 중간값도 가능하면 구조화된 `explanationSteps`로 저장해 계산 일관성을 검사한다.

### 7.3 콘텐츠 검수 체크리스트

- 질문 하나에 핵심 계산 하나만 있는가?
- 필요한 가정이 지문에 명시되어 있는가?
- 동일 기호가 다른 의미로 재사용되지 않았는가?
- 정답 단위가 입력창 옆에 보이는가?
- 계산기·엑셀 없이 한 가지 명확한 암산 경로로 제한시간 안에 풀리는가?
- 모든 나눗셈과 중간값이 정확하며 숨은 반올림·보간·반복계산이 없는가?
- 문제 화면에 계산기·수식도구·메모장·scratchpad·제출 전 힌트가 없는가?
- 회계 문제의 기준(K-IFRS/일반적 면접 단순화)이 명시되어 있는가?
- 개념 해설이 계산 결과의 경제적 의미까지 설명하는가?
- 특정 학회 기출이라고 오인할 표현이 없는가?

### 7.4 로컬 개념문제 생성 자동검수

모든 개념문항은 사용자에게 노출되기 전에 다음 불변조건을 통과해야 한다.

```text
groundedClaimCoverage = 1.00
citationAnchorValidity = 1.00
scopeLeakCount = 0
uniqueCorrectAnswer = true
unsupportedClaimCount = 0
answerPositionDistribution ≈ uniform
```

- 답과 해설의 사실 claim이 모두 `selectedClaimIds` 안에 있어야 한다.
- 정답 근거와 각 오답의 반박 근거까지 citation coverage가 100%여야 한다.
- `chunkId`·`evidenceHash`가 현재 corpus의 실제 값과 일치하고 retrieval 결과 밖의 인용이 없어야 한다.
- 같은 지문의 가정 아래 정답이 하나뿐이며, 모든 오답이 실제로 틀려야 한다.
- `excludedTopics`·`excludedClaimIds`와 최대 추론단계를 침범하지 않아야 한다.
- 공식·정의의 유일한 근거로 Tier 3 출처를 쓰지 않는다.
- 최신성이 필요한 정보는 `asOfDate`와 유효기간을 지문에 표시한다.
- 질문에 답이 노출되거나, 정답 선택지만 유난히 길거나, 같은 signature의 문항이 반복되지 않아야 한다.
- 영어 근거에서 한국어 문항을 만들 때 숫자·부호·첨자·단위·수식기호를 별도 대조한다.
- 같은 corpus·scope·renderer version·seed가 byte-identical 문항을 만드는지 검사한다.
- 요소마다 서로 다른 유효 signature를 최소 18개 만들 수 있어야 하며, 문항 생성 중 네트워크 호출은 0회여야 한다.
- 로컬 모델을 끄거나 삭제해도 결정론적 fallback으로 모든 객관식·참거짓·순서배열이 생성되어야 한다.
- 생성 실패는 검수된 다른 frame으로 최대 2회 재시도한 뒤 고정 fallback을 제공한다. 미검증 후보를 그대로 보여주지 않는다.

### 7.5 수집·인덱스 무결성 회귀검사

- 자동 fetch는 source manifest에 등록된 공개 URL만 대상으로 한다. 로그인·유료벽·CAPTCHA·비공개 토큰은 우회하지 않고 `401/403/429`에서 중단한다.
- 사용자가 정상적으로 보유한 로컬 문서는 `local_file`로 가져오되 원본을 앱 밖으로 전송하지 않는다.
- HTML의 script·style·숨은 텍스트·프롬프트형 지시를 제거하고, corpus 문장은 모두 실행할 수 없는 untrusted data로 취급한다.
- 새 fetch가 실패해도 마지막 정상 `source_version`을 삭제하거나 덮어쓰지 않는다. 내용 hash가 달라진 문서와 연관 chunk만 재파싱·재색인한다.
- SHA-256 완전중복과 정규화 텍스트 근접중복을 제거하며, 모든 `localPath`는 앱의 `data/` root 안에 있어야 한다.
- FTS 인덱스와 선택적 vector 인덱스를 삭제한 뒤 원문·parsed text·SQLite metadata만으로 재구축할 수 있어야 한다.
- SQLite, raw/parsed 파일, manifest를 함께 백업하고 hash 검증 후 복원 테스트를 수행한다.

## 8. 출처·참고자료 레지스트리

> 이 버전은 개인 PC에서 corpus를 만들고 그 검증된 콘텐츠 DB를 본인 Android APK에 넣어 혼자 쓰는 구조다. 공개 URL과 사용자가 직접 보유한 파일은 9장의 source manifest에 등록해 파싱할 수 있으며, APK·DB는 개인 OneDrive와 본인 기기 밖으로 배포하지 않는다. 정의·공식의 신뢰도는 출처 tier와 locator로 관리하고, 로그인·유료벽·CAPTCHA 등 접근통제는 우회하지 않는다.

### 8.1 공식 범위 근거

| 출처 ID | 링크 | 문서에서의 용도 |
|---|---|---|
| `SCOPE-YIG-01` | [YIG 2026-2 공식 Recruiting](https://yig.yonsei.ac.kr/recruiting) | Fit & Tech 및 Stock Pitch 범위 확인 |
| `SCOPE-YIG-02` | [YIG 공개 리서치](https://yig.yonsei.ac.kr/research) | 기업분석·실적추정·가치평가 산출물 확인 |
| `SCOPE-YFL-01` | [YFL 공식 1차 면접 안내 이미지](https://yflyonsei.com/uploads/%EB%B0%95%EC%84%9C%ED%98%84/Recruiting%203.PNG) | 재무·회계·파생 및 마켓·M&A·IPO·부동산·리서치 선택범위 확인 |
| `SCOPE-YFL-02` | [YFL 공식 Study 교재 안내 이미지](https://yflyonsei.com/uploads/%EB%B0%95%EC%84%9C%ED%98%84/Study%201.PNG) | Tuckman·Hull·BIWS 학습구조 확인 |
| `SCOPE-YFL-03` | [YFL 공식 시사 세션 안내 이미지](https://yflyonsei.com/uploads/%EB%B0%95%EC%84%9C%ED%98%84/Study%202.PNG) | 금융이슈 리포트와 인터뷰식 Q&A 확인 |
| `SCOPE-YFL-04` | [YFL 팀 활동](https://yflyonsei.com/teamactivities) | IBD·S&T·리서치·대체투자 프로젝트 확인 |

### 8.2 한국어 공개 교안·예제 PDF

| 출처 ID | 링크 | 범위 | 해설 수준 |
|---|---|---|---|
| `KO-CF-01` | [원광대 재무관리 — 화폐의 시간가치 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/03.pdf) | PV·FV·연금·영구연금 | 계산과정 포함 |
| `KO-FI-01` | [원광대 재무관리 — 채권 가치평가 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/05.pdf) | 채권가격·YTM | 공식·계산 예제 |
| `KO-EQV-01` | [원광대 재무관리 — 주식 가치평가 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/06.pdf) | DDM·주식가치 | 계산 예제 |
| `KO-EQV-02` | [원광대 재무관리 — 상대가치평가 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/07.pdf) | PER·PBR | 계산 예제 |
| `KO-INV-01` | [원광대 재무관리 — 포트폴리오 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/08.pdf) | 기대수익·분산·공분산 | 계산 예제 |
| `KO-INV-02` | [원광대 재무관리 — CAPM PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/10.pdf) | 베타·CAPM | 계산 예제 |
| `KO-CF-02` | [원광대 재무관리 — 자본예산 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2023/wku/chunghoil0208/12.pdf) | NPV·IRR·자본비용 | 계산과정 포함 |
| `KO-DER-01` | [중앙대 파생상품 — 선물가격 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/02.pdf) | 무차익 선물가격·현금앤캐리 | 문제·즉시 해설 |
| `KO-DER-02` | [중앙대 파생상품 — 선물 헤징 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/04.pdf) | 최적헤지비율·지수선물 | 문제·즉시 해설 |
| `KO-DER-03` | [중앙대 파생상품 — 이항모형 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/06.pdf) | 이항모형 옵션가격 | 단계별 계산 |
| `KO-DER-04` | [중앙대 파생상품 — 2018 CPA 문제 6 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/07.pdf) | 선도·옵션 응용 | 문제·완전해설 |
| `KO-DER-05` | [중앙대 파생상품 — Greeks·헤징 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/08.pdf) | Delta·Gamma·동적헤징 | 단계별 계산 |
| `KO-DER-06` | [중앙대 파생상품 — 2018 CPA 문제 7 PDF](http://kocw-n.xcache.kinxcdn.com/data/document/2020/cau/yooshiyong0724/10.pdf) | Put-call parity·통화선도·옵션전략 | 문제·완전해설 |
| `KO-INV-03` | [한양대 투자론 KOCW](https://www.kocw.net/home/search/kemView.do?kemId=1057221) | 포트폴리오·CAPM/APT·채권·주식·옵션 | PDF 수치예제, 별도 정답지 없음 |
| `KO-ACC-01` | [건국대 회계원리 KOCW](https://www.kocw.net/home/search/kemView.do?kemId=1196674) | 분개·결산·재고·유형자산·사채 | 영상에서 연습문제 풀이 |
| `KO-FI-02` | [한국은행 — 우리나라 채권시장의 이해와 최근 동향](https://www.bok.or.kr/portal/bbs/B0000217/view.do?menuNo=200144&nttId=10088718) | 수익률·듀레이션·국채선물 | 강의 PDF의 계산 예제 |
| `KO-MKT-01` | [KRX 채권시장 공식 PDF](https://main.krxverse.co.kr/_contents/ACA/02/02010201/03.pdf) | 국내 채권시장·상품·제도 | 개념 중심 |
| `KO-MKT-02` | [KRX 파생상품시장 공식 PDF](https://main.krxverse.co.kr/_contents/ACA/02/02010201/04.pdf) | 국내 선물·옵션 상품·거래제도 | 개념 중심 |

### 8.3 영문 공개 문제세트·시험·공식 해설

| 출처 ID | 링크 | 범위 | 해설 수준 |
|---|---|---|---|
| `EN-MIT-FIN-01` | [MIT 15.401 Finance Theory I — Problem Sets](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/problem-sets/) | PV·채권·보통주 | 문제와 공식해설 한 PDF |
| `EN-MIT-FIN-02` | [MIT 15.401 — Sample Exams & Solutions](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/exams/) | 선물·옵션·포트폴리오·CAPM·자본예산 포함 | 중간·기말 공식해설 |
| `EN-MIT-FIN-03` | [MIT 15.401 — Problem-solving Notes](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/resources/problem-solving-notes/) | 전 범위 문제풀이 교안 | 풀이 노트 |
| `EN-MIT-ACC-01` | [MIT 15.501 Accounting — Assignments & Solutions](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/assignments/) | 분개·발생주의·재고·현금흐름·장기부채 등 | 7개 세트 공식해설 |
| `EN-MIT-ACC-02` | [MIT 15.501 — Exams & Solutions](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/exams/) | 재무·관리회계 종합 | 7개 시험 공식해설 |
| `EN-MIT-ACC-03` | [MIT 15.501 — Lecture Notes](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/lecture-notes/) | 회계 전 범위 | 교안 |
| `EN-MIT-ACC-04` | [MIT 15.514 Sample Midterm PDF](https://ocw.mit.edu/courses/15-514-financial-and-managerial-accounting-summer-2003/19734bb3c6872e3d0934f40febb2ec21_samplemidterm.pdf) | 실제 재무제표 기반 회계·비율 | 문제 PDF |
| `EN-MIT-ACC-05` | [MIT 15.514 Sample Solutions PDF](https://ocw.mit.edu/courses/15-514-financial-and-managerial-accounting-summer-2003/c8d4748deabadc72a8fac83de99d6878_samplesolutions.pdf) | 위 sample midterm | 완전해설 PDF |
| `EN-MIT-INV-01` | [MIT 15.433 Investments — Assignments](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/) | 자본시장·증권분석·선물·옵션·성과귀속 | 일부 과제 공식해설 |
| `EN-MIT-INV-02` | [MIT 15.433 — Quizzes & Solutions](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/exams/) | 투자론 전 범위 | 7개 퀴즈·시험 해설 |
| `EN-MIT-CF2-01` | [MIT 15.402 Finance Theory II — Exams & Solutions](https://ocw.mit.edu/courses/15-402-finance-theory-ii-spring-2003/pages/exams/) | 자본구조·APV·실물옵션·M&A | 심화 시험·공식해설 |
| `EN-DAMO-CF-01` | [NYU Damodaran — Corporate Finance Problems & Solutions](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/cfprset.htm) | PV·위험·투자안·자본구조·배당·가치평가 | 주제별 해설 PDF |
| `EN-DAMO-CF-02` | [Damodaran — 2026 Corporate Finance Lecture Notes](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/cflect.htm) | 기업재무 전 범위 | 최신 교안 허브 |
| `EN-DAMO-VAL-01` | [Damodaran — DCF·Relative·Option·Acquisition Problems](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/eqprob.html) | 가치평가·M&A | 문제와 해설 |
| `EN-DAMO-VAL-02` | [Damodaran — Valuation Past Quizzes & Exams](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/eqexam.htm) | DCF·상대가치·사기업·종합평가 | 대량 시험·해설 |
| `EN-DAMO-MA-01` | [Damodaran — Acquisition Problems & Solutions](https://pages.stern.nyu.edu/adamodar/New_Home_Page/problems/Acqprob.htm) | 시너지·경영권·인수가격 | 문제와 해설 |
| `EN-DAMO-BOOK-01` | [Damodaran — Investment Valuation 자료·스프레드시트](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/Inv2ed.htm) | DCF·멀티플·M&A·부동산 | PDF·XLS 도구 |
| `EN-MIT-RE-01` | [MIT 11.431 Real Estate Finance — Assignments](https://ocw.mit.edu/courses/11-431j-real-estate-finance-and-investment-fall-2006/pages/assignments/) | NOI·cap rate·DCF·IRR·케이스 | 문제세트, 해설 일부 제한 |
| `EN-MIT-RE-02` | [MIT 11.431 — Practice Exams](https://ocw.mit.edu/courses/11-431j-real-estate-finance-and-investment-fall-2006/pages/exams/) | 상업용 부동산 종합 | 연습시험 |
| `EN-YALE-01` | [Open Yale ECON 252 — Options Markets](https://oyc.yale.edu/economics/econ-252-11/lecture-17) | 옵션 payoff·합성·put-call 관계 | 문제세트와 해설 PDF |
| `EN-CME-01` | [CME — A Trader's Guide to Futures PDF](https://www.cmegroup.com/education/files/a-traders-guide-to-futures.pdf) | 선물시장·헤지·거래구조 | 입문문제와 answer key; 자동수집·DB 적재 금지, 링크 전용 |
| `EN-CFA-01` | [CFA Institute Level I Sample Questions](https://www.cfainstitute.org/programs/cfa-program/cfa-program-level-i-sample-questions) | 회계·주식·채권·파생·포트폴리오 | 공식 정답·계산해설; 복제·변형 금지, 링크 전용 |
| `EN-OPENSTAX-FIN-01` | [OpenStax Principles of Finance 2e](https://openstax.org/books/principles-of-finance-2e/pages/preface) | 재무·투자·파생의 최신 OER 문제 | 학생용 문제, 전체해설은 교사용; AI 적재는 별도 허가 전 금지 |
| `EN-OPENSTAX-ACC-01` | [OpenStax Principles of Accounting Vol. 1](https://openstax.org/books/principles-financial-accounting/pages/preface) | 회계순환·재고·부채·현금흐름·비율 | 대량 연습문제, 일부 답 공개 |

### 8.4 핵심 교재·원서

| 출처 ID | 링크 | 권장 용도 |
|---|---|---|
| `BOOK-INV-01` | [《Bodie의 기본투자론 12판》](https://www.yes24.com/Product/Goods/107667515) | 투자·포트폴리오·주식·채권·파생 공통 개념 |
| `BOOK-INV-02` | [Bodie, Kane & Marcus, *Investments*, 13e](https://www.mheducation.com/highered/product/Investments-Bodie.html) | 투자론 심화 원서 |
| `BOOK-CF-01` | [《Ross의 재무관리 13판》](https://www.yes24.com/Product/Goods/117498625) | 기업재무 입문·장말문제 |
| `BOOK-CF-02` | [《핵심 기업재무 5판》](https://m.yes24.com/goods/detail/124315764) | 가치·무차익 중심 기업재무 |
| `BOOK-ACC-01` | [《사례와 함께하는 회계원리 5판》](https://www.yes24.com/product/goods/129395371) | K-IFRS 회계 기초와 한국기업 사례 |
| `BOOK-ACC-02` | [《IFRS 회계원리》 김기동·임태종](https://www.yes24.com/product/goods/170343919) | 회계 계산 심화 |
| `BOOK-EQV-01` | [《재무제표분석과 기업가치평가 4판》](https://www.yes24.com/product/goods/111384498) | 실적추정·재무제표분석·기업가치평가 |
| `BOOK-EQV-02` | [McKinsey, *Valuation*, 8e](https://books.wiley.com/series/wiley-valuation-7e/) | ROIC·FCFF·WACC·DCF |
| `BOOK-DER-01` | [Hull, *Options, Futures, and Other Derivatives*, 11e](https://www.pearson.com/en-us/subject-catalog/p/options-futures-and-other-derivatives/P200000005938/9780136939917) | 파생상품 표준 원서 |
| `BOOK-DER-02` | [《파생상품의 평가와 헤징전략 9판》](https://www.yes24.com/product/goods/124832392) | Hull 기반 한국어 학습 |
| `BOOK-FI-01` | [Tuckman & Serrat, *Fixed Income Securities*, 4e](https://onlinelibrary.wiley.com/doi/book/10.1002/9781119835622) | 채권·금리·헤지 심화 |
| `BOOK-IB-01` | [Rosenbaum & Pearl, *Investment Banking*, 3e](https://uat.store.wiley.com/en-us/investment-banking-valuation-lbos-m-a-and-ipos-%28book-valuation-models%29-3rd-edition-p-9781119867883) | Comparable·Precedent·DCF·LBO·M&A·IPO |
| `BOOK-RE-01` | [Brueggeman & Fisher, *Real Estate Finance and Investments*](https://www.mheducation.com/highered/product/Real-Estate-Finance-and-Investments-Brueggeman.html) | NOI·cap rate·부동산 금융 |

### 8.5 `EQV`·`IBT` 상세표의 참조코드

| 코드 | 클릭 가능한 자료 | 활용 |
|---|---|---|
| `R-YIG` | [YIG Research 전체](https://yig.yonsei.ac.kr/research) · [공개 기업분석 리포트 예시](https://yig.yonsei.ac.kr/research/109/vm-2026-06-08) · [예시 PDF](https://yig.yonsei.ac.kr/research/109/vm-2026-06-08.pdf) | 실적추정·리포트·목표주가 문맥 |
| `R-MITFIN` | [MIT 15.401 문제세트·해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/problem-sets/) · [시험·해설](https://ocw.mit.edu/courses/15-401-finance-theory-i-fall-2008/pages/exams/) | 주식·채권·기업재무 계산 |
| `R-ACC` | [MIT 15.501 회계 문제세트·해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/assignments/) · [시험·해설](https://ocw.mit.edu/courses/15-501-introduction-to-financial-and-managerial-accounting-spring-2004/pages/exams/) | 세 재무제표·EPS·비율 |
| `R-DCF` | [Damodaran DCF 문제와 풀이](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/dcfprob.htm) · [Valuation 자료·PDF 허브](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valuation/val.htm) | DCF·FCFF·시나리오 |
| `R-DCF25` | [Damodaran DCF 25문 25답](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/valquestions.htm) · [FCFF 설명](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/fcff.html) · [FCFF·DCF 장 PDF](https://pages.stern.nyu.edu/~adamodar/pdfiles/valn2ed/ch15.pdf) | FCFF·계속가치 |
| `R-REL` | [Damodaran 상대가치 문제와 풀이](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/relval.htm) · [가치평가 문제 목록](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/eqprob.html) | PER·PBR·EV/EBITDA·peer multiple |
| `R-CF` | [Damodaran 기업재무 문제와 해설](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/cfprset.htm) | WACC·투자안·자본구조 |
| `R-ACQ` | [Damodaran Acquisition 문제와 풀이](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/problems/Acqprob.htm) | 시너지·교환비율·A/D |
| `R-ACQPDF` | [Damodaran Acquisition Valuation PDF](https://pages.stern.nyu.edu/~adamodar/pdfiles/AcqValn.pdf) | M&A 계산 교안 |
| `R-BIWS` | [BIWS 공식](https://breakingintowallstreet.com/biws/homepage/) · [YFL Study Sessions](https://yflyonsei.com/studysessions) · [YFL 교재 안내 이미지](https://yflyonsei.com/uploads/%EB%B0%95%EC%84%9C%ED%98%84/Study%201.PNG) | IB 실무면접 문맥; BIWS는 유료 과정 |
| `R-IPO` | [Damodaran — From Private to Publicly Traded Firm](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/invfables/ipo.htm) | IPO 가치평가 |
| `R-SECIPO` | [SEC Investor.gov — Investing in an IPO](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-17) | primary·secondary·희석 개념 |
| `R-SECPDF` | [SEC IPO Investor Bulletin PDF](https://www.investor.gov/sites/default/files/ipo-investorbulletin_0.pdf) | IPO 공식 안내 PDF |
| `R-RE` | [MIT 11.431 부동산금융 문제세트·케이스](https://ocw.mit.edu/courses/11-431j-real-estate-finance-and-investment-fall-2006/pages/assignments/) · [Problem Set 1](https://ocw.mit.edu/courses/11-431j-real-estate-finance-and-investment-fall-2006/resources/ps1/) | NOI·cap rate·LTV·IRR |
| `R-REEXAM` | [MIT 11.431 연습시험](https://ocw.mit.edu/courses/11-431j-real-estate-finance-and-investment-fall-2006/pages/exams/) · [Practice Midterm](https://ocw.mit.edu/courses/11-431j-real-estate-finance-and-investment-fall-2006/resources/midterm03prac/) · [Practice Final](https://ocw.mit.edu/courses/11-431j-real-estate-finance-and-investment-fall-2006/resources/final06prac/) | 부동산 종합계산 |
| `R-FED` | [Federal Reserve Policy Rate](https://www.federalreserve.gov/economy-at-a-glance-policy-rate.htm) · [Money, Interest Rates, and Monetary Policy](https://www.federalreserve.gov/faqs/money-rates-policy.htm) | 정책금리·이자수익·FX 문맥 |
| `R-FEDPDF` | [Federal Reserve Education Monetary Policy Guide PDF](https://www.federalreserveeducation.org/resources/lessons/lesson--ap-macro-monetary-policy-lecture-guide.pdf) | bp와 정책금리 예제 |
| `R-MITINV` | [MIT 15.433 Investments 과제](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/assignments/) · [퀴즈·시험·풀이](https://ocw.mit.edu/courses/15-433-investments-spring-2003/pages/exams/) | 시장·FX·신용 응용 |

### 8.6 실무 기업 리서치 확장 참조코드

| 코드 | 클릭 가능한 공개·공식 자료 | 활용 |
|---|---|---|
| `ER-SEC-EDGAR` | [SEC EDGAR API·XBRL Company Facts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | 미국 공시 수치·항목 관계·원문 locator |
| `ER-DART-API` | [금융감독원 OpenDART 재무정보 API](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DE003) | 국내 재무제표·주석 수치 |
| `ER-SEC-FRM` | [SEC Financial Reporting Manual](https://www.sec.gov/about/divisions-offices/division-corporation-finance/financial-reporting-manual) | 공시·회계분석 기준 |
| `ER-CFA-QUALITY` | [CFA Institute — Evaluating Quality of Financial Reports](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/evaluating-quality-financial-reports) | 이익의 질 학습범위; 원문 적재는 금지 |
| `ER-SEC-NONGAAP` | [SEC Non-GAAP Financial Measures C&DIs](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/non-gaap-financial-measures) | 조정이익·비표준 KPI 검증 |
| `ER-SEC-SBC` | [SEC Staff Accounting Bulletin No. 107](https://www.sec.gov/rules-regulations/staff-guidance/staff-accounting-bulletins/staff-accounting-bulletin-no-107) | 주식보상 회계 |
| `ER-IFRS15` | [IFRS 15 Revenue from Contracts with Customers](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-15-revenue-from-contracts-with-customers/) | 수익인식·계약자산/부채·principal-agent |
| `ER-IFRS16` | [IFRS 16 Leases](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-16-leases/) | 리스 회계·가치평가 조정 |
| `ER-IFRS2` | [IFRS 2 Share-based Payment](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-2-share-based-payment/) | 주식기준보상 |
| `ER-IAS19` | [IAS 19 Employee Benefits](https://www.ifrs.org/issued-standards/list-of-standards/ias-19-employee-benefits/) | 확정급여·연금 |
| `ER-DAMO-VAL` | [NYU Damodaran Valuation 자료 허브](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valuation/val.htm) | DCF·relative·산업 가치평가 |
| `ER-DAMO-TOOLKIT` | [Damodaran Valuation Tools](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valuationtools.html) | ROIC·성장·terminal value·multiples |
| `ER-DAMO-DCF-CHECK` | [Damodaran DCF Valuation Checklist PDF](https://pages.stern.nyu.edu/~adamodar/pdfiles/eqnotes/valuationtodolist.pdf) | DCF 일관성·민감도 검수 |
| `ER-DAMO-SOTP` | [Damodaran Multi-business·SOTP Valuation PDF](https://pages.stern.nyu.edu/~adamodar/pdfiles/DSV2/Ch17.pdf) | SOTP·본사비용 |
| `ER-DAMO-CYCLICAL` | [Damodaran — Cyclical and Commodity Companies PDF](https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/commodity.pdf) | 경기민감·원자재 정규화 |
| `ER-IFRS9` | [IFRS 9 Financial Instruments](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/) | 금융자산·기대신용손실 |
| `ER-BIS-BASEL` | [BIS Basel Framework](https://www.bis.org/basel_framework/) | CET1·RWA·은행 건전성 |
| `ER-FED-BHCPR` | [Federal Reserve BHCPR User Guide PDF](https://www.federalreserve.gov/publications/files/2026-03-UGBHCPR.pdf) | 은행 수익성·자본 지표 |
| `ER-FDIC-QBP` | [FDIC Quarterly Banking Profile](https://www.fdic.gov/analysis/quarterly-banking-profile/qbp/) | 은행 산업 지표·정의 |
| `ER-IFRS17` | [IFRS 17 Insurance Contracts](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-17-insurance-contracts/) | CSM·보험서비스손익 |
| `ER-NAIC-PC` | [NAIC Property & Casualty Industry Analysis PDF](https://content.naic.org/sites/default/files/2025-annual-property-and-casualty-and-title-insurance-industries-analysis-report.pdf) | 손해율·combined ratio·reserve |
| `ER-NAIC-RBC` | [NAIC Risk-Based Capital](https://content.naic.org/insurance-topics/risk-based-capital) | 보험 지급여력 |
| `ER-EIA-API` | [U.S. EIA Open Data API](https://www.eia.gov/opendata/documentation.php) | 에너지 가격·생산량 원천 데이터 |
| `ER-SEC-OILGAS` | [SEC Oil and Gas Disclosure Rules](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/oil-gas-rules) | 매장량·자원기업 공시 |

### 8.7 수집 운영·향후 배포·선택적 원격 기능 참고 링크

다음 표의 라이선스·약관 항목은 `personal_android_sideload`에서 **기록용 advisory metadata**이며 공개 문서의 로컬 파싱을 막는 gate가 아니다. APK·원문·DB를 제3자에게 공유하거나 앱을 서비스로 바꾸는 시점에만 publication gate로 다시 평가한다. 접근제어와 기술적 rate limit은 현재 개인 모드에서도 지킨다.

| 출처 ID | 공식 링크 | 확인할 사항 |
|---|---|---|
| `RIGHT-MIT` | [MIT OCW Privacy and Terms](https://ocw.mit.edu/pages/privacy-and-terms-of-use/) | CC BY-NC-SA 4.0, 제3자 자료 제외, 비상업·동일조건 |
| `RIGHT-OPENSTAX-FIN` | [OpenStax Principles of Finance 2e Preface](https://openstax.org/books/principles-of-finance-2e/pages/preface) | 책별 라이선스와 생성형 AI ingest 고지 |
| `RIGHT-OPENSTAX-ACC` | [OpenStax Financial Accounting Preface](https://openstax.org/books/principles-financial-accounting/pages/preface) · [robots.txt](https://openstax.org/robots.txt) | AI ingest 허가 필요 여부와 접근정책 |
| `RIGHT-DAMO` | [Damodaran Site Guide](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/guide.html) | 출처표시·비상업 조건·상업적 exploitation 제한 |
| `RIGHT-KOCW` | [KOCW 저작권 가이드](https://www.kocw.net/home/copyright/intro.do) | 강좌별 CCL·NC·ND 판정 |
| `RIGHT-YIG` | [YIG 공식 사이트](https://yig.yonsei.ac.kr/) | 공개 페이지는 개인 로컬 파싱; 향후 원문·DB 배포 시 조건 재확인 |
| `RIGHT-YFL` | [YFL 이용약관](https://yflyonsei.com/join) | 공개 페이지는 개인 로컬 파싱; 향후 원문·DB 배포 시 조건 재확인 |
| `RIGHT-CME` | [CME Website Terms](https://www.cmegroup.com/tools-information/cme-website-terms-of-use.html) · [자동수집 관련 공지](https://www.cmegroup.com/notices/clearing/2023/12/Chadv23-364.html) | scraping·data mining·database 제한 |
| `RIGHT-CFA` | [CFA Institute Terms and Conditions](https://www.cfainstitute.org/about/governance/policies/terms-conditions) | 개인용 사본 외 복제·변형·재사용 제한 |
| `RIGHT-FRB` | [Federal Reserve Board Disclaimer](https://www.federalreserve.gov/disclaimer.htm) | Board 작성물 public-domain 원칙과 제3자 예외 |
| `RIGHT-NYFED` | [New York Fed Terms of Use](https://www.newyorkfed.org/privacy/termsofuse.html) | 자동접근·수정·배포 조건과 표시의무 |
| `RIGHT-FEDED` | [Federal Reserve Education Terms](https://www.federalreserveeducation.org/terms-of-service) | scraping·DB 편입·파생물 제한 |
| `RIGHT-SECDATA` | [SEC Data APIs](https://data.sec.gov/) · [SEC Fair Access](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits) | 식별 User-Agent와 전체 합산 초당 10회 미만 |
| `RIGHT-DART` | [OpenDART API 소개](https://opendart.fss.or.kr/intro/main.do) · [OpenDART 이용약관](https://opendart.fss.or.kr/intro/terms.do) | API 활용범위·인증키·금감원 저작권·공공데이터법 적용 확인 |
| `RIGHT-USGOV` | [17 U.S.C. § 105](https://www.copyright.gov/title17/92chap1.html) · [Copyright Office FAQ](https://www.copyright.gov/help/faq/faq-general.html) | 미국 정부저작물, 사실·아이디어와 표현의 구분 |
| `AI-PRICE` | [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing) | 모델·File Search의 현행 공식 단가 |
| `AI-LUNA` | [GPT-5.6 Luna 모델 페이지](https://developers.openai.com/api/docs/models/gpt-5.6-luna) | 대량·비용민감 작업용 모델과 토큰 단가 |
| `AI-EMBED` | [text-embedding-3-small](https://developers.openai.com/api/docs/models/text-embedding-3-small) | 임베딩 단가 |
| `AI-FILESEARCH` | [File Search Guide](https://developers.openai.com/api/docs/guides/tools-file-search) | 관리형 검색·vector store 사용법 |

## 9. 개인용 로컬 파싱·지식 DB 구축 설계

### 9.1 운영 전제와 출처별 가져오기 방식

이 앱은 `deploymentMode=personal_android_sideload`인 1인용 프로그램이다. 공개 URL·PDF와 사용자가 정상적으로 보유한 파일을 **PC에서 한 번 파싱해 캐시**하고, 검증된 콘텐츠 DB만 Android release bundle에 넣는다. 라이선스·이용약관 정보는 provenance와 향후 제3자 배포 판단을 위한 메타데이터로 남기되, 개인 모드의 로컬 검색을 막는 런타임 gate로 쓰지 않는다. 로그인·유료벽·CAPTCHA·비공개 API token을 우회하거나 차단을 회피하는 수집기는 만들지 않는다.

| 출처군 | 개인 로컬 기본값 | 권장 가져오기 방식 | 품질·운영 메모 |
|---|---|---|---|
| MIT OCW·OpenStax·Damodaran·KOCW | 공개 문서 로컬 파싱 | `fetch_once` 또는 `refresh_if_changed`; PDF/HTML | 페이지·절 locator 보존; 제3자 삽입자료는 별도 source로 구분 |
| YIG·YFL | 공개 페이지·이미지·PDF 로컬 파싱 | 단일 문서 fetch, 이미지 OCR | 면접 범위·출제 문맥용 Tier 3; 정의·공식은 Tier 1·2로 교차확인 |
| CME·CFA·상업교재·BIWS·Wiley·Pearson | 공개 페이지 또는 직접 보유 파일만 | 공개 URL은 단일 fetch, 보유 PDF는 `local_file` | 인증 영역을 크롤링하지 않고 원문 corpus를 배포하지 않음 |
| Federal Reserve·SEC·BIS·EIA 등 | 공개 문서·데이터 로컬 파싱 | 공식 HTML/PDF/API 우선 | 권위도 높은 정의·시계열·공식의 근거로 사용 |
| EDGAR·OpenDART | 구조화 데이터와 공시를 로컬 저장 | `api_sync`; 내용 hash 기반 증분 갱신 | 수치·단위·연결/별도·기간을 구조화하고 서술 chunk와 분리 |
| IFRS·기타 표준기관 | 공개 페이지 또는 직접 보유 문서 | 단일 fetch/`local_file` | 기준서 버전·시행일·관할을 locator와 함께 보존 |
| 로그인·유료벽·CAPTCHA·명시적 차단 뒤 자료 | 자동수집 중단 | 정상 접근 후 사용자가 직접 받은 파일만 `local_file` | `401/403/429`에서 중지; 우회·세션 탈취·토큰 추출 금지 |

원문은 근거 조회와 개인 학습에 쓰고, 런타임 문항은 `ConceptClaim`, `FormulaCard`, `MisconceptionRule`, 검수된 문장 frame을 조립한다. 이 구분 덕분에 퀴즈마다 원문 전체를 모델에 넣지 않아도 되고, 출처가 갱신돼도 영향을 받는 claim만 다시 검수할 수 있다.

### 9.2 물리 데이터 모델

논리 스키마는 하나지만 물리 파일은 **PC 제작용·APK 콘텐츠용·휴대폰 사용자용**으로 분리한다.

```text
work/data/                         # PC에만 존재
  raw/                             # URL·로컬 파일 원본
  parsed/                          # locator 보존 JSONL/text
  authoring.sqlite3                # 전체 source·검수·generator DB
  index/                           # 제작용 FTS/vector sidecar
  models/                          # 선택적 제작용 로컬 모델
  backups/

release/                           # OneDrive로 옮길 산출물
  content-v{contentDbVersion}.sqlite3  # APK에 넣는 build intermediate; 별도 업로드 안 함
  content-manifest-v{contentDbVersion}.json # APK에 함께 넣는 DB 검증값; 별도 업로드 안 함
  finance-interview-v{versionName}.apk # 같은 key로 서명된 release APK
  release-manifest.json            # APK hash·certificate fingerprint·버전 기록
  SHA256SUMS.txt

Android app-private storage/       # APK에 포함되지 않는 mutable 데이터
  content/v{N}.sqlite3             # active-version pointer가 가리키는 검증된 읽기 전용 DB
  content/v{N-1}.sqlite3           # rollback을 위해 보존하는 이전 검증 DB
  content/v{next}.sqlite3.tmp      # 새 APK asset의 검증 중 임시 copy
  content/active-version.json      # 유일한 활성화 commit point
  content/active-version.json.tmp  # fsync 뒤 단일 atomic rename할 새 pointer
  user.sqlite3                     # attempt·bookmark·setting·runtime snapshot
  exports/                         # 사용자가 만든 수동 백업 파일
```

```text
sources
  source_id, publisher, canonical_url, local_path, source_type, title, authors, language
  authority_tier, ingest_mode, parser_id, parser_config_hash
  crawl_scope, max_depth, rate_limit_rps, refresh_policy, enabled
  terms_url, redistribution_note, source_notes       # 선택 provenance

source_versions
  source_version_id, source_id, http_etag, last_modified, sha256
  mime_type, byte_size, parser_version, ocr_version
  fetched_at, parse_status, last_error, is_active, supersedes_version_id

corpus_versions
  corpus_version, created_at, manifest_hash, parser_config_hash, notes

corpus_version_sources
  corpus_version, source_version_id       # 복합 PK; 해당 corpus의 정확한 구성

documents
  document_id, source_version_id, canonical_url, title, language
  retrieved_at, published_at, as_of_date
  raw_local_path, extracted_text_path, extractor_config_hash
  page_count, extraction_method, ocr_confidence

chunks
  chunk_id, document_id, ordinal, page, heading_path, char_start, char_end, bbox
  chunk_text, normalized_text, token_count, fts_rowid
  embedding_ref, embedding_model_hash, chunk_sha256, as_of_date  # embedding 열은 nullable

chunks_fts                                # PC authoring의 전체 corpus FTS5
  chunk_id UNINDEXED, heading_path, normalized_text

chunk_elements
  chunk_id, element_id                    # 복합 PK; retrieval element filter용

index_versions
  index_version, corpus_version, index_kind, config_hash, built_at

release_manifests                         # PC authoring DB와 외부 SHA manifest에만 존재
  release_id, application_id, version_code, version_name, content_db_version
  content_db_sha256, user_db_schema_version, signing_certificate_sha256
  release_apk_sha256, built_at

knowledge_units                           # cards·formulas·claims의 검색용 projection
  knowledge_id, domain_id, element_id, kind
  canonical_statement, formula_latex, variables_json, units_json
  assumptions_json, common_mistakes_json
  source_ids, source_locator_json
  authoring_mode                         # extract / independent_synthesis / manual_note
  review_status, reviewer

knowledge_fts                             # Android content DB의 compact FTS5
  knowledge_id UNINDEXED, element_id UNINDEXED, title, normalized_text
  source_label, locator_text

domains
  domain_id, title, display_order

users
  user_id, display_name, created_at       # personal_android_sideload에서는 기본 사용자 1행

app_settings
  setting_key, setting_value_json, updated_at

elements
  element_id, domain_id, element_number, title, mode, display_order

concept_cards
  concept_id, element_id, title, definition, intuition
  interview_points_json, common_traps_json, source_ids

formula_cards
  formula_id, element_id, latex, variables_json, assumptions_json
  unit_rule, source_ids

concept_claims
  claim_id, element_id, statement, claim_kind, assumptions_json, formula_ids
  related_claim_ids, contradicts_claim_ids, misconception_tags
  evidence_anchors_json, content_version, review_status

element_scopes
  element_id, scope_version, required_claim_ids, optional_claim_ids
  excluded_claim_ids, excluded_topics, allowed_related_element_ids
  prerequisite_element_ids
  allowed_source_ids, allowed_intents, allowed_answer_kinds
  maximum_allowed_tier, max_claims, max_inference_hops, generation_policy

concept_blueprints
  blueprint_id, element_id, blueprint_version, intent, answer_kind, difficulty
  required_claim_kinds, claim_count_json, inference_hops, needs_related_claims
  scenario_families, allowed_misconception_rule_ids, choice_count
  prompt_rules, explanation_rules

render_frames
  frame_id, blueprint_id, frame_version, locale, prompt_frame
  choice_frame_json, explanation_frame, synonym_sets_json, review_status

scenario_frames
  scenario_id, scenario_family, element_id, locale, scenario_frame
  slot_schema_json, allowed_claim_kinds, review_status

misconception_rules
  rule_id, element_id, tag, mutation, applicable_claim_kinds
  render_function, why_wrong_template, review_status

calculation_templates
  template_id, element_id, content_version, generator_version, difficulty
  prompt_template, answer_kind, answer_unit, generation_mode, params_json
  context_variants_json, choices_json, correct_choice_ids, shuffle_choices
  compute_answer_id, integer_guarantee, explanation_template
  mental_math_policy_json, concept_ids, formula_ids, source_ids, tags

fallback_questions
  fallback_id, element_id, blueprint_id, difficulty, snapshot_json
  validation_report_id, review_status

validation_reports
  validation_report_id, question_id, schema_valid, scope_valid
  citation_coverage, answer_grounded, answer_unique
  distractors_invalid_under_assumptions, prompt_answer_leak
  mental_math_passed, mental_math_audit_json
  unsupported_claim_ids, invalid_citation_ids, maximum_duplicate_similarity
  validator_versions, decision, rejection_reasons

question_snapshots
  question_id, snapshot_kind, element_id, template_or_blueprint_id
  seed, item_signature, snapshot_json, created_at

attempts
  attempt_id, user_id, question_id, submitted_answer_json, correct, elapsed_ms, attempted_at

concept_attempt_evaluations
  attempt_id, grading_mode, matched_claim_ids, missing_required_claim_ids
  contradicted_claim_ids, score, confidence, feedback, grader_version

bookmarks
  bookmark_id, user_id, question_id, reason, note, resolved, created_at, resolved_at

question_lineage
  question_id, knowledge_ids, chunk_ids, source_version_ids
  corpus_version, scope_version, renderer_id, renderer_version
  model_revision, prompt_version, seed, generated_at
  similarity_score, validation_report_id, human_review_status

inference_cache                         # 선택적 로컬 LLM을 쓸 때만 생성
  cache_key, model_id, model_hash, prompt_hash, input_hash
  output_json, validation_state, created_at
```

위 목록은 전체 논리 스키마다. `authoring.sqlite3`가 PC 제작의 기준 DB이고, release build가 필요한 행과 열만 `content.sqlite3`로 투영한다. APK에는 이 DB와 `EmbeddedContentManifest`를 asset으로 함께 넣어 APK 서명으로 보호한다. Android에서는 APK asset을 app-private `content/v{contentDbVersion}.sqlite3`로 검증·복사해 읽기 전용으로 열고 `user.sqlite3`만 쓴다. `knowledge_units`와 `knowledge_fts`는 승인된 카드·공식·claim·compact citation의 runtime 검색 projection이고, 출제는 `concept_claims`를 element ID로 직접 조회한다. raw PDF·OCR 중간파일·vector index·query encoder·로컬 모델 binary는 APK에 넣지 않는다.

| 물리 DB | 포함 데이터 | 갱신 주체 | 업데이트 규칙 |
|---|---|---|---|
| PC `authoring.sqlite3` | sources부터 validator·lineage까지 전체 | PC build pipeline | hash 기반 증분 갱신 |
| APK `content.sqlite3` | domains/elements/cards/formulas/claims/scopes/blueprints/frames/rules/templates/fallback/compact citation/`knowledge_fts` | 서명 APK release | versioned copy 검증 후 active pointer만 원자 전환; 읽기 전용 |
| Android `user.sqlite3` | user/settings/attempt/evaluation/bookmark/runtime snapshot | 휴대폰 앱 | APK 업데이트와 분리; schema migration 후 보존 |

같은 `applicationId`와 같은 서명 인증서로 상위 `versionCode` APK를 설치하면 Android app-private 데이터가 유지된다. 새 APK 첫 실행 시 asset의 content DB를 `content/v{new}.sqlite3.tmp`로 복사하고, 같은 서명 APK 안의 `EmbeddedContentManifest`에 기록된 `contentDbSha256`, DB schema version, row-count invariant와 SQLite integrity를 검증한다. 검증을 통과한 임시 파일을 fsync한 뒤 `v{new}.sqlite3`로 atomic rename한다. 외부 `AndroidReleaseManifest`의 `releaseApkSha256`은 설치 전 APK 파일 확인용일 뿐 앱 내부 DB 전환에는 사용하지 않는다.

그다음 pre-migration `user.sqlite3` backup을 만들고 transaction migration을 수행한다. 사용자 DB migration은 stable ID를 유지하는 additive 방식으로 작성하고 N−1 content DB와도 호환되어야 한다. 모든 검증·migration이 끝나면 새 버전과 hash를 적은 `active-version.json.tmp`를 fsync하고, **이 pointer 파일 하나만** `active-version.json`으로 atomic rename해 활성화한다. DB 파일 rename 뒤 pointer 전환 전에 중단되면 새 DB는 미사용 파일로 남고 기존 pointer가 계속 유효하며, pointer 전환 뒤에는 새 DB가 이미 완성돼 있다. 실패한 `.tmp`와 미사용 버전은 다음 정상 시작 때 정리하되 N−1 DB와 pre-migration backup은 새 버전의 정상 시작·핵심 smoke test 완료 전까지 삭제하지 않는다. 앱 삭제는 app-private 데이터를 지우므로 삭제 전 `user.sqlite3`를 수동 export할 수 있게 한다.

| 구성요소 | 개인용 기본값 | 역할 |
|---|---|---|
| 원문·parsed 파일 | PC 로컬 파일시스템 | Android APK에 기본 포함하지 않음 |
| 메타데이터·콘텐츠 | PC authoring DB → Android read-only content DB | 검수된 runtime subset만 APK에 포함 |
| 오답·북마크·설정 | Android app-private user DB | APK/content 업데이트와 분리해 보존 |
| 키워드 검색 | PC `chunks_fts`; Android `knowledge_fts` | 필수 검색; 외부 토큰 0 |
| 의미 검색 | PC 제작 도구에서만 선택적 FAISS/HNSW | Android에는 query encoder·vector index를 넣지 않음 |
| 문제 생성 | element direct lookup + deterministic renderer | retrieval·생성 모두 로컬, seed 재현 가능 |
| 문장 다듬기·rubric 시험 | PC 제작에서만 선택적 로컬 모델 | 승인 결과만 content DB에 export; 모델은 APK에 미포함 |
| PostgreSQL·S3·Hosted File Search | 사용하지 않음 | 단일 사용자 경로에서는 불필요한 비용·운영 복잡도 |

### 9.3 한 번 파싱·증분 갱신 파이프라인

초기 source manifest는 이 문서의 8장 표와 `SourceRef`를 기계적으로 읽어 만들 수 있다. canonical URL로 중복을 합치되 여러 source ID alias는 보존한다. `pdf/course/problem_set/exam/book/official_scope/regulation/filing/api`는 내용 corpus 후보로 만들고, `license`와 API 가격 확인 링크는 provenance 전용으로 `enabled=false`를 준다. 따라서 참고 링크를 다시 손으로 입력하거나 원격 모델로 분류할 필요가 없다.

```text
Markdown·SourceRef에서 source manifest bootstrap
→ parser·authority tier·element hint 검수
→ URL fetch 또는 local file import
→ 원본 SHA-256 확인; 기존 hash면 즉시 종료
→ raw/에 불변 저장하고 source_version 추가
→ HTML/PDF/JSON/XLSX/text parser 실행; 스캔 페이지만 OCR
→ 페이지·heading·표·수식·offset 단위 정규화
→ chunk hash·MinHash·수식 AST로 중복 제거
→ element ID 매핑과 claim·공식 후보 작성/검수
→ SQLite upsert와 FTS5 증분 rebuild
→ PC semanticSearchEnabled일 때만 변경 chunk를 로컬 embedding
→ deterministic blueprint regression build
→ 계산 template 10,000-seed 독립 solver·MentalMathAudit
→ 통과한 runtime subset만 content.sqlite3로 export하고 승인 knowledge projection으로 knowledge_fts build
→ content DB hash·schema version·row-count invariant를 EmbeddedContentManifest로 생성
→ 영향 문항 역색인·snapshot·backup manifest 갱신
```

기본 Android release 설정은 다음과 같다. PC authoring은 자료 fetch를 위해 네트워크를 쓸 수 있지만 퀴즈 APK 설정과 분리한다.

```yaml
deploymentMode: personal_android_sideload
networkDuringQuiz: false
retrievalMode: element_direct
semanticSearchEnabled: false
localLlmEnabled: false
remoteApiEnabled: false
maxRemoteCallsPerDay: 0
maxRemoteTokensPerDay: 0
calculatorFeatureEnabled: false
scratchpadFeatureEnabled: false
internetPermission: false
oneDriveRuntimeSync: false
```

`sources.local.yaml`의 최소 예시는 다음과 같다.

```yaml
sources:
  - sourceRefId: SCOPE-YIG-01
    canonicalUrl: https://yig.yonsei.ac.kr/recruiting
    authorityTier: 3
    ingestMode: refresh_if_changed
    parserId: html_readability
    enabled: true
    crawlScope: single_document
    maxDepth: 0
    rateLimitRps: 0.5
    refreshPolicy: manual
    language: ko
    elementHints: [EQV]

  - sourceRefId: SCOPE-YFL-01
    canonicalUrl: https://yflyonsei.com/uploads/%EB%B0%95%EC%84%9C%ED%98%84/Recruiting%203.PNG
    authorityTier: 3
    ingestMode: fetch_once
    parserId: image_ocr
    enabled: true
    crawlScope: single_document
    maxDepth: 0
    rateLimitRps: 0.5
    refreshPolicy: manual
    language: ko
    elementHints: [ACC, CF, DER, IBT]
```

FTS와 문제 생성은 서로 분리한다. PC authoring은 전체 원문 `chunks_fts`, Android는 승인된 compact `knowledge_fts`만 검색한다. 정상 출제는 두 FTS와 무관하게 아래처럼 claim을 직접 조회한다.

```sql
SELECT claim_id, statement, assumptions_json, misconception_tags
FROM concept_claims
WHERE element_id = :element_id AND review_status = 'approved'
ORDER BY claim_id;
```

퀴즈 생성은 `element_direct` 조회가 기본이다. Android에서 사용자가 승인 지식을 검색하거나 blueprint가 인접요소를 요구할 때만 `knowledge_fts`를 호출한다. 의미 검색 실험은 PC authoring의 전체 `chunks_fts`에서만 허용하며, 필요할 때 로컬 embedding을 `(chunk_sha256, embedding_model_hash)`로 캐시한다. 이 vector와 query encoder는 release export 대상이 아니다.

PC authoring의 선택적 로컬 LLM은 로컬 JSON endpoint 뒤에 provider-neutral adapter로 붙인다. 용도는 `(a)` ingestion 시 claim 후보 제안, `(b)` 완성된 문항의 문장 변형, `(c)` rubric 시험으로 제한한다. 로컬 모델의 출력은 출처가 아니며 검증·cache를 통과하지 못하면 content DB에 export하지 않는다.

### 9.4 크롤링·PDF·버전 운영

- `FinanceInterviewLocal/1.0 (+사용자 연락처)`처럼 식별 가능한 User-Agent를 쓰고 기본 호스트당 동시요청 1개, `0.5 req/s` 이하로 시작한다. `429/403`은 즉시 중단하고 `5xx`만 지수 backoff 후 최대 3회 재시도한다.
- SEC 공식 한도는 전체 시스템 합산 초당 10회 미만이며, 이 앱은 여유를 두고 `1~2 req/s`로 제한한다. 로그인·유료벽·CAPTCHA·비공개 API·다운로드 토큰은 우회하지 않는다.
- 기본은 `crawlScope=single_document`, `maxDepth=0`이다. ETag·`If-Modified-Since`를 사용하고 source manifest 밖의 링크, 검색결과 페이지, 무한 query parameter를 따라가지 않는다.
- `local_file`을 고르면 importer가 원본을 `work/data/raw/{source_id}/{sha256}`로 복사한 뒤 그 내부 경로만 DB에 저장한다. 따라서 백업·복원이 원본 파일의 옛 위치에 의존하지 않는다.
- PDF는 MIME·magic bytes·SHA-256·크기·수집일을 저장한다. 텍스트 추출을 먼저 시도하고 텍스트가 없는 페이지만 300dpi `kor+eng` OCR을 쓰며, 평균 신뢰도 0.85 미만은 검수 대상으로 표시한다.
- 표는 셀 관계, 수식은 LaTeX·변수·단위·가정으로 분리한다. 첨자·마이너스·분수선·%·bp OCR은 자동 승인하지 않는다. 이미지·도표는 source locator와 OCR 신뢰도를 함께 저장한다.
- 원본 SHA-256으로 완전중복, 정규화 텍스트 MinHash/SimHash로 근접중복, 숫자·기업·통화를 placeholder화한 문제 골격과 수식 AST로 변형문제 중복을 찾는다.
- 새 원문은 덮어쓰지 않고 `source_versions`에 추가한다. 갱신은 사용자가 누르는 `manual sync` 또는 `refresh_if_changed`에서만 수행하며, 실패하면 마지막 정상본을 유지한다.
- ingest 완료 직후 SQLite를 정상 종료한 다음 `authoring.sqlite3 + raw/ + parsed/ + source manifest`를 PC `backups/`에 복사하고 hash manifest를 검증한다. Android `user.sqlite3` 백업은 앱의 수동 export/import 경로로 별도 관리한다.

### 9.5 권장 로컬 corpus 구축 순서

1. 이 문서의 135개 요소·수식·파라미터·오개념을 먼저 SQLite에 넣는다.
2. Federal Reserve·SEC·BIS·IFRS·OpenDART 등 1차 자료와 기업공시를 파싱해 Tier 1 locator를 채운다.
3. MIT OCW·OpenStax·Damodaran·KOCW 등 교안·예제의 공개 HTML/PDF를 로컬 파싱해 설명과 연습문제 구조를 보강한다.
4. YIG·YFL 공개 페이지는 면접 scope·리서치 산출물·질문 문맥에 매핑한다.
5. 사용자가 가진 교재·교안·PDF는 `local_file`로 가져와 개인 검색 corpus에 추가한다.
6. 각 요소의 최소 claim과 18개 결정론적 signature regression을 통과한 뒤 그 요소를 앱에 공개한다.

YIG·YFL과 인터뷰 가이드는 무엇을 묻는지 정하는 Tier 3 자료이고, 정의·공식의 진위는 가능한 한 공시·기준서·대학 교안 등 Tier 1·2와 교차검증한다. corpus와 APK는 개인 PC·개인 OneDrive·본인 Android의 폐쇄된 범위에서만 이동하며, 향후 제3자 공유 기능을 만들 때만 8.7의 조건을 publication gate로 승격한다.

## 10. 로컬 우선 운영·리소스·선택적 API fallback

### 10.1 기본 프로필의 비용은 `$0`

정상 퀴즈 경로는 `SQLite 직접 조회/FTS5 → deterministic renderer → 로컬 validator → snapshot cache`다. 원격 embedding, 원격 생성모델, Hosted File Search, 서버 호스팅을 사용하지 않으므로 **외부 API 호출·토큰·호스팅 비용은 정확히 `$0`**이다. 남는 비용은 개인 PC의 최초 PDF OCR·인덱싱 시간과 Android의 저장공간·배터리뿐이다.

| 항목 | 기본값 | 외부 토큰/호출비 |
|---|---|---:|
| 계산문제 생성·reference solver·채점 | 로컬 결정론적 코드 | `$0` |
| 개념 객관식·참거짓·순서배열 | claim+frame+오개념 규칙 조립 | `$0` |
| claim 조회 | element ID 직접 SQL | `$0` |
| corpus 검색 | SQLite FTS5/BM25 | `$0` |
| semantic embedding | 꺼짐 | `$0` |
| 로컬 LLM | Android 미포함; PC 제작에서도 기본 꺼짐 | `$0` |
| 원격 API·File Search·cloud embedding | 하드 비활성화 | `$0` |
| 퀴즈 중 네트워크 | 차단 | `$0` |

### 10.2 PC 제작 모드와 Android 실행 모드

| 모드 | 검색·생성 구성 | 쓰는 경우 | API 비용 |
|---|---|---|---:|
| `offline_strict` **Android 기본** | direct SQL + FTS5 + deterministic renderer | 계산형과 대부분의 개념형 | `$0` |
| `offline_semantic` **PC 제작 전용** | 전체 corpus + 로컬 query encoder/vector index | FTS recall을 제작·검수 단계에서 보완할 때 | `$0` |
| `offline_local_llm` **PC 제작 전용** | 로컬 모델로 문장 변형 후 검수·cache; 승인 결과만 content DB에 export | 문장 다양화·claim 후보 작성 | `$0` 외부비용; PC 연산만 사용 |
| `remote_opt_in` **PC 제작 전용** | 필요한 후보 1건만 외부 모델 호출 후 검수·cache | 로컬 제작 기능으로 해결되지 않은 경우 | 공급자 단가만큼 발생 |

Android의 문제 제공 우선순위는 다음과 같이 고정한다.

1. 계산형 deterministic template 또는 개념형 deterministic signature
2. 이미 materialize된 로컬 snapshot
3. 검수된 고정 fallback bank
4. PC에서 미리 승인해 content DB에 포함한 캐시 문장 변형

Android에는 1~4 외의 경로가 없다. 로컬 LLM binary·원격 client·API key 로더를 APK에 넣지 않고, `android.permission.INTERNET`도 선언하지 않는다. PC 제작에서 모델을 사용해도 승인 snapshot만 export하며 provider 정보·prompt secret·API key는 content DB에 넣지 않는다.

### 10.3 로컬 저장·연산 절약 규칙

- URL 원본은 `source_id + content_sha256`, parsed 문서는 `content_sha256 + parser_config_hash`로 캐시한다.
- FTS는 바뀐 document의 row만 갱신한다. 전체 corpus 재파싱은 parser version을 명시적으로 올렸을 때만 한다.
- 선택적 embedding은 `(chunk_sha256, embedding_model_hash)`로 캐시하고 변경 chunk만 계산한다.
- PC 제작의 선택적 로컬 LLM은 `(model_hash, prompt_hash, input_hash)`로 캐시하고 동일 입력을 다시 추론하지 않는다.
- 문항은 `(corpusVersion, scopeVersion, blueprintVersion, rendererVersion, seed)`로 재현하며, 북마크는 생성 결과 전체를 저장한다.
- vector 저장량의 대략값은 `chunk 수 × 차원 수 × 값당 byte`다. 예를 들어 12,500 chunk, 768차원, float32면 원시 벡터는 약 `38.4MB`다. PC에서는 작지만 APK·휴대폰 저장공간에는 불필요한 증가이므로 실제 검색 개선이 확인되기 전에는 포함하지 않는다.

### 10.4 원격 API를 정말 쓸 때의 hard cap

이 절은 **PC authoring 도구에만** 적용한다. 기본값은 `maxRemoteCallsPerDay=0`, `maxRemoteTokensPerDay=0`이고, 둘 다 양수로 직접 지정했을 때만 호출한다. 제한 초과·공급자 오류·네트워크 단절은 deterministic 제작 경로로 fallback한다. Android release는 설정 변경으로 열 수 없게 compile-time `remoteApiEnabled=false`, cap `0`, `internetPermission=false`로 고정한다. 공급자와 단가는 자주 바뀌므로 PC 기능을 실제로 켤 때만 [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing), [embedding 모델 페이지](https://developers.openai.com/api/docs/models/text-embedding-3-small), [File Search 가이드](https://developers.openai.com/api/docs/guides/tools-file-search)처럼 8.7의 공식 링크에서 확인한다.

### 10.5 개인 OneDrive를 이용한 Android 사이드로드

```text
PC authoring·검수 완료
→ read-only content.sqlite3 export
→ release APK 빌드(AAB·debug APK 아님)
→ 고정 applicationId·동일 개인 signing key로 서명
→ versionCode 증가·versionName/contentDbVersion 기록
→ APK 서명 검증·SHA-256·외부 release-manifest.json 생성
→ APK + release-manifest.json + SHA256SUMS.txt만 개인 OneDrive에 수동 업로드
→ 본인 Android에서 다운로드·checksum·certificate fingerprint 확인
→ OneDrive 또는 파일 앱에 일시적으로 설치 허용 후 sideload/업데이트
→ 비행기 모드 smoke test와 user.sqlite3 보존 확인
```

- Play Store·다른 앱스토어·공개 다운로드 페이지·테스트 배포 서비스는 사용하지 않는다. 배포 대상은 소유자 1명과 본인 기기뿐이다.
- `applicationId`와 signing certificate를 바꾸면 기존 앱의 정상 업데이트가 되지 않으므로 처음부터 고정한다. 매 release는 `versionCode`를 증가시킨다.
- signing keystore·private key·비밀번호·복구문구는 APK, 저장소, content DB, OneDrive에 넣지 않는다. 암호화한 별도 오프라인 위치에 이중 백업하고 certificate SHA-256만 release manifest에 기록한다.
- OneDrive에는 서명된 APK, 외부 release manifest, checksum, 필요할 때 사용자가 직접 export한 백업만 둔다. 앱에 OneDrive SDK·계정 로그인·자동 동기화 코드를 넣지 않는다.
- 동일 서명 APK의 상위 버전 설치는 `user.sqlite3`를 유지해야 한다. 앱 삭제·데이터 삭제 전에는 북마크·오답·설정을 수동 export하며, 재설치 후 import할 수 있어야 한다.
- release APK에는 인터넷 권한, 분석/광고/결제 SDK, Play Billing, Play Store updater, 원격 crash reporter를 넣지 않는다. 필요한 로그는 기기 내부에서만 보관하고 사용자가 직접 export한다.

## 11. 배포 전 완료 기준

- [ ] `ACC/CF/INV/FI/DER/EQV/IBT`에 총 135개 요소가 있고, 각 분야에서 번호가 연속된다.
- [ ] 일반 요소는 최소 9개, `EQV`·`IBT`는 최소 12개의 승인 claim을 가져 총 1,461개 이상이다.
- [ ] 각 요소에 최소 개념 1개와 수식 또는 명시적 관계 1개가 있고, 계산 가능한 요소에는 문제 템플릿이 있다.
- [ ] 모든 계산 템플릿에 파라미터 범위·정수답 규칙·`MentalMathPolicy`·검수된 암산 경로가 있다.
- [ ] 모든 정답 해설에 개념·수식·대입·정답·해석이 있다.
- [ ] URL 기반 출처 ID는 클릭 가능한 링크, `local_file`·`manual_note`는 유효한 로컬 locator와 연결된다.
- [ ] 10,000-seed 생성 테스트에서 독립 solver와 독립 `auditMentalMath`를 모두 통과한다.
- [ ] 모든 release 계산문항은 `calculatorAllowed=false`, 정확한 중간값, 유효숫자≤3, 금지연산 0이고 난이도별 score/input/time cap `2/4/6`, `4/6/8`, `30/60/90초`를 지킨다.
- [ ] `explicit_rounding` 템플릿과 암산 audit 불합격 instance가 Android content DB에 0개다.
- [ ] 각 요소가 최소 18개, 전체 2,430개 이상의 서로 다른 검증된 deterministic signature를 생성할 수 있다. snapshot은 최초 사용 시 materialize된다.
- [ ] 개념문항의 citation coverage·anchor validity가 100%이고 unsupported claim·scope leak가 0이다.
- [ ] 같은 corpus/scope/blueprint/renderer version과 seed가 byte-identical 문항을 만들며, 계산·개념 오답 snapshot이 재현된다.
- [ ] Android 비행기 모드 통합 테스트에서 학습·랜덤 퀴즈·암산 채점·해설·오답 북마크·복습·검색이 모두 작동한다.
- [ ] Android는 compile-time `remoteApiEnabled=false`, 호출·토큰 cap `0`, `internetPermission=false`이고 실제 네트워크 트래픽이 0이다.
- [ ] Android APK에 로컬 LLM·query encoder·vector index가 없고도 결정론적 문제·채점·`knowledge_fts` 검색이 모두 작동한다.
- [ ] 모든 source에 ingest mode·parser·parse status·SHA-256·원본 locator가 있고, 실패한 refresh가 이전 정상 version을 지우지 않는다.
- [ ] PC `chunks_fts`와 선택적 vector index는 raw/parsed에서, Android `knowledge_fts`는 승인 knowledge projection에서 재구축할 수 있다.
- [ ] PC `authoring.sqlite3+raw+parsed+manifest` 백업과 Android `user.sqlite3` 수동 export/import가 각각 hash 검증·복원 테스트를 통과한다.
- [ ] 자동수집이 `401/403/429`와 로그인·유료벽·CAPTCHA에서 중단되며 접근통제를 우회하지 않는다.
- [ ] 특정 학회 공식 기출이 아닌 자체 제작 문제임을 앱에 고지한다.
- [ ] release 산출물이 debug APK나 AAB가 아닌 서명 APK이고, 고정 `applicationId`·동일 signing certificate·증가한 `versionCode`를 사용한다.
- [ ] signing keystore·private key·비밀번호가 APK·저장소·OneDrive에 없고 별도 오프라인 백업이 있으며, APK SHA-256과 certificate fingerprint를 기록한다.
- [ ] PC authoring DB, APK의 read-only `content.sqlite3`, app-private `user.sqlite3`가 분리되고 raw/OCR/model 파일은 APK에 포함되지 않는다.
- [ ] clean install과 동일서명 upgrade를 본인 Android에서 시험하고, upgrade 후 오답·북마크·설정·snapshot이 유지된다.
- [ ] 새 content asset은 versioned `.tmp`에 복사한 뒤 서명 APK 내부 manifest의 DB SHA-256·schema version·row-count invariant와 SQLite integrity를 검증한다. 완성 DB를 먼저 확정하고 `active-version.json` pointer 하나만 atomic rename하며, 중간 crash와 N−1 rollback을 시험한다.
- [ ] 실패한 DB migration은 transaction rollback되고 기존 content/user DB로 복구된다. 삭제 전 export와 재설치 후 import도 검증한다.
- [ ] release 산출물은 APK·외부 release manifest·checksum만 개인 OneDrive로 수동 전송한다. 별도 사용자 백업은 명시적 export 파일만 허용하며 OneDrive SDK·자동 sync·분석·광고·결제·Play Store updater·원격 crash reporter가 없다.
