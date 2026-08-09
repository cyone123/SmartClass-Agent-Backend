param(
    [int]$Port = 8000,
    [string]$Python = "python",
    [string]$LlmBaseUrl = "",
    [string]$LlmModel = "mock-model",
    [switch]$WaitHealthy
)

$ErrorActionPreference = "Stop"
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$logRoot = Join-Path $backendRoot "storage\benchmarks\sse-load"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

$environment = @{
    DATABASE_URL = ($env:SMARTCLASS_BENCHMARK_DATABASE_URL ?? "postgresql://smartclass:smartclass_dev_password@127.0.0.1:5432/smartclass")
    FILE_STORAGE_ROOT = (Join-Path $backendRoot "storage")
    STORAGE_BACKEND = "local"
    OBSERVABILITY_ENABLED = "false"
    OTEL_ENABLED = "false"
    PROMETHEUS_ENABLED = "false"
    CONTEXT_COMPRESSION_ENABLED = "false"
    WORKSPACE_EXECUTION_BACKEND = "local"
    PUBLIC_API_BASE_URL = "http://127.0.0.1:$Port"
    PYTHONUTF8 = "1"
    PYTHONPATH = $backendRoot
}

if ($LlmBaseUrl) {
    $environment.MODEL = $LlmModel
    $environment.API_KEY = "mock-key"
    $environment.BASE_URL = $LlmBaseUrl
    $environment.STRUCTED_MDOEL = $LlmModel
    $environment.STRUCTED_API_KEY = "mock-key"
    $environment.STRUCTED_BASE_URL = $LlmBaseUrl
    $environment.STRUCTURED_FAST_MODEL = $LlmModel
    $environment.STRUCTURED_FAST_API_KEY = "mock-key"
    $environment.STRUCTURED_FAST_BASE_URL = $LlmBaseUrl
    $environment.SMALL_MDOEL = $LlmModel
    $environment.SMALL_API_KEY = "mock-key"
    $environment.SMALL_BASE_URL = $LlmBaseUrl
    $environment.MEMORY_MODEL = $LlmModel
    $environment.MEMORY_API_KEY = "mock-key"
    $environment.MEMORY_BASE_URL = $LlmBaseUrl
    $environment.MODEL_THINKING_MODE = "disabled"
    $environment.STRUCTURED_WARMUP_ENABLED = "false"
}

$process = Start-Process `
    -WindowStyle Hidden `
    -FilePath $Python `
    -ArgumentList "tests/benchmarks/run_sse_backend.py", "$Port" `
    -WorkingDirectory $backendRoot `
    -RedirectStandardOutput (Join-Path $logRoot "backend.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "backend.stderr.log") `
    -Environment $environment `
    -PassThru

$process.Id | Set-Content -LiteralPath (Join-Path $logRoot "backend.pid") -Encoding ascii
Write-Output "Started backend PID=$($process.Id) port=$Port"

if ($WaitHealthy) {
    $healthy = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $healthy = $true
                break
            }
        } catch {
            # The application may still be initializing its database/checkpointer.
        }
        Start-Sleep -Seconds 1
    }
    if (-not $healthy) {
        Write-Output "Backend did not become healthy. Recent stderr:"
        Get-Content -LiteralPath (Join-Path $logRoot "backend.stderr.log") -Tail 80
        exit 1
    }
    Write-Output "Backend healthy at http://127.0.0.1:$Port/health"
}
