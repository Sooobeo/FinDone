# 로컬 커밋별 릴리스 자동화

이 자동화는 Git 커밋이 끝난 직후 그 커밋의 **정확한 스냅샷**으로 개인 서명 APK를 만듭니다. 현재 작업 폴더의 미커밋 파일은 APK에 들어가지 않습니다. 공개 저장소에는 서명키나 비밀번호가 저장되지 않습니다.

## 동작 방식

1. `.githooks/post-commit`이 방금 생성된 40자리 커밋 SHA를 전달합니다.
2. `scripts/invoke_post_commit_release.ps1`이 임시 detached worktree에 그 SHA만 체크아웃합니다.
3. 현재 PC의 `local.properties`에서는 `sdk.dir` 한 줄만 임시 worktree로 복사합니다.
4. Windows DPAPI 암호문을 현재 Windows 사용자 권한의 `SecureString`으로 복호화합니다.
5. 서명 비밀번호가 전혀 없는 환경에서 정확한 커밋의 Gradle·플러그인·테스트를 실행해 unsigned APK를 만듭니다.
6. setup에서 SHA-256을 고정한 활성 clone의 로컬 래퍼가 SDK `zipalign`을 실행한 뒤, 비밀번호 환경 변수를 `apksigner` 실행 순간에만 만들고 즉시 제거합니다.
7. 서명, 정렬, APK checksum 및 권한을 다시 검증합니다.
8. 검증된 릴리스를 `dist/findone-*`에 원자적으로 게시하고 최신 두 개만 남깁니다.
9. 선택한 mirror가 있으면 완성된 폴더를 복사·재검증한 뒤 그곳도 최신 두 개만 남깁니다.

앱에는 업데이트 탐색이나 APK 설치 기능이 없으며 OneDrive API 호출·로그인·동기화 및 인터넷 권한도 사용하지 않습니다. 자동화는 검증된 릴리스 파일을 설정된 OneDrive mirror에 게시하는 역할만 합니다. 휴대폰에서는 OneDrive에서 최신 `.apk`를 직접 열어 Android 시스템 설치 화면으로 업데이트합니다.

훅은 동기식입니다. 따라서 `git commit` 명령은 릴리스 빌드가 끝날 때까지 수 분 걸릴 수 있습니다. 빌드가 실패해도 이미 만들어진 Git 커밋은 사라지지 않으며, 오류가 콘솔에 표시됩니다.

임시 worktree 정리는 `core.longpaths=true`로 실행합니다. Git metadata가 먼저 없어졌거나 Android 산출물 경로가 Windows 기본 길이를 넘겨 디렉터리가 남으면, 안전 검사를 다시 거친 worktree root를 같은 임시 볼륨의 짧은 이름으로 옮긴 뒤 정리합니다. junction·symlink·mount point는 재귀 삭제하지 않습니다. 이 정리는 best-effort이며, 정리 오류나 진단 메시지가 원래 build/state 결과를 덮어쓰지 않습니다.

## 위협 모델과 한계

이 자동화는 비밀번호가 Gradle 환경에 우연히 노출되는 시간을 줄이고, setup 당시 검토한 builder SHA-256과 공개 인증서 pin을 확인합니다. 그러나 별도 계정이나 VM 같은 OS 보안 경계는 아닙니다. 같은 Windows 사용자 권한으로 실행되는 악성 코드는 DPAPI 암호문을 복호화하거나 keystore·SDK 도구·프로세스 메모리에 접근할 수 있습니다.

따라서 본인이 변경 내용을 검토하고 신뢰한 commit에만 post-commit 훅을 사용해야 합니다. 출처를 신뢰할 수 없는 branch나 commit을 시험할 때는 먼저 훅을 해제합니다. 더 강한 공격자 격리, 별도 릴리스 계정/VM과 독립적인 전체 APK bundle validator는 이 개인 프로젝트 자동화의 범위를 벗어납니다.

## 자동 버전

일반 수동 Gradle 빌드는 `app/build.gradle.kts`의 `declaredVersionCode`와 `declaredVersionName`을 그대로 사용합니다.

커밋 훅 빌드는 다음 값을 일시적인 Gradle project property로 전달합니다.

- `versionCode`: 선언된 기본값 + 1, 마지막 로컬 할당값 + 1, 로컬/mirror의 검증된 기존 릴리스 최고값 + 1 중 가장 큰 값
- `versionName`: `<declaredVersionName>+g<커밋 SHA 앞 10자리>`

할당 상태는 `.git/findone-release/state.json`에만 저장됩니다. 빌드가 실패해도 이미 할당한 번호는 재사용하지 않아, 이후 성공한 APK의 `versionCode`가 항상 증가합니다. 실제 manifest에는 소스 정규식 값이 아니라 완성된 APK를 `aapt dump badging`으로 읽은 `versionCode`와 `versionName`이 기록됩니다.

사용자 DB schema 버전은 정확한 커밋의 `UserRepository.kt`에 선언된 `USER_DB_VERSION`에서 추출하며, 현재 값은 5입니다. 값을 찾지 못하면 잘못된 manifest를 만들지 않고 릴리스를 중단합니다.

현재 선언값과 기존 릴리스가 각각 2라면 첫 자동 릴리스는 3, 다음은 4가 됩니다. 자동 APK를 설치한 뒤 더 작은 선언 기본값의 수동 APK로 덮어쓸 수는 없으므로 휴대폰 배포본은 자동 릴리스를 사용하고, 선언 기본값은 개발 빌드용으로 유지합니다. 새 clone에서도 기존 번호를 이어가려면 검증된 `dist` 또는 설정된 mirror를 보존해야 합니다.

## 최초 설정

설정은 자동으로 실행되지 않습니다. 먼저 이 자동화 파일들을 커밋한 다음 사용자가 명시적으로 한 번 실행해야 합니다.

선택적인 OneDrive mirror는 오래된 저장소와 분리된 빈 폴더를 권장합니다.

```powershell
New-Item -ItemType Directory -Path 'C:\Users\Insun\OneDrive\FinDone-Releases'
```

그 다음 실제 저장소 밖 keystore 경로를 지정합니다. 비밀번호 두 개는 화면에 표시되지 않는 `SecureString` 입력으로 받습니다.

```powershell
.\scripts\setup_release_automation.ps1 `
  -KeystorePath 'C:\path\outside\the\repo\FinDoneSigning\findone-release.jks' `
  -KeyAlias 'findone-release' `
  -MirrorRoot 'C:\Users\Insun\OneDrive\FinDone-Releases'
```

mirror가 필요 없으면 `-MirrorRoot`를 생략합니다. 설정만 저장하고 훅은 아직 켜지 않으려면 `-SkipHookActivation`을 추가합니다.

설정 스크립트는 저장 전에 PATH의 JDK `keytool -certreq`를 실행해 keystore 비밀번호, private-key 비밀번호와 alias가 실제로 함께 동작하는지 검증합니다. 이어서 signing certificate DER의 SHA-256이 [tracked 공개 pin](../config/release-signing-certificate.sha256) 및 최신 검증 가능 릴리스 기록과 일치하는지 확인합니다. 비밀번호는 keytool의 `-storepass:env`·`-keypass:env` modifier로만 전달되어 명령줄에 나타나지 않으며, 임시 CSR·인증서·환경 변수는 즉시 제거됩니다. 검증 실패 또는 keytool 부재 시 설정 파일과 훅을 만들거나 활성화하지 않습니다.

설정 파일은 이 clone의 `.git/findone-release/credentials.json`에 저장됩니다. 비밀번호 필드는 별도 key를 코드나 파일에 저장하지 않는 Windows DPAPI current-user ciphertext입니다. 다른 Windows 계정이나 다른 PC에서는 복호화되지 않습니다. 설정에는 검증된 인증서 SHA-256과 setup 당시 `build_private_release.ps1` SHA-256도 함께 고정됩니다. builder가 바뀌면 DPAPI 복호화 전에 자동 빌드를 중단하므로 변경을 검토한 뒤 setup을 다시 실행해야 합니다. keystore 자체는 계속 저장소 밖에 보관해야 합니다.

## 보관 정책과 삭제 안전장치

자동화는 각 release root 바로 아래에서 다음 조건을 모두 만족하는 디렉터리만 오래된 릴리스로 삭제할 수 있습니다.

- 이름이 엄격한 `findone-<version>-<timestamp>[-<commit>]` 형식
- release root 자체가 drive root가 아니며, 일반 디렉터리 또는 Microsoft Cloud reparse point임
- release 디렉터리도 일반 디렉터리 또는 Microsoft Cloud reparse point임
- 바로 아래에 APK, `release-manifest.json`, `SHA256SUMS.txt` 세 파일만 존재
- application ID가 `com.findone.app`
- manifest와 checksum의 SHA-256이 실제 APK와 일치

OneDrive Files On-Demand가 root나 하위 폴더에 붙이는 Microsoft Cloud 계열 tag만 예외로 허용합니다. Windows API로 실제 reparse tag를 읽어 `(tag & 0xFFFF0FFF) == 0x9000001A`인지 검사하며, `LinkType`이 비어 있다는 이유만으로 허용하지 않습니다. symlink, junction, mount point와 그 밖의 알 수 없는 reparse tag는 계속 거부합니다.

그 밖의 파일과 폴더, 인식할 수 없는 `findone-*` 폴더는 보존합니다. 삭제 직전에 root와 candidate의 실제 parent·경로·reparse tag·bundle checksum을 다시 확인하며, 열거 이후 바뀐 항목은 삭제하지 않습니다. 새 릴리스가 완전히 빌드되고 검증된 뒤에만 로컬 retention을 수행합니다. mirror는 `.findone-release-root.json` 안전 marker가 있는 경우에만 복사하고, 복사가 완성된 뒤에만 mirror retention을 수행합니다.

보관 개수는 의도적으로 2로 고정되어 현재 릴리스와 직전 릴리스만 남습니다.

## 수동 실행과 해제

설정 후 현재 HEAD를 자동 방식으로 다시 빌드하려면 다음처럼 실행할 수 있습니다.

```powershell
$headCommit = git rev-parse HEAD
.\scripts\invoke_post_commit_release.ps1 -Commit $headCommit
```

훅만 해제하려면 다음을 실행합니다. 암호화된 로컬 설정과 기존 릴리스는 삭제하지 않습니다.

```powershell
git config --local --unset core.hooksPath
```

다시 켤 때는 최초 설정 명령을 재실행합니다. 비밀번호나 keystore를 변경한 경우에도 설정 명령을 재실행해 DPAPI ciphertext를 교체합니다.
