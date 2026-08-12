# FinDone 문서 인덱스

이 디렉터리는 구현 상태를 설명하는 유지보수 문서, 운영 절차, 모델 실험
기록과 과거 구현 계획을 분리한다. 코드와 데이터 생성기가 직접 읽는 두 명세는
경로 안정성을 위해 저장소 루트에 유지한다.

## 기준 문서와 우선순위

1. [앱 최종 명세](../finance_interview_app_final_spec.md): 앱 콘텐츠와 출시 조건의
   canonical 입력. `tools/build_content_db.py`가 이 정확한 루트 경로를 읽는다.
2. [Admin 시스템 명세](../finance_interview_admin_system_spec.md): 관리자 저작,
   검토, 원본 처리와 릴리스 요구사항.
3. [Supabase migrations](../supabase/migrations): 실제 서버 데이터 모델과 권한의
   실행 가능한 기준.
4. Android, Admin, Worker 소스 코드: 실제 런타임 동작의 최종 기준.
5. 아래 설명 문서: 위 구현을 사람이 빠르게 파악하기 위한 유지보수 뷰.

문서와 코드가 다르면 코드·migration을 먼저 확인하고 문서를 같은 변경에서
갱신한다.

## Architecture

- [시스템 아키텍처](architecture/SYSTEM_ARCHITECTURE.md): 구성요소, 데이터 흐름,
  신뢰 경계, 배포 및 품질 게이트
- [데이터 모델 및 ERD](architecture/DATA_MODEL_ERD.md): Supabase PostgreSQL,
  앱 콘텐츠 SQLite, 사용자 SQLite의 관계와 매핑

## Modeling

- [모델링 문서 인덱스](modeling/README.md)
- [개념형 5지선다 오프라인 모델링 설계](modeling/CONCEPT_MCQ_MODELING_DESIGN.md)
- `modeling/experiments/`: 가중치·정규화·임베딩 조합별 재현 가능한 실험 기록

## Operations

- [Codex 실행 전 오류 방지 게이트](operations/CODEX_PREFLIGHT.md)
- [Admin 배포](operations/ADMIN_DEPLOYMENT.md)
- [릴리스 자동화](operations/RELEASE_AUTOMATION.md)
- [릴리스 체크리스트](operations/RELEASE_CHECKLIST.md)
- [업데이트 작업 최적화](operations/UPDATE_WORKFLOW_OPTIMIZATION.md)

## Guides and planning records

- [학습 콘텐츠 작성 가이드](guides/LEARNING_CONTENT_GUIDE.md)
- [Supabase Admin 구현 계획](planning/SUPABASE_ADMIN_IMPLEMENTATION_PLAN.md): 구현
  배경과 단계 기록. 현재 동작 확인에는 migration과 architecture 문서를 우선한다.

## 파일 배치 원칙

- 루트: 빌드 입력, Gradle wrapper·설정, 최상위 README와 Codex 지침만 둔다.
- `docs/architecture`: 현재 시스템과 데이터 구조
- `docs/modeling`: 설계와 실험 기록
- `docs/operations`: 배포, CI, 릴리스와 장애 예방 절차
- `docs/guides`: 저작·개발 가이드
- `docs/planning`: 구현 계획과 의사결정 배경
- `build`, `dist`, `.gradle`, `.kotlin`, `.ruff_cache`, `.tooling`, `.venv-concept`, Admin
  `.next`와 `node_modules`: 재생성 가능한 로컬 산출물이며 Git 추적 대상이 아니다.

이번 정리에서는 문서 삭제를 하지 않았다. 참조가 없더라도 설계 근거가 될 수
있는 파일은 적절한 하위 폴더로 이동해 보존했다.
