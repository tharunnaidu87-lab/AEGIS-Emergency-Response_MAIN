param(
    [switch]$Validate
)

$ErrorActionPreference = "Stop"


# ============================================================
# AEGIS PROJECT ROOT
# ============================================================

$demoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

Set-Location -LiteralPath $demoRoot


Write-Host ""
Write-Host "============================================================"
Write-Host " AEGIS LOCAL EMERGENCY DEMONSTRATION"
Write-Host "============================================================"
Write-Host ""
Write-Host "Project:"
Write-Host $demoRoot
Write-Host ""


# ============================================================
# PROJECT-LOCAL CACHE DIRECTORIES
# ============================================================

$cacheRoot = Join-Path $demoRoot ".cache"
$tmpDir = Join-Path $cacheRoot "tmp"
$npmCache = Join-Path $cacheRoot "npm"
$demoDir = Join-Path $cacheRoot "demo"


New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
New-Item -ItemType Directory -Path $npmCache -Force | Out-Null
New-Item -ItemType Directory -Path $demoDir -Force | Out-Null


$env:TEMP = $tmpDir
$env:TMP = $tmpDir
$env:npm_config_cache = $npmCache
$env:PYTHONDONTWRITEBYTECODE = "1"


# ============================================================
# LOCAL DEMO NETWORK CONFIGURATION
# ============================================================

$env:AEGIS_BACKEND_URL = "http://127.0.0.1:8001"

# Production Vite build should talk directly to the local backend.
$env:VITE_API_BASE_URL = "http://127.0.0.1:8001"

$env:AEGIS_CORS_ORIGINS = "http://127.0.0.1:5173,http://localhost:5173"


# ============================================================
# FRESH DEMO DATABASE
# ============================================================

$sessionId = [guid]::NewGuid().ToString("N")

$env:AEGIS_DB_PATH = ".cache/demo/session-$sessionId.sqlite"


Write-Host "Demo session:"
Write-Host $sessionId
Write-Host ""


# ============================================================
# DEMO COMMAND AUTHORITY ACCOUNT
# ============================================================

$env:AEGIS_COMMAND_USERNAME = "demo-command"
$env:AEGIS_COMMAND_PASSWORD = "AEGIS-demo-only"

$secretPart1 = [guid]::NewGuid().ToString("N")
$secretPart2 = [guid]::NewGuid().ToString("N")

$env:AEGIS_COMMAND_AUTH_SECRET = "$secretPart1$secretPart2"


# ============================================================
# DEMO RESPONDER ACCOUNTS
# ============================================================

$resourcesPath = Join-Path $demoRoot "data\resources.json"

if (-not (Test-Path -LiteralPath $resourcesPath)) {
    throw "Missing data\resources.json"
}


$resources = Get-Content -LiteralPath $resourcesPath -Raw | ConvertFrom-Json

$demoAccounts = @{}


foreach ($resource in $resources) {

    if ($null -ne $resource.id -and "$($resource.id)".Trim() -ne "") {

        $demoAccounts["$($resource.id)"] = "AEGIS-demo-only"
    }
}


if ($demoAccounts.Count -eq 0) {
    throw "No simulated responder resources were found."
}


$env:AEGIS_RESPONDER_ACCOUNTS = $demoAccounts | ConvertTo-Json -Compress

$env:AEGIS_ENABLE_RESET = "false"


Write-Host "Configured simulated responder accounts:"
Write-Host $demoAccounts.Count
Write-Host ""


# ============================================================
# IMPORTANT SAFETY LABEL
# ============================================================

Write-Host "------------------------------------------------------------"
Write-Host " DEMO MODE"
Write-Host "------------------------------------------------------------"
Write-Host "All police, ambulance, fire and responder units are"
Write-Host "SIMULATED / DEMO-ONLY."
Write-Host ""
Write-Host "No real police, ambulance, fire, 112, NDRF or SDRF"
Write-Host "service is contacted by this demo launcher."
Write-Host "------------------------------------------------------------"
Write-Host ""


# ============================================================
# TOOL PATHS
# ============================================================

$pythonPath = Join-Path $demoRoot "backend\.venv\Scripts\python.exe"


if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Backend Python environment not found: $pythonPath"
}


$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue


if ($null -eq $npmCommand) {
    throw "npm.cmd was not found in PATH."
}


$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue


if ($null -eq $nodeCommand) {
    throw "node.exe was not found in PATH."
}


$nodePath = $nodeCommand.Source


# ============================================================
# PREFLIGHT
# ============================================================

Write-Host "Running AEGIS preflight..."
Write-Host ""


& $pythonPath "scripts\preflight.py"


if ($LASTEXITCODE -ne 0) {
    throw "AEGIS preflight failed."
}


Write-Host ""
Write-Host "Preflight passed."
Write-Host ""


# ============================================================
# OPTIONAL FULL VALIDATION
# ============================================================

if ($Validate) {

    Write-Host "============================================================"
    Write-Host " FULL VALIDATION"
    Write-Host "============================================================"
    Write-Host ""


    # --------------------------------------------------------
    # TYPESCRIPT
    # --------------------------------------------------------

    Write-Host "[1/3] Running frontend TypeScript check..."
    Write-Host ""


    & npm.cmd --prefix frontend run typecheck


    if ($LASTEXITCODE -ne 0) {
        throw "Frontend TypeScript validation failed."
    }


    Write-Host ""
    Write-Host "TypeScript validation passed."
    Write-Host ""


    # --------------------------------------------------------
    # BACKEND TESTS
    # --------------------------------------------------------

    Write-Host "[2/3] Running backend test suite..."
    Write-Host ""


    & $pythonPath -m unittest discover -s backend\tests -p "test_*.py"


    if ($LASTEXITCODE -ne 0) {
        throw "Backend test suite failed."
    }


    Write-Host ""
    Write-Host "Backend tests passed."
    Write-Host ""


    # --------------------------------------------------------
    # PYTHON PREFLIGHT SYNTAX
    # --------------------------------------------------------

    Write-Host "[3/3] Verifying Python preflight syntax..."
    Write-Host ""


    & $pythonPath -m py_compile scripts\preflight.py


    if ($LASTEXITCODE -ne 0) {
        throw "preflight.py syntax validation failed."
    }


    Write-Host ""
    Write-Host "Python syntax validation passed."
    Write-Host ""
}


# ============================================================
# FRONTEND PRODUCTION BUILD
# ============================================================

Write-Host "============================================================"
Write-Host " BUILDING AEGIS FRONTEND"
Write-Host "============================================================"
Write-Host ""


& npm.cmd --prefix frontend run build


if ($LASTEXITCODE -ne 0) {
    throw "Frontend production build failed."
}


Write-Host ""
Write-Host "Frontend production build completed."
Write-Host ""


# ============================================================
# PORT CHECK
# ============================================================

function Test-PortAvailable {

    param(
        [int]$Port
    )

    $listener = $null

    try {

        $listener = New-Object System.Net.Sockets.TcpListener(
            [System.Net.IPAddress]::Loopback,
            $Port
        )

        $listener.Start()

        return $true
    }
    catch {

        return $false
    }
    finally {

        if ($null -ne $listener) {

            try {
                $listener.Stop()
            }
            catch {
                # Ignore cleanup errors.
            }
        }
    }
}


if (-not (Test-PortAvailable -Port 8001)) {

    throw "Port 8001 is already in use. Stop the old AEGIS backend first."
}


if (-not (Test-PortAvailable -Port 5173)) {

    throw "Port 5173 is already in use. Stop the old AEGIS frontend first."
}


# ============================================================
# SERVICE VARIABLES
# ============================================================

$backendProcess = $null
$frontendProcess = $null


$backendLog = Join-Path $demoDir "backend.log"
$backendErrorLog = Join-Path $demoDir "backend-error.log"

$frontendLog = Join-Path $demoDir "frontend.log"
$frontendErrorLog = Join-Path $demoDir "frontend-error.log"


# Clear previous logs.

Remove-Item -LiteralPath $backendLog -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $backendErrorLog -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $frontendLog -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $frontendErrorLog -Force -ErrorAction SilentlyContinue


# ============================================================
# HTTP WAIT HELPER
# ============================================================

function Wait-AegisUrl {

    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [int]$TimeoutSeconds = 30
    )


    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)


    while ((Get-Date) -lt $deadline) {

        try {

            $response = Invoke-WebRequest `
                -Uri $Url `
                -UseBasicParsing `
                -TimeoutSec 2


            if (
                $response.StatusCode -ge 200 -and
                $response.StatusCode -lt 500
            ) {

                return $true
            }
        }
        catch {

            Start-Sleep -Milliseconds 350
        }
    }


    return $false
}


# ============================================================
# START SERVICES
# ============================================================

try {

    # --------------------------------------------------------
    # BACKEND
    # --------------------------------------------------------

    Write-Host "============================================================"
    Write-Host " STARTING AEGIS BACKEND"
    Write-Host "============================================================"
    Write-Host ""


    $backendArguments = @(
        "-B",
        "-m",
        "uvicorn",
        "main:app",
        "--app-dir",
        "backend",
        "--host",
        "127.0.0.1",
        "--port",
        "8001"
    )


    $backendProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList $backendArguments `
        -WorkingDirectory $demoRoot `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $backendLog `
        -RedirectStandardError $backendErrorLog


    Write-Host "Waiting for backend health check..."


    $backendReady = Wait-AegisUrl `
        -Url "http://127.0.0.1:8001/health" `
        -TimeoutSeconds 30


    if (-not $backendReady) {

        Write-Host ""
        Write-Host "Backend failed to become ready."
        Write-Host ""


        if (Test-Path -LiteralPath $backendErrorLog) {

            Write-Host "Backend error log:"
            Get-Content -LiteralPath $backendErrorLog -Tail 40
        }


        throw "AEGIS backend startup failed."
    }


    Write-Host "Backend ONLINE."
    Write-Host ""


    # --------------------------------------------------------
    # FRONTEND
    # --------------------------------------------------------

    Write-Host "============================================================"
    Write-Host " STARTING AEGIS FRONTEND"
    Write-Host "============================================================"
    Write-Host ""


    $viteScript = Join-Path $demoRoot "frontend\node_modules\vite\bin\vite.js"


    if (-not (Test-Path -LiteralPath $viteScript)) {

        throw "Vite executable was not found. Run npm install inside frontend."
    }


    $frontendArguments = @(
        $viteScript,
        "preview",
        "--host",
        "127.0.0.1",
        "--port",
        "5173",
        "--strictPort"
    )


    $frontendProcess = Start-Process `
        -FilePath $nodePath `
        -ArgumentList $frontendArguments `
        -WorkingDirectory (Join-Path $demoRoot "frontend") `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $frontendLog `
        -RedirectStandardError $frontendErrorLog


    Write-Host "Waiting for frontend..."


    $frontendReady = Wait-AegisUrl `
        -Url "http://127.0.0.1:5173/report" `
        -TimeoutSeconds 30


    if (-not $frontendReady) {

        Write-Host ""
        Write-Host "Frontend failed to become ready."
        Write-Host ""


        if (Test-Path -LiteralPath $frontendErrorLog) {

            Write-Host "Frontend error log:"
            Get-Content -LiteralPath $frontendErrorLog -Tail 40
        }


        throw "AEGIS frontend startup failed."
    }


    # ========================================================
    # READY
    # ========================================================

    Write-Host ""
    Write-Host "============================================================"
    Write-Host " AEGIS READY"
    Write-Host "============================================================"
    Write-Host ""


    Write-Host "CITIZEN REPORTING"
    Write-Host "http://127.0.0.1:5173/report"
    Write-Host ""


    Write-Host "COMMAND CENTER"
    Write-Host "http://127.0.0.1:5173/command"
    Write-Host ""
    Write-Host "Username:"
    Write-Host "demo-command"
    Write-Host ""
    Write-Host "Password:"
    Write-Host "AEGIS-demo-only"
    Write-Host ""


    Write-Host "RESPONDER"
    Write-Host "http://127.0.0.1:5173/responder"
    Write-Host ""
    Write-Host "Unit ID:"
    Write-Host "Use the resource ID assigned by Command."
    Write-Host ""
    Write-Host "Password:"
    Write-Host "AEGIS-demo-only"
    Write-Host ""


    Write-Host "------------------------------------------------------------"
    Write-Host "Recommended demo setup"
    Write-Host "------------------------------------------------------------"
    Write-Host "Window 1 : Citizen"
    Write-Host "Window 2 : Command Center"
    Write-Host "Window 3 : Responder / Incognito"
    Write-Host ""


    Write-Host "All responder movement and resources are SIMULATED."
    Write-Host ""


    Write-Host "Backend log:"
    Write-Host $backendLog
    Write-Host ""


    Write-Host "Frontend log:"
    Write-Host $frontendLog
    Write-Host ""


    Write-Host "Press Ctrl+C to stop AEGIS."
    Write-Host ""


    # ========================================================
    # KEEP DEMO RUNNING
    # ========================================================

    while ($true) {

        if ($backendProcess.HasExited) {

            Write-Host ""
            Write-Host "Backend process exited unexpectedly."


            if (Test-Path -LiteralPath $backendErrorLog) {

                Get-Content -LiteralPath $backendErrorLog -Tail 40
            }


            throw "AEGIS backend stopped."
        }


        if ($frontendProcess.HasExited) {

            Write-Host ""
            Write-Host "Frontend process exited unexpectedly."


            if (Test-Path -LiteralPath $frontendErrorLog) {

                Get-Content -LiteralPath $frontendErrorLog -Tail 40
            }


            throw "AEGIS frontend stopped."
        }


        Start-Sleep -Seconds 1
    }
}
finally {

    # ========================================================
    # CLEAN SHUTDOWN
    # ========================================================

    Write-Host ""
    Write-Host "Stopping AEGIS demo services..."


    if (
        $null -ne $frontendProcess -and
        -not $frontendProcess.HasExited
    ) {

        Stop-Process `
            -Id $frontendProcess.Id `
            -Force `
            -ErrorAction SilentlyContinue
    }


    if (
        $null -ne $backendProcess -and
        -not $backendProcess.HasExited
    ) {

        Stop-Process `
            -Id $backendProcess.Id `
            -Force `
            -ErrorAction SilentlyContinue
    }


    Write-Host "AEGIS stopped."
}