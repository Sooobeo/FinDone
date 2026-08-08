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

function Get-FinDoneGitRepositoryLocalEnvironmentVariableNames {
    # Keep this list byte-for-byte equivalent to `git rev-parse --local-env-vars`.
    # These variables describe one repository and must not leak from the hook's
    # main worktree into a detached child worktree.
    return @(
        'GIT_ALTERNATE_OBJECT_DIRECTORIES',
        'GIT_CONFIG',
        'GIT_CONFIG_PARAMETERS',
        'GIT_CONFIG_COUNT',
        'GIT_OBJECT_DIRECTORY',
        'GIT_DIR',
        'GIT_WORK_TREE',
        'GIT_IMPLICIT_WORK_TREE',
        'GIT_GRAFT_FILE',
        'GIT_INDEX_FILE',
        'GIT_NO_REPLACE_OBJECTS',
        'GIT_REPLACE_REF_BASE',
        'GIT_PREFIX',
        'GIT_SHALLOW_FILE',
        'GIT_COMMON_DIR'
    )
}

function Clear-FinDoneGitRepositoryEnvironment {
    foreach ($name in @(Get-FinDoneGitRepositoryLocalEnvironmentVariableNames)) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
}

function Get-FinDoneGitExecutable {
    $uniquePaths = @(
        Get-Command git.exe -CommandType Application -All -ErrorAction Stop |
            Select-Object -ExpandProperty Source -Unique
    )
    if ($uniquePaths.Count -eq 0 -or [string]::IsNullOrWhiteSpace([string]$uniquePaths[0])) {
        throw 'Unable to resolve git.exe from PATH.'
    }
    return [string]$uniquePaths[0]
}

function Write-FinDoneCleanupDiagnostic {
    param([Parameter(Mandatory = $true)][string]$Message)

    try {
        [Console]::Error.WriteLine("[FinDone release cleanup] $Message")
    } catch {
        # Cleanup diagnostics are intentionally non-throwing, including when stderr
        # is unavailable or the caller configured WarningPreference=Stop.
    }
}

function Invoke-FinDoneGitCleanupCommand {
    param([Parameter(Mandatory = $true)][string[]]$GitArguments)

    $gitCommand = Get-FinDoneGitExecutable
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell promotes redirected native stderr to ErrorRecord objects.
        # Capture it with a non-terminating preference so a nonzero Git cleanup exit
        # can be handled explicitly instead of masking the release result.
        $ErrorActionPreference = 'Continue'
        $commandOutput = @(& $gitCommand @GitArguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    return [pscustomobject]@{
        ExitCode = [int]$exitCode
        Output = (($commandOutput | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine).Trim()
    }
}

function Assert-FinDoneDirectoryTreeSafeForRecursiveRemoval {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    $rootFull = Get-FullPath $RootPath
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($rootFull)
    while ($pending.Count -gt 0) {
        $currentPath = $pending.Pop()
        $currentItem = Get-Item -LiteralPath $currentPath -Force
        Assert-FinDoneReparsePointAllowed -Item $currentItem -Context 'Temporary worktree cleanup tree entry'

        foreach ($child in @(Get-ChildItem -LiteralPath $currentPath -Force -ErrorAction Stop)) {
            # Do not descend until the native tag check has proved any reparse point
            # is a Microsoft Cloud placeholder, not a junction/mount/symlink.
            Assert-FinDoneReparsePointAllowed -Item $child -Context 'Temporary worktree cleanup child'
            if ($child.PSIsContainer) { $pending.Push($child.FullName) }
        }
    }
}

function Remove-FinDoneTemporaryWorktree {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$TemporaryRoot,
        [Parameter(Mandatory = $true)][string]$WorktreePath
    )

    try {
        $repositoryFull = Get-FullPath $RepositoryRoot
        $temporaryFull = Get-FullPath $TemporaryRoot
        $worktreeFull = Get-FullPath $WorktreePath
        if (-not (Test-Path -LiteralPath $temporaryFull -PathType Container)) {
            throw "Temporary worktree root does not exist: $temporaryFull"
        }
        $temporaryItem = Get-Item -LiteralPath $temporaryFull -Force
        Assert-FinDoneReparsePointAllowed -Item $temporaryItem -Context 'Temporary release worktree root before cleanup'
        $temporaryWithSeparator = $temporaryFull + [System.IO.Path]::DirectorySeparatorChar
        if (-not $worktreeFull.StartsWith($temporaryWithSeparator, [StringComparison]::OrdinalIgnoreCase) -or
            (Split-Path -Parent $worktreeFull) -ne $temporaryFull -or
            (Split-Path -Leaf $worktreeFull) -cnotmatch '^worktree-[0-9a-f]{32}$') {
            throw "Temporary worktree path failed its direct-child safety check: $worktreeFull"
        }

        if (Test-Path -LiteralPath $worktreeFull) {
            $worktreeItem = Get-Item -LiteralPath $worktreeFull -Force
            Assert-FinDoneReparsePointAllowed -Item $worktreeItem -Context 'Temporary release worktree before Git cleanup'
        }

        $removeResult = Invoke-FinDoneGitCleanupCommand -GitArguments @(
            '-c', 'core.longpaths=true', '-C', $repositoryFull,
            'worktree', 'remove', '--force', $worktreeFull
        )

        if (Test-Path -LiteralPath $worktreeFull) {
            if ($removeResult.ExitCode -ne 0) {
                $detail = if ([string]::IsNullOrWhiteSpace($removeResult.Output)) { 'no Git diagnostic' } else { $removeResult.Output }
                Write-FinDoneCleanupDiagnostic "Git could not completely remove the temporary worktree; using the validated short-path fallback. $detail"
            }

            # Revalidate immediately before moving. Moving the root directory within
            # the same temp volume does not enumerate long descendants and gives the
            # PowerShell fallback enough path headroom for Android build outputs.
            $worktreeItem = Get-Item -LiteralPath $worktreeFull -Force
            Assert-FinDoneReparsePointAllowed -Item $worktreeItem -Context 'Temporary release worktree before short-path fallback'
            $temporaryItem = Get-Item -LiteralPath $temporaryFull -Force
            Assert-FinDoneReparsePointAllowed -Item $temporaryItem -Context 'Temporary release worktree root before short-path fallback'
            if ((Split-Path -Parent $worktreeItem.FullName) -ne $temporaryFull) {
                throw "Temporary worktree parent changed before fallback cleanup: $($worktreeItem.FullName)"
            }

            $systemTemporaryRoot = Get-FullPath ([System.IO.Path]::GetTempPath())
            if ($systemTemporaryRoot.Equals([System.IO.Path]::GetPathRoot($systemTemporaryRoot), [StringComparison]::OrdinalIgnoreCase)) {
                throw "A filesystem root cannot be used for fallback cleanup: $systemTemporaryRoot"
            }
            $systemTemporaryItem = Get-Item -LiteralPath $systemTemporaryRoot -Force
            Assert-FinDoneReparsePointAllowed -Item $systemTemporaryItem -Context 'System temporary root for worktree cleanup'

            $shortCleanupPath = Join-Path $systemTemporaryRoot ('FDR-' + [guid]::NewGuid().ToString('N'))
            if (Test-Path -LiteralPath $shortCleanupPath) {
                throw "Unexpected fallback cleanup path collision: $shortCleanupPath"
            }
            [System.IO.Directory]::Move($worktreeFull, $shortCleanupPath)

            $shortCleanupFull = Get-FullPath $shortCleanupPath
            if ((Split-Path -Parent $shortCleanupFull) -ne $systemTemporaryRoot -or
                (Split-Path -Leaf $shortCleanupFull) -cnotmatch '^FDR-[0-9a-f]{32}$') {
                throw "Short-path fallback failed its direct-child safety check: $shortCleanupFull"
            }
            $shortCleanupItem = Get-Item -LiteralPath $shortCleanupFull -Force
            Assert-FinDoneReparsePointAllowed -Item $shortCleanupItem -Context 'Relocated temporary worktree before fallback cleanup'
            Assert-FinDoneDirectoryTreeSafeForRecursiveRemoval -RootPath $shortCleanupFull

            # Recheck the root and its exact parent immediately before recursive
            # deletion. A forbidden nested reparse point leaves the relocated tree
            # intact for inspection instead of risking traversal outside temp.
            $shortCleanupItem = Get-Item -LiteralPath $shortCleanupFull -Force
            Assert-FinDoneReparsePointAllowed -Item $shortCleanupItem -Context 'Relocated temporary worktree immediately before fallback cleanup'
            if ((Split-Path -Parent $shortCleanupItem.FullName) -ne $systemTemporaryRoot -or
                (Split-Path -Leaf $shortCleanupItem.FullName) -cnotmatch '^FDR-[0-9a-f]{32}$') {
                throw "Relocated temporary worktree changed before recursive cleanup: $($shortCleanupItem.FullName)"
            }
            Remove-Item -LiteralPath $shortCleanupFull -Recurse -Force -ErrorAction Stop
            if (Test-Path -LiteralPath $shortCleanupFull) {
                throw "Short-path fallback did not remove the temporary worktree: $shortCleanupFull"
            }
        }
    } catch {
        # Cleanup must never replace a build/state exception or turn a successful
        # release into a failed commit. Preserve unsafe/locked paths for inspection.
        Write-FinDoneCleanupDiagnostic "Temporary release worktree cleanup was incomplete and did not change the release result: $($_.Exception.Message)"
    } finally {
        try {
            $pruneResult = Invoke-FinDoneGitCleanupCommand -GitArguments @(
                '-c', 'core.longpaths=true', '-C', (Get-FullPath $RepositoryRoot),
                'worktree', 'prune'
            )
            if ($pruneResult.ExitCode -ne 0) {
                $detail = if ([string]::IsNullOrWhiteSpace($pruneResult.Output)) { 'no Git diagnostic' } else { $pruneResult.Output }
                Write-FinDoneCleanupDiagnostic "Git worktree metadata prune was incomplete and did not change the release result: $detail"
            }
        } catch {
            Write-FinDoneCleanupDiagnostic "Git worktree metadata prune could not run and did not change the release result: $($_.Exception.Message)"
        }
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

$repoRoot = Get-FullPath (Split-Path -Parent $PSScriptRoot)
$gitExecutable = Get-FinDoneGitExecutable
Clear-FinDoneGitRepositoryEnvironment
Clear-SigningEnvironment
$resolvedCommit = (& $gitExecutable -C $repoRoot rev-parse --verify "$Commit^{commit}" 2>&1).ToString().Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $resolvedCommit -notmatch '^[0-9a-f]{40}$') {
    throw "The post-commit release target is not a valid commit: $Commit"
}

$gitCommonText = (& $gitExecutable -C $repoRoot rev-parse --git-common-dir 2>&1).ToString().Trim()
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
    & $gitExecutable -C $repoRoot worktree add --detach $worktreePath $resolvedCommit
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
        if ($null -ne $storePassword) {
            try {
                $storePassword.Dispose()
            } catch {
                Write-FinDoneCleanupDiagnostic "Store password SecureString disposal was incomplete and did not change the release result: $($_.Exception.Message)"
            }
        }
        if ($null -ne $keyPassword) {
            try {
                $keyPassword.Dispose()
            } catch {
                Write-FinDoneCleanupDiagnostic "Key password SecureString disposal was incomplete and did not change the release result: $($_.Exception.Message)"
            }
        }
        $storePassword = $null
        $keyPassword = $null
        try {
            Clear-SigningEnvironment
        } catch {
            Write-FinDoneCleanupDiagnostic "Inner signing environment cleanup was incomplete and did not change the release result: $($_.Exception.Message)"
        }
    }
} finally {
    try {
        Clear-SigningEnvironment
    } catch {
        Write-FinDoneCleanupDiagnostic "Signing environment cleanup was incomplete and did not change the release result: $($_.Exception.Message)"
    }

    if ($null -ne $worktreePath) {
        try {
            Remove-FinDoneTemporaryWorktree `
                -RepositoryRoot $repoRoot `
                -TemporaryRoot $temporaryRoot `
                -WorktreePath $worktreePath
        } catch {
            # Defense in depth: the cleanup helper is best-effort by contract.
            Write-FinDoneCleanupDiagnostic "Temporary release cleanup returned unexpectedly and did not change the release result: $($_.Exception.Message)"
        }
    }
    if ($hasMutex) {
        try {
            $mutex.ReleaseMutex()
        } catch {
            Write-FinDoneCleanupDiagnostic "Release mutex could not be released cleanly and did not change the release result: $($_.Exception.Message)"
        }
    }
    try {
        $mutex.Dispose()
    } catch {
        Write-FinDoneCleanupDiagnostic "Release mutex could not be disposed cleanly and did not change the release result: $($_.Exception.Message)"
    }
}
