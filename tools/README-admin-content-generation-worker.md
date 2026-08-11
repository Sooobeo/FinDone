# Admin 콘텐츠 DB 자동 생성 Worker

`admin_content_generation_worker.py`는 기존 앱 콘텐츠 DB를 baseline으로 읽고, Source Worker가 만든 불변 원문 fragment를 근거로 앱용 콘텐츠 변경 후보를 자동 생성한다. 후보는 최종 승인 전까지 authoring 테이블이나 앱 SQLite에 반영되지 않는다.

## 자동 처리 흐름

초기 앱 DB에 URL만 있던 웹 출처도 Source Worker가 실행당 4건씩 자동 snapshot·가공하므로 별도 관리자 단계가 필요 없다.

1. 아직 생성 배치에 포함되지 않은 `ready` 원본 버전을 최대 50개씩 자동 묶음
2. 원본의 결정론적 요소 후보와 기존 `element_sources` 연결로 대상 요소 선택
3. 긴 문서는 앞부분만 자르지 않고 전체 fragment에서 균등 표본을 만든 뒤 요소별 관련도 재정렬
4. 기존 `elements`, `concepts`, primary `formulas`를 immutable baseline으로 고정
5. OpenAI Responses API의 strict JSON Schema로 변경 후보와 필드별 fragment ID 생성
6. 기존 Admin 검증기(`admin-v2`)로 Markdown, LaTeX, stable ID, 학습 카드 품질 검사
7. 오류 또는 근거 누락 시 같은 schema로 최대 2회 자동 수정
8. 변경된 모든 필드에 배치 범위 내 source fragment가 있는지 재확인
9. 후보·before/after·근거·모델/프롬프트 hash·token 사용량을 최종 검토 배치에 봉인

모델이 근거 없는 내용을 추가하거나 검증을 통과하지 못하면 해당 요소는 저장하지 않는다. 모든 요소가 실패하면 배치를 재시도하고, 최대 3회 후 `failed`로 종료한다. 모델이 baseline을 유지한 경우에는 `no_changes`로 끝난다.

## 최종 승인 이후

Owner가 Admin의 **최종 검토**에서 한 번 승인하면 `approve_content_generation_batch` RPC가 한 트랜잭션 안에서 다음을 수행한다.

- baseline이 검토 중 바뀌지 않았는지 재검사
- 생성 후보를 normalized authoring 테이블에 적용
- append-only revision 생성
- 저장된 검증 결과를 queued → running → passed로 기록
- approval snapshot 생성
- 해당 배치 revision만 포함한 release 생성
- 클린 SQLite 빌드 작업 등록

Release Worker가 새 schema에 canonical row만 다시 적재하고 FTS를 재생성한 뒤 해시·무결성·135개 요소를 검증한다. 통과한 결과만 `stable`에 자동 공개된다.

## 운영 설정

필수 GitHub secrets:

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `OPENAI_API_KEY`

필수 repository variables:

- `OPENAI_CONTENT_MODEL`: 운영에서 고정할 Structured Outputs 지원 모델 ID
- `ADMIN_CONTENT_GENERATION_WORKER_ENABLED=true`

로컬 실행 예시:

```powershell
$env:SUPABASE_URL = 'https://<project-ref>.supabase.co'
$env:SUPABASE_SECRET_KEY = '<secret key>'
$env:OPENAI_API_KEY = '<OpenAI API key>'
$env:OPENAI_CONTENT_MODEL = '<structured-output model>'
python tools/admin_content_generation_worker.py --worker-id 'generation:local-01'
Remove-Item Env:SUPABASE_SECRET_KEY
Remove-Item Env:OPENAI_API_KEY
```

API key는 환경변수와 HTTPS Authorization header에만 사용하고 DB, model input, 로그, 오류 메시지에는 기록하지 않는다.

## 승인 데이터의 모델 학습 준비

기존 DB와 웹 문서만으로 만든 미검토 후보를 정답으로 학습시키지 않는다. `released` 배치에서 사람 승인을 받아 revision과 원문 근거가 모두 고정된 항목만 학습·평가용 JSONL로 내보낸다.

```powershell
python tools/export_content_generation_training.py --output artifacts/content-training.jsonl
```

각 레코드는 baseline snapshot, 필드별 source fragment, 승인된 generated snapshot, 모델·프롬프트 버전과 release/revision ID를 포함한다. 이 데이터가 충분히 쌓인 뒤 별도 holdout 평가를 통과한 모델만 운영 Worker의 `OPENAI_CONTENT_MODEL`로 교체한다.

## 검증

```powershell
python -m unittest tools.test_admin_content_generation_worker -v
python -m unittest tools.test_admin_release_worker -v
python tools/validate_supabase_sql.py
```
