[CmdletBinding()]
param(
    [string]$CsvDirectory = ""
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$exporter = Join-Path $repositoryRoot 'tools\admin_export_content.py'
$elementFixture = Join-Path $repositoryRoot 'admin\data\content-elements.generated.json'
$sourceFixture = Join-Path $repositoryRoot 'admin\data\sources.generated.json'

$arguments = @(
    $exporter,
    '--frontend-json', $elementFixture,
    '--frontend-sources-json', $sourceFixture
)

if ($CsvDirectory) {
    $resolvedCsvDirectory = [System.IO.Path]::GetFullPath(
        (Join-Path (Get-Location) $CsvDirectory)
    )
    $arguments += @('--csv-dir', $resolvedCsvDirectory)
}

& python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Admin content export failed with exit code $LASTEXITCODE"
}

Write-Output "Admin fixtures refreshed from the verified packaged content DB."
