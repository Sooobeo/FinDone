# Admin source-ingestion worker

`admin_source_ingestion_worker.py`는 Admin에서 등록한 `file_extract`와 `url_fetch` 작업을 실제로 가공하는 전용 one-shot Worker다. 작업 큐의 상태만 바꾸는 모형이 아니라 원본 검증, parser/OCR, fragment 저장, FTS, 요소 후보 대조까지 수행하고 `ready`, `needs_review`, `failed` 중 하나로 반드시 종료한다.

## 자동 가공 범위

- 파일: PDF/스캔 PDF, DOCX, XLSX, PPTX, CSV, Markdown, TXT, HTML, PNG/JPG/WEBP
- URL: 공개 HTTP(S) HTML, PDF 및 위 지원 문서 형식
- Storage 또는 HTTP 응답을 임시 sandbox로 stream 처리하고 크기 상한 적용
- 등록 byte size와 SHA-256 재검증, URL snapshot은 SHA-256을 새로 계산
- ZIP entry 수·압축 해제 크기·압축률, PDF 페이지 수, 이미지 pixel 수 제한
- PDF는 native text를 먼저 추출하고 텍스트가 부족한 페이지만 `kor+eng` OCR
- 본문·표·수식·OCR fragment와 page/slide/sheet/row/selector locator 저장
- `simple` FTS용 정규화 text와 fragment SHA-256 생성
- 업로드 전 동일 SHA-256 private object를 찾으면 바이트를 다시 전송하지 않고 alias를 만들며, 가공 시 기존 immutable fragment도 재사용
- 요소·개념·공식 텍스트를 결정론적으로 대조해 후보와 점수만 저장
- top score 0.92 이상·2위와 gap 0.12 이상인 R0 결과만 source lineage를 자동 연결
- OCR 신뢰도 0.90 미만, 요소 후보 불명확, 추출 상한 도달은 자동 승인하지 않고 `needs_review`
- Worker 오류, lease 만료, retry 소진은 `failed`로 봉인해 UI가 영원히 로딩되지 않게 처리

이 Worker는 개념 콘텐츠 자체를 자동 승인하거나 Android DB를 수정하지 않는다. R0가 아닌 의미 연결과 신규 claim·공식·문항 생성은 사람 검토 대상으로만 보낸다.

## URL fetch 보안

URL은 브라우저 cookie나 인증정보를 사용하지 않는다.

- `http`/`https` 기본 포트만 허용
- credential, IP literal, localhost 및 내부용 hostname 차단
- 최초 URL과 최대 5회 redirect의 DNS를 매번 다시 해석
- 해석된 주소 중 하나라도 private, loopback, link-local, reserved 등이면 차단
- 검증한 IP에 직접 연결하고 원래 hostname으로 TLS 인증/SNI를 수행해 DNS rebinding 방어
- HTTPS에서 HTTP로 내려가는 redirect 차단
- `Accept-Encoding: identity`만 요청하고 압축 응답은 거부
- 응답 크기·timeout·MIME/signature를 제한하고 raw snapshot을 `source-private`에 보존
- final URL, redirect chain, 제한된 응답 header, 수집 시각, snapshot hash를 version metadata에 저장

## 사전 조건과 실행

Supabase migration `202608110004_source_ingestion_worker.sql`까지 적용해야 한다. Worker RPC는 `service_role`만 실행할 수 있다. Secret은 파일이나 명령행에 넣지 않고 프로세스 환경변수로만 전달한다.

```powershell
python -m pip install --requirement tools/requirements-source-worker.txt
$env:SUPABASE_URL = 'https://<project-ref>.supabase.co'
$env:SUPABASE_SECRET_KEY = '<sb_secret key>'
python tools/admin_source_ingestion_worker.py --worker-id 'source:local-01' --max-jobs 4
Remove-Item Env:SUPABASE_SECRET_KEY
```

OCR에는 Python package 외에 Tesseract 실행 파일과 `eng`, `kor` language data가 필요하다. GitHub Worker workflow는 Ubuntu에서 이를 자동 설치한다. OCR이 필요한 페이지인데 엔진이 없거나 신뢰도가 기준 미달이면 내용을 추측하지 않고 `needs_review`로 보낸다.

기본 원본 상한은 1024 MiB다. 운영 정책에 따라 `ADMIN_SOURCE_WORKER_MAX_MIB` 또는 `--max-source-mib`로 1–10240 MiB 사이에서 조정할 수 있으며, Supabase Storage의 global file size limit도 같거나 더 커야 한다.

## 자동 실행

Repository secrets에 `SUPABASE_URL`, `SUPABASE_SECRET_KEY`를 등록하고 variable `ADMIN_SOURCE_WORKER_ENABLED=true`를 설정한다. `.github/workflows/admin-source-worker.yml`이 5분마다 최대 4건을 처리한다. 같은 Worker ID의 live claim 복구, 20분 lease 회수, 최대 attempt 소진 봉인은 DB RPC에서 원자적으로 수행한다.

Admin UI는 upload/hash 계산, Storage 전송, URL 등록 중에는 즉시 로딩 표시를 띄운다. 등록 후에는 `source_catalog_overview`를 3초마다 갱신해 대기·내려받기·검증·snapshot 보관·추출·OCR·정규화·요소 대조·저장 단계와 실제 진행률을 표시한다.

## 검증

```powershell
python -m unittest tools.test_admin_source_ingestion_worker -v
python -m unittest discover -s tools -p "test_admin*.py" -v
python tools/validate_supabase_sql.py
```

Supabase CLI와 Docker가 있는 환경에서는 migration 적용 전후로 아래 pgTAP까지 실행한다.

```powershell
supabase db reset --local
supabase test db
supabase db lint --local --level warning
```
