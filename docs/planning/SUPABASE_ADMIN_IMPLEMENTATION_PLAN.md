# FinDone Supabase 관리자 시스템 구현 계획

작성일: 2026-08-09
상태: 구현 전 의사결정 및 작업 계획

## 1. 목적

FinDone은 현재 Android 앱 내부의 SQLite를 사용한다. 앞으로는 배포된 관리자 웹에서 새로운 자료와 레퍼런스를 등록하고, 검수한 콘텐츠를 Android 앱에 배포할 수 있도록 Supabase를 중앙 제작 시스템으로 사용한다.

이 문서의 목표는 다음 작업을 시작할 때 기존 논의를 다시 정리하지 않고 바로 구현할 수 있게 하는 것이다.

## 2. 확정한 방향

- 관리자 웹은 인터넷에서 접속할 수 있도록 배포한다.
- Supabase를 콘텐츠 제작 및 관리의 중앙 데이터베이스로 사용한다.
- 관리자 웹에는 로그인 기능을 둔다.
- 관리자 계정은 처음부터 한 개만 생성한다.
- 사용자가 직접 가입할 수 있는 기능은 제공하지 않는다.
- Google OAuth는 사용하지 않고 Supabase 이메일/비밀번호 로그인을 사용한다.
- 관리자 아이디와 비밀번호를 소스 코드나 환경변수에 하드코딩하지 않는다.
- Android 앱의 SQLite를 전부 제거하지 않는다.
- 승인된 콘텐츠는 Android에서 로컬 SQLite로 사용하여 오프라인 동작과 빠른 검색을 유지한다.
- 사용자 풀이 기록의 실시간 클라우드 동기화는 초기 범위에서 제외한다.

## 3. 현재 상태

Android 앱은 두 종류의 SQLite 데이터를 사용한다.

### `content.sqlite3`

- APK에 포함되는 읽기 전용 콘텐츠 데이터베이스다.
- 현재 크기는 약 2.1MB다.
- 앱 실행 시 앱 전용 저장소로 복사하고 무결성을 검증한 후 읽기 전용으로 연다.
- 현재 콘텐츠, 분야, 요소, 공식, 출처 및 검색 projection을 포함한다.

### `user.sqlite3`

- 문제 풀이, 오답, 북마크, 진도, 개인 메모 및 설정을 저장한다.
- 휴대폰의 앱 전용 저장소에 존재한다.
- 시도 기록과 오답 큐에는 보존 개수 제한이 있어 무한히 증가하지 않는다.
- 앱 삭제 또는 앱 데이터 삭제 시 제거될 수 있다.

SQLite의 용량 부족은 현재 Supabase 도입의 주된 이유가 아니다. Supabase를 도입하는 이유는 관리자 웹, 중앙 제작 데이터, 레퍼런스 업로드, 검수 및 원격 콘텐츠 배포다.

## 4. 목표 아키텍처

```text
관리자 웹 (배포)
  ├─ 관리자 로그인
  ├─ 레퍼런스/PDF/URL 등록
  ├─ 콘텐츠 작성 및 수정
  ├─ 검증 결과 확인
  ├─ 승인/반려
  └─ 릴리스 생성
          │
          ▼
Supabase
  ├─ Auth: 사전 생성한 관리자 계정 1개
  ├─ PostgreSQL: 제작 데이터와 검수 이력
  ├─ Storage: 원본 자료와 릴리스 파일
  └─ RLS: 관리자만 접근 가능
          │
          ▼ 승인된 데이터만 export
content.sqlite3 + content-manifest.json
          │
          ▼ 다운로드 및 검증
Android 앱
  ├─ content.sqlite3: 로컬 읽기 전용 콘텐츠
  └─ user.sqlite3: 로컬 사용자 데이터
```

Android 앱이 작성 중인 Supabase 테이블을 매 화면에서 직접 조회하게 만들지 않는다. 검수되지 않은 데이터 노출, 네트워크 의존성 및 서버 장애 영향을 피하기 위해 승인된 콘텐츠를 버전이 있는 SQLite 스냅샷으로 배포한다.

## 5. 컴포넌트별 책임

### 관리자 웹

- 이메일/비밀번호 로그인
- 로그인하지 않은 사용자를 `/login`으로 이동
- 회원가입 UI와 회원가입 API를 제공하지 않음
- 레퍼런스 메타데이터 입력
- PDF 등의 원본 파일 업로드
- 콘텐츠 작성, 수정, 검수, 승인 및 반려
- 검증 오류와 ingestion 작업 상태 표시
- 승인된 데이터의 릴리스 요청
- 릴리스 버전과 배포 이력 표시

### Supabase Auth

- 관리자 계정 한 개를 Dashboard에서 사전 생성
- 이메일 로그인 사용
- 신규 사용자 가입 비활성화
- 익명 로그인 비활성화
- 비밀번호를 Supabase Auth에서 해시로 관리
- 필요하면 이후 TOTP MFA 추가

### Supabase PostgreSQL

- 제작 데이터의 기준 저장소
- 원본 레퍼런스와 생성된 콘텐츠의 lineage 보존
- 상태 변경과 검수 이력 보존
- 승인된 데이터와 작성 중인 데이터 분리
- RLS로 관리자 이외의 접근 차단

### Supabase Storage

- 비공개 원본 자료 저장
- 생성된 릴리스 번들 저장
- 관리자 export 및 백업 저장

### 릴리스 작업자

초기에는 GitHub Actions 또는 별도 서버 작업자로 구현한다. 관리자 브라우저가 직접 `content.sqlite3`를 생성하거나 secret key를 사용하지 않게 한다.

- 승인된 데이터만 조회
- 스키마 및 참조 무결성 검증
- 기존 `tools/build_content_db.py` 흐름을 재사용하여 SQLite 생성
- SHA-256, 스키마 버전, 행 개수를 포함한 manifest 생성
- SQLite integrity 검사
- Storage 업로드
- 성공한 릴리스만 활성 버전으로 전환

### Android 앱

- 시작 시 또는 사용자가 새로고침할 때 최신 릴리스 메타데이터 확인
- 더 높은 콘텐츠 버전이 있으면 SQLite와 manifest 다운로드
- SHA-256, byte size, schema version, row count 및 SQLite integrity 검증
- 검증이 끝난 파일만 원자적으로 활성화
- 다운로드나 검증에 실패하면 기존 콘텐츠 DB 유지
- 인터넷이 없어도 기존 콘텐츠로 정상 작동

## 6. 인증 및 권한 설계

### 관리자 계정 생성

1. Supabase Dashboard의 `Authentication > Users`에서 본인 이메일 계정을 생성한다.
2. 이메일을 확인된 상태로 만들고 강력한 비밀번호를 설정한다.
3. `Authentication` 설정에서 신규 가입을 비활성화한다.
4. 익명 로그인을 비활성화한다.
5. 배포 도메인을 비밀번호 재설정 Redirect URL에 등록한다.

비밀번호는 Git, `.env`, 프런트엔드 코드 또는 SQL migration에 넣지 않는다.

### 관리자 판별

관리자 이메일을 프런트엔드에서 비교하는 방식 대신 Auth 사용자 UUID를 별도 테이블에 등록한다.

```sql
create table public.admin_users (
    user_id uuid primary key references auth.users(id) on delete cascade,
    created_at timestamptz not null default now()
);

alter table public.admin_users enable row level security;
```

콘텐츠 테이블의 RLS 정책은 개념적으로 다음 조건을 사용한다.

```sql
exists (
    select 1
    from public.admin_users
    where user_id = auth.uid()
)
```

구현 시 `admin_users` 자체가 일반 authenticated 사용자에게 노출되지 않도록 권한과 정책을 함께 검토한다. 사용자가 수정할 수 있는 `user_metadata`를 관리자 권한 판별에 사용하지 않는다.

### 키 관리

- 브라우저에는 Supabase Project URL과 publishable key만 둔다.
- publishable key가 공개되는 것을 전제로 RLS를 설계한다.
- secret/service-role key는 서버 작업자 또는 CI secret에만 둔다.
- secret/service-role key를 Android APK, 브라우저 bundle 또는 Git 저장소에 넣지 않는다.

## 7. 콘텐츠 상태 모델

콘텐츠는 최소한 다음 상태를 거친다.

```text
DRAFT
  → VALIDATING
  → REVIEWED
  → APPROVED
  → PUBLISHED
```

필요한 예외 상태:

- `REJECTED`: 검수에서 반려
- `VALIDATION_FAILED`: 자동 검증 실패
- `ARCHIVED`: 더 이상 사용하지 않는 항목

`PUBLISHED`는 단순히 행의 상태만 바꾸는 작업이 아니다. 릴리스 번들 생성, 검증, 업로드 및 활성 버전 전환이 모두 성공한 후에만 기록한다.

## 8. 초기 데이터 모델 초안

기존 명세와 실제 SQLite 스키마를 기준으로 구현 전에 세부 필드를 확정한다. 최초 Supabase 모델은 다음 영역을 포함한다.

| 테이블 | 역할 |
| --- | --- |
| `admin_users` | 관리자 Auth UUID 허용 목록 |
| `sources` | URL, 문서, 책 등 출처의 논리 레코드 |
| `source_versions` | 출처 파일 버전, hash 및 파싱 상태 |
| `source_files` | Storage object와 출처 연결 |
| `ingestion_jobs` | 업로드, OCR, 파싱, 생성 및 검증 작업 |
| `content_items` | 카드, 공식, claim 등 제작 콘텐츠 |
| `content_item_sources` | 콘텐츠와 출처 위치의 연결 |
| `review_decisions` | 승인, 반려, 검수자 및 사유 이력 |
| `content_releases` | 릴리스 버전, hash, manifest 및 상태 |

이미 명세에 더 상세한 authoring 스키마가 있으므로 실제 migration 작성 시 `finance_interview_admin_system_spec.md`와 `finance_interview_app_final_spec.md`를 기준으로 정규화한다. 위 표는 구현 순서를 위한 최소 영역 구분이다.

## 9. Storage 버킷

| 버킷 | 공개 여부 | 내용 |
| --- | --- | --- |
| `source-private` | 비공개 | PDF, OCR 원본, 이미지 및 파싱 입력 |
| `release-bundles` | 기본 비공개 | `content.sqlite3`, manifest 및 릴리스 메타데이터 |
| `exports-private` | 비공개 | 관리자 export와 백업 |

Android 다운로드는 다음 중 하나로 구현한다.

1. 짧은 만료 시간을 가진 signed URL 발급
2. 공개해도 되는 릴리스 번들만 별도 공개 경로로 제공

초기에는 signed URL 방식이 안전하다. 단, Android 앱이 인증 없이 콘텐츠를 받을 계획이라면 signed URL을 발급하는 공개 릴리스 endpoint가 필요하다.

## 10. 관리자 웹 배포

관리자 웹이 Next.js라면 Vercel을 우선 고려한다. 다른 프레임워크라면 Cloudflare Pages 등으로 변경할 수 있다.

필수 환경변수 예시:

```text
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
```

서버/CI에서만 사용하는 값:

```text
SUPABASE_SECRET_KEY=
```

실제 값은 호스팅 서비스와 CI의 secret 저장소에 넣고 `.env` 파일은 Git에 commit하지 않는다.

배포 후 확인할 항목:

- `/login` 정상 동작
- 비로그인 상태에서 관리자 route 차단
- 로그인 후 새로고침해도 세션 유지
- 로그아웃 후 관리자 route 접근 차단
- 가입 요청 실패
- 관리자 외 Auth 사용자의 DB 읽기/쓰기 실패
- 브라우저 개발자 도구에 secret key가 노출되지 않음

## 11. Android 콘텐츠 업데이트 규칙

Supabase 연동 이후에도 기존의 안전한 로컬 DB 전환 원칙을 유지한다.

1. 현재 활성 버전 확인
2. Supabase에서 최신 `PUBLISHED` 릴리스 조회
3. 새 버전일 때 임시 경로로 다운로드
4. manifest와 파일 hash 검증
5. SQLite read-only open 및 integrity 검사
6. row-count invariant와 schema version 검사
7. 완성 파일 이름으로 atomic rename
8. active-version pointer 원자 전환
9. 실패 시 임시 파일만 정리하고 기존 버전 유지

앱이 Supabase Postgres를 콘텐츠 화면마다 직접 조회하는 형태로 변경하지 않는다.

## 12. 사용자 데이터 정책

초기 단계에서는 `user.sqlite3`를 휴대폰 로컬에 유지한다.

- 풀이 기록
- 오답 큐
- 북마크
- 진도
- 개인 메모
- 설정

앱 삭제나 휴대폰 분실에 대비한 자동 백업이 필요하면 관리자 시스템과 별도 단계로 구현한다. 후보는 다음과 같다.

- OneDrive App Folder에 버전 백업
- Supabase Storage에 암호화된 사용자 백업 업로드
- Supabase 테이블로 행 단위 동기화

혼자 사용하고 단일 기기가 기준이라면 우선 버전 백업으로 충분하다. 여러 기기에서 동시에 수정할 필요가 생기면 UUID, `updated_at`, `deleted_at`, `device_id`, outbox 및 충돌 정책을 설계한 후 행 단위 동기화를 추가한다.

## 13. 구현 단계

### Phase 1: Supabase 기반 구성

- [ ] Supabase 프로젝트 생성
- [ ] 리전 선택
- [ ] Supabase CLI 및 migration 디렉터리 구성
- [ ] 관리자 계정 한 개 생성
- [ ] 신규 가입 비활성화
- [ ] 익명 로그인 비활성화
- [ ] `admin_users`와 기본 RLS migration 작성
- [ ] Storage 버킷과 접근 정책 생성
- [ ] 개발/운영 환경변수 관리 방식 확정

### Phase 2: 제작 데이터 이전

- [ ] 기존 authoring 스키마와 Supabase 스키마 매핑
- [ ] 출처, 출처 버전 및 파일 테이블 구현
- [ ] 콘텐츠 및 출처 연결 테이블 구현
- [ ] 검수 결정과 상태 이력 구현
- [ ] 기존 제작 데이터를 import하는 일회성 도구 작성
- [ ] import row count와 hash 검증

### Phase 3: 관리자 웹

- [ ] 웹 프레임워크 확정
- [ ] 로그인/로그아웃 구현
- [ ] route 보호 구현
- [ ] 레퍼런스 목록/상세/등록 화면 구현
- [ ] 파일 업로드 구현
- [ ] 콘텐츠 작성 및 검수 화면 구현
- [ ] 승인/반려 이력 구현
- [ ] validation job 상태 화면 구현
- [ ] 릴리스 요청 및 이력 화면 구현

### Phase 4: 릴리스 파이프라인

- [ ] 승인 데이터 export query 확정
- [ ] 기존 SQLite 생성기를 Supabase 입력에 연결
- [ ] manifest 생성과 무결성 검사 자동화
- [ ] 릴리스 번들 Storage 업로드
- [ ] 활성 릴리스 원자 전환
- [ ] 실패한 릴리스 rollback 처리
- [ ] CI secret 및 최소 권한 설정

### Phase 5: Android 원격 업데이트

- [ ] 인터넷 권한 확인
- [ ] 릴리스 확인 API 구현
- [ ] SQLite/manifest 다운로드 구현
- [ ] hash 및 schema 검증 구현
- [ ] 로컬 활성 버전 전환 구현
- [ ] 오프라인 및 실패 fallback 테스트
- [ ] 이전 버전 rollback 테스트

### Phase 6: 배포와 보안 검증

- [ ] 관리자 웹 배포
- [ ] 배포 도메인 Auth Redirect URL 등록
- [ ] 회원가입 차단 확인
- [ ] 비관리자 접근 차단 확인
- [ ] RLS 우회 테스트
- [ ] Storage 비인가 다운로드 테스트
- [ ] 프런트엔드 bundle secret 검사
- [ ] 관리자 계정 복구 절차 기록
- [ ] 필요하면 TOTP MFA 활성화

## 14. 완료 조건

다음 조건을 모두 충족하면 초기 Supabase 관리자 시스템이 완성된 것으로 본다.

- 배포된 관리자 URL에서 로그인할 수 있다.
- 사전 생성한 관리자 계정 외에는 가입하거나 접근할 수 없다.
- 레퍼런스와 원본 파일을 등록할 수 있다.
- 콘텐츠를 작성하고 검수 상태를 변경할 수 있다.
- 승인된 데이터만 릴리스에 포함된다.
- 릴리스된 SQLite와 manifest가 hash 및 integrity 검사를 통과한다.
- Android 앱이 새 콘텐츠를 다운로드하고 안전하게 활성화한다.
- 네트워크 또는 릴리스 실패 시 기존 콘텐츠로 계속 동작한다.
- secret/service-role key가 브라우저, APK 및 Git에 포함되지 않는다.
- 모든 공개 스키마 테이블과 Storage object에 필요한 RLS 정책이 적용돼 있다.

## 15. 구현 시 피해야 할 방식

- 관리자 아이디나 비밀번호를 프런트엔드 코드에 문자열로 저장
- 이메일이 특정 값인지 브라우저에서만 확인해 관리자 권한 부여
- RLS 없이 로그인 화면만 구현
- secret/service-role key를 `NEXT_PUBLIC_*` 환경변수에 저장
- Android APK에 secret/service-role key 포함
- 작성 중인 Supabase 데이터를 Android 앱이 그대로 조회
- 승인 상태만 바꾸고 검증되지 않은 파일을 릴리스로 표시
- 쓰기 중인 SQLite 파일 자체를 그대로 업로드
- 네트워크 오류 시 기존 로컬 콘텐츠까지 사용할 수 없게 만들기

## 16. 참고 문서

- Supabase Auth 일반 설정: <https://supabase.com/docs/guides/auth/general-configuration>
- Supabase 사용자 관리: <https://supabase.com/docs/guides/auth/users>
- Supabase 비밀번호 보안: <https://supabase.com/docs/guides/auth/password-security>
- Supabase Row Level Security: <https://supabase.com/docs/guides/database/postgres/row-level-security>
- Supabase Kotlin/Android 시작 가이드: <https://supabase.com/docs/guides/getting-started/quickstarts/kotlin>
- Supabase 요금 및 제한: <https://supabase.com/docs/guides/platform/billing-on-supabase>
- SQLite 제한: <https://www.sqlite.org/limits.html>
- OneDrive App Folder: <https://learn.microsoft.com/en-us/graph/onedrive-sharepoint-appfolder>
