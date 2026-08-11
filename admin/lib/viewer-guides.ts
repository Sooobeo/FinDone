export interface ViewerGuideSection {
  title: string;
  description: string;
  items: string[];
}

export interface ViewerGuide {
  eyebrow: string;
  title: string;
  description: string;
  sections: ViewerGuideSection[];
}

export const viewerGuides = {
  dashboard: {
    eyebrow: "CONTENT OVERVIEW",
    title: "콘텐츠 운영 구조",
    description: "FinDone 콘텐츠가 작성부터 앱 반영까지 어떤 단계와 정보로 관리되는지 소개합니다.",
    sections: [
      { title: "학습 콘텐츠", description: "앱에서 읽는 금융 학습 단위입니다.", items: ["분야와 요소 식별 정보", "개념·수식·학습 설명", "출처와 학습 체크리스트"] },
      { title: "원본 근거", description: "설명의 근거와 위치를 추적합니다.", items: ["문서·웹 자료 정보", "페이지·절·URL 위치", "학습요소 연결 상태"] },
      { title: "품질 관리", description: "자동 검사와 사람의 검토를 분리합니다.", items: ["revision 변경 이력", "자동 검증 결과", "승인·수정·반려 결정"] },
      { title: "앱 반영", description: "승인된 내용만 새 버전으로 묶습니다.", items: ["콘텐츠 버전과 변경 요약", "SQLite·manifest 무결성", "배포 채널과 반영 상태"] },
    ],
  },
  concepts: {
    eyebrow: "CONTENT DATABASE",
    title: "개념 DB 구성 안내",
    description: "실제 금융 콘텐츠 값 대신, 하나의 학습요소에 어떤 정보가 들어가는지 설명합니다.",
    sections: [
      { title: "기본 식별 정보", description: "요소를 찾고 분류하기 위한 기준입니다.", items: ["분야 ID와 분야명", "요소 ID와 표시 순서", "개념형·계산형 구분"] },
      { title: "학습 설명", description: "사용자가 읽는 핵심 본문입니다.", items: ["제목과 핵심 관계", "정의와 직관 설명", "적용 범위와 상세 학습 노트"] },
      { title: "수식 정보", description: "공식의 의미와 사용 조건을 함께 기록합니다.", items: ["수식 표현", "변수와 적용 가정", "수식 설명과 계산 기준"] },
      { title: "근거와 품질", description: "출처와 배포 가능 상태를 확인합니다.", items: ["출처명과 원본 위치", "학습 체크리스트", "revision 상태와 검증 이슈"] },
    ],
  },
  sources: {
    eyebrow: "SOURCE LIBRARY",
    title: "원본 자료 구성 안내",
    description: "실제 파일명과 주소를 공개하지 않고, 근거 자료를 어떻게 관리하는지 설명합니다.",
    sections: [
      { title: "자료 식별", description: "원본을 중복 없이 구분합니다.", items: ["자료 ID와 표시 이름", "PDF·문서·표·URL 유형", "등록 시각과 버전"] },
      { title: "원본 위치", description: "파일 또는 웹 근거의 위치를 보존합니다.", items: ["비공개 저장 경로", "공개 웹 URL", "문서 페이지·절 위치"] },
      { title: "처리 상태", description: "가공 진행 상황을 표시합니다.", items: ["처리 중", "검토 필요", "사용 준비 완료·실패"] },
      { title: "콘텐츠 연결", description: "어떤 학습요소의 근거인지 연결합니다.", items: ["연결된 요소 수", "인용한 근거 조각", "주출처와 보조출처 구분"] },
    ],
  },
  distractors: {
    eyebrow: "DISTRACTOR LIBRARY",
    title: "오답 후보 구성 안내",
    description: "실제 문제 선택지 대신, 좋은 오답 후보를 구성하는 필드를 설명합니다.",
    sections: [
      { title: "연결 대상", description: "오답이 사용될 학습요소를 지정합니다.", items: ["요소 ID와 제목", "개념형 문제 연결", "사용 여부"] },
      { title: "오답 문구", description: "정답처럼 보이지만 명확히 틀린 문장을 기록합니다.", items: ["한 가지 개념 오류", "정답과 유사한 문장 구조", "불필요한 단서 배제"] },
      { title: "오답 해설", description: "왜 틀렸는지 학습자가 이해하도록 설명합니다.", items: ["잘못 적용한 관계", "올바른 판단 기준", "연결 학습 포인트"] },
      { title: "분류 정보", description: "출제 균형과 검수를 위한 메타데이터입니다.", items: ["혼동 유형", "기초·보통·심화 난이도", "초안·검토·승인 상태"] },
    ],
  },
  validation: {
    eyebrow: "QUALITY GATE",
    title: "자동 검증 구성 안내",
    description: "실제 검증 대상과 오류 내용 대신, 콘텐츠가 통과해야 하는 검사 구조를 설명합니다.",
    sections: [
      { title: "검증 대상", description: "저장된 변경 단위를 대상으로 합니다.", items: ["revision ID와 유형", "변경 사유와 작성 시각", "콘텐츠 해시"] },
      { title: "구조 검사", description: "앱이 안전하게 읽을 수 있는지 확인합니다.", items: ["필수 필드와 데이터 형식", "Markdown·수식 구조", "요소 간 참조 무결성"] },
      { title: "콘텐츠 검사", description: "학습 정보의 완결성을 확인합니다.", items: ["정의·수식·가정 연결", "출처와 체크리스트", "문제 생성 가능 여부"] },
      { title: "결과 기록", description: "검사 결과는 별도 이력으로 남깁니다.", items: ["통과·실패 검사 수", "오류·경고·정보 이슈", "검증기 버전과 실행 상태"] },
    ],
  },
  review: {
    eyebrow: "HUMAN REVIEW",
    title: "승인 검토 구성 안내",
    description: "실제 변경 내용은 숨기고, Owner가 어떤 근거로 변경을 검토하는지 설명합니다.",
    sections: [
      { title: "검토 대상", description: "자동 검증을 통과한 revision만 표시합니다.", items: ["요소와 변경 유형", "변경 사유", "검증 통과 상태"] },
      { title: "변경 비교", description: "이전 값과 수정 값을 필드별로 비교합니다.", items: ["변경된 필드", "이전 revision", "검토할 revision"] },
      { title: "검토 근거", description: "자동 검증과 원본 근거를 함께 확인합니다.", items: ["검증기와 통과 검사 수", "콘텐츠 해시", "출처 연결 상태"] },
      { title: "검토 결정", description: "Owner가 최종 상태를 결정합니다.", items: ["승인", "수정 요청", "반려와 검토 코멘트"] },
    ],
  },
  releases: {
    eyebrow: "APP DELIVERY",
    title: "앱 반영 구성 안내",
    description: "실제 릴리스 값과 파일은 공개하지 않고, 승인본이 앱에 반영되는 구조를 설명합니다.",
    sections: [
      { title: "버전 정보", description: "앱이 구분할 콘텐츠 버전을 정의합니다.", items: ["콘텐츠 버전과 이름", "DB schema 버전", "최소 앱 버전"] },
      { title: "포함 항목", description: "승인된 revision만 릴리스에 담습니다.", items: ["학습요소 수", "변경 요약", "릴리스 노트"] },
      { title: "무결성", description: "다운로드 후 변조 여부를 확인합니다.", items: ["SQLite SHA-256", "manifest SHA-256", "파일 크기와 artifact 수"] },
      { title: "배포 상태", description: "생성부터 공개까지 단계를 나눕니다.", items: ["초안·빌드·검증", "공개·철회 상태", "stable 채널 반영"] },
    ],
  },
} satisfies Record<string, ViewerGuide>;
