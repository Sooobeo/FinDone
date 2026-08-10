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
    $fileHasSupabaseUrl = $false
    $fileHasSupabaseKey = $false
    foreach ($environmentFile in @('.env.local', '.env')) {
        if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) { continue }
        foreach ($line in Get-Content -Encoding UTF8 -LiteralPath $environmentFile) {
            if ($line -match '^\s*NEXT_PUBLIC_SUPABASE_URL\s*=\s*.+$') { $fileHasSupabaseUrl = $true }
            if ($line -match '^\s*NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY\s*=\s*.+$') { $fileHasSupabaseKey = $true }
        }
    }
    $hasSupabaseUrl = -not [string]::IsNullOrWhiteSpace($env:NEXT_PUBLIC_SUPABASE_URL) -or $fileHasSupabaseUrl
    $hasSupabaseKey = -not [string]::IsNullOrWhiteSpace($env:NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY) -or $fileHasSupabaseKey
    if (-not $hasSupabaseUrl -and -not $hasSupabaseKey) {
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
