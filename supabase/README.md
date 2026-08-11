# FinDone Supabase admin backend

이 디렉터리는 FinDone 개념 DB를 정돈하는 관리자 웹의 데이터 계층이다. Supabase에는 편집 원본, 출처, 검증, 승인 이력과 릴리스 메타데이터를 저장한다. Android는 이 제작 테이블을 직접 조회하지 않고, 승인 후 생성된 `content.sqlite3`만 받는다. 사용자 학습기록 DB와 랜덤 문제 템플릿은 이 스키마의 범위가 아니다.

## 구현된 범위

- 회원가입 계정을 자동으로 읽기 전용 `viewer`로 등록하는 `admin_users` 멤버십
- 분야·요소·개념 설명·수식·변수 설명·개념형 오답 후보
- URL/파일 출처, 출처 버전, 비공개 Storage 파일, 근거 위치
- 모든 개념 변경의 자동 immutable revision과 상태 이력
- validation run/issue, 사람의 승인·반려와 승인 snapshot
- 승인 revision만 포함할 수 있는 SQLite 릴리스와 원자적 active channel
- ingestion/validation/release 작업 큐와 append-only event
- 주요 변경의 audit log 및 모든 `public` 테이블 RLS
- 현재 앱 SQLite export JSON을 원자적으로 가져오는 최초 import RPC

문제 생성 템플릿, 계산 AST, 파라미터/seed 편집 테이블은 의도적으로 만들지 않았다. `distractors`는 랜덤 개념문제에서 뽑을 승인된 오답 문구 목록만 관리한다.

## 마이그레이션 순서

1. `202608100001_foundation.sql`: 관리자 allowlist, 역할, 보안 helper
2. `202608100002_authoring.sql`: source와 개념 authoring 정규화 테이블
3. `202608100003_revision_review_validation.sql`: revision·검증·검수
4. `202608100004_jobs_releases.sql`: 작업 큐와 SQLite release
5. `202608100005_import_api_views.sql`: 최초 import, grid save RPC, read views
6. `202608100006_security_audit_storage.sql`: audit, RLS, grants, private buckets
7. `202608100007_bulk_grid_import.sql`: 최대 135개 grid 행의 원자적 일괄 저장
8. `202608100008_security_hardening.sql`: 안전한 출처 URL, 릴리스 fingerprint와 검증 경계
9. `202608100009_worker_boundaries.sql`: 출처·릴리스 RPC, worker write 경계와 최신 read view
10. `202608100010_validation_worker_rpc.sql`: validation worker의 claim·완료·실패·lease 복구 RPC
11. `202608100011_release_worker_rpc.sql`: SQLite release build·검증 완료와 자동 stable 공개 RPC
12. `202608110001_viewer_signup.sql`: viewer 자동 가입과 owner-only write 권한

## 로컬 실행

Supabase CLI와 Docker가 설치된 환경에서 저장소 루트에서 실행한다.

```powershell
supabase start
supabase db reset --local
supabase test db
```

`config.toml`은 로컬 이메일 가입을 허용하고 anonymous sign-in은 끈다. 새 Auth 계정은 DB trigger가 무조건 `viewer`로 등록하며 클라이언트 metadata로 역할을 지정할 수 없다. 비밀값은 들어 있지 않다. OAuth나 외부 작업자 secret을 추가할 때도 파일에 직접 쓰지 말고 `env(...)`만 사용한다.

## 운영 프로젝트 최초 설정

1. Supabase Dashboard의 `Authentication > Sign In / Providers`에서 **Allow new users to sign up**과 email signup을 켜고 anonymous sign-in은 끈다. `config.toml`은 로컬 stack용이며 `supabase db push`만으로 hosted Auth 설정이 바뀌지는 않는다.
2. 기존 owner Auth 계정의 UUID를 확인한다.
3. Dashboard SQL Editor처럼 service-role 권한이 있는 신뢰 경로에서 아래 SQL을 한 번 실행한다. 이 SQL에는 이메일이나 비밀번호를 넣지 않는다.

```sql
insert into public.admin_users (user_id, role, display_name)
values ('AUTH_USERS_UUID_HERE'::uuid, 'owner', 'FinDone owner')
on conflict (user_id) do update
set role = 'owner', is_active = true;
```

4. 로그인 후 owner의 `select public.is_admin()`이 `true`인지 확인한다.
5. 이후 `/signup`에서 가입한 모든 계정은 자동으로 `viewer`가 된다. Viewer를 owner로 올리는 UI나 클라이언트 API는 제공하지 않는다.
6. 운영 admin URL과 비밀번호 재설정 URL을 Auth redirect allowlist에 등록한다.
7. TOTP는 local config에서 활성화되어 있다. 운영에서도 owner 계정에 TOTP를 등록하고 필요 시 AAL2 강제를 별도 정책으로 켠다.

Auth 계정을 만들면 `admin_users`에 활성 viewer 행이 자동 생성된다. Viewer는 RLS상 SELECT만 가능하고 모든 write RPC와 Storage write가 차단된다. 마지막 활성 `owner`는 DB trigger 때문에 삭제·비활성화·강등할 수 없다.

공식 설정 참고: [Supabase CLI config](https://supabase.com/docs/guides/local-development/cli/config), [Auth general configuration](https://supabase.com/docs/guides/auth/general-configuration), [Storage RLS](https://supabase.com/docs/guides/storage/security/access-control).

## 현재 앱 데이터 최초 import

저장소의 exporter가 SQLite와 manifest를 검증하고 canonical JSON을 만든다.

```powershell
python tools/admin_export_content.py --json build/admin-content.json --csv-dir build/admin-content-csv
```

로그인한 owner의 Admin 서버 또는 브라우저가 JSON을 읽어 다음 RPC를 호출한다.

```ts
const snapshot = JSON.parse(fileText)
const { data, error } = await supabase.rpc('import_content_snapshot', {
  p_snapshot: snapshot,
  p_allow_overwrite: false,
})
```

지원 형식은 `findone-admin-content-v1`이며 다음 mapping을 사용한다.

| export table | Supabase mapping |
| --- | --- |
| `domains` | `domains`; `element_count` → `expected_element_count` |
| `sources` | `sources`; URL locator는 자동으로 `kind=url` |
| `elements` | `elements`; legacy ID와 표시 순서를 그대로 유지 |
| `concept_cards` | `concepts`; `scope_notes` → `learning_notes_markdown` |
| `formula_cards` | primary `formulas`; `notes`는 수식 notes이자 초기 checklist |
| `element_sources` | 같은 이름의 정규화 연결 테이블 |

RPC는 한 트랜잭션에서 실행된다. database SHA-256이 같은 snapshot을 다시 올리면 `already_imported`를 반환한다. 기존 authoring 데이터가 있으면 기본적으로 중단하며, owner가 명시적으로 `p_allow_overwrite=true`를 전달한 경우에만 upsert한다. overwrite도 빠진 행을 자동 삭제하지 않는다.

## Admin 데이터 계약

### 스프레드시트 grid

- 조회 view: `admin_content_grid`
- 원자적 저장 RPC:

```text
save_content_grid_row(
  p_element_id text,
  p_element_patch jsonb = {},
  p_concept_patch jsonb = {},
  p_formula_patch jsonb = {},
  p_change_reason text = null
) -> jsonb
```

Excel 호환 CSV에서 여러 행을 적용할 때는 `save_content_grid_rows(p_rows, p_change_reason)`를 사용한다. 한 번에 1~135개 요소만 허용하며, 요소 ID 중복이나 어느 한 행의 오류가 있으면 전체 트랜잭션이 rollback된다.

지원 patch key는 정규화 테이블 column명을 사용한다. 따라서 view의 `element_scope_notes`, `concept_title`, `formula_title`은 각각 patch의 `scope_notes`, concept `title`, formula `title`에 대응한다. 요소 ID, concept ID, formula ID와 formula key는 변경 불가다. 실제로 전달된 patch의 테이블만 업데이트하므로 빈 patch가 불필요한 revision을 만들지 않는다.

오답 후보는 `distractors`를 직접 CRUD한다.

```text
distractor_id       uuid, 자동 생성
element_id          text, 고정
distractor_key      text, 요소 내 고정 key
text                text
explanation         text
misconception_type  text
difficulty          1..5
display_order       integer
is_enabled          boolean
```

### 출처와 파일

URL/파일 공통으로 `sources`를 만들고, 실제 fetch/upload마다 증가하는 `source_versions.version_number`를 추가한다. URL fetch는 `source_versions.fetch_url`에 저장한다.

DB trigger는 자격증명 포함 URL, 로컬 host, IP literal을 거부한다. 실제 fetch worker는 이 검사에 더해 매 DNS 해석과 redirect hop마다 loopback/private/link-local/reserved IP를 다시 차단해야 한다. DNS rebinding 방어가 없는 worker는 실행하면 안 된다.

브라우저 업로드는 Storage에 직접 보낸 후 `source_files` metadata를 기록한다. `source-private` object path의 첫 segment는 반드시 로그인 사용자 UUID여야 한다.

브라우저는 Storage 업로드가 끝난 뒤 `register_file_source`를 호출한다. RPC는 object 존재와 사용자 UUID prefix를 확인하고 source/version/file/job metadata를 한 트랜잭션으로 만든다. URL은 `register_url_source`가 source/version/job을 함께 만든다. 정규 테이블 직접 insert 권한은 브라우저에 주지 않는다.

```text
{auth.uid()}/sources/{source_id}/{source_version_id}/{safe-file-name}
```

세 bucket은 전부 private이다.

| bucket | 용도 | 브라우저 write 역할 |
| --- | --- | --- |
| `source-private` | 원본, snapshot, OCR | owner |
| `exports-private` | XLSX/CSV/백업 | owner |
| `release-bundles` | SQLite, manifest, signature | owner |

업로드 성공 후 DB insert가 실패하면 Admin이 방금 올린 object를 보상 삭제해야 한다. Worker의 service key는 브라우저 bundle에 넣지 않는다.

## Revision, 검증, 승인

`domains`, `elements`, `concepts`, `formulas`, `distractors`의 insert/update/delete는 자동으로 `content_revisions` snapshot과 최초 `draft` state를 만든다. 이 테이블들과 review/approval/audit event는 DB trigger 수준에서 append-only다.

```text
start_revision_validation(revision_id)
  → validation_runs + ingestion_jobs
  → service-role worker가 validation_issues를 기록하고 run을 passed/failed로 마감
submit_review(revision_id, approved|rejected|changes_requested, comment)
  → approved면 immutable approval_snapshots 생성
```

최신 revision이 아니거나 validation이 성공하지 않은 revision은 승인할 수 없다. release item에는 현재 상태가 `approved`인 revision만 들어간다.

## 릴리스

`content_releases`는 다음 상태만 허용한다. `release_items`는 전체 135개 복제가 아니라 직전 배포본 위에 적용할 승인 revision의 immutable delta/freeze 목록이다. Worker는 active/embedded 기준 DB에 이 delta를 적용한 뒤 반드시 완전한 135개 요소 SQLite를 새로 검증한다.

릴리스 생성은 응답 유실 후 재시도해도 중복 릴리스나 작업을 만들지 않도록 호출자가 만든 UUID를 필수 멱등성 키로 받는다.

```text
create_release_from_approved(
  p_request_key uuid,
  p_version_name text = null,
  p_release_notes text = '',
  p_minimum_app_version integer = 1
)
```

현재 Android SQLite `schema_version`은 `1`이고, 콘텐츠 배포 번호인 `content_version`은 기존 최대값(초기 기준 5) 다음 번호로 별도 증가한다. `findone-admin-content-v1`은 이 둘과 다른 최초 import용 export format 이름이다.

```text
draft → building → ready → published(stable 자동 전환)
                    ↘ withdrawn
          ↘ validation_failed → building
```

`ready`가 되려면 승인 item, `content_database`/`manifest` artifact, hash/size/manifest, 성공한 release validation이 모두 있어야 한다. 011 Worker 완료 RPC는 성공한 검증과 정확히 같은 트랜잭션에서 `ready → published`와 `stable` pointer 교체를 수행하므로 앱이 미검증 산출물을 볼 수 없다. `activate_release(release_id, 'stable')`는 이전 published 릴리스로 명시적으로 되돌릴 때도 사용할 수 있다. artifact object는 계속 private이고 Admin `/api/content/stable`이 service key로 10분짜리 signed URL을 발급한다.

릴리스 검증은 item·artifact·manifest·hash를 포함한 SHA-256 fingerprint에 묶인다. 검증 도중 또는 통과 후 어느 구성요소라도 바뀌면 기존 결과로 `ready` 전환할 수 없고 `start_release_validation`을 다시 실행해야 한다.

## 역할과 RLS

| 역할 | 권한 |
| --- | --- |
| `owner` | 개념·출처·오답 편집, 검증·승인, 릴리스와 계정 상태 관리 |
| `viewer` | 모든 관리 화면 조회만 가능, write 권한 없음 |

Owner도 validation 결과나 release item/artifact 행을 직접 쓰지 않는다. revision validation 결과는 010의 service-role 전용 완료 RPC가, 릴리스 투영·검증·자동 stable 공개는 011의 service-role 전용 RPC와 `tools/admin_release_worker.py`가 담당한다. 모든 `public` 테이블에 RLS가 켜져 있고 active owner/viewer만 읽을 수 있다. `anon`에는 테이블/view 권한이 없다. Storage catalog는 Supabase가 관리하며, FinDone의 파일 접근은 `storage.objects` RLS 정책으로 제한한다.

`audit_events`는 주요 mutable 테이블의 old/new 값을 남긴다. 용량 폭증을 막기 위해 `source_versions.extracted_text/extraction_metadata`, job input/output, release manifest 본문은 audit에서 원문 대신 byte length 또는 SHA-256만 저장한다. 실제 콘텐츠 편집 snapshot은 `content_revisions`에 보존된다.

## 검증과 배포

```powershell
supabase test db
supabase db lint --local --level warning
supabase link --project-ref YOUR_PROJECT_REF
supabase db push --linked --dry-run
supabase db push --linked
```

`tests/database/schema_and_security.test.sql`은 핵심 테이블/view/RPC, 모든 public table RLS, private bucket, append-only trigger, anon/non-admin 차단을 확인한다. `validation_worker_rpc.test.sql`과 `release_worker_rpc.test.sql`은 worker claim·완료·실패 및 검증 통과 후 stable 자동 공개를 확인한다. 운영 push 전 local reset과 pgTAP을 모두 통과해야 한다.
