# FinDone 데이터 모델 및 ERD

문서 상태: 2026-08-12 migration과 SQLite DDL 기준

## 데이터 저장소 분리

FinDone에는 역할이 다른 네 데이터 모델이 있다.

| 저장소 | 목적 | 변경 주체 | 배포/보존 |
|---|---|---|---|
| Supabase PostgreSQL | 원본, 저작, 검토, 작업, 릴리스 이력 | Admin과 권한 분리 Worker | migration으로 관리 |
| 앱 콘텐츠 SQLite | 검증된 읽기 전용 학습 콘텐츠 | 로컬 compiler 또는 Release Worker | APK 내장 또는 stable update |
| 앱 용어집 SQLite | 검증된 읽기 전용 금융 용어와 FTS | Glossary Worker | APK baseline 또는 독립 glossary stable update |
| 사용자 SQLite | 시도, 오답, 북마크, 메모, 주석, 용어 상태 | Android 앱 사용자 | 콘텐츠 교체와 독립, 기기 보존 |

ERD는 읽을 수 있도록 bounded context별로 나눈다. 전체 컬럼과 trigger/RLS의
최종 기준은 [Supabase migrations](../../supabase/migrations)와
[`SCHEMA_SQL`](../../tools/build_content_db.py),
[`glossary SCHEMA_SQL`](../../tools/build_glossary_db.py),
[`UserDatabase`](../../app/src/main/java/com/findone/app/data/UserRepository.kt)다.

## Supabase: 원본과 저작

```mermaid
erDiagram
    DOMAINS ||--o{ ELEMENTS : contains
    SOURCES ||--o{ SOURCE_VERSIONS : versions
    SOURCE_VERSIONS ||--o{ SOURCE_FILES : stores
    SOURCE_VERSIONS ||--o{ SOURCE_FRAGMENTS : extracts
    SOURCE_VERSIONS ||--o{ SOURCE_ELEMENT_CANDIDATES : ranks
    ELEMENTS ||--o{ SOURCE_ELEMENT_CANDIDATES : matched_by
    ELEMENTS ||--o| CONCEPTS : defines
    ELEMENTS ||--o{ FORMULAS : explains
    ELEMENTS ||--o{ DISTRACTORS : owns
    ELEMENTS ||--o{ ELEMENT_SOURCES : cites
    SOURCES ||--o{ ELEMENT_SOURCES : linked_to
    SOURCE_VERSIONS ||--o{ CONTENT_EVIDENCE : supports

    DOMAINS {
        text domain_id PK
        text name
        int display_order
        bool is_active
    }
    ELEMENTS {
        text element_id PK
        text domain_id FK
        int element_number
        text title
        text mode
        bool is_active
    }
    SOURCES {
        text source_id PK
        text kind
        text label
        text locator
        bool is_active
    }
    SOURCE_VERSIONS {
        uuid source_version_id PK
        text source_id FK
        int version_number
        text parse_status
        text sha256
    }
    SOURCE_FILES {
        uuid source_file_id PK
        uuid source_version_id FK
        text file_role
        text object_path
        text sha256
    }
    SOURCE_FRAGMENTS {
        uuid source_fragment_id PK
        uuid source_version_id FK
        int ordinal
        text fragment_kind
        text content_sha256
    }
    SOURCE_ELEMENT_CANDIDATES {
        uuid source_version_id PK, FK
        text element_id PK, FK
        int rank
        decimal score
    }
    CONCEPTS {
        text concept_id PK
        text element_id FK, UK
        text definition_markdown
        json glossary_terms
    }
    FORMULAS {
        text formula_id PK
        text element_id FK
        text formula_key
        bool is_primary
    }
    DISTRACTORS {
        uuid distractor_id PK
        text element_id FK
        text distractor_key
        int difficulty
    }
    ELEMENT_SOURCES {
        text element_id PK, FK
        text source_id PK, FK
        int ordinal
    }
    CONTENT_EVIDENCE {
        uuid evidence_id PK
        text entity_type
        text entity_key
        uuid source_version_id FK
        json locator
    }
```

`content_evidence.entity_type + entity_key`는 concept, formula 등 저작 엔티티를
가리키는 polymorphic key다. 대상 엔티티 존재 여부는 trigger가 검사하며 단일
SQL FK로 표현되지 않는다.

## Supabase: 로컬 생성 파이프라인

```mermaid
erDiagram
    CONTENT_GENERATION_BATCHES ||--o{ CONTENT_GENERATION_BATCH_SOURCES : consumes
    SOURCE_VERSIONS ||--o{ CONTENT_GENERATION_BATCH_SOURCES : included_in
    SOURCES ||--o{ CONTENT_GENERATION_BATCH_SOURCES : identifies
    CONTENT_GENERATION_BATCHES ||--o{ CONTENT_GENERATION_ITEMS : proposes
    ELEMENTS ||--o{ CONTENT_GENERATION_ITEMS : targets
    CONTENT_GENERATION_ITEMS ||--o{ CONTENT_GENERATION_EVIDENCE : justified_by
    SOURCE_FRAGMENTS ||--o{ CONTENT_GENERATION_EVIDENCE : supports
    CONTENT_GENERATION_BATCHES ||--o{ CONTENT_MODEL_RUNS : records
    ELEMENTS o|..o{ CONTENT_MODEL_RUNS : measured_for
    CONTENT_REVISIONS o|..o| CONTENT_GENERATION_ITEMS : materialized_by
    CONTENT_RELEASES o|..o| CONTENT_GENERATION_BATCHES : approved_from

    CONTENT_GENERATION_BATCHES {
        uuid batch_id PK
        uuid request_key UK
        text status
        text model_name
        int progress_percent
        text processing_stage
        uuid release_id FK, UK
    }
    CONTENT_GENERATION_BATCH_SOURCES {
        uuid batch_id PK, FK
        uuid source_version_id PK, FK
        text source_id FK
    }
    CONTENT_GENERATION_ITEMS {
        uuid generation_item_id PK
        uuid batch_id FK
        text element_id FK
        text entity_type
        json generated_snapshot
        decimal confidence
        text risk_level
        uuid revision_id FK, UK
    }
    CONTENT_GENERATION_EVIDENCE {
        uuid generation_evidence_id PK
        uuid generation_item_id FK
        uuid source_fragment_id FK
        text field_path
        text support_role
    }
    CONTENT_MODEL_RUNS {
        uuid model_run_id PK
        uuid batch_id FK
        text element_id FK
        text run_kind
        text model_name
        int duration_ms
        text status
    }
```

`content_model_runs`는 외부 API 응답 로그가 아니라 체크인된 결정론적 로컬 규칙
실행 audit다. 현재 계약에서는 input/output token이 0이다.

## Supabase: revision, 검토와 릴리스

```mermaid
erDiagram
    CONTENT_REVISIONS ||--o{ REVISION_STATE_EVENTS : transitions
    CONTENT_REVISIONS o|..o{ VALIDATION_RUNS : validates
    VALIDATION_RUNS ||--o{ VALIDATION_ISSUES : reports
    CONTENT_REVISIONS ||--o{ REVIEW_DECISIONS : reviewed_by
    CONTENT_REVISIONS ||--o{ APPROVAL_SNAPSHOTS : freezes
    REVIEW_DECISIONS ||--o| APPROVAL_SNAPSHOTS : authorizes
    CONTENT_RELEASES ||--o{ RELEASE_ITEMS : contains
    CONTENT_REVISIONS ||--o{ RELEASE_ITEMS : included_in
    CONTENT_RELEASES ||--o{ RELEASE_ARTIFACTS : emits
    CONTENT_RELEASES ||--o{ RELEASE_EVENTS : transitions
    CONTENT_RELEASES o|..o{ VALIDATION_RUNS : validates
    CONTENT_RELEASES o|..o{ INGESTION_JOBS : processed_by
    INGESTION_JOBS ||--o{ JOB_EVENTS : logs
    CONTENT_RELEASES ||--o{ RELEASE_CHANNELS : activated_as

    CONTENT_REVISIONS {
        uuid revision_id PK
        text entity_type
        text entity_key
        int revision_number
        text operation
        text content_hash
        json snapshot
    }
    REVISION_STATE_EVENTS {
        int revision_state_event_id PK
        uuid revision_id FK
        text state
        datetime created_at
    }
    VALIDATION_RUNS {
        uuid validation_run_id PK
        text target_type
        uuid revision_id FK
        uuid release_id FK
        text status
        text release_fingerprint
    }
    VALIDATION_ISSUES {
        uuid validation_issue_id PK
        uuid validation_run_id FK
        text severity
        text code
        text field_path
    }
    REVIEW_DECISIONS {
        uuid review_decision_id PK
        uuid revision_id FK
        text decision
        uuid reviewer_id FK
    }
    APPROVAL_SNAPSHOTS {
        uuid approval_snapshot_id PK
        uuid revision_id FK
        uuid review_decision_id FK, UK
        text content_hash
        json snapshot
    }
    CONTENT_RELEASES {
        uuid release_id PK
        int content_version UK
        text version_name UK
        text status
        text database_sha256
        text manifest_sha256
    }
    RELEASE_ITEMS {
        uuid release_item_id PK
        uuid release_id FK
        uuid revision_id FK
        text content_hash
    }
    RELEASE_ARTIFACTS {
        uuid release_artifact_id PK
        uuid release_id FK
        text artifact_kind
        text object_path
        text sha256
    }
    RELEASE_EVENTS {
        int release_event_id PK
        uuid release_id FK
        text status
        datetime created_at
    }
    RELEASE_CHANNELS {
        text channel PK
        uuid release_id FK
        datetime activated_at
    }
    INGESTION_JOBS {
        uuid job_id PK
        text job_kind
        text status
        uuid release_id FK
        int progress_percent
    }
    JOB_EVENTS {
        int job_event_id PK
        uuid job_id FK
        text status
        text level
    }
```

`validation_runs`는 revision, release, system 중 정확히 한 target 형태만 허용한다.
릴리스 검증에는 release item과 artifact를 포함한 fingerprint가 묶이므로 검증 뒤
내용이 바뀐 stale release는 활성화할 수 없다.

## 앱 콘텐츠 SQLite schema 2

```mermaid
erDiagram
    DOMAINS ||--o{ ELEMENTS : contains
    ELEMENTS ||--|| CONCEPT_CARDS : has
    ELEMENTS ||--|| FORMULA_CARDS : has
    ELEMENTS ||--o{ CONCEPT_QUESTIONS : asks
    CONCEPT_QUESTIONS ||--|{ CONCEPT_QUESTION_CHOICES : offers
    ELEMENTS ||--o{ CONCEPT_QUESTION_CHOICES : references
    ELEMENTS ||--o{ ELEMENT_SOURCES : cites
    SOURCES ||--o{ ELEMENT_SOURCES : linked_to

    METADATA {
        text key PK
        text value
    }
    DOMAINS {
        text domain_id PK
        text name
        int display_order UK
    }
    ELEMENTS {
        text element_id PK
        text domain_id FK
        int element_number
        text title
        text mode
    }
    CONCEPT_CARDS {
        text concept_id PK
        text element_id FK, UK
        text definition
        text intuition
    }
    FORMULA_CARDS {
        text formula_id PK
        text element_id FK, UK
        text expression
        text assumptions
    }
    CONCEPT_QUESTIONS {
        text question_id PK
        text element_id FK
        text question_type
        int difficulty
        text review_status
    }
    CONCEPT_QUESTION_CHOICES {
        text question_id PK, FK
        text choice_key PK
        text element_id FK
        bool is_correct
    }
    SOURCES {
        text source_id PK
        text label
        text locator
    }
    ELEMENT_SOURCES {
        text element_id PK, FK
        text source_id PK, FK
        int ordinal
    }
```

`knowledge_fts`는 `elements`의 검색 projection인 FTS5 virtual table이다. FK를
갖지 않으며 compiler가 같은 transaction에서 채우고 검증한다.

### Authoring에서 앱 DB로의 투영

| Supabase/생성 원천 | 앱 SQLite | 규칙 |
|---|---|---|
| `domains` | `domains` | 활성·승인된 분야만 |
| `elements` | `elements` | 안정적인 `element_id` 유지 |
| `concepts` | `concept_cards` | element당 1개 |
| primary `formulas` | `formula_cards` | element당 앱용 primary 1개 |
| `sources`, `element_sources` | 같은 이름의 두 테이블 | 출처 추적 보존 |
| 생성·검토된 question bank | `concept_questions`, `concept_question_choices` | 정확히 5개 선택지와 1개 정답 |
| release/build metadata | `metadata`, manifest | schema, version, hash, release status |

Admin의 `distractors`는 저작 후보 단위이고 앱의 5지선다 choice row와 동일한
스키마가 아니다. question/choice ID가 없는 legacy distractor를 임의로 앱
질문은행에 덮어쓰지 않는다.

## 독립 용어집 SQLite schema 1

```mermaid
erDiagram
    CATEGORIES ||--o{ TERMS : contains
    TERMS ||--o{ ALIASES : names
    TERMS ||--o{ LIMITATIONS : qualifies
    TERMS ||--o{ TERM_SOURCES : cites
    SOURCES ||--o{ TERM_SOURCES : supports
    TERMS ||--o{ RELATED_TERMS : links

    CATEGORIES {
        text category_id PK
        text name
        int display_order UK
        int term_count
    }
    TERMS {
        text term_id PK
        text category_id FK
        int display_order
        text canonical_name_en
        text canonical_name_ko
        text one_line_definition_ko
        text core_definition_ko
        text practical_context_ko
        text example_ko
    }
    ALIASES {
        text term_id PK, FK
        text label PK
        int display_order
    }
    LIMITATIONS {
        text term_id PK, FK
        int display_order PK
        text body_ko
    }
    SOURCES {
        text source_code PK
        text title
        text url
    }
    TERM_SOURCES {
        text term_id PK, FK
        text source_code PK, FK
    }
    RELATED_TERMS {
        text term_id PK, FK
        text related_term_id PK, FK
    }
```

`glossary_fts`는 이름·별칭·정의·실무 문맥을 투영한 FTS5 table이다. Supabase의
`glossary_term_admin_references`는 기존 비공개 `sources`와 용어를 연결하지만
Glossary Worker snapshot과 이 SQLite schema에는 포함되지 않는다. Admin의
soft archive는 감사 흔적을 보존하며 active row만 다음 독립 stable DB에 들어간다.

## 사용자 SQLite schema 5

```mermaid
erDiagram
    ATTEMPTS o|..o{ WRONG_QUEUE : last_attempt

    ATTEMPTS {
        int id PK
        text instance_id
        text element_id
        text template_id
        text mode
        int seed
        bool is_correct
        datetime created_at
    }
    BOOKMARKS {
        text instance_id PK
        text element_id
        text template_id
        text origin
        json snapshot_json
    }
    WRONG_QUEUE {
        text element_id PK
        text template_id PK
        int last_attempt_id FK
        int correct_streak
        bool resolved
    }
    ELEMENT_PROGRESS {
        text element_id PK
        int attempts
        int correct
        int current_streak
    }
    SETTINGS {
        text key PK
        text value
    }
    CONCEPT_NOTES {
        int id PK
        text element_id
        text title
        text body
        datetime updated_at
    }
    TEXT_ANNOTATIONS {
        int id PK
        text element_id
        text section_key
        text selected_text
        text style
        text comment
    }
    GLOSSARY_TERM_STATE {
        text term_id PK
        bool checked
        bool bookmarked
        datetime updated_at
    }
```

`element_id`, `term_id`와 template 식별자는 두 읽기 전용 DB를 논리적으로 참조하지만
서로 다른 SQLite 파일 사이에 물리 FK를 만들 수 없다. 용어 메모와 본문 표시는
`GLOSSARY:FIN-..` target을 사용한다. 앱은 콘텐츠·용어집 업데이트
뒤에도 안정 ID를 유지하고, 사라진 콘텐츠를 조회할 때 안전하게 무시하거나
정리한다. 사용자 DB의 유일한 물리 FK는 현재 `wrong_queue.last_attempt_id`에서
`attempts.id`로 이어지며 삭제 시 `NULL`이 된다.

## 주요 불변조건

- authoring row는 audit column과 revision snapshot으로 추적한다.
- 승인 snapshot과 release item의 `content_hash`는 동일해야 한다.
- release artifact의 저장 hash, release row hash와 실제 파일 hash가 같아야 한다.
- 앱 DB의 manifest row count, byte size, SHA-256과 SQLite 실물이 같아야 한다.
- 학습 콘텐츠 DB, 용어집 DB와 사용자 DB schema/version은 독립적으로 증가한다.
- RLS와 RPC 권한은 migration의 일부이며 ERD만 보고 권한을 추론하면 안 된다.
