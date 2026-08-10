[CmdletBinding()]
param(
    [string]$SourceRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DistRoot,
    [string]$KeystorePath = $env:FINDONE_KEYSTORE_PATH,
    [string]$KeyAlias = $env:FINDONE_KEY_ALIAS,
    [Security.SecureString]$StorePassword,
    [Security.SecureString]$KeyPassword,
    [string]$ExpectedSigningCertificateSha256,
    [string]$ExpectedOrchestratorScriptSha256,
    [string]$ExpectedCommit,
    [string]$ContentReleaseEndpoint = $env:FINDONE_CONTENT_RELEASE_ENDPOINT,
    [ValidateRange(0, 2100000000)]
    [int]$VersionCodeOverride = 0,
    [string]$VersionNameOverride,
    [ValidateRange(1, 20)]
    [int]$KeepReleases = 2,
    [string]$MirrorRoot
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


$orchestratorScriptSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash.ToLowerInvariant()
if (-not [string]::IsNullOrWhiteSpace($ExpectedOrchestratorScriptSha256) -and
    ($ExpectedOrchestratorScriptSha256 -notmatch '^[0-9a-fA-F]{64}$' -or
    $orchestratorScriptSha256 -ne $ExpectedOrchestratorScriptSha256.ToLowerInvariant())) {
    throw 'The active release builder does not match the orchestrator SHA-256 pinned during setup. Run setup again after reviewing the change.'
}

$trustedRepositoryRoot = Split-Path -Parent $PSScriptRoot
$signingPinPath = Join-Path $trustedRepositoryRoot 'config\release-signing-certificate.sha256'
if (-not (Test-Path -LiteralPath $signingPinPath -PathType Leaf)) {
    throw "Tracked signing certificate pin is missing: $signingPinPath"
}
$trackedSigningCertificateSha256 = (Get-Content -Raw -Encoding ASCII -LiteralPath $signingPinPath).Trim().ToLowerInvariant()
if ($trackedSigningCertificateSha256 -notmatch '^[0-9a-f]{64}$') {
    throw "Tracked signing certificate pin is invalid: $signingPinPath"
}
if (-not [string]::IsNullOrWhiteSpace($ExpectedSigningCertificateSha256) -and
    ($ExpectedSigningCertificateSha256 -notmatch '^[0-9a-fA-F]{64}$' -or
    $ExpectedSigningCertificateSha256.ToLowerInvariant() -ne $trackedSigningCertificateSha256)) {
    throw 'Configured signing certificate pin does not match the reviewed tracked pin. Run setup again only after resolving the mismatch.'
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

function Assert-SafeReleaseRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$MustExist
    )

    $root = Get-FullPath $Path
    if (Test-IsFileSystemRoot $root) { throw "A filesystem root cannot be used as a release root: $root" }
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        if ($MustExist) { throw "Release root does not exist: $root" }
        return $root
    }
    $rootItem = Get-Item -LiteralPath $root -Force
    Assert-FinDoneReparsePointAllowed -Item $rootItem -Context 'Release root'
    return $root
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

function Assert-SigningEnvironmentCleared {
    foreach ($name in @(
        'FINDONE_KEYSTORE_PATH',
        'FINDONE_KEY_ALIAS',
        'FINDONE_STORE_PASSWORD',
        'FINDONE_KEY_PASSWORD',
        'FINDONE_APKSIGNER_STORE_PASSWORD',
        'FINDONE_APKSIGNER_KEY_PASSWORD'
    )) {
        if ($null -ne [Environment]::GetEnvironmentVariable($name, 'Process')) {
            throw "Signing environment isolation failed before Gradle: $name"
        }
    }
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

function Get-AndroidSdkPath {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $localProperties = Join-Path $ProjectRoot 'local.properties'
    if (-not (Test-Path -LiteralPath $localProperties -PathType Leaf)) {
        throw "local.properties was not found in the release worktree: $localProperties"
    }

    $line = Get-Content -LiteralPath $localProperties -Encoding UTF8 |
        Where-Object { $_ -match '^\s*sdk\.dir\s*=' } |
        Select-Object -First 1
    if (-not $line) { throw 'local.properties does not contain sdk.dir.' }

    $value = ($line -replace '^\s*sdk\.dir\s*=\s*', '').Trim()
    $value = $value.Replace('\:', ':').Replace('\\', '\')
    if ([string]::IsNullOrWhiteSpace($value)) { throw 'local.properties sdk.dir is empty.' }
    $sdkPath = Get-FullPath $value
    if (-not (Test-Path -LiteralPath $sdkPath -PathType Container)) {
        throw "Android SDK directory does not exist: $sdkPath"
    }
    return $sdkPath
}

function Get-LatestBuildTools {
    param([Parameter(Mandatory = $true)][string]$SdkPath)

    $buildToolsRoot = Join-Path $SdkPath 'build-tools'
    $candidates = @(Get-ChildItem -LiteralPath $buildToolsRoot -Directory -ErrorAction Stop | ForEach-Object {
        try {
            [pscustomobject]@{ Directory = $_; Version = [version]$_.Name }
        } catch {
            # Preview or vendor-specific build-tools directories are ignored.
        }
    } | Sort-Object Version -Descending)

    foreach ($candidate in $candidates) {
        $apkSigner = Join-Path $candidate.Directory.FullName 'apksigner.bat'
        $apkSignerJar = Join-Path $candidate.Directory.FullName 'lib\apksigner.jar'
        $aapt = Join-Path $candidate.Directory.FullName 'aapt.exe'
        $zipAlign = Join-Path $candidate.Directory.FullName 'zipalign.exe'
        if ((Test-Path -LiteralPath $apkSigner -PathType Leaf) -and
            (Test-Path -LiteralPath $apkSignerJar -PathType Leaf) -and
            (Test-Path -LiteralPath $aapt -PathType Leaf) -and
            (Test-Path -LiteralPath $zipAlign -PathType Leaf)) {
            return [pscustomobject]@{
                ApkSigner = $apkSigner
                ApkSignerJar = $apkSignerJar
                Aapt = $aapt
                ZipAlign = $zipAlign
            }
        }
    }
    throw "No Android build-tools installation containing zipalign.exe, apksigner, and aapt.exe was found under $buildToolsRoot"
}

function Get-ValidatedReleaseBundle {
    param([Parameter(Mandatory = $true)][string]$Directory)

    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return $null }
    $item = Get-Item -LiteralPath $Directory -Force
    if (-not (Test-FinDoneReparsePointAllowed -Item $item)) { return $null }

    $files = @(Get-ChildItem -LiteralPath $Directory -File -Force)
    $childDirectories = @(Get-ChildItem -LiteralPath $Directory -Directory -Force)
    if ($files.Count -ne 3 -or $childDirectories.Count -ne 0) { return $null }

    $manifestPath = Join-Path $Directory 'release-manifest.json'
    $sumsPath = Join-Path $Directory 'SHA256SUMS.txt'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $sumsPath -PathType Leaf)) { return $null }

    $apks = @(Get-ChildItem -LiteralPath $Directory -File -Filter 'FinDone-*.apk')
    if ($apks.Count -ne 1) { return $null }

    try {
        $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
        if ($manifest.applicationId -ne 'com.findone.app') { return $null }
        $builtAt = [DateTimeOffset]::Parse($manifest.builtAt, [Globalization.CultureInfo]::InvariantCulture)
        $sumLine = (Get-Content -Raw -Encoding ASCII -LiteralPath $sumsPath).Trim()
        if ($sumLine -notmatch '^([0-9a-fA-F]{64})\s{2}([^\\/\r\n]+\.apk)$') { return $null }
        if ($Matches[2] -ne $apks[0].Name) { return $null }
        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $apks[0].FullName).Hash.ToLowerInvariant()
        if ($actualHash -ne $Matches[1].ToLowerInvariant()) { return $null }
        if ($manifest.releaseApkSha256.ToString().ToLowerInvariant() -ne $actualHash) { return $null }

        return [pscustomobject]@{
            Directory = $item
            BuiltAt = $builtAt
            ApkSha256 = $actualHash
        }
    } catch {
        return $null
    }
}

function Remove-OldReleaseBundles {
    param(
        [Parameter(Mandatory = $true)][string]$ReleaseRoot,
        [Parameter(Mandatory = $true)][int]$Keep,
        [Parameter(Mandatory = $true)][string]$ProtectedDirectory
    )

    $root = Assert-SafeReleaseRoot -Path $ReleaseRoot -MustExist
    $rootWithSeparator = $root + [System.IO.Path]::DirectorySeparatorChar
    $protected = Get-FullPath $ProtectedDirectory
    if (-not $protected.StartsWith($rootWithSeparator, [StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path -Parent $protected) -ne $root) {
        throw "The protected release is outside its configured root: $protected"
    }
    $validBundles = @()

    foreach ($directory in @(Get-ChildItem -LiteralPath $root -Directory -Force)) {
        if ($directory.Name -notmatch '^findone-[0-9A-Za-z][0-9A-Za-z.+_-]*-\d{8}-\d{6}(?:\d{3})?(?:-[0-9a-f]{7,40})?$') {
            continue
        }
        $bundle = Get-ValidatedReleaseBundle -Directory $directory.FullName
        if ($null -eq $bundle) {
            Write-Warning "Preserving unrecognized release-like directory: $($directory.FullName)"
            continue
        }
        $candidatePath = Get-FullPath $directory.FullName
        if (-not $candidatePath.StartsWith($rootWithSeparator, [StringComparison]::OrdinalIgnoreCase) -or
            (Split-Path -Parent $candidatePath) -ne $root) {
            throw "Refusing to prune a path outside the configured release root: $candidatePath"
        }
        $validBundles += $bundle
    }

    $protectedBundle = @($validBundles | Where-Object {
        (Get-FullPath $_.Directory.FullName).Equals($protected, [StringComparison]::OrdinalIgnoreCase)
    })
    if ($protectedBundle.Count -ne 1) {
        throw "The newly published release did not pass retention validation: $protected"
    }
    $orderedBundles = @($protectedBundle[0]) + @($validBundles | Where-Object {
        -not (Get-FullPath $_.Directory.FullName).Equals($protected, [StringComparison]::OrdinalIgnoreCase)
    } | Sort-Object -Property BuiltAt, @{ Expression = { $_.Directory.Name } } -Descending)
    $toDelete = @($orderedBundles | Select-Object -Skip $Keep)
    foreach ($bundle in $toDelete) {
        # Re-resolve and revalidate immediately before deletion. If OneDrive or another
        # process swapped the entry after enumeration, preserve it instead of guessing.
        $root = Assert-SafeReleaseRoot -Path $root -MustExist
        $candidatePath = Get-FullPath $bundle.Directory.FullName
        if (-not $candidatePath.StartsWith($rootWithSeparator, [StringComparison]::OrdinalIgnoreCase) -or
            (Split-Path -Parent $candidatePath) -ne $root -or
            (Split-Path -Leaf $candidatePath) -notmatch '^findone-[0-9A-Za-z][0-9A-Za-z.+_-]*-\d{8}-\d{6}(?:\d{3})?(?:-[0-9a-f]{7,40})?$') {
            throw "Refusing to prune a release whose path changed after validation: $candidatePath"
        }
        if (-not (Test-Path -LiteralPath $candidatePath -PathType Container)) {
            Write-Warning "Release disappeared before retention; preserving state: $candidatePath"
            continue
        }
        $candidateItem = Get-Item -LiteralPath $candidatePath -Force
        if (-not (Test-FinDoneReparsePointAllowed -Item $candidateItem)) {
            Write-Warning "Release became a forbidden reparse point before retention and was preserved: $candidatePath"
            continue
        }
        $freshBundle = Get-ValidatedReleaseBundle -Directory $candidatePath
        if ($null -eq $freshBundle -or
            $freshBundle.ApkSha256 -ne $bundle.ApkSha256 -or
            $freshBundle.BuiltAt -ne $bundle.BuiltAt) {
            Write-Warning "Release changed after retention enumeration and was preserved: $candidatePath"
            continue
        }
        Remove-Item -LiteralPath $candidatePath -Recurse -Force
        Write-Host "Pruned old release bundle: $($candidateItem.Name)"
    }
}

function Assert-MirrorRoot {
    param([Parameter(Mandatory = $true)][string]$Path)

    $root = Assert-SafeReleaseRoot -Path $Path -MustExist
    $markerPath = Join-Path $root '.findone-release-root.json'
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw "Configured release mirror is missing its safety marker: $markerPath"
    }
    $marker = Get-Content -Raw -Encoding UTF8 -LiteralPath $markerPath | ConvertFrom-Json
    if ($marker.schemaVersion -ne 1 -or $marker.purpose -ne 'findone-release-mirror' -or
        $marker.applicationId -ne 'com.findone.app') {
        throw "Configured release mirror has an invalid safety marker: $markerPath"
    }
    return $root
}

function Copy-ReleaseToMirror {
    param(
        [Parameter(Mandatory = $true)][string]$ReleaseDirectory,
        [Parameter(Mandatory = $true)][string]$ReleaseMirrorRoot
    )

    $mirror = Assert-MirrorRoot $ReleaseMirrorRoot
    $name = Split-Path -Leaf $ReleaseDirectory
    $destination = Join-Path $mirror $name
    $sourceBundle = Get-ValidatedReleaseBundle -Directory $ReleaseDirectory
    if ($null -eq $sourceBundle) { throw "Local release bundle failed validation: $ReleaseDirectory" }

    if (Test-Path -LiteralPath $destination) {
        $destinationBundle = Get-ValidatedReleaseBundle -Directory $destination
        if ($null -ne $destinationBundle -and $destinationBundle.ApkSha256 -eq $sourceBundle.ApkSha256) {
            Write-Host "Release already exists in mirror: $destination"
            return $destination
        }
        throw "Mirror destination already exists but is not the same validated release: $destination"
    }

    $partial = Join-Path $mirror ('.findone-partial-' + [guid]::NewGuid().ToString('N'))
    try {
        Copy-Item -LiteralPath $ReleaseDirectory -Destination $partial -Recurse
        if ($null -eq (Get-ValidatedReleaseBundle -Directory $partial)) {
            throw "Copied release failed validation before publication: $partial"
        }
        Move-Item -LiteralPath $partial -Destination $destination
    } finally {
        if (Test-Path -LiteralPath $partial) {
            $partialFull = Get-FullPath $partial
            $mirror = Assert-SafeReleaseRoot -Path $mirror -MustExist
            $mirrorWithSeparator = $mirror + [System.IO.Path]::DirectorySeparatorChar
            $partialItem = Get-Item -LiteralPath $partialFull -Force
            if ((Test-FinDoneReparsePointAllowed -Item $partialItem) -and
                $partialFull.StartsWith($mirrorWithSeparator, [StringComparison]::OrdinalIgnoreCase) -and
                (Split-Path -Parent $partialFull) -eq $mirror -and
                (Split-Path -Leaf $partialFull) -like '.findone-partial-*') {
                Remove-Item -LiteralPath $partialFull -Recurse -Force
            }
        }
    }
    Write-Host "Copied release to mirror: $destination"
    return $destination
}

$source = Get-FullPath $SourceRoot
if (-not (Test-Path -LiteralPath (Join-Path $source 'gradlew.bat') -PathType Leaf)) {
    throw "Not a FinDone source root: $source"
}
if ([string]::IsNullOrWhiteSpace($DistRoot)) { $DistRoot = Join-Path $source 'dist' }
$dist = Assert-SafeReleaseRoot -Path $DistRoot
if ([string]::IsNullOrWhiteSpace($KeystorePath)) { throw 'FINDONE_KEYSTORE_PATH or -KeystorePath is required.' }
if ($KeyAlias -notmatch '^[A-Za-z0-9._-]+$') {
    throw 'FINDONE_KEY_ALIAS or -KeyAlias must contain only ASCII letters, digits, dot, underscore, and hyphen.'
}

# Preserve backward compatibility with the documented manual command, but turn
# plaintext environment inputs into SecureString values and remove every signing
# variable before Git, Gradle, project plugins, or tests execute.
$environmentStorePassword = [Environment]::GetEnvironmentVariable('FINDONE_STORE_PASSWORD', 'Process')
$environmentKeyPassword = [Environment]::GetEnvironmentVariable('FINDONE_KEY_PASSWORD', 'Process')
Clear-SigningEnvironment
try {
    if ($null -eq $StorePassword) {
        if ([string]::IsNullOrWhiteSpace($environmentStorePassword)) {
            throw 'A DPAPI-decrypted -StorePassword or process-local FINDONE_STORE_PASSWORD is required.'
        }
        $StorePassword = ConvertTo-SecureString $environmentStorePassword -AsPlainText -Force
    }
    if ($null -eq $KeyPassword) {
        if ([string]::IsNullOrWhiteSpace($environmentKeyPassword)) {
            throw 'A DPAPI-decrypted -KeyPassword or process-local FINDONE_KEY_PASSWORD is required.'
        }
        $KeyPassword = ConvertTo-SecureString $environmentKeyPassword -AsPlainText -Force
    }
} finally {
    $environmentStorePassword = $null
    $environmentKeyPassword = $null
    Clear-SigningEnvironment
}
if ($StorePassword.Length -eq 0 -or $KeyPassword.Length -eq 0) { throw 'Signing passwords must not be empty.' }
$keystore = (Resolve-Path -LiteralPath $KeystorePath -ErrorAction Stop).Path

[Uri]$contentReleaseUri = $null
if ([string]::IsNullOrWhiteSpace($ContentReleaseEndpoint) -or
    -not [Uri]::TryCreate($ContentReleaseEndpoint.Trim(), [UriKind]::Absolute, [ref]$contentReleaseUri) -or
    $contentReleaseUri.Scheme -cne 'https' -or
    [string]::IsNullOrWhiteSpace($contentReleaseUri.Host) -or
    -not [string]::IsNullOrEmpty($contentReleaseUri.UserInfo) -or
    -not [string]::IsNullOrEmpty($contentReleaseUri.Query) -or
    -not [string]::IsNullOrEmpty($contentReleaseUri.Fragment)) {
    throw 'A public HTTPS content release endpoint without credentials, query, or fragment is required.'
}
$normalizedContentReleaseEndpoint = $contentReleaseUri.AbsoluteUri.TrimEnd('/')

$head = (& git -C $source rev-parse --verify HEAD 2>&1).ToString().Trim()
if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') { throw "Unable to resolve Git HEAD in $source" }
$isExactCommitBuild = -not [string]::IsNullOrWhiteSpace($ExpectedCommit)
if ($isExactCommitBuild) {
    if ($ExpectedCommit -notmatch '^[0-9a-fA-F]{40}$' -or $head -ne $ExpectedCommit.ToLowerInvariant()) {
        throw "Release worktree HEAD ($head) does not match expected commit ($ExpectedCommit)."
    }
    $trackedChanges = @(& git -C $source status --porcelain --untracked-files=no)
    if ($LASTEXITCODE -ne 0 -or $trackedChanges.Count -ne 0) {
        throw 'The exact-commit release worktree contains tracked changes; refusing to build.'
    }
}

$publishedDirectory = $null
try {
    $buildTools = Get-LatestBuildTools -SdkPath (Get-AndroidSdkPath -ProjectRoot $source)
    $trustedKeystoreHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $keystore).Hash
    $trustedToolHashes = @{}
    foreach ($toolPath in @($buildTools.ApkSigner, $buildTools.ApkSignerJar, $buildTools.Aapt, $buildTools.ZipAlign)) {
        $trustedToolHashes[$toolPath] = (Get-FileHash -Algorithm SHA256 -LiteralPath $toolPath).Hash
    }

    $gradleArguments = @('--no-daemon', 'clean', 'test', 'lintRelease', 'assembleRelease', '--console=plain')
    if ($VersionCodeOverride -gt 0) { $gradleArguments += "-Pfindone.versionCode=$VersionCodeOverride" }
    if (-not [string]::IsNullOrWhiteSpace($VersionNameOverride)) {
        $gradleArguments += "-Pfindone.versionName=$VersionNameOverride"
    }
    $gradleArguments += "-Pfindone.contentReleaseEndpoint=$normalizedContentReleaseEndpoint"

    Push-Location $source
    try {
        Clear-SigningEnvironment
        Assert-SigningEnvironmentCleared
        & (Join-Path $source 'gradlew.bat') @gradleArguments
        if ($LASTEXITCODE -ne 0) { throw "Gradle release build failed with exit code $LASTEXITCODE." }
    } finally {
        Clear-SigningEnvironment
        Pop-Location
    }

    $generatedBuildConfigPath = Join-Path $source 'app\build\generated\source\buildConfig\release\com\findone\app\BuildConfig.java'
    if (-not (Test-Path -LiteralPath $generatedBuildConfigPath -PathType Leaf)) {
        throw "Gradle did not generate the release BuildConfig: $generatedBuildConfigPath"
    }
    $generatedBuildConfig = Get-Content -Raw -Encoding UTF8 -LiteralPath $generatedBuildConfigPath
    $endpointPattern = 'CONTENT_RELEASE_ENDPOINT\s*=\s*"' + [regex]::Escape($normalizedContentReleaseEndpoint) + '"\s*;'
    if ($generatedBuildConfig -notmatch $endpointPattern) {
        throw 'The generated release BuildConfig does not contain the configured content release endpoint.'
    }

    foreach ($toolPath in $trustedToolHashes.Keys) {
        $currentHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $toolPath).Hash
        if ($currentHash -ne $trustedToolHashes[$toolPath]) {
            throw "Android build tool changed while Gradle/project code was running; refusing to sign: $toolPath"
        }
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $keystore).Hash -ne $trustedKeystoreHash) {
        throw 'The signing keystore changed while Gradle/project code was running; refusing to sign.'
    }

    $releaseOutputDirectory = Join-Path $source 'app\build\outputs\apk\release'
    $unsignedApk = Join-Path $releaseOutputDirectory 'app-release-unsigned.apk'
    $alignedApk = Join-Path $releaseOutputDirectory 'app-release-aligned.apk'
    $apk = Join-Path $releaseOutputDirectory 'app-release-signed.apk'
    if (-not (Test-Path -LiteralPath $unsignedApk -PathType Leaf)) {
        throw "Gradle did not produce the required unsigned release APK: $unsignedApk"
    }
    $unexpectedSignedApk = Join-Path $releaseOutputDirectory 'app-release.apk'
    if (Test-Path -LiteralPath $unexpectedSignedApk -PathType Leaf) {
        throw "Gradle unexpectedly produced a signed release; external trusted signing is required: $unexpectedSignedApk"
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $unsignedVerifyOutput = @(& $buildTools.ApkSigner verify $unsignedApk 2>&1)
        $unsignedVerifyExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($unsignedVerifyExitCode -eq 0) {
        throw 'Gradle output already contains a valid APK signature; refusing to apply the private signing key.'
    }

    & $buildTools.ZipAlign -f -p 4 $unsignedApk $alignedApk
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $alignedApk -PathType Leaf)) {
        throw "zipalign failed with exit code $LASTEXITCODE."
    }

    $storePasswordPlainText = Convert-SecureValueToPlainText $StorePassword
    $keyPasswordPlainText = Convert-SecureValueToPlainText $KeyPassword
    try {
        # These two variables exist only while the trusted SDK apksigner process runs.
        # Gradle and project-controlled code have already exited at this point.
        [Environment]::SetEnvironmentVariable('FINDONE_APKSIGNER_STORE_PASSWORD', $storePasswordPlainText, 'Process')
        [Environment]::SetEnvironmentVariable('FINDONE_APKSIGNER_KEY_PASSWORD', $keyPasswordPlainText, 'Process')
        $storePasswordPlainText = $null
        $keyPasswordPlainText = $null

        & $buildTools.ApkSigner sign `
            --ks $keystore `
            --ks-key-alias $KeyAlias `
            --ks-pass 'env:FINDONE_APKSIGNER_STORE_PASSWORD' `
            --key-pass 'env:FINDONE_APKSIGNER_KEY_PASSWORD' `
            --v1-signing-enabled true `
            --v2-signing-enabled true `
            --v3-signing-enabled true `
            --v4-signing-enabled false `
            --out $apk `
            $alignedApk
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $apk -PathType Leaf)) {
            throw "External APK signing failed with exit code $LASTEXITCODE."
        }
    } finally {
        $storePasswordPlainText = $null
        $keyPasswordPlainText = $null
        Clear-SigningEnvironment
    }

    & $buildTools.ZipAlign -c -p 4 $apk
    if ($LASTEXITCODE -ne 0) { throw "Signed APK zip alignment verification failed with exit code $LASTEXITCODE." }

    $verifyOutput = @(& $buildTools.ApkSigner verify --verbose --print-certs $apk 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "APK signature verification failed: $($verifyOutput -join [Environment]::NewLine)" }
    $certificateLine = $verifyOutput | Where-Object { $_ -match 'certificate SHA-256 digest:\s*([0-9a-fA-F]{64})' } | Select-Object -First 1
    if (-not $certificateLine -or $certificateLine -notmatch '([0-9a-fA-F]{64})') {
        throw 'Could not read the signing certificate SHA-256 from apksigner output.'
    }
    $certificateSha256 = $Matches[1].ToLowerInvariant()
    if ($certificateSha256 -ne $trackedSigningCertificateSha256) {
        throw "Signed APK certificate SHA-256 does not match the reviewed tracked pin. Expected $trackedSigningCertificateSha256, got $certificateSha256."
    }
    $verifyText = $verifyOutput -join "`n"
    foreach ($scheme in @(2, 3)) {
        if ($verifyText -notmatch "(?mi)^Verified using v$scheme scheme[^:]*:\s*true\s*$") {
            throw "APK signature verification did not explicitly confirm v$scheme signing."
        }
    }
    if ($verifyText -notmatch '(?mi)^Verified using v1 scheme[^:]*:\s*true\s*$') {
        Write-Warning 'APK v1 signing was not reported as verified; v2 and v3 remain mandatory for minSdk 26.'
    }

    $permissionOutput = @(& $buildTools.Aapt dump permissions $apk 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "APK permission inspection failed: $($permissionOutput -join [Environment]::NewLine)" }
    if (($permissionOutput -join "`n") -notmatch 'android\.permission\.INTERNET') {
        throw 'The release APK is missing android.permission.INTERNET required for verified content updates.'
    }

    $badgingOutput = @(& $buildTools.Aapt dump badging $apk 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "APK version inspection failed: $($badgingOutput -join [Environment]::NewLine)" }
    $packageLine = $badgingOutput | Where-Object { $_ -match '^package:' } | Select-Object -First 1
    if (-not $packageLine -or
        $packageLine -notmatch "name='([^']+)'\s+versionCode='(\d+)'\s+versionName='([^']*)'") {
        throw 'Could not parse applicationId, versionCode, and versionName from the built APK.'
    }
    $applicationId = $Matches[1]
    $actualVersionCode = [int64]$Matches[2]
    $actualVersionName = $Matches[3]
    if ($applicationId -ne 'com.findone.app') { throw "Unexpected applicationId in APK: $applicationId" }
    if ($VersionCodeOverride -gt 0 -and $actualVersionCode -ne $VersionCodeOverride) {
        throw "APK versionCode $actualVersionCode does not match requested override $VersionCodeOverride."
    }
    if (-not [string]::IsNullOrWhiteSpace($VersionNameOverride) -and $actualVersionName -ne $VersionNameOverride) {
        throw "APK versionName '$actualVersionName' does not match requested override '$VersionNameOverride'."
    }

    $contentManifestPath = Join-Path $source 'app\src\main\assets\content-manifest.json'
    $contentManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $contentManifestPath | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($contentManifest.sha256) -or -not $contentManifest.contentDbVersion) {
        throw 'content-manifest.json is missing contentDbVersion or sha256.'
    }
    $userRepositoryPath = Join-Path $source 'app\src\main\java\com\findone\app\data\UserRepository.kt'
    $userRepositorySource = Get-Content -Raw -Encoding UTF8 -LiteralPath $userRepositoryPath
    $userDbVersionMatch = [regex]::Match(
        $userRepositorySource,
        '(?m)^\s*private\s+const\s+val\s+USER_DB_VERSION\s*=\s*(\d+)\s*$'
    )
    if (-not $userDbVersionMatch.Success) {
        throw 'Could not derive USER_DB_VERSION from UserRepository.kt.'
    }
    $userDbVersion = [int]$userDbVersionMatch.Groups[1].Value
    if ($userDbVersion -lt 1) { throw "Invalid USER_DB_VERSION: $userDbVersion" }

    if ($isExactCommitBuild) {
        $trackedChangesAfterBuild = @(& git -C $source status --porcelain --untracked-files=no)
        if ($LASTEXITCODE -ne 0 -or $trackedChangesAfterBuild.Count -ne 0) {
            throw 'The build modified tracked files in the exact-commit worktree; refusing to publish.'
        }
    }

    $apkSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $apk).Hash.ToLowerInvariant()
    $builtAt = [DateTimeOffset]::UtcNow
    $stamp = $builtAt.ToString('yyyyMMdd-HHmmssfff')
    $safeVersionName = $actualVersionName -replace '[^0-9A-Za-z._+-]', '_'
    $commitSuffix = if ($isExactCommitBuild) { '-' + $head.Substring(0, 10) } else { '' }
    $releaseName = "findone-$safeVersionName-$stamp$commitSuffix"

    New-Item -ItemType Directory -Path $dist -Force | Out-Null
    $dist = Assert-SafeReleaseRoot -Path $dist -MustExist
    $stagingDirectory = Join-Path $dist ('.findone-partial-' + [guid]::NewGuid().ToString('N'))
    $publishedDirectory = Join-Path $dist $releaseName
    if (Test-Path -LiteralPath $publishedDirectory) { throw "Release destination already exists: $publishedDirectory" }
    New-Item -ItemType Directory -Path $stagingDirectory | Out-Null

    try {
        $releaseApkName = "FinDone-$safeVersionName.apk"
        $releaseApk = Join-Path $stagingDirectory $releaseApkName
        Copy-Item -LiteralPath $apk -Destination $releaseApk

        $releaseManifest = [ordered]@{
            schemaVersion = 3
            distributionChannel = 'private_onedrive_sideload'
            publicStoreRelease = $false
            targetUser = 'self_only'
            internetPermission = $true
            oneDriveRuntimeSync = $false
            updateSource = 'https_stable_content_channel'
            contentReleaseEndpoint = $normalizedContentReleaseEndpoint
            directOneDriveApi = $false
            applicationId = $applicationId
            versionCode = $actualVersionCode
            versionName = $actualVersionName
            contentDbVersion = $contentManifest.contentDbVersion
            contentDbSha256 = $contentManifest.sha256
            userDbSchemaVersion = $userDbVersion
            signingCertificateSha256 = $certificateSha256
            orchestratorBuildScriptSha256 = $orchestratorScriptSha256
            releaseApkSha256 = $apkSha256
            gitCommit = $head
            sourceSnapshot = if ($isExactCommitBuild) { 'exact_git_commit' } else { 'working_tree' }
            builtAt = $builtAt.ToString('o')
        }
        $manifestJson = $releaseManifest | ConvertTo-Json
        [System.IO.File]::WriteAllText(
            (Join-Path $stagingDirectory 'release-manifest.json'),
            $manifestJson + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
        [System.IO.File]::WriteAllText(
            (Join-Path $stagingDirectory 'SHA256SUMS.txt'),
            "$apkSha256  $releaseApkName`r`n",
            [System.Text.Encoding]::ASCII
        )

        if ($null -eq (Get-ValidatedReleaseBundle -Directory $stagingDirectory)) {
            throw 'The staged release bundle failed checksum or metadata validation.'
        }
        Move-Item -LiteralPath $stagingDirectory -Destination $publishedDirectory
    } finally {
        if (Test-Path -LiteralPath $stagingDirectory) {
            $stagingFull = Get-FullPath $stagingDirectory
            $dist = Assert-SafeReleaseRoot -Path $dist -MustExist
            $distWithSeparator = $dist + [System.IO.Path]::DirectorySeparatorChar
            $stagingItem = Get-Item -LiteralPath $stagingFull -Force
            if ((Test-FinDoneReparsePointAllowed -Item $stagingItem) -and
                $stagingFull.StartsWith($distWithSeparator, [StringComparison]::OrdinalIgnoreCase) -and
                (Split-Path -Parent $stagingFull) -eq $dist -and
                (Split-Path -Leaf $stagingFull) -like '.findone-partial-*') {
                Remove-Item -LiteralPath $stagingFull -Recurse -Force
            }
        }
    }

    Remove-OldReleaseBundles -ReleaseRoot $dist -Keep $KeepReleases -ProtectedDirectory $publishedDirectory

    if (-not [string]::IsNullOrWhiteSpace($MirrorRoot)) {
        $mirroredDirectory = Copy-ReleaseToMirror -ReleaseDirectory $publishedDirectory -ReleaseMirrorRoot $MirrorRoot
        Remove-OldReleaseBundles `
            -ReleaseRoot (Get-FullPath $MirrorRoot) `
            -Keep $KeepReleases `
            -ProtectedDirectory $mirroredDirectory
    }

    Write-Host "Release completed: $publishedDirectory"
    return $publishedDirectory
} finally {
    Clear-SigningEnvironment
}
