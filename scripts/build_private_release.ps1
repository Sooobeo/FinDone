param(
    [Parameter(Mandatory = $true)]
    [string]$KeystorePath,
    [Parameter(Mandatory = $true)]
    [string]$KeyAlias
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$resolvedKeystore = (Resolve-Path -LiteralPath $KeystorePath).Path

if ([string]::IsNullOrWhiteSpace($env:FINDONE_STORE_PASSWORD) -or
    [string]::IsNullOrWhiteSpace($env:FINDONE_KEY_PASSWORD)) {
    throw 'FINDONE_STORE_PASSWORD와 FINDONE_KEY_PASSWORD 환경 변수를 현재 터미널에만 설정한 뒤 다시 실행하세요.'
}

$env:FINDONE_KEYSTORE_PATH = $resolvedKeystore
$env:FINDONE_KEY_ALIAS = $KeyAlias

Push-Location $repoRoot
try {
    & .\gradlew.bat --no-daemon clean test lintRelease assembleRelease --console=plain
    if ($LASTEXITCODE -ne 0) { throw "Gradle release build failed: $LASTEXITCODE" }

    $apk = Join-Path $repoRoot 'app\build\outputs\apk\release\app-release.apk'
    if (-not (Test-Path -LiteralPath $apk)) {
        throw "서명 APK를 찾지 못했습니다: $apk"
    }

    $sdkDirLine = Get-Content (Join-Path $repoRoot 'local.properties') | Where-Object { $_ -like 'sdk.dir=*' } | Select-Object -First 1
    if (-not $sdkDirLine) { throw 'local.properties의 sdk.dir을 찾지 못했습니다.' }
    $sdkDir = ($sdkDirLine -replace '^sdk.dir=', '') -replace '\\\\', '\'
    $apkSigner = Get-ChildItem -LiteralPath (Join-Path $sdkDir 'build-tools') -Filter apksigner.bat -Recurse |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $apkSigner) { throw 'Android SDK에서 apksigner.bat를 찾지 못했습니다.' }

    $verifyOutput = & $apkSigner.FullName verify --verbose --print-certs $apk 2>&1
    if ($LASTEXITCODE -ne 0) { throw "APK 서명 검증 실패: $verifyOutput" }
    $certLine = $verifyOutput | Where-Object { $_ -match 'SHA-256 digest:' } | Select-Object -First 1
    $certSha = if ($certLine) { ($certLine -split 'SHA-256 digest:')[1].Trim() } else { 'unknown' }
    if ($certSha -eq 'unknown') { throw '서명 인증서 SHA-256을 읽지 못했습니다.' }

    $aapt = Join-Path $apkSigner.DirectoryName 'aapt.exe'
    if (-not (Test-Path -LiteralPath $aapt)) { throw 'Android SDK에서 aapt.exe를 찾지 못했습니다.' }
    $permissionOutput = & $aapt dump permissions $apk 2>&1
    if ($LASTEXITCODE -ne 0) { throw "APK 권한 검사 실패: $permissionOutput" }
    if ($permissionOutput -match "android\.permission\.INTERNET") {
        throw '릴리스 APK에 android.permission.INTERNET이 포함되어 배포를 중단했습니다.'
    }

    $versionName = (Select-String -Path 'app\build.gradle.kts' -Pattern 'versionName\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
    $versionCode = [int](Select-String -Path 'app\build.gradle.kts' -Pattern 'versionCode\s*=\s*(\d+)').Matches[0].Groups[1].Value
    $contentManifest = Get-Content -Raw -Encoding UTF8 'app\src\main\assets\content-manifest.json' | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($contentManifest.sha256) -or -not $contentManifest.contentDbVersion) {
        throw 'content-manifest.json의 DB 버전 또는 SHA-256이 비어 있습니다.'
    }
    $apkSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $apk).Hash.ToLowerInvariant()
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $distDir = Join-Path $repoRoot "dist\findone-$versionName-$stamp"
    New-Item -ItemType Directory -Path $distDir | Out-Null
    $distApk = Join-Path $distDir "FinDone-$versionName.apk"
    Copy-Item -LiteralPath $apk -Destination $distApk

    $releaseManifest = [ordered]@{
        distributionChannel = 'private_onedrive_sideload'
        publicStoreRelease = $false
        targetUser = 'self_only'
        internetPermission = $false
        oneDriveRuntimeSync = $false
        applicationId = 'com.findone.app'
        versionCode = $versionCode
        versionName = $versionName
        contentDbVersion = $contentManifest.contentDbVersion
        contentDbSha256 = $contentManifest.sha256
        userDbSchemaVersion = 2
        signingCertificateSha256 = $certSha
        releaseApkSha256 = $apkSha
        builtAt = (Get-Date).ToUniversalTime().ToString('o')
    }
    $releaseManifest | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $distDir 'release-manifest.json')
    "$apkSha  FinDone-$versionName.apk" | Set-Content -Encoding ASCII (Join-Path $distDir 'SHA256SUMS.txt')
    Write-Host "완료: $distDir"
} finally {
    Pop-Location
    Remove-Item Env:FINDONE_KEYSTORE_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:FINDONE_KEY_ALIAS -ErrorAction SilentlyContinue
    Remove-Item Env:FINDONE_STORE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:FINDONE_KEY_PASSWORD -ErrorAction SilentlyContinue
}
