# Admin content-validation worker

`admin_validation_worker.py`는 Supabase의 `content_validation` 작업을 한 번에 한 건만 처리하는 독립 실행 도구다. Android 코드와 SQLite 사용자 학습기록에는 접근하지 않는다.

## 제공 범위

- `FOR UPDATE SKIP LOCKED` 기반 원자 claim
- claim과 해당 `validation_runs`의 `queued → running` 전환을 한 트랜잭션에서 처리
- immutable revision snapshot의 필수 필드, JSON 크기/깊이, stable ID, Markdown 코드 구분자, LaTeX `$`/`$$` 및 중괄호 검증
- issue insert, `validation_runs`의 `passed`/`failed`, job 완료를 한 RPC에서 원자 처리
- worker 자체 오류 시 error issue, failed validation run, failed job을 한 RPC에서 기록
- lost HTTP response 후 같은 worker ID로 재호출할 때 이미 claim한 running job 복구
- Admin이 큐에 기록한 validator 계약(`findone-content-validator` / `admin-v1`) 일치 확인
- 15분이 지난 abandoned claim을 다음 worker가 retry budget 안에서 원자적으로 회수하고, budget 소진 시 job/run을 실패로 봉인
- complete/fail RPC의 terminal 재호출과 completion 응답 유실을 idempotent하게 조정

다음 기능은 의도적으로 구현하지 않았다.

- `url_fetch`, redirect/DNS 처리, SSRF 관련 네트워크 작업
- `file_extract`, OCR, 업로드 파일 처리
- `release_build`와 `release_validation`
- `content.sqlite3` 또는 `user.sqlite` 수정

특히 release build는 승인 snapshot을 기존 SQLite 스키마에 안전하게 투영하는 계약이 확정된 뒤 별도 worker로 구현해야 한다. 현재 validation worker는 release job을 claim하지 않는다.

## 사전 조건

Supabase migration `202608100010_validation_worker_rpc.sql`을 적용해야 한다. 세 RPC는 `service_role`에만 열려 있고 브라우저의 authenticated/anon 역할에서는 실행할 수 없다.

비밀값은 저장소 파일이나 명령행 인자로 전달하지 않고 환경변수에만 둔다.
최신 `sb_secret_...` opaque key 호환을 위해 REST 요청에는 `apikey` 헤더만 사용하며, secret을 `Authorization: Bearer`로 보내지 않는다.

```powershell
$env:SUPABASE_URL = "https://PROJECT_REF.supabase.co"
$env:SUPABASE_SECRET_KEY = "SERVICE_ROLE_KEY_FROM_SECRET_MANAGER"
python tools/admin_validation_worker.py --worker-id "validator:prod-01"
```

로컬 Supabase만 `http://127.0.0.1` 또는 `http://localhost`를 허용한다. 원격 URL은 HTTPS여야 하며 path/query/fragment를 넣을 수 없다.

worker는 한 번 실행할 때 queued 작업 최대 한 건을 처리하고 종료한다. 큐가 비어 있으면 `{"status":"idle"}`을 출력한다. 운영 scheduler가 일정 간격으로 실행하거나, 프로세스 관리자가 one-shot 명령을 반복 실행하게 한다.

## Worker ID와 복구

- 동시에 실행되는 프로세스마다 서로 다른 worker ID를 사용한다.
- 네트워크 응답 유실 뒤 같은 프로세스가 재시도할 때는 같은 worker ID를 유지한다.
- 같은 ID로 재호출하면 해당 ID가 이미 claim한 running job을 먼저 반환하므로 새 attempt나 두 번째 job을 만들지 않는다.
- 서로 다른 두 프로세스가 같은 worker ID를 동시에 사용하면 같은 running job을 처리할 수 있으므로 금지한다.

기본 ID에는 host와 PID가 들어가지만, 운영 supervisor가 재시작 복구까지 보장하려면 인스턴스별 stable ID를 명시하는 편이 안전하다.

## 검증 결과 의미

콘텐츠가 규칙을 위반한 경우 worker 실행 자체는 성공한 것이다. 따라서:

- `validation_runs.status = failed`
- `validation_issues`에 구체적인 error 기록
- `ingestion_jobs.status = succeeded`

로 끝난다. 반면 REST 장애, snapshot 조회 실패, 결과 저장 실패 같은 인프라 오류는 validation run과 ingestion job 모두 `failed`로 기록한다.

검증 summary와 job output에는 canonical snapshot SHA-256, byte size, 검사 개수만 저장한다. 원문 Markdown, snapshot 전체, service key는 기록하지 않는다.

## 안전 제한

| 항목 | 제한 |
| --- | ---: |
| HTTP 응답 | 2 MiB |
| HTTP 요청 | 512 KiB |
| revision snapshot | 1 MiB |
| Markdown 필드 | 256 KiB |
| JSON 중첩 | 20단계 |
| 한 validation run issue | 100개 |
| 요청 timeout | 1–60초 |

Markdown scanner는 Android renderer와 같이 closing fence의 공백 remainder, 4-space/tab indented code, 같은 줄의 `$...$`와 `$$...$$`, inline delimiter 인접 공백을 판정한다. fenced/inline/indented code 안의 `$`는 수식 구분자로 세지 않고 `\$`와 닫는 구분자가 없는 `$100`도 literal로 처리한다. `\(`/`\[` delimiter는 앱이 인식하지 않으므로 오류로 기록한다. 이 검사는 delimiter·중괄호·`\left`/`\right`·environment 구조 검사이며 JLatexMath 전체 문법 실행을 대체하지 않는다. 앱도 렌더 실패 시 bundled fallback을 사용해야 한다.

## 테스트

```powershell
python -m unittest tools.test_admin_validation_worker -v
python -m unittest discover -s tools -p "test_*.py"
python tools/validate_supabase_sql.py
```

마지막 SQL parse gate에는 `pglast`가 필요하다. 실제 배포 전에는 parser만으로 끝내지 말고 Supabase CLI/Docker 환경에서 fresh reset과 pgTAP도 실행한다.

```powershell
supabase db reset --local
supabase test db
supabase db lint --local --level warning
```
