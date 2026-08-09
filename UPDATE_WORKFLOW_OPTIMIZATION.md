# FinDone 업데이트 작업 최적화 가이드

이 문서는 FinDone의 코드 수정, 검증, 커밋, 서명 APK 게시를 수행할 때 노트북의 CPU·메모리·디스크 부하를 줄이기 위한 운영 기준이다. 앞으로 업데이트 작업을 시작하기 전에 이 문서를 먼저 확인한다.

## 핵심 원칙

1. 작은 수정은 작은 테스트로 먼저 검증한다.
2. 동일한 커밋에 전체 릴리스 빌드를 중복 실행하지 않는다.
3. 커밋하면 `post-commit` 훅이 전체 릴리스를 실행한다는 사실을 고려한다.
4. 이미 Gradle 또는 릴리스 프로세스가 실행 중이면 새 빌드를 시작하지 않는다.
5. 정상 캐시는 유지하고, 안전성이 확인된 산출물과 임시 파일만 정리한다.
6. 릴리스 자동화나 서명 관련 파일은 일반 앱 코드와 같은 방식으로 즉흥 수정하지 않는다.

## 현재 자동 릴리스 흐름

커밋이 완료되면 `.githooks/post-commit`이 동기 방식으로 다음 작업을 실행한다.

```text
완료된 HEAD SHA 확인
→ 저장소 전용 Git 환경변수 제거
→ 임시 detached worktree 생성
→ main worktree의 sdk.dir만 임시 worktree에 전달
→ 다음 versionCode 예약
→ clean test lintRelease assembleRelease
→ unsigned APK 생성
→ zipalign 및 개인 키 서명
→ 패키지명·버전·권한·서명·SHA-256 검증
→ 로컬 dist 게시
→ OneDrive mirror 복사 및 재검증
→ 양쪽의 정상 릴리스 최신 2개 유지
→ 성공 상태 기록
→ 임시 worktree 정리
```

휴대폰 업데이트는 앱 내부에서 수행하지 않는다. OneDrive의 최신 APK를 휴대폰에서 직접 열고 Android 시스템 설치 화면을 이용한다.

## 작업 단계별 검증 수준

### 1단계: 수정 중 표적 검증

변경한 기능과 직접 관련된 테스트만 실행한다.

```powershell
.\gradlew.bat testDebugUnitTest --tests "관련.테스트.클래스" --no-daemon --console=plain
```

- 컴파일 오류와 해당 기능 회귀를 가장 먼저 확인한다.
- 실패한 표적 테스트가 있는 동안 전체 빌드를 실행하지 않는다.
- 서로 다른 Gradle 명령을 동시에 실행하지 않는다.

### 2단계: 커밋 전 통합 검증

위험도가 있는 앱 코드 변경일 때 한 번만 실행한다.

```powershell
.\gradlew.bat testDebugUnitTest lintDebug compileReleaseKotlin --no-daemon --console=plain
```

- UI 문구나 작은 순수 함수 변경이라면 표적 테스트와 `testDebugUnitTest`만으로 충분할 수 있다.
- 릴리스 변형에서만 발생할 수 있는 변경이라면 `compileReleaseKotlin`을 포함한다.
- 이 단계에서 `clean test lintRelease assembleRelease`를 실행한 뒤 곧바로 커밋하면, 커밋 훅이 같은 전체 작업을 다시 수행하므로 피한다.

### 3단계: 커밋 및 서명 릴리스

커밋은 한 번만 만든다. 활성화된 `post-commit` 훅이 다음 전체 게이트를 수행한다.

```powershell
clean test lintRelease assembleRelease
```

정상적인 전체 릴리스는 현재 노트북에서 약 9분이 걸릴 수 있다. 실행 제한은 최소 15분으로 두고, 출력이 잠시 없더라도 CPU 시간이 증가하거나 Java 프로세스가 살아 있으면 중단하지 않는다.

## 중복 빌드 방지 체크리스트

전체 빌드나 릴리스 재시도 전 다음을 확인한다.

```powershell
Get-Process -Name java,gradle,kotlinc -ErrorAction SilentlyContinue
git worktree list --porcelain
Get-Content .git\findone-release\state.json -Raw
```

- Java/Gradle 프로세스가 실행 중이면 기존 작업의 종료 여부를 먼저 확인한다.
- `lastAllocatedVersionCode`가 `lastSuccessfulVersionCode`보다 크면 이전 시도가 예약 후 중단된 상태일 수 있다.
- 도구 호출 시간이 초과됐더라도 자식 Gradle 프로세스가 계속 실행 중일 수 있다. 즉시 새 릴리스를 시작하지 않는다.
- 동일 커밋을 재시도하면 새 versionCode가 할당된다. 실패 번호를 재사용하거나 `state.json`을 수동으로 되돌리지 않는다.
- 이미 정상 릴리스가 생성됐다면 같은 커밋을 다시 빌드하지 않는다.

## 릴리스 완료 확인

자동화의 종료 코드만 보지 말고 다음 조건을 확인한다.

1. `.git/findone-release/state.json`의 성공 커밋이 현재 HEAD와 같다.
2. `lastSuccessfulVersionCode`가 이번 할당 번호와 같다.
3. 로컬 `dist`와 OneDrive mirror에 동일한 릴리스 폴더가 있다.
4. 각 릴리스 폴더에는 다음 파일만 있다.

   ```text
   FinDone-<version>.apk
   release-manifest.json
   SHA256SUMS.txt
   ```

5. 양쪽 APK의 SHA-256이 manifest와 `SHA256SUMS.txt`에 모두 일치한다.
6. `apksigner verify`에서 v2와 v3 서명이 모두 검증된다.
7. 임시 release worktree와 Java/Gradle 프로세스가 남아 있지 않다.

## 캐시와 산출물 관리

### 유지해야 하는 항목

- `%USERPROFILE%\.gradle\caches`
  - Gradle 배포본, Android/Kotlin 플러그인, 라이브러리 의존성을 보관한다.
  - 현재 약 1.4GB지만 정상 캐시다.
  - 자주 삭제하면 다음 빌드가 다운로드와 변환을 반복해 오히려 CPU·네트워크 부하가 커진다.
- 프로젝트 `.gradle`
  - 현재 약 9MB로 작고 정상이다.
- Android SDK와 build-tools
  - 빌드와 APK 서명에 필요하다.
- `.git/findone-release/credentials.json`과 `state.json`
  - 자동 버전 할당과 릴리스 서명 자동화에 필요하다.
- 로컬 및 OneDrive의 최신 정상 릴리스 2개
  - 업데이트와 롤백 확인에 사용한다.

### 필요할 때 정리 가능한 항목

- `app/build`
  - 로컬 검증 산출물이며 삭제해도 소스나 사용자 데이터는 손실되지 않는다.
  - 현재 약 320MB다.
  - 다음 빌드에서 다시 생성되므로 디스크 공간이 필요할 때만 정리한다.
- 루트 `build`
  - 생성 산출물이며 현재 크기는 매우 작다.
- `%USERPROFILE%\.gradle\daemon`의 오래된 로그
  - 삭제 가능하지만 현재 약 10MB로 효과는 작다.
- `%TEMP%\FinDoneReleaseWorktrees` 아래의 고아 worktree
  - Java/Gradle 프로세스가 모두 종료된 뒤, `git worktree list`와 정확한 경로를 검증한 경우에만 정리한다.
- APK가 없고 manifest/checksum만 남은 불완전 OneDrive 릴리스 폴더
  - 자동화가 안전상 보존할 수 있다.
  - 용량 영향은 거의 없지만 휴대폰에서 오래된 릴리스처럼 보일 수 있으므로 검증 후 수동 정리할 수 있다.

### 삭제하면 안 되는 항목

- 저장소 전체 `.git`
- `.git/findone-release` 전체
- Android SDK
- 서명 keystore
- OneDrive `FinDone-Releases` 루트 전체
- 경로가 검증되지 않은 `%TEMP%` 또는 재분석 지점, junction, symlink
- 사용자의 `user.sqlite3` 또는 백업 파일

## 부하를 줄이기 위한 개선 후보

다음 항목은 아직 기본 자동화에 적용되지 않았다. 적용할 때는 한 항목씩 변경하고 실제 릴리스 검증을 수행한다.

### 우선순위 1: APK 관련 커밋만 자동 릴리스

문서나 계획 파일만 바뀐 커밋은 APK를 만들 필요가 없다. 아래 입력에 변경이 있을 때만 자동 릴리스를 실행하도록 필터를 둘 수 있다.

```text
app/
gradle/
build.gradle.kts
settings.gradle.kts
gradle.properties
콘텐츠 DB 생성에 영향을 주는 명세와 tools/
```

서명·릴리스 스크립트 자체가 바뀐 경우에는 자동 실행보다 변경 검토와 setup 재검증을 우선한다.

### 우선순위 2: CPU 작업자 수 제한

노트북 발열을 줄이는 것이 목표라면 다음 설정을 시험할 수 있다.

```properties
org.gradle.workers.max=2
```

빌드 시간은 늘어날 수 있지만 순간 CPU 사용률과 발열을 낮출 수 있다. 적용 전후 시간을 측정하고 2와 3 중 더 나은 값을 선택한다.

### 우선순위 3: Gradle 빌드 캐시 활성화

```properties
org.gradle.caching=true
```

서로 다른 임시 worktree에서도 입력이 같은 캐시 가능 작업을 재사용할 가능성이 있다. Kotlin, 리소스 처리 등에서 효과를 기대할 수 있지만 R8과 서명 단계는 계속 실행될 수 있다. 적용 후 exact-commit, APK 해시, 서명 검증을 다시 확인한다.

### 우선순위 4: 불필요한 전체 작업 축소

- 새 임시 worktree에는 기존 `build` 산출물이 없으므로 `clean`의 실효성이 작다.
- 전체 `test` 대신 `testDebugUnitTest`만 실행하고 release 컴파일은 `assembleRelease`에 맡기는 방안을 시험할 수 있다.
- `lintRelease`와 `assembleRelease`는 배포 안전성을 위해 유지한다.

후보 명령은 다음과 같다.

```powershell
testDebugUnitTest lintRelease assembleRelease
```

변경 전후에 debug/release 테스트 수, 린트 결과, R8 APK, JLatex corpus 검증이 동일하게 통과하는지 확인해야 한다.

### 우선순위 5: 실패 재시도와 로그 개선

- 릴리스 시도 상태를 `reserved → built → localPublished → mirrored → successful`로 기록한다.
- 프로세스가 중단됐을 때 이미 검증된 결과부터 이어서 처리한다.
- 최근 로그만 제한적으로 보존해 원인을 확인한 뒤 무작정 전체 빌드를 다시 돌리지 않게 한다.
- 동일 커밋의 정상 릴리스가 이미 있으면 새 versionCode를 할당하지 않고 종료한다.

## 현재 기준 상태

2026-08-10 측정 기준:

- 전체 릴리스 소요 시간: 약 8분 42초
- 프로젝트 `app/build`: 약 320MB
- 사용자 Gradle 캐시: 약 1.4GB
- 로컬 릴리스: 정상 2개, 약 13.3MB
- OneDrive 릴리스: 정상 2개, 약 13.3MB
- 임시 릴리스 worktree: 0개
- 실행 중 Java/Gradle 프로세스: 0개
- 실행 중 ADB: 1개, 약 15MB 메모리

이 수치는 진단 기준값이며 시간이 지나면 달라질 수 있다.

## 작업 종료 브리핑 형식

업데이트 작업을 마친 뒤 최소한 다음을 보고한다.

```text
- 변경한 기능과 핵심 파일
- 실행한 표적/통합/릴리스 테스트
- 실제로 전체 릴리스를 몇 번 실행했는지
- 릴리스 versionCode, 커밋 SHA, APK 경로와 SHA-256
- 로컬/OneDrive 보존 릴리스 수
- 남은 Java/Gradle 프로세스와 임시 worktree 수
- 정리하지 않고 보존한 캐시 또는 불완전 폴더
```

특히 전체 빌드를 중복 실행했거나 자동화가 중단돼 versionCode가 건너뛴 경우 반드시 명시한다.
