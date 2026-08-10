# FinDone 개인 릴리스 체크리스트

이 문서는 FinDone을 **본인 Android 기기에만** 설치하는 개인 서명 APK의 준비·빌드·검증 절차입니다. OneDrive는 APK와 사용자가 명시적으로 만든 백업 파일을 옮기는 수단일 뿐, 앱의 서버나 자동 동기화 계층이 아닙니다. 앱에는 OneDrive API·로그인·동기화나 인앱 업데이트 기능이 없습니다. 휴대폰의 OneDrive에서 최신 `.apk`를 직접 열어 Android 시스템 설치 화면으로 업데이트합니다.

> 개인 설치가 가능한 기술 빌드와 전체 명세 완료는 서로 다른 상태입니다. 1,461개 이상의 authored/approved claim과 독립 solver를 포함한 전체 10,000-seed 검증이 끝나기 전에는 산출물을 “전체 콘텐츠 완성판”으로 표시하지 않습니다.

## 1. 릴리스 종류 결정

- [ ] 새 설치 시험인지, 기존 앱 위에 올리는 upgrade인지 기록했다.
- [ ] upgrade라면 `applicationId=com.findone.app`를 유지하고 이전 APK와 **동일한 키**를 사용한다.
- [ ] upgrade라면 새 `versionCode`가 설치된 버전보다 높은지 확인했다.
- [ ] 실제 사용자 데이터가 있는 폰에서는 clean install 시험을 하지 않는다. clean install은 별도 기기/프로필에서 하거나 먼저 검증된 수동 백업을 만든다.
- [ ] 현재 콘텐츠 상태가 기준선인지, 명세 완료판인지 릴리스 메모에 사실대로 표시했다.

## 2. 서명 키 최초 준비

키 저장소는 저장소 디렉터리, OneDrive 등 동기화 폴더, APK 산출물 폴더 밖에 만듭니다. JDK의 `keytool`을 대화형으로 실행하면 비밀번호가 명령 기록에 남지 않습니다.

```powershell
$keystorePath = Read-Host '저장소와 OneDrive 밖 키 파일의 절대 경로'
if (-not [System.IO.Path]::IsPathRooted($keystorePath)) { throw '절대 경로가 필요합니다.' }
keytool -genkeypair -v -keystore $keystorePath -storetype JKS -alias findone-release -keyalg RSA -keysize 4096 -validity 9125
```

- [ ] 키 저장소와 개인 키 비밀번호를 길고 고유하게 정하고, 소스 파일·스크립트·`gradle.properties`·`local.properties`에 적지 않았다.
- [ ] 키 저장소를 서로 다른 암호화된 오프라인 매체 두 곳에 백업했다.
- [ ] 복사본에서 `keytool -list -v -keystore <경로> -alias findone-release`가 성공하는지 시험했다.
- [ ] 인증서 SHA-256 fingerprint만 릴리스 기록에 보존했다. 비밀번호와 private key는 기록에 넣지 않았다.
- [ ] `git status --short`에서 키 파일과 비밀 파일이 보이지 않는다.
- [ ] 아래 명령의 결과가 비어 있다.

```powershell
git ls-files -- '*.jks' '*.keystore' '*.apk' '*.aab' '*.idsig'
```

`.gitignore`는 보조 장치일 뿐입니다. 실수로 이미 추적된 비밀은 ignore 규칙만으로 보호되지 않습니다. 비밀이 한 번이라도 커밋되었다면 파일 삭제만 하지 말고 키를 폐기·재발급한 뒤 저장소 이력 노출도 별도로 처리해야 합니다.

## 3. 빌드 전 확인

- [ ] JDK 17과 Android SDK API 35 및 Build Tools가 설치되어 있다.
- [ ] 추적되지 않는 `local.properties`에 올바른 `sdk.dir`이 있다.
- [ ] 의도하지 않은 작업 트리 변경이 없는지 `git status --short`와 `git diff --check`로 확인했다.
- [ ] `app/build.gradle.kts`의 `versionName`과 `versionCode`를 기록했다.
- [ ] `app/src/main/AndroidManifest.xml`에 `android.permission.INTERNET`가 없고, 자동 백업과 cleartext 통신이 비활성화되어 있다.
- [ ] `app/src/main/assets/content-manifest.json`의 7개 분야, 135개 요소, 분야별 수량, DB SHA-256과 byte size를 확인했다.
- [ ] 원본 명세가 바뀐 경우에만 `python .\tools\build_content_db.py`를 실행하고 생성된 DB와 manifest 변경을 검토했다.
- [ ] 디버그 검증이 성공했다.

```powershell
.\gradlew.bat test lintDebug assembleDebug --console=plain
```

다음 콘텐츠 게이트는 “통과 증거가 있을 때만” 체크합니다.

- [ ] 일반 요소 53개 × 최소 9개와 `EQV`·`IBT` 82개 × 최소 12개, 총 1,461개 이상의 claim이 작성·출처 연결·승인되었다.
- [ ] claim scope, blueprint, 오개념 규칙, citation coverage와 deterministic signature 조건을 검증했다.
- [ ] 전체 10,000-seed를 독립 solver와 독립 암산 audit로 검증했고 실패가 0이다.
- [ ] 같은 version/seed의 byte-identical snapshot 재현성을 회귀 테스트로 확인했다.

하나라도 미완료라면 개인 테스트 빌드는 가능하지만, 릴리스 메모에 **명세 구현 중 기준선**이라고 표시합니다.

## 4. 개인 서명 릴리스 빌드

비밀번호는 명령행 문자열, `setx`, 설정 파일에 넣지 않습니다. 아래 수동 호환 방식은 현재 PowerShell 프로세스에만 평문 환경 변수를 만들지만, 릴리스 스크립트가 이를 즉시 `SecureString`으로 가져온 뒤 Gradle·플러그인·테스트를 실행하기 전에 제거합니다. 비밀번호는 unsigned APK 빌드가 모두 끝난 뒤 로컬 SDK `apksigner` 프로세스에만 다시 전달되고 즉시 제거됩니다.

이 절차는 OS sandbox가 아닙니다. 같은 Windows 사용자 권한으로 실행되는 악성 코드는 DPAPI 암호문, keystore, 프로세스 또는 SDK 도구에 접근할 수 있습니다. 본인이 변경 내용을 검토하고 신뢰한 commit에서만 훅을 사용하며, 더 강한 격리가 필요하면 별도 Windows 계정이나 VM에서 릴리스합니다.

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

[scripts/build_private_release.ps1](../scripts/build_private_release.ps1)는 비밀번호가 없는 환경에서 `clean test lintRelease assembleRelease`를 실행하고, SDK `zipalign`과 `apksigner`로 외부 서명한 뒤 서명·정렬을 재검증합니다. 그 다음 새 `dist/findone-<version>-<timestamp>/`에 APK·외부 release manifest·checksum을 만듭니다.

- [ ] 스크립트가 오류 없이 종료되었다.
- [ ] 비밀번호 환경 변수가 제거되었는지 확인했다.

```powershell
Get-ChildItem Env:FINDONE_* -ErrorAction SilentlyContinue
```

- [ ] 위 명령에 비밀번호, 키 경로, alias가 남지 않았다.

## 5. PC에서 산출물 검증

가장 최근 폴더를 자동 선택할 때는 경로와 version을 화면에서 다시 확인합니다.

```powershell
$releaseDir = Get-ChildItem .\dist -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$releaseApks = @(Get-ChildItem $releaseDir.FullName -Filter 'FinDone-*.apk')
if ($releaseApks.Count -ne 1) { throw '릴리스 APK가 정확히 하나여야 합니다.' }
$releaseApk = $releaseApks[0]
$actualApkSha = (Get-FileHash -Algorithm SHA256 $releaseApk.FullName).Hash.ToLowerInvariant()
$expectedApkSha = ((Get-Content (Join-Path $releaseDir.FullName 'SHA256SUMS.txt')) -split '\s+')[0].ToLowerInvariant()
if ($actualApkSha -ne $expectedApkSha) { throw 'APK SHA-256 불일치' }
Get-Content -Raw -Encoding UTF8 (Join-Path $releaseDir.FullName 'release-manifest.json') | ConvertFrom-Json | Format-List
```

- [ ] 폴더에 서명 APK, `release-manifest.json`, `SHA256SUMS.txt`만 있다.
- [ ] APK의 실제 SHA-256이 checksum 및 release manifest와 일치한다.
- [ ] Android SDK의 `apksigner verify --verbose --print-certs`를 다시 실행해 APK 검증이 성공한다.
- [ ] 인증서 SHA-256 fingerprint가 최초에 별도 기록한 개인 키 fingerprint와 일치한다.
- [ ] release manifest의 application ID, version, content DB version/hash, user DB schema version이 빌드 입력과 일치하며 필수 값이 빈 문자열이나 `null`이 아니다.
- [ ] release manifest에 `targetUser=self_only`, `publicStoreRelease=false`, `internetPermission=false`, `oneDriveRuntimeSync=false`, `directOneDriveApi=false`가 기록되어 있다.
- [ ] Android Studio의 APK Analyzer 또는 SDK의 `apkanalyzer manifest permissions <APK>`로 확인했을 때 `android.permission.INTERNET`가 없다.
- [ ] APK 안에 키 저장소, private key, 비밀번호, 복구 문구, API key, 사용자 백업이 포함되지 않았다.

어느 값이든 다르거나 비어 있으면 OneDrive에 올리지 말고 빌드 입력이나 자동화 문제를 먼저 해결합니다.

## 6. OneDrive로 수동 전송

- [ ] 개인 OneDrive의 접근 권한과 계정 2단계 인증 상태를 확인했다.
- [ ] 서명 APK, 외부 release manifest, checksum만 릴리스 폴더에 올렸다.
- [ ] 키 저장소, private key, 비밀번호, 저장소 전체, `local.properties`, 사용자 백업을 릴리스 폴더에 넣지 않았다.
- [ ] 사용자 백업이 필요하면 릴리스 산출물과 구분된 개인 폴더에 사용자가 명시적으로 올렸다.
- [ ] 동기화가 끝난 파일의 이름과 크기를 PC 원본과 비교했다. 가능한 경우 내려받은 복사본의 SHA-256도 다시 확인했다.

## 7. Android clean install 및 오프라인 smoke test

기존 데이터가 필요한 폰에서는 앱을 제거하거나 “데이터 삭제”를 누르지 않습니다. clean install은 백업을 검증한 뒤 별도 기기나 프로필에서 수행합니다.

- [ ] 설치 파일의 출처가 본인 OneDrive이고 APK 이름·version·SHA-256이 릴리스 기록과 일치한다.
- [ ] APK를 연 OneDrive 또는 파일 관리자 앱에 “이 출처의 앱 설치 허용”을 잠시 켜고 시스템 설치 화면에서 설치한 뒤 바로 다시 껐다.
- [ ] 첫 실행 전에 비행기 모드를 켰고, 비행기 모드에서 별도로 다시 켤 수 있는 Wi-Fi도 껐다.
- [ ] 앱이 네트워크 오류나 로그인 요구 없이 시작된다.
- [ ] 7개 분야와 총 135개 요소가 보이고 각 분야 수량이 manifest와 일치한다.
- [ ] 여러 한글 검색어와 요소 ID 검색에서 FTS 결과가 나오며, 결과 상세를 열 수 있다.
- [ ] 개념 문항을 생성·제출하고 정답 및 5단계 해설을 확인했다.
- [ ] 계산 템플릿이 있는 요소에서 난이도별 정수답 암산 문항을 풀고 단위·채점·해설·audit 표시를 확인했다.
- [ ] 의도적으로 틀린 답을 제출해 오답 이력과 미해결 오답 큐가 갱신되는지 확인했다.
- [ ] 문항을 북마크하고 앱을 완전히 종료·재실행한 뒤 동일 snapshot이 남는지 확인했다.
- [ ] 진도·정답률·설정이 재실행 후 유지된다.
- [ ] 학습 본문 구절에 형광펜·밑줄·코멘트를 만들고, 앱 재실행 후 같은 위치에 다시 표시된다.
- [ ] 용어집의 대단원 전환, 학습 완료 체크, 별 북마크와 북마크 전용 보기가 동작한다.
- [ ] 수동 백업 export와 import가 비행기 모드에서 동작하고 무결성 오류가 없는지 확인했다.
- [ ] `adb shell dumpsys package com.findone.app` 출력에도 `android.permission.INTERNET`가 없다.
- [ ] crash, ANR, 데이터 유실이 없고 기기 모델·Android version·시험 일시를 기록했다.

## 8. 동일 서명 upgrade 시험

- [ ] 기존 버전에서 확인용 오답, 문제 북마크, 설정, snapshot, 개인 메모, 본문 주석과 용어 상태를 만들고 개수를 기록했다.
- [ ] 앱 안에서 수동 사용자 백업을 export하고 앱 전용 저장소 밖에 복사했다.
- [ ] 백업 파일의 SHA-256과 생성 시각을 별도로 기록했다.
- [ ] 더 높은 `versionCode`를 동일한 key alias와 키 저장소로 서명했다.
- [ ] 새 APK의 인증서 fingerprint가 기존 릴리스와 같은지 확인했다.
- [ ] 기존 앱을 제거하거나 데이터를 지우지 않고 새 APK를 설치했다. ADB를 쓸 경우 `adb install -r <APK>`를 사용한다.
- [ ] 시작 후 오답, 북마크, 설정, 진도, 저장된 snapshot, 개인 메모, 본문 주석, 용어 상태와 통계가 그대로 남아 있다.
- [ ] 새 콘텐츠 DB version과 검색 결과는 의도한 버전으로 바뀌었다.
- [ ] 비행기 모드 smoke test를 다시 통과했다.

서명이 다르거나 `versionCode`가 낮으면 기존 앱 위에 설치되지 않는 것이 정상입니다. 이 경우 기존 앱을 삭제해서 우회하지 말고 올바른 키와 version을 사용해 다시 빌드합니다.

## 9. 사용자 백업·복원 안전 확인

- [ ] Android 자동 백업은 비활성화되어 있으며, 앱 삭제·데이터 삭제가 `user.sqlite3`를 제거한다는 점을 이해했다.
- [ ] 앱 삭제나 기기 교체 전에 항상 앱의 명시적 export 기능으로 백업했다.
- [ ] export 파일을 앱 전용 저장소 밖으로 복사하고 SHA-256을 기록했다.
- [ ] import는 현재 사용자 데이터를 교체하므로, 복원 시험 전에 현재 상태도 별도로 export했다.
- [ ] 복원 후 시도 수, 오답, 북마크, 설정, 진도, snapshot, 개인 메모, 본문 주석과 용어 상태를 표본 대조했다.
- [ ] 백업 JSON의 SHA-256 envelope는 우발적 손상 감지용이며 암호화나 제3자 변조 방지 서명이 아님을 이해했다.
- [ ] 백업 파일에 학습 이력이 평문으로 들어갈 수 있으므로 접근이 통제된 위치에 보관하고 불필요한 복사본을 정리했다.

서명 키 백업과 사용자 데이터 백업은 서로 대체할 수 없습니다. 전자는 upgrade 권한을, 후자는 학습 기록을 복원합니다.

## 10. 릴리스 기록

비밀을 제외한 다음 값만 개인 릴리스 기록에 남깁니다.

```text
versionName / versionCode:
Git commit:
content DB version / SHA-256:
release APK SHA-256:
signing certificate SHA-256:
build test / lint 결과:
기기 모델 / Android version:
clean install 또는 upgrade 결과:
비행기 모드 smoke 결과:
사용자 백업 export/import 결과:
미완료 명세 게이트:
```

- [ ] 기록에 키 저장소, private key, 비밀번호, 복구 문구, API key가 없다.
- [ ] 개인 설치가 끝난 뒤 “이 출처의 앱 설치 허용”을 껐다.
- [ ] 재현에 필요한 APK·manifest·checksum은 보관하되, 비밀과 사용자 백업은 각각 분리된 보호 위치에 보관했다.
