param(
    [int]$Port = 9001,
    [int]$DelayMs = 20,
    [string]$Python = "python",
    [switch]$WaitHealthy
)

$ErrorActionPreference = "Stop"
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$logRoot = Join-Path $backendRoot "storage\benchmarks\mock-llm"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

$environment = @{
    MOCK_LLM_DELAY_MS = "$DelayMs"
    PYTHONUTF8 = "1"
    PYTHONPATH = $backendRoot
}

$process = Start-Process `
    -WindowStyle Hidden `
    -FilePath $Python `
    -ArgumentList "tests/benchmarks/run_mock_openai_server.py", "$Port" `
    -WorkingDirectory $backendRoot `
    -RedirectStandardOutput (Join-Path $logRoot "mock.stdout.log") `
    -RedirectStandardError (Join-Path $logRoot "mock.stderr.log") `
    -Environment $environment `
    -PassThru

$process.Id | Set-Content -LiteralPath (Join-Path $logRoot "mock.pid") -Encoding ascii
Write-Output "Started Mock LLM PID=$($process.Id) port=$Port"

if ($WaitHealthy) {
    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/stats" -TimeoutSec 2
            if ($null -ne $response.calls) {
                $healthy = $true
                break
            }
        } catch {
            # The server may still be starting.
        }
        Start-Sleep -Seconds 1
    }
    if (-not $healthy) {
        Write-Output "Mock LLM did not become healthy. Recent stderr:"
        Get-Content -LiteralPath (Join-Path $logRoot "mock.stderr.log") -Tail 80
        exit 1
    }
    Write-Output "Mock LLM healthy at http://127.0.0.1:$Port/stats"
}
