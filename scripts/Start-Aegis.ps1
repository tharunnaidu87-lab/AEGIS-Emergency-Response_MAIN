param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Backend', 'Frontend')]
    [string]$Component,
    [switch]$FreshDemo
)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
foreach ($relative in @('.cache\tmp', '.cache\npm', '.cache\pip')) {
    New-Item -ItemType Directory -Path (Join-Path $projectRoot $relative) -Force | Out-Null
}
$env:TEMP = Join-Path $projectRoot '.cache\tmp'
$env:TMP = $env:TEMP
$env:npm_config_cache = Join-Path $projectRoot '.cache\npm'
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache\pip'
$env:PYTHONDONTWRITEBYTECODE = '1'
if ($Component -eq 'Backend') {
    $pythonExecutable = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonExecutable)) {
        throw 'Missing backend virtual environment. Follow README.md setup first.'
    }
    if ($FreshDemo) {
        $env:AEGIS_DB_PATH = '.cache/demo-' + [guid]::NewGuid().ToString('N') + '.sqlite'
    }
    $env:AEGIS_ENABLE_RESET = 'false'
    Write-Host ('AEGIS backend | database: ' + $(if ($env:AEGIS_DB_PATH) { $env:AEGIS_DB_PATH } else { 'data/aegis.db' }))
    & $pythonExecutable -B -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8001
} else {
    if ($FreshDemo) { throw '-FreshDemo is an option for Backend only.' }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules'))) {
        throw 'Missing frontend dependencies. Follow README.md setup first.'
    }
    & npm.cmd --prefix frontend run dev -- --strictPort
}
exit $LASTEXITCODE
