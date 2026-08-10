[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$adminRoot = Join-Path $repositoryRoot 'admin'

& (Join-Path $PSScriptRoot 'refresh_admin_content.ps1')

Push-Location $adminRoot
try {
    $hadDemoFlag = Test-Path Env:NEXT_PUBLIC_FINDONE_ADMIN_DEMO
    $previousDemoFlag = $env:NEXT_PUBLIC_FINDONE_ADMIN_DEMO
    if (-not $env:NEXT_PUBLIC_SUPABASE_URL -and -not $env:NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY) {
        $env:NEXT_PUBLIC_FINDONE_ADMIN_DEMO = '1'
    }
    if (-not $SkipInstall -and -not (Test-Path 'node_modules')) {
        npm install
        if ($LASTEXITCODE -ne 0) {
            throw "npm install failed with exit code $LASTEXITCODE"
        }
    }
    npm run dev
    if ($LASTEXITCODE -ne 0) {
        throw "Admin dev server failed with exit code $LASTEXITCODE"
    }
} finally {
    if ($hadDemoFlag) {
        $env:NEXT_PUBLIC_FINDONE_ADMIN_DEMO = $previousDemoFlag
    } else {
        Remove-Item Env:NEXT_PUBLIC_FINDONE_ADMIN_DEMO -ErrorAction SilentlyContinue
    }
    Pop-Location
}
