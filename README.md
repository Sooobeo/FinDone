# FinDone

FinDone은 회계·기업재무·투자·채권·파생상품·주식 리서치·IB 실무의 핵심 개념과 문제를 익혀 **금융권 진출을 준비하는 개인용 오프라인 Android 앱**입니다. 서버, 로그인, 광고, 분석 SDK 없이 동작하며, 서명한 APK를 개인 OneDrive로 옮겨 본인 Android 기기에만 사이드로드하는 것을 전제로 합니다.

> 현재 저장소는 명세를 구현 중인 기준선입니다. 7개 분야와 135개 학습요소를 담은 앱 기반은 구현되어 있지만, 명세가 요구하는 1,461개 이상의 승인 claim과 전체 10,000-seed 검증은 아직 완료 조건으로 남아 있습니다. 현재 상태를 “최종 콘텐츠 완성” 또는 “전체 명세 통과”로 간주하면 안 됩니다.

## 현재 구현된 기준선

- **7개 분야, 135개 학습요소:** `ACC` 12개, `CF` 12개, `INV` 9개, `FI` 10개, `DER` 10개, `EQV` 64개, `IBT` 18개를 읽기 전용 SQLite 콘텐츠 DB에 포함합니다.
- **콘텐츠 무결성 확인:** APK에 들어 있는 DB를 설치할 때 파일 크기와 SHA-256, schema version, 테이블별 row count, 분야별 요소 수, SQLite integrity와 foreign key를 검사합니다.
- **로컬 검색:** 135개 요소를 SQLite FTS5/BM25로 검색하고, 검색어를 FTS 질의로 만들 수 없는 경우 `LIKE` 검색으로 보완합니다.
- **상세 개념학습:** 모든 요소를 정의·직관·핵심 공식·가정·응용 범위·학습 체크리스트의 Markdown 카드로 구성하고, 요소별 복수 원문 링크를 외부 브라우저로 연결합니다.
- **결정론적 개념 퀴즈:** 요소의 제목과 핵심 관계를 사용해 4지선다 문항을 조립합니다. 동일한 요소·난이도·seed·renderer version은 동일한 snapshot을 만듭니다.
- **결정론적 계산 퀴즈:** 현재 36개 학습요소에 정수답 계산 템플릿이 연결되어 있습니다. 생성 과정은 정수 중간값과 난이도별 연산 한도를 검사하고, 개념·수식·대입·정답·해석을 snapshot에 보존합니다.
- **용량 제한 사용자 DB:** 누적 성적은 요소별 집계로 보존하고, 용량이 큰 상세 시도는 요소당 최근 20개·전체 2,000개로 제한합니다. 미해결 최신 오답과 수동 북마크는 자동 정리 대상에서 제외하며, 수동 JSON 백업에는 SHA-256 무결성 값이 포함됩니다.
- **엄격한 오프라인 기본값:** Manifest에 `android.permission.INTERNET`가 없고 cleartext 통신과 Android 자동 백업도 비활성화되어 있습니다. OneDrive SDK나 런타임 동기화 기능은 앱에 넣지 않습니다.
- **FinDone 브랜드:** 앱 이름, 아이콘, Compose 색상·타이포그래피와 별도의 로고·컬러 토큰이 포함되어 있습니다. 브랜드 자산과 사용 규칙은 [brand/README.md](brand/README.md)를 참고하세요.

위 항목은 코드와 데이터 계층의 현재 기준선입니다. Compose 화면 연결과 로컬 단위 테스트·Lint·debug/release 빌드는 확인했지만, 실제 Android 기기의 비행기 모드·백업 복원·동일 서명 업데이트 검증은 아직 남아 있습니다.

## 아직 남아 있는 명세 완료 조건

현재 `content.sqlite3`의 135개 상세 concept/formula card는 요소별 학습 설명을 제공하지만, 아래의 검수된 claim corpus를 대신하지 않습니다.

- 일반 요소 53개에 각 9개 이상, `EQV`·`IBT` 요소 82개에 각 12개 이상인 **총 1,461개 이상의 claim**을 실제로 작성하고 출처 위치와 연결한 뒤 사람의 승인을 받아야 합니다.
- 승인 claim, scope manifest, blueprint, 오개념 규칙과 citation을 사용하는 최종 개념문제 renderer를 완성하고 unsupported claim 및 scope leak가 없음을 입증해야 합니다. 현재 개념 퀴즈는 요소 제목·핵심 관계 기반의 결정론적 기준선입니다.
- 각 요소의 검증된 deterministic signature 최소 18개, 전체 2,430개 이상과 정답 유일성·오답 유효성·citation coverage 조건을 검증해야 합니다.
- 계산 문제를 독립 solver와 독립 암산 audit로 대조하는 **전체 10,000-seed 생성 검증**을 완료해야 합니다. 현재 renderer 내부 audit가 있다는 사실만으로 이 게이트를 통과한 것은 아닙니다.
- 같은 version과 seed의 byte-identical 재현성, 비행기 모드에서의 검색·퀴즈·채점·해설·오답·북마크·백업, 동일 서명 upgrade 후 사용자 데이터 유지까지 실제 기기에서 확인해야 합니다.

전체 기준은 [finance_interview_app_final_spec.md](finance_interview_app_final_spec.md)의 출시 체크리스트가 최종 기준입니다.

## 저장 구조

```text
APK
├─ content.sqlite3       7개 분야·135개 요소의 읽기 전용 콘텐츠
├─ content-manifest.json
└─ Android 앱 코드      검색·결정론적 퀴즈·로컬 저장

앱 전용 저장소
└─ user.sqlite3          시도·오답·북마크·진도·설정

사용자 명시적 작업
└─ 수동 백업 파일        필요할 때만 export/import 및 OneDrive 전송
```

콘텐츠 DB와 사용자 DB는 역할이 다릅니다. 앱을 업데이트할 때 콘텐츠 자산은 교체될 수 있지만, 동일한 application ID와 동일한 서명 키로 더 높은 `versionCode`를 설치하면 사용자 DB는 유지되어야 합니다. 사용자 DB schema 3으로 올리기 전에는 검증된 N-1 복사본을 남기며, schema 1·2 백업은 순서대로 schema 3 형식으로 변환해 가져옵니다. 앱 삭제나 데이터 삭제 전에는 별도의 수동 백업도 반드시 만드세요. 백업은 일관된 DB snapshot으로 만들며, 앱이 다시 읽을 수 없는 파일을 만들지 않도록 export와 import 모두 25MB로 제한합니다.

## 개발 환경과 콘텐츠 DB

기본 요구 사항은 JDK 17과 Android SDK API 35입니다. Windows에서는 저장소 루트에서 다음 명령을 실행합니다.

```powershell
.\gradlew.bat test lintDebug assembleDebug --console=plain
```

macOS 또는 Linux에서는 `.\gradlew.bat` 대신 `./gradlew`을 사용합니다. 디버그 APK는 다음 위치에 생성됩니다.

```text
app/build/outputs/apk/debug/app-debug.apk
```

원본 명세를 변경한 경우에만 콘텐츠 자산을 다시 생성합니다.

```powershell
python .\tools\build_content_db.py
```

생성기는 분야/요소 수와 ID 연속성, FTS row, 참조 무결성을 확인하고 `app/src/main/assets/content.sqlite3`와 `content-manifest.json`을 갱신합니다. 생성 결과가 있다는 것과 1,461개 claim 승인 게이트를 통과했다는 것은 별개입니다.

## 개인 서명 릴리스와 OneDrive 설치

장기간 같은 앱 위에 업데이트하려면 매번 같은 개인 릴리스 키를 사용해야 합니다. 키 저장소와 비밀번호는 저장소 및 OneDrive 밖의 암호화된 오프라인 위치에 보관하세요. 키를 잃으면 기존 앱 위에 동일 서명 업데이트를 설치할 수 없습니다.

반복 가능한 개인 릴리스는 [scripts/build_private_release.ps1](scripts/build_private_release.ps1)로 만듭니다. 비밀번호를 명령행 인자나 파일에 쓰지 않고 현재 PowerShell 프로세스의 환경 변수에만 잠시 넣는 예시는 다음과 같습니다.

```powershell
$storeSecret = Read-Host '키 저장소 비밀번호' -AsSecureString
$keySecret = Read-Host '개인 키 비밀번호' -AsSecureString
$env:FINDONE_STORE_PASSWORD = [System.Net.NetworkCredential]::new('', $storeSecret).Password
$env:FINDONE_KEY_PASSWORD = [System.Net.NetworkCredential]::new('', $keySecret).Password
$keystorePath = Read-Host '저장소 밖 키 저장소의 절대 경로'

try {
    .\scripts\build_private_release.ps1 -KeystorePath $keystorePath -KeyAlias 'findone-release'
} finally {
    Remove-Item Env:FINDONE_STORE_PASSWORD, Env:FINDONE_KEY_PASSWORD -ErrorAction SilentlyContinue
    Remove-Variable storeSecret, keySecret -ErrorAction SilentlyContinue
}
```

스크립트는 `clean test lintRelease assembleRelease`, APK 서명 확인, APK SHA-256 계산을 수행하고 `dist/findone-<version>-<timestamp>/`에 다음 파일을 만듭니다.

- 서명된 `FinDone-<version>.apk`
- 외부 `release-manifest.json`
- `SHA256SUMS.txt`

이 세 산출물만 개인 OneDrive로 수동 전송합니다. 앱은 OneDrive에 로그인하거나 자동 동기화하지 않습니다. 설치 전 체크섬·서명·권한을 확인하고, Android의 “이 출처의 앱 설치 허용”은 설치할 때만 켰다가 다시 끄세요.

키 준비부터 오프라인 기기 시험, upgrade와 사용자 백업 복원까지의 상세 절차는 [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)를 따르세요.

## 개인정보와 용도

학습 기록은 기본적으로 기기 내부에만 있습니다. 수동 export 파일은 암호화 파일이 아니므로 개인 OneDrive에 둘 경우 계정 보호와 파일 접근 권한을 직접 관리해야 합니다. 앱 삭제 또는 데이터 삭제 시 로컬 기록은 함께 사라집니다.

FinDone의 콘텐츠와 계산 결과는 금융권 진출 학습용 일반 정보이며 금융·투자 자문이 아닙니다.
