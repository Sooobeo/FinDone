[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$Commit
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3.0

if ($null -eq ('FinDone.ReleaseAutomation.ReparsePointNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace FinDone.ReleaseAutomation
{
    public static class ReparsePointNative
    {
        private const uint FileFlagBackupSemantics = 0x02000000;
        private const uint FileFlagOpenReparsePoint = 0x00200000;
        private const uint FsctlGetReparsePoint = 0x000900A8;

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(
            string fileName,
            uint desiredAccess,
            FileShare shareMode,
            IntPtr securityAttributes,
            FileMode creationDisposition,
            uint flagsAndAttributes,
            IntPtr templateFile);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool DeviceIoControl(
            SafeFileHandle device,
            uint controlCode,
            IntPtr inputBuffer,
            uint inputBufferSize,
            byte[] outputBuffer,
            uint outputBufferSize,
            out uint bytesReturned,
            IntPtr overlapped);

        public static uint GetTag(string path)
        {
            using (SafeFileHandle handle = CreateFileW(
                path,
                0,
                FileShare.Read | FileShare.Write | FileShare.Delete,
                IntPtr.Zero,
                FileMode.Open,
                FileFlagBackupSemantics | FileFlagOpenReparsePoint,
                IntPtr.Zero))
            {
                if (handle.IsInvalid)
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to open reparse point.");

                byte[] buffer = new byte[16 * 1024];
                uint bytesReturned;
                if (!DeviceIoControl(
                    handle,
                    FsctlGetReparsePoint,
                    IntPtr.Zero,
                    0,
                    buffer,
                    (uint)buffer.Length,
                    out bytesReturned,
                    IntPtr.Zero))
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "Unable to query reparse point.");
                }
                if (bytesReturned < 8)
                    throw new InvalidDataException("Reparse point data is shorter than its header.");

                return BitConverter.ToUInt32(buffer, 0);
            }
        }

        public static bool IsMicrosoftCloudTag(uint tag)
        {
            return (tag & 0xFFFF0FFFu) == 0x9000001Au;
        }
    }
}
'@
}

function Get-FinDoneReparsePointTag {
    param([Parameter(Mandatory = $true)][System.IO.FileSystemInfo]$Item)
    if (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) {
        throw "The path is not a reparse point: $($Item.FullName)"
    }
    return [FinDone.ReleaseAutomation.ReparsePointNative]::GetTag($Item.FullName)
}

function Test-FinDoneReparsePointAllowed {
    param([Parameter(Mandatory = $true)][System.IO.FileSystemInfo]$Item)
    if (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) { return $true }
    $tag = Get-FinDoneReparsePointTag -Item $Item
    return [FinDone.ReleaseAutomation.ReparsePointNative]::IsMicrosoftCloudTag($tag)
}

function Assert-FinDoneReparsePointAllowed {
    param(
        [Parameter(Mandatory = $true)][System.IO.FileSystemInfo]$Item,
        [Parameter(Mandatory = $true)][string]$Context
    )
    if (($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) { return }
    $tag = Get-FinDoneReparsePointTag -Item $Item
    if (-not [FinDone.ReleaseAutomation.ReparsePointNative]::IsMicrosoftCloudTag($tag)) {
        $formattedTag = '0x{0:x8}' -f $tag
        throw "$Context uses a forbidden reparse point tag ($formattedTag): $($Item.FullName)"
    }
}


function Get-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    $pathRoot = [System.IO.Path]::GetPathRoot($full)
    if ($full.Equals($pathRoot, [StringComparison]::OrdinalIgnoreCase)) { return $pathRoot }
    return $full.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
}

function Write-Utf8JsonAtomically {
    param(
        [Parameter(Mandatory = $true)][object]$Value,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = Join-Path $directory ('.tmp-' + [guid]::NewGuid().ToString('N'))
    try {
        $json = $Value | ConvertTo-Json
        [System.IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $Path) {
            [System.IO.File]::Replace($temporary, $Path, $null)
        } else {
            [System.IO.File]::Move($temporary, $Path)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Convert-DpapiValueToSecureString {
    param([Parameter(Mandatory = $true)][string]$CipherText)
    return ConvertTo-SecureString $CipherText
}

function Clear-SigningEnvironment {
    foreach ($name in @(
        'FINDONE_KEYSTORE_PATH',
        'FINDONE_KEY_ALIAS',
        'FINDONE_STORE_PASSWORD',
        'FINDONE_KEY_PASSWORD',
        'FINDONE_APKSIGNER_STORE_PASSWORD',
        'FINDONE_APKSIGNER_KEY_PASSWORD'
    )) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}

function Get-HighestReleaseVersionCode {
    param([string]$ReleaseRoot)

    if ([string]::IsNullOrWhiteSpace($ReleaseRoot) -or
        -not (Test-Path -LiteralPath $ReleaseRoot -PathType Container)) {
        return 0L
    }

    $releaseRootItem = Get-Item -LiteralPath $ReleaseRoot -Force
    Assert-FinDoneReparsePointAllowed -Item $releaseRootItem -Context 'Version allocation release root'

    $highest = 0L
    foreach ($directory in @(Get-ChildItem -LiteralPath $ReleaseRoot -Directory -Force)) {
        if ($directory.Name -notmatch '^findone-[0-9A-Za-z][0-9A-Za-z.+_-]*-\d{8}-\d{6}(?:\d{3})?(?:-[0-9a-f]{7,40})?$') {
            continue
        }
        if (-not (Test-FinDoneReparsePointAllowed -Item $directory)) { continue }

        try {
            $manifestPath = Join-Path $directory.FullName 'release-manifest.json'
            $sumsPath = Join-Path $directory.FullName 'SHA256SUMS.txt'
            $files = @(Get-ChildItem -LiteralPath $directory.FullName -File -Force)
            $childDirectories = @(Get-ChildItem -LiteralPath $directory.FullName -Directory -Force)
            $apks = @(Get-ChildItem -LiteralPath $directory.FullName -File -Filter 'FinDone-*.apk')
            if ($files.Count -ne 3 -or $childDirectories.Count -ne 0 -or $apks.Count -ne 1 -or
                -not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
                -not (Test-Path -LiteralPath $sumsPath -PathType Leaf)) {
                continue
            }

            $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
            if ($manifest.applicationId -ne 'com.findone.app') { continue }
            $sumLine = (Get-Content -Raw -Encoding ASCII -LiteralPath $sumsPath).Trim()
            if ($sumLine -notmatch '^([0-9a-fA-F]{64})\s{2}([^\\/\r\n]+\.apk)$' -or $Matches[2] -ne $apks[0].Name) {
                continue
            }
            $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $apks[0].FullName).Hash.ToLowerInvariant()
            if ($actualHash -ne $Matches[1].ToLowerInvariant() -or
                $manifest.releaseApkSha256.ToString().ToLowerInvariant() -ne $actualHash) {
                continue
            }
            $versionCode = [int64]$manifest.versionCode
            if ($versionCode -gt $highest -and $versionCode -le 2100000000L) { $highest = $versionCode }
        } catch {
            # Invalid or unrelated release-like directories do not influence version allocation.
        }
    }
    return $highest
}

Clear-SigningEnvironment
$repoRoot = Get-FullPath (Split-Path -Parent $PSScriptRoot)
$resolvedCommit = (& git -C $repoRoot rev-parse --verify "$Commit^{commit}" 2>&1).ToString().Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $resolvedCommit -notmatch '^[0-9a-f]{40}$') {
    throw "The post-commit release target is not a valid commit: $Commit"
}

$gitCommonText = (& git -C $repoRoot rev-parse --git-common-dir 2>&1).ToString().Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($gitCommonText)) {
    throw 'Unable to locate the repository Git metadata directory.'
}
$gitCommonDir = if ([System.IO.Path]::IsPathRooted($gitCommonText)) {
    Get-FullPath $gitCommonText
} else {
    Get-FullPath (Join-Path $repoRoot $gitCommonText)
}
$automationDirectory = Join-Path $gitCommonDir 'findone-release'
$configurationPath = Join-Path $automationDirectory 'credentials.json'
$statePath = Join-Path $automationDirectory 'state.json'
if (-not (Test-Path -LiteralPath $configurationPath -PathType Leaf)) {
    throw "Release automation is not configured. Run scripts\setup_release_automation.ps1 explicitly: $configurationPath"
}

$configuration = Get-Content -Raw -Encoding UTF8 -LiteralPath $configurationPath | ConvertFrom-Json
if ($configuration.schemaVersion -ne 2) { throw 'Unsupported release automation configuration version; run setup again.' }
$requiredConfigurationProperties = @(
    'repositoryRoot',
    'keystorePath',
    'keyAlias',
    'storePasswordDpapi',
    'keyPasswordDpapi',
    'expectedSigningCertificateSha256',
    'orchestratorBuildScriptSha256',
    'keepReleases'
)
foreach ($propertyName in $requiredConfigurationProperties) {
    if ($configuration.PSObject.Properties.Name -notcontains $propertyName) {
        throw "Release automation configuration is missing '$propertyName'; run setup again."
    }
}
if ((Get-FullPath $configuration.repositoryRoot) -ne $repoRoot) {
    throw 'Release automation configuration belongs to a different repository path; run setup again.'
}
if (-not (Test-Path -LiteralPath $configuration.keystorePath -PathType Leaf)) {
    throw "Configured signing keystore does not exist: $($configuration.keystorePath)"
}

# Verify reviewed orchestration and the public certificate pin before DPAPI
# ciphertext is decrypted. Any intentional builder update requires setup again.
$builder = Join-Path $PSScriptRoot 'build_private_release.ps1'
if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) { throw "Release builder is missing: $builder" }
$activeBuilderSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $builder).Hash.ToLowerInvariant()
if ($configuration.orchestratorBuildScriptSha256.ToString() -notmatch '^[0-9a-fA-F]{64}$' -or
    $activeBuilderSha256 -ne $configuration.orchestratorBuildScriptSha256.ToString().ToLowerInvariant()) {
    throw 'Release builder SHA-256 differs from the setup pin. Review the builder and run setup again before releasing.'
}
$signingPinPath = Join-Path $repoRoot 'config\release-signing-certificate.sha256'
if (-not (Test-Path -LiteralPath $signingPinPath -PathType Leaf)) { throw "Tracked signing certificate pin is missing: $signingPinPath" }
$trackedSigningCertificateSha256 = (Get-Content -Raw -Encoding ASCII -LiteralPath $signingPinPath).Trim().ToLowerInvariant()
if ($trackedSigningCertificateSha256 -notmatch '^[0-9a-f]{64}$' -or
    $configuration.expectedSigningCertificateSha256.ToString() -notmatch '^[0-9a-fA-F]{64}$' -or
    $trackedSigningCertificateSha256 -ne $configuration.expectedSigningCertificateSha256.ToString().ToLowerInvariant()) {
    throw 'Configured signing certificate SHA-256 differs from the reviewed tracked pin. Run setup again only after resolving it.'
}

$repoIdentityBytes = [System.Text.Encoding]::UTF8.GetBytes($repoRoot.ToLowerInvariant())
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $repoIdentity = ([BitConverter]::ToString($sha256.ComputeHash($repoIdentityBytes))).Replace('-', '').Substring(0, 24)
} finally {
    $sha256.Dispose()
}
$mutex = [Threading.Mutex]::new($false, "Local\FinDoneRelease_$repoIdentity")
$hasMutex = $false
$worktreePath = $null
$temporaryRoot = Get-FullPath (Join-Path ([System.IO.Path]::GetTempPath()) 'FinDoneReleaseWorktrees')

try {
    try {
        $hasMutex = $mutex.WaitOne([TimeSpan]::FromHours(3))
    } catch [Threading.AbandonedMutexException] {
        $hasMutex = $true
    }
    if (-not $hasMutex) { throw 'Timed out waiting for another FinDone release build to finish.' }

    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
    $temporaryRootItem = Get-Item -LiteralPath $temporaryRoot -Force
    Assert-FinDoneReparsePointAllowed -Item $temporaryRootItem -Context 'Temporary release worktree root'
    $worktreePath = Join-Path $temporaryRoot ('worktree-' + [guid]::NewGuid().ToString('N'))
    & git -C $repoRoot worktree add --detach $worktreePath $resolvedCommit
    if ($LASTEXITCODE -ne 0) { throw "Failed to create an exact-commit release worktree for $resolvedCommit" }
    $worktreeItem = Get-Item -LiteralPath $worktreePath -Force
    Assert-FinDoneReparsePointAllowed -Item $worktreeItem -Context 'Temporary release worktree'

    $sdkLine = Get-Content -LiteralPath (Join-Path $repoRoot 'local.properties') -Encoding UTF8 |
        Where-Object { $_ -match '^\s*sdk\.dir\s*=' } |
        Select-Object -First 1
    if (-not $sdkLine) { throw 'The main repository local.properties does not contain sdk.dir.' }
    [System.IO.File]::WriteAllText(
        (Join-Path $worktreePath 'local.properties'),
        $sdkLine.Trim() + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )

    $declaredBuildFile = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $worktreePath 'app\build.gradle.kts')
    $declaredCodeMatch = [regex]::Match($declaredBuildFile, '(?m)^\s*val\s+declaredVersionCode\s*=\s*(\d+)\s*$')
    $declaredNameMatch = [regex]::Match($declaredBuildFile, '(?m)^\s*val\s+declaredVersionName\s*=\s*"([^"]+)"\s*$')
    if (-not $declaredCodeMatch.Success -or -not $declaredNameMatch.Success) {
        throw 'The committed build file does not expose declaredVersionCode and declaredVersionName.'
    }
    $declaredVersionCode = [int64]$declaredCodeMatch.Groups[1].Value
    $declaredVersionName = $declaredNameMatch.Groups[1].Value
    $shortCommit = $resolvedCommit.Substring(0, 10)
    $automaticVersionName = "$declaredVersionName+g$shortCommit"

    $lastAllocatedVersionCode = 0L
    $state = $null
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        $state = Get-Content -Raw -Encoding UTF8 -LiteralPath $statePath | ConvertFrom-Json
        if ($state.schemaVersion -ne 1) { throw 'Unsupported release automation state version.' }
        $lastAllocatedVersionCode = [int64]$state.lastAllocatedVersionCode
    }
    $configuredMirrorRoot = $null
    if ($configuration.PSObject.Properties.Name -contains 'mirrorRoot' -and
        -not [string]::IsNullOrWhiteSpace([string]$configuration.mirrorRoot)) {
        $configuredMirrorRoot = [string]$configuration.mirrorRoot
    }
    $highestPublishedVersionCode = [Math]::Max(
        (Get-HighestReleaseVersionCode -ReleaseRoot (Join-Path $repoRoot 'dist')),
        (Get-HighestReleaseVersionCode -ReleaseRoot $configuredMirrorRoot)
    )
    $automaticVersionCode = [Math]::Max(
        $declaredVersionCode + 1L,
        [Math]::Max($lastAllocatedVersionCode + 1L, $highestPublishedVersionCode + 1L)
    )
    if ($automaticVersionCode -gt 2100000000L) {
        throw "The computed automatic versionCode exceeds Android's maximum; update the version allocation scheme."
    }

    # Reserve before building. A failed build consumes a number so a later APK can never go backwards.
    $reservedState = [ordered]@{
        schemaVersion = 1
        lastAllocatedVersionCode = $automaticVersionCode
        lastAllocatedCommit = $resolvedCommit
        lastAllocatedAt = [DateTimeOffset]::UtcNow.ToString('o')
        lastSuccessfulVersionCode = if ($null -ne $state -and $state.PSObject.Properties.Name -contains 'lastSuccessfulVersionCode') { $state.lastSuccessfulVersionCode } else { $null }
        lastSuccessfulCommit = if ($null -ne $state -and $state.PSObject.Properties.Name -contains 'lastSuccessfulCommit') { $state.lastSuccessfulCommit } else { $null }
        lastReleaseDirectory = if ($null -ne $state -and $state.PSObject.Properties.Name -contains 'lastReleaseDirectory') { $state.lastReleaseDirectory } else { $null }
    }
    Write-Utf8JsonAtomically -Value $reservedState -Path $statePath

    $storePassword = Convert-DpapiValueToSecureString $configuration.storePasswordDpapi
    $keyPassword = Convert-DpapiValueToSecureString $configuration.keyPasswordDpapi
    try {
        $keepReleases = [int]$configuration.keepReleases
        if ($keepReleases -ne 2) { throw 'Release automation retention must be exactly two bundles.' }
        # The reviewed builder is active-clone orchestration code, not code checked
        # out from the target worktree. This reduces accidental secret exposure but
        # is not an OS security boundary; see the documented threat model.
        & $builder `
            -SourceRoot $worktreePath `
            -DistRoot (Join-Path $repoRoot 'dist') `
            -KeystorePath $configuration.keystorePath `
            -KeyAlias $configuration.keyAlias `
            -StorePassword $storePassword `
            -KeyPassword $keyPassword `
            -ExpectedSigningCertificateSha256 $trackedSigningCertificateSha256 `
            -ExpectedOrchestratorScriptSha256 $activeBuilderSha256 `
            -ExpectedCommit $resolvedCommit `
            -VersionCodeOverride ([int]$automaticVersionCode) `
            -VersionNameOverride $automaticVersionName `
            -KeepReleases 2 `
            -MirrorRoot $configuredMirrorRoot

        $matchingRelease = @(Get-ChildItem -LiteralPath (Join-Path $repoRoot 'dist') -Directory -Filter 'findone-*' | ForEach-Object {
            $manifestPath = Join-Path $_.FullName 'release-manifest.json'
            if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
                try {
                    $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
                    if ($manifest.gitCommit -eq $resolvedCommit -and [int64]$manifest.versionCode -eq $automaticVersionCode) { $_ }
                } catch { }
            }
        } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1)
        if ($matchingRelease.Count -ne 1) { throw 'The build completed but its exact release bundle could not be identified.' }

        $successfulState = [ordered]@{
            schemaVersion = 1
            lastAllocatedVersionCode = $automaticVersionCode
            lastAllocatedCommit = $resolvedCommit
            lastAllocatedAt = $reservedState.lastAllocatedAt
            lastSuccessfulVersionCode = $automaticVersionCode
            lastSuccessfulCommit = $resolvedCommit
            lastReleaseDirectory = $matchingRelease[0].Name
            lastSuccessfulAt = [DateTimeOffset]::UtcNow.ToString('o')
        }
        Write-Utf8JsonAtomically -Value $successfulState -Path $statePath
    } finally {
        if ($null -ne $storePassword) { $storePassword.Dispose() }
        if ($null -ne $keyPassword) { $keyPassword.Dispose() }
        $storePassword = $null
        $keyPassword = $null
        Clear-SigningEnvironment
    }
} finally {
    Clear-SigningEnvironment

    if ($null -ne $worktreePath) {
        $worktreeFull = Get-FullPath $worktreePath
        $temporaryRootWithSeparator = $temporaryRoot + [System.IO.Path]::DirectorySeparatorChar
        if ($worktreeFull.StartsWith($temporaryRootWithSeparator, [StringComparison]::OrdinalIgnoreCase) -and
            (Split-Path -Parent $worktreeFull) -eq $temporaryRoot -and
            (Split-Path -Leaf $worktreeFull) -like 'worktree-*') {
            $cleanupAllowed = $true
            if (Test-Path -LiteralPath $worktreeFull) {
                try {
                    $worktreeItem = Get-Item -LiteralPath $worktreeFull -Force
                    Assert-FinDoneReparsePointAllowed -Item $worktreeItem -Context 'Temporary release worktree before cleanup'
                } catch {
                    Write-Warning "Temporary worktree was preserved because its reparse point could not be validated safely: $worktreeFull ($($_.Exception.Message))"
                    $cleanupAllowed = $false
                }
            }
            if ($cleanupAllowed) {
                & git -C $repoRoot worktree remove --force $worktreeFull 2>$null
                if (Test-Path -LiteralPath $worktreeFull) {
                    $worktreeItem = Get-Item -LiteralPath $worktreeFull -Force
                    Assert-FinDoneReparsePointAllowed -Item $worktreeItem -Context 'Temporary release worktree before fallback cleanup'
                    Remove-Item -LiteralPath $worktreeFull -Recurse -Force
                }
                & git -C $repoRoot worktree prune 2>$null
            }
        }
    }
    if ($hasMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
