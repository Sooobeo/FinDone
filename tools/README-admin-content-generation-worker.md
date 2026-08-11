# 로컬 앱 콘텐츠 컴파일러

`admin_content_generation_worker.py`는 원본 fragment와 현재 앱 콘텐츠를 읽어 최종 검토 후보를 만드는 **결정론적 로컬 Worker**다. 외부 LLM API, API key, 토큰 과금이 없으며 Admin은 변환을 실행하지 않고 결과 검토와 승인만 담당한다.

변환 규칙은 다음 파일에 버전으로 고정한다.

- `content/model/local-content-model.json`: 요소 ID·필드 별칭, 품질 게이트와 준비도 가중치
- `tools/local_content_model.py`: JSON·CSV·TSV·라벨형 텍스트 파서, 충돌 차단, 안전 복원 로직
- `content/model/golden-set.json`: 운영 코드와 별도로 유지하는 회귀 평가 케이스

## 자동 처리 범위

다음처럼 요소 ID와 앱 필드가 명시된 원본만 자동 반영한다.

- 중첩/평면 JSON 및 JSON 배열
- 헤더가 있는 CSV·TSV
- `요소ID: ACC-01`, `정의: ...` 형태의 라벨형 문서
- 한국어·영어 필드 별칭
- 제목 동기화, 실무 사용 사례의 concept/formula 동시 반영

일반 웹 문장, 요소 ID가 없는 문서, 서로 다른 값이 충돌하는 필드는 재작성하거나 추측하지 않는다. 기존 검토 콘텐츠를 그대로 유지하고, 새 스키마가 반복되면 Codex 작업에서 별칭·변환 규칙과 골든셋을 추가한다. 이렇게 한 번 코드화한 스키마는 이후 같은 구조의 DB에 자동 적용된다.

## 실행 흐름

1. Source Worker가 파일·URL의 실제 본문, 표, 수식, OCR fragment를 저장한다.
2. 로컬 Worker가 현재 앱 DB와 요소별 근거 fragment를 읽는다.
3. 명시적 구조 필드를 로컬 규칙으로 매핑한다.
4. 모든 변경 필드에 원본 fragment ID를 연결한다.
5. Admin과 동일한 validator를 실행한다.
6. 실패 필드는 창작해서 고치지 않고 검토된 baseline으로 되돌린다.
7. 통과한 변경만 격리된 최종 검토 배치로 저장한다.
8. Owner가 한 번 승인하면 클린 SQLite 빌드·검증·stable 공개가 이어진다.

## 운영 Worker 실행

필요한 환경변수는 자체 백엔드 큐를 읽고 쓰기 위한 다음 두 개뿐이다.

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

```powershell
$env:SUPABASE_URL = 'https://<project>.supabase.co'
$env:SUPABASE_SECRET_KEY = '<service-role key>'
python tools/admin_content_generation_worker.py `
  --worker-id 'local-compiler:local-01' `
  --model-config content/model/local-content-model.json
Remove-Item Env:SUPABASE_SECRET_KEY
Remove-Item Env:SUPABASE_URL
```

Supabase REST는 큐 상태·원본·검토 후보를 전달하는 저장소 통신일 뿐 콘텐츠 판단을 수행하지 않는다. 변환 판단은 모두 이 저장소의 Python 코드에서 이뤄진다.

## 앱 DB 컴파일·학습률·성능 측정

```powershell
python tools/compile_app_content.py --benchmark-rounds 3
```

명령은 다음 순서로 진행률을 표시한다.

- 규칙과 품질 게이트 로드
- 독립 앱 DB 반복 빌드
- SQLite 무결성·필수 필드·출처 추적 검사
- 골든셋 평가
- 준비도와 처리 성능 계산
- 품질 게이트 통과 시에만 앱 asset 승격

측정 결과는 `admin/data/local-content-model-report.generated.json`에 저장되고 Admin의 **로컬 모델 현황** 화면에서 표시된다. 현재의 “학습률”은 신경망 파라미터 학습률이 아니다. 검토 코퍼스 커버리지, 앱 필수 필드 완성률, 출처 추적률, 골든셋 정확도, 결정론 빌드를 가중 합산한 **규칙 모델 준비도**다.

CI에서는 앱 asset을 바꾸지 않고 다음처럼 검사한다.

```powershell
python tools/compile_app_content.py --check --benchmark-rounds 3 `
  --report build/local-content-model-report.json
```

## 사람 승인 피드백

`export_content_generation_training.py`는 기존 파일명 호환을 유지하지만 ML API 학습을 실행하지 않는다. 승인·릴리스된 before/after와 근거만 내보내므로, 새 규칙과 골든 회귀 케이스를 추가할 때 사용하는 오프라인 피드백 자료다.

```powershell
python tools/export_content_generation_training.py --output artifacts/content-feedback.jsonl
```

## 테스트

```powershell
python -m unittest tools.test_local_content_model -v
python -m unittest tools.test_admin_content_generation_worker -v
python -m unittest tools.test_build_content_db -v
```
