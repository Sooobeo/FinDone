[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$KeystorePath,
    [string]$KeyAlias = 'findone-release',
    [Security.SecureString]$StorePassword,
    [Security.SecureString]$KeyPassword,
    [Parameter(Mandatory = $true)]
    [string]$ContentReleaseEndpoint,
    [string]$MirrorRoot,
    [switch]$SkipHookActivation
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

function Test-IsWithinPath {
    param(
        [Parameter(Mandatory = $true)][string]$Child,
        [Parameter(Mandatory = $true)][string]$Parent
    )
    $childFull = Get-FullPath $Child
    $parentFull = Get-FullPath $Parent
    return $childFull.Equals($parentFull, [StringComparison]::OrdinalIgnoreCase) -or
        $childFull.StartsWith($parentFull + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}

function Test-IsFileSystemRoot {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Get-FullPath $Path
    $pathRoot = [System.IO.Path]::GetPathRoot($full)
    $fullComparable = $full.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $rootComparable = $pathRoot.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    return $fullComparable.Equals($rootComparable, [StringComparison]::OrdinalIgnoreCase)
}

function Convert-SecureValueToPlainText {
    param([Parameter(Mandatory = $true)][Security.SecureString]$SecureValue)
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

function Write-FinDoneAtomicJsonDiagnostic {
    param([Parameter(Mandatory = $true)][string]$Message)
    try { [Console]::Error.WriteLine("[FinDone atomic JSON] $Message") } catch { }
}

function Write-Utf8JsonAtomically {
    param(
        [Parameter(Mandatory = $true)][object]$Value,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $destinationFull = [System.IO.Path]::GetFullPath($Path)
    $directoryFull = Get-FullPath ([System.IO.Path]::GetDirectoryName($destinationFull))
    $destinationLeaf = [System.IO.Path]::GetFileName($destinationFull)
    if (@('state.json', 'credentials.json', '.findone-release-root.json') -cnotcontains $destinationLeaf -or
        -not ([System.IO.Path]::GetDirectoryName($destinationFull)).Equals($directoryFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Atomic JSON destination is not an approved direct-child path: $destinationFull"
    }

    New-Item -ItemType Directory -Path $directoryFull -Force | Out-Null
    $directoryItem = Get-Item -LiteralPath $directoryFull -Force
    Assert-FinDoneReparsePointAllowed -Item $directoryItem -Context 'Atomic JSON parent directory'

    $temporaryFull = Get-FullPath (Join-Path $directoryFull ('.tmp-' + [guid]::NewGuid().ToString('N')))
    $backupFull = Get-FullPath (Join-Path $directoryFull ('.bak-' + [guid]::NewGuid().ToString('N')))
    if (([System.IO.Path]::GetDirectoryName($temporaryFull)) -ne $directoryFull -or
        ([System.IO.Path]::GetFileName($temporaryFull)) -cnotmatch '^\.tmp-[0-9a-f]{32}$' -or
        ([System.IO.Path]::GetDirectoryName($backupFull)) -ne $directoryFull -or
        ([System.IO.Path]::GetFileName($backupFull)) -cnotmatch '^\.bak-[0-9a-f]{32}$') {
        throw 'Atomic JSON temporary paths failed their same-parent or strict-name safety check.'
    }

    $primaryError = $null
    $committed = $false
    try {
        $jsonBytes = [System.Text.UTF8Encoding]::new($false).GetBytes(
            (($Value | ConvertTo-Json) + [Environment]::NewLine)
        )
        $fileStream = $null
        $writeError = $null
        try {
            $fileStream = [System.IO.FileStream]::new(
                $temporaryFull,
                [System.IO.FileMode]::CreateNew,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::None
            )
            $fileStream.Write($jsonBytes, 0, $jsonBytes.Length)
            $fileStream.Flush($true)
        } catch {
            $writeError = $_
        }
        if ($null -ne $fileStream) {
            try {
                $fileStream.Dispose()
            } catch {
                if ($null -eq $writeError) { $writeError = $_ } else {
                    Write-FinDoneAtomicJsonDiagnostic "File stream disposal also failed: $($_.Exception.Message)"
                }
            }
        }
        if ($null -ne $writeError) { throw $writeError }

        if (Test-Path -LiteralPath $destinationFull) {
            $destinationItem = Get-Item -LiteralPath $destinationFull -Force
            if ($destinationItem.PSIsContainer) {
                throw "Atomic JSON destination must be a regular file, not a directory: $destinationFull"
            }
            Assert-FinDoneReparsePointAllowed -Item $destinationItem -Context 'Atomic JSON destination'
            [System.IO.File]::Replace($temporaryFull, $destinationFull, $backupFull)
        } else {
            [System.IO.File]::Move($temporaryFull, $destinationFull)
        }
        $committed = $true
    } catch {
        $primaryError = $_
    }

    if ($committed) {
        foreach ($artifact in @($temporaryFull, $backupFull)) {
            try { [System.IO.File]::Delete($artifact) } catch {
                Write-FinDoneAtomicJsonDiagnostic "Committed JSON, but could not delete cleanup artifact '$artifact'; it was preserved: $($_.Exception.Message)"
            }
        }
        return
    }

    $restoreFailed = $false
    if (-not [System.IO.File]::Exists($destinationFull) -and [System.IO.File]::Exists($backupFull)) {
        try {
            $backupItem = Get-Item -LiteralPath $backupFull -Force
            if ($backupItem.PSIsContainer -or
                ($backupItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Atomic JSON backup became an unsafe reparse point: $backupFull"
            }
            [System.IO.File]::Move($backupFull, $destinationFull)
        } catch {
            $restoreFailed = $true
            Write-FinDoneAtomicJsonDiagnostic "Could not restore the original JSON; temporary and backup artifacts were preserved when present: $($_.Exception.Message)"
        }
    }

    if (-not $restoreFailed) {
        if ([System.IO.File]::Exists($destinationFull) -or [System.IO.File]::Exists($backupFull)) {
            try { [System.IO.File]::Delete($temporaryFull) } catch {
                Write-FinDoneAtomicJsonDiagnostic "Could not delete failed-write temporary '$temporaryFull'; it was preserved: $($_.Exception.Message)"
            }
        } elseif ([System.IO.File]::Exists($temporaryFull)) {
            Write-FinDoneAtomicJsonDiagnostic "The failed write produced no destination or backup; its temporary was preserved: $temporaryFull"
        }
    }
    # A backup created by a failed replace is never deleted here. It either moved
    # back to a missing destination above or remains as the recoverable original.
    throw $primaryError
}

function Get-LatestValidatedReleaseCertificateSha256 {
    param([string[]]$ReleaseRoots)

    $candidates = @()
    foreach ($releaseRoot in $ReleaseRoots) {
        if ([string]::IsNullOrWhiteSpace($releaseRoot) -or
            -not (Test-Path -LiteralPath $releaseRoot -PathType Container)) { continue }
        $rootItem = Get-Item -LiteralPath $releaseRoot -Force
        if (-not (Test-FinDoneReparsePointAllowed -Item $rootItem)) { continue }

        foreach ($directory in @(Get-ChildItem -LiteralPath $releaseRoot -Directory -Force)) {
            if ($directory.Name -notmatch '^findone-[0-9A-Za-z][0-9A-Za-z.+_-]*-\d{8}-\d{6}(?:\d{3})?(?:-[0-9a-f]{7,40})?$' -or
                -not (Test-FinDoneReparsePointAllowed -Item $directory)) { continue }
            try {
                $files = @(Get-ChildItem -LiteralPath $directory.FullName -File -Force)
                $childDirectories = @(Get-ChildItem -LiteralPath $directory.FullName -Directory -Force)
                $apks = @(Get-ChildItem -LiteralPath $directory.FullName -File -Filter 'FinDone-*.apk')
                $manifestPath = Join-Path $directory.FullName 'release-manifest.json'
                $sumsPath = Join-Path $directory.FullName 'SHA256SUMS.txt'
                if ($files.Count -ne 3 -or $childDirectories.Count -ne 0 -or $apks.Count -ne 1 -or
                    -not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
                    -not (Test-Path -LiteralPath $sumsPath -PathType Leaf)) { continue }

                $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
                $sumLine = (Get-Content -Raw -Encoding ASCII -LiteralPath $sumsPath).Trim()
                if ($manifest.applicationId -ne 'com.findone.app' -or
                    $manifest.signingCertificateSha256.ToString() -notmatch '^[0-9a-fA-F]{64}$' -or
                    $sumLine -notmatch '^([0-9a-fA-F]{64})\s{2}([^\\/\r\n]+\.apk)$' -or
                    $Matches[2] -ne $apks[0].Name) { continue }
                $actualApkSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $apks[0].FullName).Hash.ToLowerInvariant()
                if ($actualApkSha256 -ne $Matches[1].ToLowerInvariant() -or
                    $actualApkSha256 -ne $manifest.releaseApkSha256.ToString().ToLowerInvariant()) { continue }
                $candidates += [pscustomobject]@{
                    BuiltAt = [DateTimeOffset]::Parse($manifest.builtAt, [Globalization.CultureInfo]::InvariantCulture)
                    CertificateSha256 = $manifest.signingCertificateSha256.ToString().ToLowerInvariant()
                    Directory = $directory.FullName
                }
            } catch {
                # Invalid release-like directories are ignored and never establish trust.
            }
        }
    }
    $latest = $candidates | Sort-Object BuiltAt -Descending | Select-Object -First 1
    if ($null -eq $latest) { return $null }
    return $latest
}

if ($env:OS -ne 'Windows_NT') {
    throw 'This setup uses Windows DPAPI and must be run on Windows.'
}

$repoRoot = Get-FullPath (Split-Path -Parent $PSScriptRoot)
$resolvedTopLevel = (& git -C $repoRoot rev-parse --show-toplevel 2>&1).ToString().Trim()
if ($LASTEXITCODE -ne 0 -or (Get-FullPath $resolvedTopLevel) -ne $repoRoot) {
    throw "Unable to resolve the FinDone repository root: $repoRoot"
}

[Uri]$contentReleaseUri = $null
if ([string]::IsNullOrWhiteSpace($ContentReleaseEndpoint) -or
    -not [Uri]::TryCreate($ContentReleaseEndpoint.Trim(), [UriKind]::Absolute, [ref]$contentReleaseUri) -or
    $contentReleaseUri.Scheme -cne 'https' -or
    [string]::IsNullOrWhiteSpace($contentReleaseUri.Host) -or
    -not [string]::IsNullOrEmpty($contentReleaseUri.UserInfo) -or
    -not [string]::IsNullOrEmpty($contentReleaseUri.Query) -or
    -not [string]::IsNullOrEmpty($contentReleaseUri.Fragment)) {
    throw 'ContentReleaseEndpoint must be a public HTTPS URL without credentials, query, or fragment.'
}
$normalizedContentReleaseEndpoint = $contentReleaseUri.AbsoluteUri.TrimEnd('/')

$signingPinPath = Join-Path $repoRoot 'config\release-signing-certificate.sha256'
if (-not (Test-Path -LiteralPath $signingPinPath -PathType Leaf)) {
    throw "Tracked signing certificate pin is missing: $signingPinPath"
}
$trackedSigningCertificateSha256 = (Get-Content -Raw -Encoding ASCII -LiteralPath $signingPinPath).Trim().ToLowerInvariant()
if ($trackedSigningCertificateSha256 -notmatch '^[0-9a-f]{64}$') {
    throw "Tracked signing certificate pin is invalid: $signingPinPath"
}
$builderPath = Join-Path $PSScriptRoot 'build_private_release.ps1'
if (-not (Test-Path -LiteralPath $builderPath -PathType Leaf)) { throw "Release builder is missing: $builderPath" }
$orchestratorBuildScriptSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $builderPath).Hash.ToLowerInvariant()

$resolvedKeystore = (Resolve-Path -LiteralPath $KeystorePath -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $resolvedKeystore -PathType Leaf)) {
    throw "Keystore is not a file: $resolvedKeystore"
}
if (Test-IsWithinPath -Child $resolvedKeystore -Parent $repoRoot) {
    throw 'The signing keystore must be outside the public Git repository.'
}
if ($KeyAlias -notmatch '^[A-Za-z0-9._-]+$') {
    throw 'KeyAlias may contain only ASCII letters, digits, dot, underscore, and hyphen.'
}

if ($null -eq $StorePassword) { $StorePassword = Read-Host 'Keystore password' -AsSecureString }
if ($null -eq $KeyPassword) { $KeyPassword = Read-Host 'Signing key password' -AsSecureString }
if ($StorePassword.Length -eq 0 -or $KeyPassword.Length -eq 0) { throw 'Signing passwords must not be empty.' }

# Validate the store password, private-key password, and alias before persisting
# anything or enabling the hook. Only environment variable names appear on the
# keytool command line; plaintext values exist only for the trusted keytool call.
$keytoolCommand = Get-Command keytool.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $keytoolCommand) {
    $keytoolCommand = Get-Command keytool -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
}
if ($null -eq $keytoolCommand) { throw 'JDK keytool was not found on PATH; signing credentials cannot be validated safely.' }

$credentialCheckStoreEnvironment = 'FINDONE_SETUP_STORE_PASSWORD'
$credentialCheckKeyEnvironment = 'FINDONE_SETUP_KEY_PASSWORD'
$credentialCheckCsr = Join-Path ([System.IO.Path]::GetTempPath()) ('FinDoneCredentialCheck-' + [guid]::NewGuid().ToString('N') + '.csr')
$credentialCheckCertificate = Join-Path ([System.IO.Path]::GetTempPath()) ('FinDoneCredentialCheck-' + [guid]::NewGuid().ToString('N') + '.cer')
$storePasswordPlainText = Convert-SecureValueToPlainText $StorePassword
$keyPasswordPlainText = Convert-SecureValueToPlainText $KeyPassword
try {
    [Environment]::SetEnvironmentVariable($credentialCheckStoreEnvironment, $storePasswordPlainText, 'Process')
    [Environment]::SetEnvironmentVariable($credentialCheckKeyEnvironment, $keyPasswordPlainText, 'Process')
    $storePasswordPlainText = $null
    $keyPasswordPlainText = $null

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $credentialCheckOutput = @(& $keytoolCommand.Source `
            -certreq `
            -alias $KeyAlias `
            -keystore $resolvedKeystore `
            -storepass:env $credentialCheckStoreEnvironment `
            -keypass:env $credentialCheckKeyEnvironment `
            -file $credentialCheckCsr `
            2>&1)
        $credentialCheckExitCode = $LASTEXITCODE
        $certificateExportOutput = @(& $keytoolCommand.Source `
            -exportcert `
            -alias $KeyAlias `
            -keystore $resolvedKeystore `
            -storepass:env $credentialCheckStoreEnvironment `
            -file $credentialCheckCertificate `
            2>&1)
        $certificateExportExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($credentialCheckExitCode -ne 0 -or
        -not (Test-Path -LiteralPath $credentialCheckCsr -PathType Leaf) -or
        (Get-Item -LiteralPath $credentialCheckCsr).Length -eq 0) {
        throw "Keystore credential validation failed; configuration was not saved: $($credentialCheckOutput -join [Environment]::NewLine)"
    }
    if ($certificateExportExitCode -ne 0 -or
        -not (Test-Path -LiteralPath $credentialCheckCertificate -PathType Leaf) -or
        (Get-Item -LiteralPath $credentialCheckCertificate).Length -eq 0) {
        throw "Signing certificate export failed; configuration was not saved: $($certificateExportOutput -join [Environment]::NewLine)"
    }
    $actualSigningCertificateSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $credentialCheckCertificate).Hash.ToLowerInvariant()
    if ($actualSigningCertificateSha256 -ne $trackedSigningCertificateSha256) {
        throw "Signing certificate mismatch; configuration was not saved. Expected reviewed pin $trackedSigningCertificateSha256, got $actualSigningCertificateSha256."
    }
} finally {
    $storePasswordPlainText = $null
    $keyPasswordPlainText = $null
    [Environment]::SetEnvironmentVariable($credentialCheckStoreEnvironment, $null, 'Process')
    [Environment]::SetEnvironmentVariable($credentialCheckKeyEnvironment, $null, 'Process')
    if (Test-Path -LiteralPath $credentialCheckCsr -PathType Leaf) {
        $csrFull = [System.IO.Path]::GetFullPath($credentialCheckCsr)
        $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\')
        if ((Split-Path -Parent $csrFull) -eq $tempRoot -and
            (Split-Path -Leaf $csrFull) -like 'FinDoneCredentialCheck-*.csr') {
            [System.IO.File]::Delete($csrFull)
        }
    }
    if (Test-Path -LiteralPath $credentialCheckCertificate -PathType Leaf) {
        $certificateFull = [System.IO.Path]::GetFullPath($credentialCheckCertificate)
        $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\')
        if ((Split-Path -Parent $certificateFull) -eq $tempRoot -and
            (Split-Path -Leaf $certificateFull) -like 'FinDoneCredentialCheck-*.cer') {
            [System.IO.File]::Delete($certificateFull)
        }
    }
}

$latestLocalRelease = Get-LatestValidatedReleaseCertificateSha256 -ReleaseRoots @((Join-Path $repoRoot 'dist'))
if ($null -ne $latestLocalRelease -and $latestLocalRelease.CertificateSha256 -ne $actualSigningCertificateSha256) {
    throw "Signing certificate does not match the newest validated local release at $($latestLocalRelease.Directory); configuration was not saved."
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

$configuredMirror = $null
if ($PSBoundParameters.ContainsKey('MirrorRoot') -and -not [string]::IsNullOrWhiteSpace($MirrorRoot)) {
    $configuredMirror = Get-FullPath $MirrorRoot
    if (-not (Test-Path -LiteralPath $configuredMirror -PathType Container)) {
        throw "MirrorRoot must already exist; setup will not create it: $configuredMirror"
    }
    if (Test-IsFileSystemRoot $configuredMirror) { throw 'A filesystem root cannot be used as MirrorRoot.' }
    $mirrorRootItem = Get-Item -LiteralPath $configuredMirror -Force
    Assert-FinDoneReparsePointAllowed -Item $mirrorRootItem -Context 'MirrorRoot'
    if (Test-IsWithinPath -Child $configuredMirror -Parent $repoRoot) {
        throw 'MirrorRoot must be outside the Git repository.'
    }

    $latestMirrorRelease = Get-LatestValidatedReleaseCertificateSha256 -ReleaseRoots @($configuredMirror)
    if ($null -ne $latestMirrorRelease -and $latestMirrorRelease.CertificateSha256 -ne $actualSigningCertificateSha256) {
        throw "Signing certificate does not match the newest validated mirror release at $($latestMirrorRelease.Directory); configuration was not saved."
    }

    $markerPath = Join-Path $configuredMirror '.findone-release-root.json'
    if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
        $marker = Get-Content -Raw -Encoding UTF8 -LiteralPath $markerPath | ConvertFrom-Json
        if ($marker.schemaVersion -ne 1 -or $marker.purpose -ne 'findone-release-mirror' -or
            $marker.applicationId -ne 'com.findone.app') {
            throw "MirrorRoot contains an invalid safety marker: $markerPath"
        }
    } else {
        $existingItems = @(Get-ChildItem -LiteralPath $configuredMirror -Force)
        if ($existingItems.Count -ne 0) {
            throw 'MirrorRoot must be empty when it is initialized, so unrelated files can never be mistaken for releases.'
        }
        $marker = [ordered]@{
            schemaVersion = 1
            purpose = 'findone-release-mirror'
            applicationId = 'com.findone.app'
            initializedAt = [DateTimeOffset]::UtcNow.ToString('o')
        }
        Write-Utf8JsonAtomically -Value $marker -Path $markerPath
    }
}

# ConvertFrom-SecureString without -Key uses Windows DPAPI for the current Windows user.
$configuration = [ordered]@{
    schemaVersion = 3
    repositoryRoot = $repoRoot
    keystorePath = $resolvedKeystore
    keyAlias = $KeyAlias
    expectedSigningCertificateSha256 = $actualSigningCertificateSha256
    orchestratorBuildScriptSha256 = $orchestratorBuildScriptSha256
    storePasswordDpapi = ConvertFrom-SecureString $StorePassword
    keyPasswordDpapi = ConvertFrom-SecureString $KeyPassword
    keepReleases = 2
    mirrorRoot = $configuredMirror
    contentReleaseEndpoint = $normalizedContentReleaseEndpoint
    configuredAt = [DateTimeOffset]::UtcNow.ToString('o')
}
Write-Utf8JsonAtomically -Value $configuration -Path $configurationPath

if (-not $SkipHookActivation) {
    foreach ($hookPath in @('.githooks/pre-commit', '.githooks/post-commit')) {
        $trackedHook = (& git -C $repoRoot ls-files --error-unmatch -- $hookPath 2>$null).ToString().Trim()
        if ($LASTEXITCODE -ne 0 -or $trackedHook -ne $hookPath) {
            throw "The tracked $hookPath hook is missing. Commit the automation files before enabling it."
        }
    }
    & git -C $repoRoot config --local core.hooksPath .githooks
    if ($LASTEXITCODE -ne 0) { throw 'Failed to enable the repository-local hooks path.' }
}

Write-Host "DPAPI-protected release configuration saved locally: $configurationPath"
if ($SkipHookActivation) {
    Write-Host 'The repository hooks were not enabled.'
} else {
    Write-Host 'The pre-commit preflight and synchronous post-commit release hooks are enabled for this clone.'
}
