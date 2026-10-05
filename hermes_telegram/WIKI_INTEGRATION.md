# 개인 단어·구문 위키

저장한 뉴스 단어·비즈니스 구문의 **문맥별 뜻·정확한 원문 전체 문장·기사 제목·출처·발행일·URL·사용 설명**을 [Oh My Wiki](https://github.com/dandacompany/oh-my-wiki)의 개인 Markdown vault에 보관합니다. 같은 표현이라도 기사 URL이나 문맥별 의미가 다르면 별도 단어 UUID를 쓰며 페이지도 구분합니다. Telegram ID, 정오답, 연속 정답 수, 다음 복습 시각은 별도 단어 SQLite에만 남깁니다. OMW의 `review` 기능은 사용하지 않습니다.

`wiki.py`는 공식 `omw page write`와 `omw visibility set … private`를 호출합니다. 페이지 작성과 색인은 OMW가 수행하며 내부 Python 모듈이나 registry DB를 직접 호출·수정하지 않습니다. 기존 사용자 페이지를 덮어쓰지 않습니다. 단어 저장과 위키 반영은 분리되어 위키 CLI 장애가 단어 저장을 취소하지 않습니다. 저장 후 outbox를 재처리하면 같은 UUID·출처 스냅샷의 페이지를 추가로 만들지 않고 private 설정과 색인을 복구합니다.

## 기사에서 저장하기

뉴스 프로필의 `FINDONE_NEWS_FOCUS=securities_insurance` 모드는 CNBC·Bloomberg의 공개 기사에서 사건·배경·사업 영향을 영·한으로 요약하고 금융·보험 전문용어와 중요한 비즈니스 구문을 제시합니다. 전문성에 임의의 CEFR 등급을 붙이지 않습니다. 요약 모델은 현재 공개 기사로 품질과 속도를 비교해 선정 중이며 위키 연결에는 특정 모델 이름을 설정하지 않습니다.

Telegram에서 **저장할 기사 메시지에 직접 답장**으로 다음처럼 보냅니다. 구문을 따옴표로 감쌀 필요는 없습니다.

```text
/word combined ratio
/word institutional liquidity
/word back on track
```

각 표현이 해당 기사 원문에 있어야 합니다. 뉴스에서 제시한 표현은 발송한 문맥별 뜻과 그 표현이 등장한 원문 전체 문장을 함께 보존합니다. 같은 표현이 다른 의미로 등장하는 앞선 문장이나 모델이 만든 예문으로 바꾸지 않습니다. 새로운 표현은 원문 문맥에서 뜻을 확인한 뒤 저장합니다. 뉴스 봇이 실제 발송한 메시지 ID와 기사 스냅샷을 대조하므로 연결 없는 최근 기사나 입력한 인용문으로 출처를 대신하지 않습니다.

위키의 기사 예문은 확보한 공개본문의 정확한 문장입니다. 구문의 사용 설명은 승인된 사전 뜻에서 구성한 내용을 저장합니다. 공개 부분 본문을 사용한 기사는 뉴스 메시지에 그 범위를 표시하며 제한된 전문에서 문장을 가져오지 않습니다. 같은 표현·기사·의미를 재저장해도 처음 저장한 뜻·문장·출처를 덮어쓰지 않습니다. `/words`는 저장 수·현재 복습 대상 수를 보여주고 대기 중인 위키 반영도 다시 시도합니다. 위키 장애 중에도 단어·구문 저장과 별도 SQLite의 복습 기록은 유지됩니다.

## 설치와 설정

OMW 2.54.0은 Hermes PM 환경과 분리한 가상환경에 설치합니다. 다음 예시는 저장소 밖 개인 경로이며 비밀값을 포함하지 않습니다.

```powershell
$wikiInstallPath = Join-Path $env:LOCALAPPDATA "FinDone/oh-my-wiki"
python -m venv "$wikiInstallPath/venv"
& "$wikiInstallPath/venv/Scripts/python.exe" -m pip install "oh-my-wiki==2.54.0"
$env:OMW_HOME = "$wikiInstallPath/home"
$env:PYTHONIOENCODING = "utf-8"
$omwCli = "$wikiInstallPath/venv/Scripts/omw.exe"
& $omwCli status
& $omwCli vault create findone-news --mode wiki --type markdown --location "$env:LOCALAPPDATA/FinDone/hermes-news/wiki"
```

이미 만든 vault를 다시 생성하지 않습니다. 뉴스 프로필의 저장소 밖 `.env`에 네 값을 모두 지정합니다.

```dotenv
FINDONE_WIKI_CLI_PATH=C:/Users/Insun/AppData/Local/FinDone/oh-my-wiki/venv/Scripts/omw.exe
FINDONE_WIKI_HOME=C:/Users/Insun/AppData/Local/FinDone/oh-my-wiki/home
FINDONE_WIKI_VAULT=findone-news
FINDONE_WIKI_VAULT_PATH=C:/Users/Insun/AppData/Local/FinDone/hermes-news/wiki
```

지정 경로는 절대 경로이고 저장소 밖이어야 합니다. OMW의 등록 vault 경로가 설정 경로와 다르거나 기존 페이지가 다른 출처의 내용이면 반영을 중단합니다. CLI 실행 환경에는 Telegram 토큰·모델 키·OMW 서버 토큰을 전달하지 않습니다.

## Hermes에서 검색

공식 OMW 스킬과 `omw` 별칭 스킬은 뉴스 Hermes 프로필에 설치합니다. 실행 파일과 `OMW_HOME`을 명시한 `findone-news-wiki` 스킬로 단어의 뜻이나 문장을 찾습니다. 직접 확인할 때는 다음처럼 공식 CLI를 사용합니다.

```powershell
$env:OMW_HOME = "$env:LOCALAPPDATA/FinDone/oh-my-wiki/home"
$env:PYTHONIOENCODING = "utf-8"
& "$env:LOCALAPPDATA/FinDone/oh-my-wiki/venv/Scripts/omw.exe" find "capital headroom" --vault findone-news --json
```

개인 페이지를 검색하려고 `visibility: public`으로 바꾸지 않습니다. OMW `serve`는 public 페이지용이므로 이 연결에서는 사용하지 않습니다. 로컬 CLI 검색은 추가 모델 호출이나 유료 검색 제공자를 요구하지 않습니다. Hermes Telegram에서의 단어 저장·퀴즈는 FinDone 플러그인이 처리하며, 일반 에이전트의 위키 검색과 별도 경로입니다.

공식 계약: [CLI와 스킬](https://github.com/dandacompany/oh-my-wiki), [페이지 작성 절차](https://github.com/dandacompany/oh-my-wiki/blob/main/commands/distill.md), [개인 페이지와 조회 서버의 경계](https://github.com/dandacompany/oh-my-wiki/blob/main/references/messenger-api.md).
