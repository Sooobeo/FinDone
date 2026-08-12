# Codex 실행 전 오류 방지 게이트

이 저장소는 설명용 문서에만 의존하지 않는다. Codex가 자동으로 읽는 루트
`AGENTS.md`, 추적 파일을 직접 바꾸지 않는 `tools/repo_preflight.py`, Git
pre-commit hook, GitHub Actions가 같은 검증 계약을 공유한다.

## 방지하려는 재발 유형

1. 앱 패키지 DB는 `v7`인데 Admin 생성 fixture는 `v6`인 상태로 커밋되어
   Admin CI의 `git diff --exit-code`가 실패하는 경우
2. 로컬에서는 절대경로로 성공하지만 GitHub Actions의 상대경로에서는
   `Path.relative_to(ROOT)`가 예외를 내 모든 ranker가 실패하는 경우
3. `bootstrap_not_reviewed`를 실제 가공 또는 릴리스 가능 상태로 오해하고
   release Gradle task를 실행하는 경우
4. 로컬 검증 명령과 GitHub Actions 명령이 따로 관리되어 한쪽만 통과하는 경우

## 계층별 동작

### 1. 작업 시작 전: inspect

```powershell
python tools/repo_preflight.py inspect --scope admin --changes working
python tools/repo_preflight.py inspect --scope model --changes working
python tools/repo_preflight.py inspect --scope all --changes working
```

`inspect`는 다음을 확인한다.

- Git 루트와 repository hook 활성화 여부
- 현재 변경 파일과 실행할 scope
- `content-manifest.json`의 개념문항 릴리스 상태
- 임시 폴더에 다시 생성한 Admin fixture와 추적 fixture의 byte 단위 일치
- 모델 trainer에 CI 상대경로를 깨뜨리는 직접 `.relative_to(ROOT)` 사용 여부
- 루트 지침, pre-commit hook, Admin/모델 CI의 공통 preflight 연결 여부
- 이동된 문서를 포함한 모든 추적·신규 Markdown의 로컬 링크 유효성

Admin 재생성 결과는 OS 임시 폴더에서만 비교하고 추적 파일은 수정하지 않는다.
`all`은 개발 검증인 Admin·모델·Android를 뜻하며 release를 실행하지 않는다.

### 2. 완료 전: verify

```powershell
python tools/repo_preflight.py verify --scope auto --changes working
```

| Scope | 실행하는 검증 |
|---|---|
| `admin` | Admin Python 테스트, Supabase SQL 파싱, canonical fixture 비교, `npm ci`, Vitest, Next production build |
| `model` | 로컬 모델 회귀 테스트, GitHub와 동일한 상대경로 ranker baseline, 결정론적 앱 DB compile check |
| `android` | `testDebugUnitTest`, `lintDebug`, debug APK assembly; 범용 `test`와 release task는 제외 |
| `release` | 먼저 `release_ready`를 요구한 뒤 Gradle 개념문항 release gate 실행 |
| `all` | `admin` + `model` + `android`; release 제외 |

모델 검증은 외부 LLM API를 호출하지 않는다. `build/` 결과만 만들며 Git에서
제외된다. Admin fixture 비교도 production Supabase나 secret을 사용하지 않는다.

### 3. 커밋 직전: staged snapshot gate

`.githooks/pre-commit`은 다음 명령을 자동 실행한다.

```text
python tools/repo_preflight.py verify --scope auto --changes staged
```

선택된 scope에 staged되지 않은 관련 변경이 남아 있으면 실패한다. 따라서
working tree의 최신 생성물을 보고 통과했지만 실제 commit에는 이전 생성물이
들어가는 문제를 막는다.

hook 활성화:

```powershell
git config --local core.hooksPath .githooks
```

### 4. GitHub Actions

- `admin-ci.yml`은 `verify --scope admin --changes head --ci`
- `local-content-model-evaluation.yml`은 `verify --scope model --changes head --ci`
- `repository-preflight.yml`은 guardrail 단위 테스트와 read-only 전체 inspect

로컬과 CI가 동일한 Python entrypoint를 사용하므로 검증 명령을 두 군데에서
별도로 갱신하지 않는다.

## 의존성 복구

preflight는 누락된 패키지를 몰래 설치하지 않고 필요한 명령을 출력한 뒤
실패한다.

```powershell
python -m pip install pglast==7.10
python -m pip install -r tools/requirements-concept-model-core.txt
cd admin
npm ci
```

의존성을 설치한 뒤 저장소 루트에서 같은 preflight 명령을 다시 실행한다.

## 릴리스 상태 해석

- `bootstrap_not_reviewed`: 자동 생성·약지도 평가 상태. 개발 가능, 릴리스 불가
- `candidate`: 사람 라벨이 일부 반영된 후보. 릴리스 불가
- `release_ready`: 독립적인 사람 검토와 모든 품질 게이트를 통과한 상태

`bootstrap`의 NDCG·Precision 또는 readiness 100%는 파이프라인/내부 기준
통과를 뜻할 뿐 실제 사용자 문제 품질 100%나 일반화 성능을 뜻하지 않는다.
