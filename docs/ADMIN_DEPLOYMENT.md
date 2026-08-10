# FinDone Admin 배포 절차

Admin은 Next.js 웹, Supabase Auth/PostgreSQL/Storage, 별도 worker로 나뉜다. 브라우저에는 publishable key만 두며 `SUPABASE_SECRET_KEY`는 최초 import나 worker 같은 신뢰 실행 환경에서만 사용한다. 현재 저장소의 worker는 개념 revision 자동 검증까지 담당한다.

## 1. 로컬 확인

저장소 루트에서 아래 명령을 실행하면 현재 APK에 포함된 `content.sqlite3`를 검증해 Admin fixture를 다시 만들고 웹을 연다.

```powershell
.\scripts\start_admin.ps1
```

Supabase 환경변수가 없으면 로그인 없이 읽기 전용 데모로 열린다. 이 상태에서도 실제 7개 분야, 135개 요소, 174개 출처를 검색하고 Excel 호환 UTF-8 CSV로 내보낼 수 있지만 저장·업로드는 서버로 전송하지 않는다.

검증 명령:

```powershell
python -m unittest discover -s tools -p "test_admin*.py" -v
Push-Location admin
npm ci
npm test
npm run build
Pop-Location
```

## 2. Supabase 프로젝트 설정

1. Supabase 프로젝트를 만들고 리전을 정한다.
2. Supabase CLI와 Docker가 있는 PC에서 `supabase link --project-ref <PROJECT_REF>`를 실행한다.
3. 반드시 먼저 로컬에서 `supabase db reset --local`, `supabase test db`, `supabase db lint --local --level warning`을 통과시킨다.
4. `supabase db push --linked --dry-run` 결과를 검토한 뒤 `supabase db push --linked`를 실행한다.
5. Dashboard `Authentication > Users`에서 소유자 계정 한 개를 직접 생성한다.
6. Dashboard에서 신규 회원가입, 이메일 signup, anonymous sign-in을 모두 끈다. 저장소의 `config.toml`은 hosted 설정을 자동으로 바꾸지 않는다.
7. 생성한 Auth UUID를 `public.admin_users`에 `owner`로 등록한다. SQL은 [Supabase 안내](../supabase/README.md)의 예시를 사용한다.
8. Storage의 `source-private`, `exports-private`, `release-bundles`가 모두 private인지 확인한다.

Admin 웹용 값:

```text
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
```

`service_role`/secret key에는 절대 `NEXT_PUBLIC_` 접두사를 붙이지 않는다. 최신 `sb_secret_...` 키는 JWT가 아니므로 Python import/worker는 공식 계약대로 `apikey` 헤더에만 넣고 `Authorization: Bearer`로 보내지 않는다.

## 3. 현재 앱 데이터 최초 전송

신뢰하는 로컬 셸에서만 secret을 프로세스 환경변수로 설정한다. 명령은 비밀값을 출력하지 않는다.

```powershell
$env:SUPABASE_URL = 'https://<project-ref>.supabase.co'
$env:SUPABASE_SECRET_KEY = '<secret-key>'
python tools/admin_import_supabase.py --dry-run
python tools/admin_import_supabase.py
Remove-Item Env:SUPABASE_SECRET_KEY
```

같은 DB hash는 다시 넣어도 `already_imported`로 끝난다. 기존 제작 데이터를 덮는 `--allow-overwrite`는 owner가 검토한 복구 작업에서만 사용한다.

## 4. 자동 검증 Worker

`202608100010_validation_worker_rpc.sql`까지 적용한 뒤 GitHub repository secret에 `SUPABASE_URL`, `SUPABASE_SECRET_KEY`를 등록하고 repository variable `ADMIN_VALIDATION_WORKER_ENABLED=true`를 설정한다. [Admin Validation Worker](../.github/workflows/admin-validation-worker.yml)는 그때부터 5분마다 revision validation 작업 한 건을 원자적으로 claim해 검사한다. 같은 worker ID의 실행 중 작업은 먼저 복구하고, 15분 넘게 중단된 lease는 retry 예산 안에서 회수하며, 예산을 소진한 작업은 실패로 봉인한다. variable이 없으면 예약 실행은 건너뛰며, 같은 작업을 수동 또는 로컬에서 한 번 실행할 수도 있다.

```powershell
$env:SUPABASE_URL = 'https://<project-ref>.supabase.co'
$env:SUPABASE_SECRET_KEY = '<sb_secret key>'
python tools/admin_validation_worker.py --worker-id 'validator:local-01'
Remove-Item Env:SUPABASE_SECRET_KEY
```

Worker는 URL fetch, 파일 파싱, `release_build`, `release_validation` 작업을 claim하지 않는다. 해당 작업자는 DNS rebinding·redirect·archive bomb·SQLite projection 계약을 갖춘 뒤 별도 배포해야 한다.

## 5. 웹 배포

Vercel 프로젝트의 Root Directory를 `admin`으로 지정하고 위의 공개 환경변수 두 개만 Production/Preview에 등록한다. 빌드 명령은 `npm run build`, 출력은 Next.js 기본값을 사용한다.

배포 후 Supabase Auth의 Site URL과 Redirect URL allowlist에 실제 HTTPS Admin 도메인을 추가한다. 다음을 직접 확인한다.

- 비로그인 사용자는 `/login`으로 이동한다.
- 회원가입 화면과 API가 없다.
- allowlist에 없는 Auth 사용자는 관리자 route와 DB/Storage를 읽지 못한다.
- 로그아웃 후 세션이 남지 않는다.
- 브라우저 bundle과 네트워크 요청에 secret key가 없다.
- 업로드 파일은 private bucket에서만 보인다.

## 6. 아직 외부 설정이 필요한 경계

코드만으로는 Supabase 프로젝트·관리자 Auth 사용자·호스팅 도메인을 생성할 수 없다. 실제 URL 배포는 프로젝트 URL/publishable key와 Vercel 프로젝트 권한이 준비된 뒤 수행한다. URL/file ingestion worker, 승인본 SQLite build/validation worker, Android의 서명된 원격 SQLite 활성화도 아직 별도 구현 경계다. 그 전까지 승인 콘텐츠는 기존 APK 빌드 흐름으로 `content.sqlite3`를 포함해 전달한다.
