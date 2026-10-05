# FinDone × Hermes Telegram

기존 FinDone 콘텐츠 DB를 읽어 개인 Telegram DM에 퀴즈·주간 복습·금융 영어 뉴스를 보내는 독립 Python 패키지입니다. [서비스 설계서](SERVICE_DESIGN.md)를 구현합니다. Android 학습 기록과 자동 동기화하지 않습니다.

Asia/Seoul 기준 기본 `learning` 봇은 매일 **12:30·20:30 퀴즈**를 보냅니다. 일요일 20:30은 주간 통계·복습으로 대체합니다. **08:00 뉴스는 별도 Telegram 봇과 `findone-news` Hermes 프로필**에서 보냅니다. 학습 봇은 `2,4`, `/help`, `/stats`, `/stats FI`, `/why 2`, `/skip`, `/review`를 처리하며 답안은 섞인 선택지의 **1~5번**입니다. 미완료 회차는 한 개만 유지하고 자동 만료하지 않습니다.

뉴스 봇의 증권사·보험사 모드는 **CNBC·Bloomberg의 공개 기사**에서 사건·배경·사업 영향이나 반응을 영·한으로 요약하고, 기사 속 금융 전문용어와 중요한 비즈니스 구문을 함께 보여줍니다. 요약 모델은 현재 품질·속도를 비교해 선정 중이며 이 문서는 특정 모델의 선정을 전제하지 않습니다.

뉴스 봇에서는 `/now`로 새 뉴스를 요청하고, 기사 메시지에 답장으로 `/word yield` 또는 `/word back on track`을 보내 단어나 구문을 저장합니다. `/vocab 5`는 저장 항목 최대 5개를 **4지선다**로 복습하며, `/words`는 저장 수와 지금 복습할 수를 보여줍니다. 문맥별 뜻·정확한 원문 문장·원문 링크는 개인 위키에 보관하고, 정오답과 복습 간격은 독립적인 단어 DB에서 관리합니다.

## 실행 경계

- `src/findone_hermes/`: 읽기 전용 콘텐츠 검증, 회차 스냅샷, 채점·통계·뉴스 처리.
- `hermes/plugin/`: Hermes의 Telegram 메시지를 받아 직접 처리하는 `findone-telegram` 플러그인.
- `hermes/scripts/`: 실제 Hermes 데이터 홈의 `scripts/`에 복사할 cron 래퍼.
- 학습·단어·기사 SQLite, 단어 목록 캐시와 개인 위키, BotFather 토큰, Telegram ID, 모델 키는 **저장소 밖**에 둡니다. 운영 값을 이 README나 Git에 적지 마세요.

Python 3.11 이상을 사용합니다. FinDone 패키지는 외부 Python 의존성이 없습니다. Hermes 자체의 지원 Python 버전은 [현재 설치 문서](https://hermes-agent.nousresearch.com/docs/getting-started/installation)를 따릅니다. 아래 예시는 Windows PowerShell이며 경로는 실제 설치에 맞게 조정합니다. POSIX의 기본 Hermes 홈은 `~/.hermes`, 현재 Windows 기본값은 `%LOCALAPPDATA%/hermes`입니다. `HERMES_HOME` 또는 프로필을 사용하면 해당 홈에 설치해야 합니다.

## 설치

[Hermes](https://hermes-agent.nousresearch.com/docs/getting-started/installation)를 먼저 설치합니다. 이 저장소의 코드만으로 BotFather 등록이나 Hermes 설치가 자동 수행되지는 않습니다.

```powershell
$repoRoot = (Resolve-Path "C:/Users/Insun/FinDone").Path
$hermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }
$env:HERMES_HOME = $hermesHome
$venvPath = Join-Path $env:LOCALAPPDATA "FinDone/hermes-venv"
python -m venv $venvPath
$cronPython = Join-Path $venvPath "Scripts/python.exe"
& $cronPython -m pip install "$repoRoot/hermes_telegram"

$env:FINDONE_REPO_ROOT = $repoRoot
& $cronPython -m findone_hermes.jobs validate-content
& $cronPython -m findone_hermes.jobs preview
```

`validate-content`와 `preview`는 학습 DB를 만들거나 Telegram에 전송하지 않습니다. 처음 사용할 실제 문항은 `preview`로 본문·정답·해설을 확인하세요. 콘텐츠 manifest의 버전·크기·SHA-256·문항 수 검증이 실패하면 콘텐츠를 먼저 수정해야 합니다.

플러그인과 래퍼를 **복사**합니다. cron 스크립트가 저장소를 가리키는 심볼릭 링크이면 Hermes의 스크립트 경로 검증에서 거부됩니다. 플러그인 디렉터리에 서비스의 `pyproject.toml`과 `src/`도 함께 둬 Hermes PM이 로컬 workspace member로 설치하게 합니다. Hermes의 관리 Python 환경은 직접 pip/uv로 수정하지 않습니다. `python_dependencies`의 직접 URL 선언은 현재 PM 그래프에서 제외되므로 `findone-hermes @ file:///...`을 추가하지 마세요. [Hermes 패키지 관리](https://hermes-agent.nousresearch.com/docs/reference/package-management), [현재 플러그인 의존성 처리](https://github.com/NousResearch/hermes-agent/blob/c8301ea6c9b797184df16a9c5dd462400b264ff4/pm/plugin_declarations.py)

```powershell
$pluginPath = Join-Path $hermesHome "plugins/findone-telegram"
$pluginPackagePath = Join-Path $pluginPath "src/findone_hermes"
$scriptsPath = Join-Path $hermesHome "scripts"
New-Item -ItemType Directory -Path $pluginPath, $pluginPackagePath, $scriptsPath -Force | Out-Null
Copy-Item -Path "$repoRoot/hermes_telegram/hermes/plugin/*" -Destination $pluginPath -Force
Copy-Item -LiteralPath "$repoRoot/hermes_telegram/pyproject.toml" -Destination $pluginPath -Force
Copy-Item -Path "$repoRoot/hermes_telegram/src/findone_hermes/*.py" -Destination $pluginPackagePath -Force
Copy-Item -Path "$repoRoot/hermes_telegram/hermes/scripts/*.py" -Destination $scriptsPath -Force

hermes plugins enable findone-telegram
hermes pm install
hermes plugins show findone-telegram
```

이것으로 플러그인이 쓰는 Hermes PM 환경과 cron 전용 가상환경에 같은 서비스 코드가 준비됩니다. `plugins show`의 enabled 표시는 설정 확인이며 실제 import·hook 등록 성공까지 증명하지 않습니다. gateway 로그와 실제 DM 동작도 확인해야 합니다. 이미 활성화된 플러그인에 `enable`만 다시 실행하면 의존성 그래프를 갱신하지 않으므로 `hermes pm install`까지 실행하세요.

코드를 업데이트할 때 gateway를 멈추고 `& $cronPython -m pip install --upgrade "$repoRoot/hermes_telegram"`을 다시 실행합니다. 위 복사 블록을 다시 실행해 `plugin.yaml`·hook·`pyproject.toml`·서비스 모듈·래퍼를 갱신하고, `hermes pm install`을 완료한 뒤 gateway를 재시작합니다. 삭제되거나 이름이 바뀐 파일은 저장소 밖의 기존 복사본에서도 정리하고 새 파일이 있으면 함께 복사하세요. 실행 중인 프로세스의 import는 자동 갱신되지 않습니다.

## 로컬 설정

`hermes dashboard --host 127.0.0.1 --port 9119 --no-open --skip-build`로 설치 시 빌드된 대시보드를 열고, `http://127.0.0.1:9119`의 Messaging → Telegram → Create with QR에서 봇을 만들 수 있습니다. 휴대전화에서 QR을 스캔하고 Create Bot을 누르면 대시보드가 본인 ID를 감지하고 선택한 프로필에 토큰·allowlist를 저장합니다. 기존 gateway가 실행 중일 필요는 없습니다. 수동 설정은 `hermes gateway setup`에서 Telegram을 선택합니다. 운영 홈의 `.env`에는 아래 **예시를 실제 값으로 바꿔** 추가합니다. 숫자 ID는 단 한 개만 허용하며 `*`, 목록, 그룹 ID는 거부됩니다. [Hermes Telegram 설정](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram)

```dotenv
TELEGRAM_BOT_TOKEN=<BotFather에서 받은 토큰>
TELEGRAM_ALLOWED_USERS=<본인의 양수 숫자 ID 한 개>
FINDONE_TELEGRAM_MODE=learning
FINDONE_REPO_ROOT="C:/Users/Insun/FinDone"
STATE_DB_PATH="C:/Users/Insun/AppData/Local/FinDone/hermes/state.sqlite3"
# FINDONE_QUIZ_COUNT=2
# CONTENT_DB_PATH="C:/Users/Insun/FinDone/app/src/main/assets/content.sqlite3"
# CONTENT_MANIFEST_PATH="C:/Users/Insun/FinDone/app/src/main/assets/content-manifest.json"
```

모든 지정 파일 경로는 절대 경로여야 합니다. `STATE_DB_PATH`는 저장소 내부이면 실행을 거부합니다. 생략하면 OS 사용자 데이터 디렉터리에 학습 DB를 만듭니다. 일반 pip 설치는 소스 경로를 보존하지 않으므로 `FINDONE_REPO_ROOT` 또는 두 콘텐츠 경로를 반드시 설정합니다.

cron 래퍼는 설치된 `scripts/`의 부모 홈 `.env`를 명시적으로 읽습니다. `FINDONE_ENV_FILE`을 절대 경로로 지정할 수도 있습니다. 기본 bootstrap은 필요한 FinDone 설정·모델 키만 읽으며, 뉴스 직접 발송 경로는 해당 뉴스 프로필의 Bot 토큰도 읽습니다. `.env` 값은 리터럴이며 `${...}`나 셸 명령을 실행하지 않습니다. 모델 공급자 키가 cron 자식 환경에서 제거되는 Hermes의 동작을 고려한 처리입니다.

운영 홈의 `config.yaml`에 다음을 기존 설정과 합칩니다. 같은 YAML 키를 중복으로 추가하지 마세요. [플러그인 활성화](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins), [시간대](https://hermes-agent.nousresearch.com/docs/user-guide/configuration#timezone), [누락 작업 정책](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron#local-missed-run-policy)

```yaml
timezone: Asia/Seoul
plugins:
  enabled:
    - findone-telegram
cron:
  catch_up_missed: false
```

`pre_gateway_dispatch`는 Hermes 자체 인증보다 먼저 실행됩니다. 플러그인은 Telegram·본인 ID·개인 DM·일치하는 chat ID를 다시 확인하고 모든 Telegram 경로에서 `skip`을 반환합니다. 허용되지 않은 사용자·그룹, 패키지 import 실패, 처리·전송 오류도 일반 에이전트로 넘기지 않습니다. 다른 플랫폼은 해당 hook의 기존 흐름을 유지합니다. Hermes 자체는 hook 예외 때 일반 처리로 넘어가므로 플러그인 활성화·로딩 성공을 반드시 확인해야 합니다. [현재 hook 계약](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/hooks.md)

### 별도 뉴스 봇

뉴스용 봇을 하나 더 만들고 아래와 같이 빈 프로필을 준비합니다. 기본 프로필을 복제하지 않습니다. 기존 기본 프로필에 `findone-news` 일정이 있으면 로컬 `hermes -p default cron list`로 작업 ID를 확인해 **먼저 `hermes -p default cron pause <news_job_id>`로 중지**합니다. 이후 08:00 일정은 뉴스 프로필에만 등록합니다.

```powershell
hermes profile create findone-news --no-skills --no-alias
$newsHome = Join-Path $hermesHome "profiles/findone-news"
$newsPluginPath = Join-Path $newsHome "plugins/findone-telegram"
$newsScriptsPath = Join-Path $newsHome "scripts"
New-Item -ItemType Directory -Path $newsPluginPath, $newsScriptsPath -Force | Out-Null
Copy-Item -Path "$repoRoot/hermes_telegram/hermes/plugin/*" -Destination $newsPluginPath -Force
Copy-Item -LiteralPath "$repoRoot/hermes_telegram/hermes/scripts/findone_news.py", "$repoRoot/hermes_telegram/hermes/scripts/_findone_bootstrap.py" -Destination $newsScriptsPath -Force
hermes -p findone-news plugins enable findone-telegram
```

뉴스 프로필의 `plugins/findone-telegram/`에는 hook과 `plugin.yaml`만 둡니다. `pyproject.toml`·`src/`를 다시 복사해 동일 패키지를 중복 설치하지 않습니다. 기본 프로필에서 준비한 Hermes PM 서비스 패키지와 cron 가상환경을 공유합니다. 코드 갱신 시 두 프로필의 hook을 함께 갱신합니다.

대시보드에서 **`findone-news` 프로필을 선택한 후** Messaging → Telegram에 별도 뉴스 봇의 토큰을 저장합니다. 기본 봇과 동일한 본인 ID를 사용해도 되며, 로컬 기본 프로필 `.env`에서 ID만 복사하거나 직접 입력합니다. 기본 봇의 토큰을 복사하지 않습니다. 뉴스 프로필 `.env`는 다음과 같이 독립적인 상태 경로와 모드를 지정합니다.

```dotenv
TELEGRAM_BOT_TOKEN=<별도 뉴스 봇의 토큰>
TELEGRAM_ALLOWED_USERS=<같은 본인의 양수 숫자 ID 한 개>
FINDONE_TELEGRAM_MODE=news
FINDONE_NEWS_FOCUS=securities_insurance
FINDONE_REPO_ROOT="C:/Users/Insun/FinDone"
STATE_DB_PATH="C:/Users/Insun/AppData/Local/FinDone/hermes-news/state.sqlite3"
FINDONE_NEWS_ARCHIVE_PATH="C:/Users/Insun/AppData/Local/FinDone/hermes-news/news_archive.sqlite3"
FINDONE_VOCAB_DB_PATH="C:/Users/Insun/AppData/Local/FinDone/hermes-news/vocabulary.sqlite3"
```

`FINDONE_NEWS_FOCUS=securities_insurance`는 CNBC·Bloomberg의 증권사·투자은행·보험사 관련 기사를 고릅니다. 설정을 생략하거나 `general`로 지정하면 기존 중앙은행·공식 금융기관 RSS 모드를 사용합니다. 자동 전문용어·구문 선택에는 Oxford 목록 캐시가 필요하지 않습니다.

CNBC Finance·Health and Science와 Bloomberg Markets의 공식 RSS를 사용합니다. Finance에 빠진 건강보험사 사업 기사도 찾되, 일반 의료·제약 기사는 증권사·보험사 주제 필터로 제외합니다.

뉴스 프로필 `config.yaml`에도 위의 `timezone`·`plugins`·`cron` 설정을 합칩니다. 두 프로필은 한 gateway가 함께 제공하며 별도 Windows 자동 시작 서비스를 추가하지 않습니다. 프로필 생성 전 gateway가 기본 봇만 제공하고 있었다면 준비 후 `hermes gateway restart`로 두 프로필을 연결합니다. 뉴스 봇의 `1`~`4` 답장은 단어 복습에만 사용하며, `/stats`·`/review`는 뉴스 전용 안내를 보냅니다.

뉴스 봇에 `/now`를 보내면 08:00 슬롯과 예약 실행의 30분 유예 시간에 관계없이 최근 7일 이내의 미발송 기사를 즉시 준비합니다. 설정된 출처의 RSS·원문 검증과 URL 중복 방지는 예약 뉴스와 같습니다. 같은 Telegram 메시지가 재수신되어도 중복 처리·전송하지 않습니다. `/now`는 기존 08:00 예약 일정을 변경하지 않습니다.

플러그인은 인증과 모드를 Hermes의 활성 프로필 secret scope에서 읽고, 답장은 메시지를 받은 프로필의 adapter로 전송합니다. 뉴스 봇 adapter가 끊겼을 때 기본 봇으로 대신 보내지 않습니다. 뉴스 모델 설정은 아래 선택적 모델 절차에 따라 **뉴스 프로필 `.env`에만** 추가합니다.

### 뉴스 단어 저장·복습

Telegram에서 저장할 **기사 메시지 자체에 답장**으로 `/word yield` 또는 `/word back on track`처럼 입력합니다. 구문은 따옴표 없이 그대로 입력합니다. 봇은 뉴스 프로필이 실제 발송한 메시지 ID와 보관한 기사 스냅샷을 대조하고, 해당 원문에 단어나 구문이 있는지 확인합니다. 기사 연결 없이 최근 기사를 추측해서 저장하지 않습니다. 뉴스에 제시된 항목은 발송한 문맥별 뜻과 그 표현이 등장한 **정확한 원문 전체 문장**을 함께 저장합니다. 동일 표현의 다른 등장 위치나 새로 만든 예문으로 바꾸지 않습니다. 새 항목의 뜻은 설정된 모델로 원문 문맥을 확인한 뒤 저장하며, 수동 `/word`에는 CEFR 난도 제한을 적용하지 않습니다.

`/vocab 5`는 복습 시각이 된 단어부터 최대 5문항을 준비합니다. 모바일에서는 첫 미답 문항을 하나씩 표시하며 **`1`~`4` 중 한 번호**로 답하면 정오답·한국어 해설·저장한 원문 예문과 다음 문항을 보여줍니다. 현재 발송이 확인된 문항만 채점하며, 예전 문항에 답장하면 새 문항을 채점하지 않습니다. 오답 단어는 **10분 뒤**, 연속 정답은 **1·3·7·14·30·60일 뒤**로 복습 시각을 잡습니다. `/words`는 저장 단어 수·현재 복습 대상 수를 확인합니다. 미완료 단어 회차와 선택지·뜻·예문은 재시작 후에도 유지하고 같은 메시지 ID는 다시 저장하거나 채점하지 않습니다.

같은 표제어라도 **기사 URL과 문맥상 의미**가 다르면 별도 단어로 저장합니다. 같은 표제어·URL·의미의 재저장은 기존 뜻·예문·복습 기록을 덮어쓰지 않습니다. 오답 선택지는 발송된 다른 단어의 뜻과 검증한 FinDone 개념 후보에서만 고르며, 서로 다른 근거 있는 선택지 4개를 만들 수 없으면 문제를 만들지 않습니다.

`vocabulary.sqlite3`에는 단어 스냅샷·정오답·다음 복습 시각·미완료 회차·중복 처리 기록을 둡니다. `news_archive.sqlite3`에는 검증한 기사·발송 메시지와의 연결·기사별 어휘를 둡니다. 두 파일은 학습 봇의 `state.sqlite3`와 별개이며 `FINDONE_VOCAB_DB_PATH`, `FINDONE_NEWS_ARCHIVE_PATH`로 외부 절대 경로를 지정합니다. 생략하면 뉴스 `STATE_DB_PATH`의 부모 디렉터리에 각각 `vocabulary.sqlite3`, `news_archive.sqlite3`를 사용합니다. 기존 학습 DB를 이 경로에 지정하면 별도 스키마 검증에서 거부합니다.

### 금융 전문용어·비즈니스 구문과 개인 위키

증권사·보험사 모드는 전문용어와 비즈니스 구문을 각각 최대 2개 표시합니다. `combined ratio`, `gross written premiums`, `assets under management`, `institutional liquidity` 같은 금융·보험 용어와 `back on track`, `on the sidelines`, `make a play for` 같은 표현이 대상입니다. 기사에 실제로 등장하는 표현만 고르므로 모든 기사에 같은 개수의 항목이 나오지는 않습니다.

`news_language.py`의 작은 오프라인 용어·구문 목록은 NAIC·CFA Institute·SIFMA 등 전문기관 자료와 사전의 출처를 항목별로 보관합니다. 원문의 표현·대소문자·문장과 후보 ID는 코드가 확정하고 모델은 제공된 후보의 문맥별 한국어 뜻을 작성합니다. 구문의 활용 형태와 저장하는 사용 설명은 승인된 사전 뜻을 바탕으로 코드가 구성합니다. 전문성에 CEFR 등급을 붙이거나 쉬운 일반 C1 단어로 빈자리를 채우지 않습니다. 뉴스에는 구문의 한국어 뜻과 활용 형태를 간결하게 표시하고, `/word`로 저장하면 정확한 원문 전체 문장을 위키에서도 확인할 수 있습니다.

자동 어휘에서 `investment bank`, `ETF`, `hedge fund`, `reinsurance`, `prediction market`, `profit margin` 같은 기본 명칭은 제외합니다. 후보가 적어도 이 명칭으로 보충하지 않습니다. `facultative reinsurance`, `excess of loss reinsurance`, `retrocession` 같은 전문적인 재보험 용어는 유지하며, 원문에 있는 기본 명칭도 수동 `/word`로 저장할 수 있습니다.

기존 `general` 모드의 자동 어휘는 [Oxford 5000의 B2–C1 추가 단어 목록](https://www.oxfordlearnersdictionaries.com/external/pdf/wordlists/oxford-3000-5000/The_Oxford_5000.pdf)을 사용합니다. 이 모드에서만 `FINDONE_CEFR_WORDLIST_PATH`와 `FINDONE_VOCAB_MIN_LEVEL`의 B2 또는 C1 기준을 적용합니다. 현재 캐시의 1,990개 항목은 전체 Oxford 5000이나 문맥별 난도 판정을 뜻하지 않습니다. 기존 캐시를 다시 준비할 때는 `pypdf`가 있는 사용자 관리 Python에서 다음을 실행합니다.

```powershell
python "$repoRoot/hermes_telegram/tools/build_cefr_index.py" --output "$env:LOCALAPPDATA/FinDone/hermes-news/oxford5000_cefr.json"
```

저장한 단어·구문은 **Oh My Wiki의 private 페이지**에 문맥별 뜻·정확한 원문 문장·기사 제목·출처·발행일·URL·사용 설명을 투영합니다. 정오답·연속 정답·다음 복습 시각·Telegram ID는 위키로 보내지 않고, OMW `review`에도 연결하지 않습니다. 위키 반영에 실패해도 SQLite 저장은 유지하며 재처리는 같은 페이지를 중복 생성하지 않습니다.

뉴스 프로필 `.env`에서 `FINDONE_WIKI_CLI_PATH`, `FINDONE_WIKI_HOME`, `FINDONE_WIKI_VAULT`, `FINDONE_WIKI_VAULT_PATH`를 모두 설정합니다. 설치·private 설정·로컬 검색과 경로 예시는 [개인 단어 위키 안내](WIKI_INTEGRATION.md)를 따릅니다.

## 예약과 실행

본인이 Telegram에서 **두 봇을 각각 먼저 시작한 뒤**, 앞에서 사용한 `$cronPython`과 실제 본인 ID로 세 작업을 각 프로필에 만듭니다. 이미 같은 일정이 있으면 중복 생성하지 않습니다. ID는 로컬 PowerShell에서 직접 입력하고 저장소에 저장하지 않습니다. 학습 래퍼는 고정 CLI `regular --slot 12:30`, `regular --slot 20:30`을 호출하고 뉴스 래퍼는 `news_delivery`의 08:00 직접 발송 경로를 호출합니다. 일요일 복습용 별도 cron은 추가하지 않습니다.

```powershell
$telegramId = Read-Host "본인 Telegram 숫자 ID"
hermes -p default cron create "30 12 * * *" --no-agent --script findone_quiz_midday.py --interpreter $cronPython --deliver "telegram:$telegramId" --name findone-midday
hermes -p default cron create "30 20 * * *" --no-agent --script findone_quiz_evening.py --interpreter $cronPython --deliver "telegram:$telegramId" --name findone-evening
hermes -p findone-news cron create "0 8 * * *" --no-agent --script findone_news.py --interpreter $cronPython --deliver local --name findone-news
hermes -p default cron list
hermes -p findone-news cron list
hermes gateway run
```

`--interpreter`는 사용자가 관리하는 Python 실행 파일의 절대 경로입니다. 학습 퀴즈의 stdout은 Hermes가 Telegram으로 전달합니다. **뉴스 래퍼는 뉴스 프로필의 봇으로 직접 발송하고 Telegram이 반환한 메시지 ID를 기사 보관 DB에 연결**하므로 `--deliver local`을 사용합니다. 뉴스에 `--deliver telegram:...`을 함께 설정하면 본문이 이중 전송될 수 있습니다. 기존 뉴스 일정을 갱신할 때도 전달 대상을 `local`로 맞추고 같은 일정은 중복 생성하지 않습니다. `--no-agent` 경로에서 Hermes 에이전트 호출은 발생하지 않습니다. [Script-only cron 계약](https://hermes-agent.nousresearch.com/docs/guides/cron-script-only)

Windows에서 로그인 시 자동 시작하려면 다음을 실행합니다. `gateway run`으로 실행한 프로세스는 먼저 종료합니다. 비관리자 계정에서는 비대화형 모드가 기본값이 false인 UAC 제안을 거절하고 현재 사용자 Startup 폴더에 공식 `.vbs` 실행 항목을 설치합니다. 관리자 계정에서는 Scheduled Task를 사용합니다. `--no-start-now`로 등록만 한 뒤, Telegram 설정이 저장되면 숨겨진 gateway를 시작하고 상태를 확인합니다. [현재 Windows 실행 방식](https://github.com/NousResearch/hermes-agent/blob/c8301ea6c9b797184df16a9c5dd462400b264ff4/hermes_cli/gateway_windows.py)

```powershell
$previousNoninteractive = $env:HERMES_NONINTERACTIVE
try {
    $env:HERMES_NONINTERACTIVE = "1"
    hermes gateway install --no-start-now --start-on-login
} finally {
    $env:HERMES_NONINTERACTIVE = $previousNoninteractive
}
hermes gateway start
hermes gateway status --deep
```

PC와 네트워크가 켜져 있고 **gateway의 로컬 스케줄러가 실행 중**이어야 정기 작업·답장 수신이 됩니다. 별도 외부 스케줄러가 스크립트를 실행시키면 Telegram REST 전송 자체는 gateway 없이도 가능하지만, 위 구성은 gateway 내장 스케줄러를 사용합니다. 절전·종료 중의 정시 전달은 보장하지 않습니다. `catch_up_missed: false`도 Hermes 유예 시간 안의 지연 실행을 허용하므로 작업 자체가 예약 시각 이후 30분까지만 실행합니다.

같은 작업 종류·KST 날짜·슬롯은 한 번만 확보합니다. 학습 퀴즈의 `emitted`는 stdout 인계 상태이며 전달 완료를 뜻하지 않습니다. 뉴스는 직접 발송 응답의 메시지 ID를 기록하지만 네트워크 발송과 SQLite 기록은 하나의 원자적 작업이 아니므로, 중간 종료·전송 오류·실패 슬롯을 자동 재전송하지 않습니다. `hermes cron run <job_id>`도 이 중복·유예 규칙을 따르며, 운영자가 Telegram과 `job_runs`·기사 발송 연결을 확인해야 합니다.

오래된 퀴즈에 답할 때는 그 봇 메시지에 답장을 걸어 주세요. 보존된 `회차 ID`로 해당 회차를 선택하므로 과거 회차 재답장이 현재 회차를 채점하지 않습니다. 답장 연결 없는 숫자는 현재 활성 회차에 적용됩니다. 동일 Telegram 메시지 ID는 재채점하지 않습니다. 정답·선택지·해설은 발송 스냅샷을 사용해 콘텐츠가 갱신되어도 유지됩니다.

## 선택적 모델

퀴즈·채점·통계·주간 수치는 모델 없이 동작합니다. `/why`는 기본적으로 저장된 해설을 보여줍니다. 모델을 사용하려면 아래 값을 해당 기능의 프로필 `.env`에 지정하고 gateway를 재시작합니다. 뉴스 모델은 `findone-news`, 선택적 `/why` 설명 모델은 기본 학습 프로필에 따로 설정합니다. `FINDONE_MODEL_BASE_URL`과 `FINDONE_MODEL_NAME`이 모두 명시된 경우에만 OpenAI 호환 API 또는 로컬 모델을 호출합니다. 공급자가 인증을 요구하면 `FINDONE_MODEL_API_KEY`도 직접 설정하며, 인증 없는 로컬 API는 키를 생략할 수 있습니다. Hermes의 기본 모델이나 다른 공급자 키로 자동 대체하지 않습니다.

영·한 뉴스레터에는 요약 모델 설정이 필요하며 `/now`에도 같은 조건을 적용합니다. 미설정이면 RSS를 조회하거나 요약을 지어내지 않고 `뉴스 요약 모델이 설정되지 않아 영·한 뉴스레터를 준비할 수 없습니다`를 보냅니다. 모델을 설정한 경우에만 선택한 출처의 RSS와 원문을 대조해 최근 7일 이내의 새 기사 1~2건을 준비합니다. 검증 실패와 새 기사 없음은 서로 다른 안내로 표시합니다. 이번 운영 구성은 모델 API 요금이 발생하지 않는 로컬 경로를 사용하며, 최종 모델은 공개 기사에서 요약 품질과 응답 시간을 검증한 뒤 선택합니다.

```dotenv
# 예: 사용자가 운영하는 로컬 OpenAI 호환 API
FINDONE_MODEL_BASE_URL=http://127.0.0.1:11434/v1
FINDONE_MODEL_NAME=<설치한 모델 이름>
# FINDONE_MODEL_API_KEY=<필요한 경우 로컬에만 설정>
# FINDONE_MODEL_TIMEOUT_SECONDS=90
# FINDONE_MODEL_REASONING_EFFORT=none
# FINDONE_MODEL_PRESENCE_PENALTY=0
```

모델 요청별 대기 시간은 기본 30초입니다. 느린 로컬 모델은 같은 프로필 `.env`의 `FINDONE_MODEL_TIMEOUT_SECONDS`로 1~180초 범위에서 조정할 수 있습니다. 이 값은 뉴스 전체 처리 시간 제한이 아니며, 여러 기사에서 모델을 호출하면 전체 대기 시간은 더 길어질 수 있습니다. cron 래퍼도 해당 프로필의 값을 읽습니다.

`FINDONE_MODEL_REASONING_EFFORT`는 `none`·`low`·`medium`·`high`를 허용하며, 지정한 경우에만 API 요청에 `reasoning_effort`를 추가합니다. 생략하거나 비워 두면 공급자의 기본 동작을 유지합니다. Ollama의 thinking 켜기·끄기를 지원하는 모델은 `none`으로 thinking을 끌 수 있으며, 모델별 지원 수준은 `/api/show`로 확인합니다. [Ollama OpenAI 호환 설정](https://docs.ollama.com/api/openai-compatibility)

`FINDONE_MODEL_PRESENCE_PENALTY`는 선택적 설정이며 -2부터 2까지의 유한한 수만 허용합니다. 명시한 값만 요청의 `presence_penalty`에 추가하며, 생략하거나 비우면 공급자 기본값을 유지합니다. 각 프로필 설정과 cron bootstrap에 같은 규칙을 적용합니다. 뉴스 JSON 출력의 비교 실험에는 `0`을 지정할 수 있습니다. Ollama는 이 요청 필드를 지원하고, Qwen 공식 모델 카드는 높은 값에서 언어가 섞이거나 성능이 낮아질 수 있다고 설명합니다. `0`의 실제 요약 품질 개선 여부는 공개 기사 출력으로 확인해야 합니다. [Ollama 지원 요청 필드](https://docs.ollama.com/api/openai-compatibility), [Qwen3.5-9B 모델 카드의 Best Practices](https://huggingface.co/Qwen/Qwen3.5-9B#best-practices)

증권사·보험사 모드는 기사 한 건마다 **무슨 일이 있었나 → 배경 → 사업 영향·반응** 순서로 2~3개의 짧은 영·한 요약을 작성합니다. 원문에 영향 근거가 없으면 사건과 배경만 표시합니다. 모델에는 검증한 원문의 완전한 근거 문장과 전문용어·구문 후보를 제공하며, 각각의 요약을 원문 근거에 연결합니다. 논의·계획·가능성을 확정된 거래나 인사로 바꾸지 않도록 요청하고 숫자·단위·회사명도 검증합니다. 이 모드에서는 FinDone 개념 연결을 억지로 추가하지 않습니다. 한 기사는 원문 링크를 포함한 3,000 UTF-16 단위 이내의 별도 Telegram 메시지로 발송합니다.

CNBC·Bloomberg는 발행사가 일반 요청에 공개한 본문만 사용합니다. 구독·로그인·CAPTCHA로 제한된 기사는 제외하고 우회하거나 제3자 사본을 가져오지 않습니다. 공개 부분 본문만 확보했다면 **공개된 본문 범위를 바탕으로 요약했다는 안내**를 표시하며 비공개 전문의 내용을 추정하지 않습니다. 원제목·발행일·출처·URL은 코드가 검증하고 모델 출력으로 바꾸지 않습니다.

기존 `general` 모드는 짧은 원문 금융 문장 최대 4개·총 2,000자와 실제 FinDone 개념 후보를 사용합니다. `/why` 추가 설명에는 해당 문항·기본 해설만 보냅니다. 어느 경로에서도 사용자 ID나 전체 답안 이력을 모델에 보내지 않습니다. 자동 검증만으로 영·한 요약의 의미 정확성을 보장할 수 없으므로 모델 선정 전에 실제 공개 기사 출력 품질을 확인합니다. 사용자가 별도로 외부 API를 설정한다면 비용은 해당 공급자의 요금에 따릅니다.

## 확인과 문제 해결

```powershell
python tools/repo_preflight.py verify --scope auto --changes working
```

이 명령이 Hermes 전용 테스트·실제 상대 경로 콘텐츠 검증 CLI를 실행하며 CI도 같은 preflight를 사용합니다. 실제 봇에 대한 별도 확인은 로컬 설치 후 본인 DM `/help`, 퀴즈 숫자 답장·중복 답장·`/skip`, `/stats`, 일요일 복습, 08:00 뉴스로 수행합니다. 토큰을 제공하지 않은 개발 검증에서는 실제 Telegram 전송이나 Hermes 배포가 수행되지 않습니다.

분리 설정 후에는 학습 봇에 08:00 뉴스 일정이 실행되지 않는지, 뉴스 봇에 금융 퀴즈 일정이 없는지 확인합니다. 뉴스 봇 `/now`는 정시 밖에서도 뉴스를 준비하고 같은 메시지 재수신 시 중복 전송하지 않아야 합니다. 증권사·보험사 모드에서는 사건·배경·영향의 근거와 공개 부분 본문 안내, 전문용어·구문의 실제 원문 포함 여부를 확인합니다. 기사 메시지에 `/word`로 단어와 구문을 각각 답장해 같은 기사·원문 문장·문맥별 뜻이 저장되는지, `/vocab 5`의 `1`~`4` 답이 단어 DB만 바꾸는지, 재시작 후 미답 문항과 중복 채점 방지가 유지되는지 확인합니다. 위키 페이지는 private이며 복습 시각·Telegram ID를 포함하지 않아야 합니다. 모델이 미설정인 뉴스 봇은 `/now`에도 준비 불가 안내를 보내는 것이 정상입니다.

| 증상 | 확인할 항목 |
| --- | --- |
| DM에 답이 없음 | gateway 실행, `hermes plugins list`의 활성화·로딩 상태, 한 개 숫자 allowlist, 개인 DM, 패키지 준비 상태 |
| 예약 작업이 조용함 | KST 시간대, 30분 유예, 이미 확보된 `job_runs`, gateway·PC 상태 |
| `FinDone job failed` | 절대 콘텐츠 경로, manifest 검증, 저장소 밖 상태 경로, 슬롯 기록 |
| 뉴스가 비어 있거나 오류 | 선택한 모드의 RSS·공개 원문 연결, 주제 적합성과 새 기사 여부; 제한된 기사나 검증 실패 기사는 제외 |
| `/word`가 기사를 찾지 못함 | 해당 뉴스 봇이 발송한 기사 메시지에 직접 답장했는지, 기사 보관 DB의 메시지 ID 연결이 있는지 확인 |
| 단어 복습 문제가 없음 | 저장 단어와 근거 있는 서로 다른 오답 선택지 3개가 준비됐는지 확인 |
| 전문용어·구문이 적거나 없음 | 원문에 출처가 있는 목록의 표현과 완전한 예문이 실제 있는지 확인; 일반 C1 단어로 자동 보충하지 않음 |
| `general` 모드 자동 어휘가 없음 | Oxford 목록 캐시 경로·B2/C1 기준·원문 표제어 포함 여부 확인; 수동 `/word`는 난도 필터를 적용하지 않음 |
| 위키 반영 실패 | [개인 단어 위키 안내](WIKI_INTEGRATION.md)의 CLI·vault 경로·private 상태 확인; SQLite 저장은 유지 |
| 해설 모델 오류 | 기본 스냅샷 해설 사용; 로컬 모델 주소·이름 확인 |
| 전송 중 프로세스 종료 | Telegram 실제 수신과 `job_runs` 확인; 자동 재전송하지 않음 |

개인 기록을 지우려면 gateway와 cron을 멈추고 원하는 기능의 외부 DB와 그 SQLite `-wal`·`-shm` 파일을 운영자가 삭제합니다. `STATE_DB_PATH`는 해당 봇의 기존 기록, `FINDONE_VOCAB_DB_PATH`는 단어·복습 기록, `FINDONE_NEWS_ARCHIVE_PATH`는 기사·발송 연결입니다. 기사 보관 DB를 지우면 과거 기사 메시지에서 `/word` 연결도 사라집니다. 삭제 후 다음 실행에서 빈 기록을 시작하며 콘텐츠 DB·단어 목록 캐시·개인 위키는 별도로 관리합니다.

Hermes API 확인 기준: 2026-10-03 공식 문서·현재 upstream 소스. 전송 어댑터 호출은 [BasePlatformAdapter의 async `send`](https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/base.py), 입력은 [MessageEvent](https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/event.py)의 정규화된 필드를 사용합니다. Hermes 업그레이드 후 plugin 로딩·hook 반환·cron interpreter 계약을 다시 확인하세요.
