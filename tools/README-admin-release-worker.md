# Admin Release Worker

`admin_release_worker.py`는 Admin에서 생성한 승인 릴리스를 Android가 소비하는 완전한 SQLite bundle로 바꿉니다.

## 처리 흐름

1. `release_build` 작업을 원자적으로 claim합니다.
2. 현재 `stable` DB를 canonical baseline으로 읽고, 아직 stable 릴리스가 없으면 APK 내장 DB v6를 사용합니다.
3. 새 SQLite schema를 빈 파일에 만들고 canonical row만 다시 적재한 뒤, 해당 릴리스에 고정된 분야·요소·개념·수식 revision을 투영하고 FTS를 재생성합니다. 기존 파일의 freelist·편집 이력·임시 페이지는 복사하지 않습니다.
4. 7개 분야·135개 요소, row count, 빈 필드, FK, SQLite integrity와 SHA-256을 검증합니다.
5. private `release-bundles/<release-id>/`에 DB와 manifest를 올리고 `release_validation`을 자동 생성합니다.
6. 검증 작업을 이어서 claim해 내려받은 산출물을 독립적으로 다시 검사합니다.
7. 통과하면 service-role RPC가 같은 트랜잭션에서 릴리스를 `published`로 만들고 `stable`을 교체합니다.

Android schema v1에 없는 distractor revision은 누락하지 않고 릴리스를 실패시킵니다. `user.sqlite3`와 Android 소스 asset은 Worker가 읽거나 쓰지 않습니다.

## 실행

```powershell
$env:SUPABASE_URL = 'https://<project-ref>.supabase.co'
$env:SUPABASE_SECRET_KEY = '<sb_secret key>'
python tools/admin_release_worker.py --worker-id 'release:local-01' --max-jobs 4
Remove-Item Env:SUPABASE_SECRET_KEY
```

`--max-jobs` 기본값은 2이며 1~10만 허용합니다. 보통 build 한 건이 validation 한 건을 즉시 만들기 때문에 2면 한 릴리스를 끝까지 처리합니다. GitHub 예약 실행은 최대 4건을 처리하며 `ADMIN_RELEASE_WORKER_ENABLED=true`일 때만 자동 실행됩니다.

Secret key는 브라우저나 Android APK에 넣지 않습니다. Worker는 최신 `sb_secret_...` 값을 `apikey` 헤더로만 전송하고 로그에 출력하지 않습니다.

## 검증

```powershell
python -m unittest tools.test_admin_release_worker -v
python tools/validate_supabase_sql.py
supabase db reset --local
supabase test db
supabase db lint --local --level warning
```

마지막 세 명령은 Supabase CLI와 Docker가 있는 환경에서 실행해야 합니다.
