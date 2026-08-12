# 용어집 저작·컴파일·오프라인 배포

FinDone 용어집은 학습요소 검색과 별도의 정적 데이터 제품이다. Android 런타임은
LLM, 임베딩 API, 검색 API를 호출하지 않는다. 용어 설명·예문·한계·수식은 사전에
저작하고 검증된 SQLite FTS5 데이터베이스로 컴파일한다.

## 데이터 경계

- `용어집/2_finance_term_master_inventory.md`: 21개 카테고리, 용어 ID와 공개
  출처 코드의 기준 목록
- `content/glossary/glossary-catalog.json`: 검증된 설명·예문 등의 canonical 저작본
- `content/glossary/agent-review-overrides.json`: Agent 초안의 의미 오류를 재생성 없이
  교정하고 merge 때 적용하는 검토 기록. inventory identity는 바꿀 수 없다.
- `glossary_categories`, `glossary_sources`, `glossary_terms`: Admin에서 편집하는 동일한
  공개 가능 용어 데이터
- `glossary_term_admin_references`: Admin의 비공개 원문 자료와 용어 사이의 링크
- `glossary.sqlite3`: Android가 검색하고 표시하는 독립 오프라인 DB
- `user.sqlite3`: 북마크, 읽음 상태, 메모, 밑줄, 형광펜, 코멘트. 용어 DB를
  교체해도 유지된다.

PDF·Office 원문, OCR 결과, 업로드 경로와 Admin source ID는 컴파일 snapshot과
Android DB에 포함하지 않는다. 앱 DB에는 용어 본문과 공개 출처 메타데이터만
들어간다.

## 최초 저작과 bootstrap

용어 설명 생성은 개발/Admin 저작 단계에서만 실행한다. Android 소스나 APK에는
모델 호출 코드·프롬프트·자격 증명을 넣지 않는다.

```powershell
python tools/generate_glossary_content.py run --batch-size 25 --workers 4
python tools/generate_glossary_content.py merge --batch-size 25
python tools/generate_glossary_content.py validate
python tools/build_glossary_db.py
python tools/admin_import_glossary.py --dry-run
```

Supabase migration을 적용한 뒤 검증본을 최초 한 번 Admin으로 가져온다.
`SUPABASE_SECRET_KEY`는 현재 터미널 환경변수로만 전달한다.

```powershell
python tools/admin_import_glossary.py
```

## Admin 변경과 앱 반영

Admin `/glossary`에서 저장 또는 삭제하면 RPC가 변경과 컴파일 작업 생성을 한
트랜잭션으로 처리한다. 삭제는 감사 추적을 위해 soft archive하며, 바로 생성되는
다음 컴파일 snapshot에는 해당 용어가 없다.

```text
Admin 저장/삭제
  -> glossary_terms 변경 + compile job queue
  -> deterministic Worker가 active 용어만 SQLite FTS5로 컴파일
  -> 해시·크기·schema·행 수·foreign key 검증
  -> 독립 glossary stable 채널 원자적 전환
  -> Android가 HTTPS로 manifest/DB를 내려받아 재검증 후 교체
  -> 이후 검색과 상세 열람은 네트워크 없이 동작
```

Worker는 이미 저작된 snapshot만 처리하며 LLM을 사용하지 않는다.

```powershell
python tools/admin_glossary_worker.py --max-jobs 10
```

stable 채널과 signed artifact를 앱과 같은 보안 경계로 종단간 검증한다.

```powershell
python tools/verify_glossary_release.py https://<admin-domain>/api/glossary/stable
```

운영에서는 GitHub Actions secret `SUPABASE_URL`, `SUPABASE_SECRET_KEY`를 설정하고
repository variable `ADMIN_GLOSSARY_WORKER_ENABLED=true`,
`GLOSSARY_RELEASE_ENDPOINT=https://<admin-domain>/api/glossary/stable`을 설정한다.
`admin-glossary-worker.yml`이 5분마다 대기열을 확인한다. 수동 실행도 가능하다.

여러 번의 빠른 편집은 대기 중인 작업 하나로 합쳐진다. 이미 실행 중인 snapshot은
불변이고, 그 뒤 편집은 후속 작업으로 묶인다. 따라서 삭제 반영 기준은 “Admin 행
삭제 즉시”가 아니라 “삭제로 생성된 glossary stable 릴리스가 앱에 설치된 뒤”이다.

## Android 배포 설정

APK에는 최소 동작용 baseline `glossary.sqlite3`와 manifest를 넣는다. 이후 용어만
바뀔 때는 APK를 다시 만들 필요가 없다. 빌드 시 아래 endpoint를 주입하면 앱이
독립 stable 채널을 확인한다.

```text
FINDONE_GLOSSARY_RELEASE_ENDPOINT=https://<admin-domain>/api/glossary/stable
```

값을 따로 주지 않았고 기존 content endpoint가 `/api/content/stable` 형식이면
Gradle이 `/api/glossary/stable`을 파생한다. 다운로드는 HTTPS, signed URL, SHA-256,
파일 크기, SQLite application ID/schema, FTS와 행 수를 모두 통과해야 설치된다.
실패하면 마지막 검증본 또는 APK baseline을 계속 사용한다.

## 검증

```powershell
python -m unittest tools.test_glossary_content tools.test_admin_glossary_worker
cd admin
npm test
npx tsc --noEmit
cd ..
.\gradlew.bat :app:testDebugUnitTest --no-daemon --max-workers=2 --console=plain
python tools/repo_preflight.py verify --scope auto --changes working
```

공개 APK 출시는 저장소의 별도 release gate를 통과해야 한다. 용어집 컴파일 성공은
APK 공개 승인과 동일하지 않다.
