param(
    [Parameter(Mandatory = $true)]
    [int]$BackendPid,
    [Parameter(Mandatory = $true)]
    [ValidateSet("live", "mock")]
    [string]$Mode,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Python = "backend/.venv/Scripts/python.exe",
    [string]$LlmStatsUrl = "",
    [int]$DurationSeconds = 300,
    [int]$Rounds = 3,
    [int]$StartRound = 1,
    [int[]]$ConcurrencyStages = @(1, 2, 4, 8)
)

$ErrorActionPreference = "Stop"

if ($DurationSeconds -lt 1) {
    throw "DurationSeconds must be positive."
}
if ($Rounds -lt 1) {
    throw "Rounds must be positive."
}
if ($StartRound -lt 1 -or $StartRound -gt $Rounds) {
    throw "StartRound must be between 1 and Rounds."
}
if (-not (Get-Process -Id $BackendPid -ErrorAction SilentlyContinue)) {
    throw "Backend PID $BackendPid is not running."
}

$scriptRoot = (Resolve-Path $PSScriptRoot).Path
$backendRoot = (Resolve-Path (Join-Path $scriptRoot "..\..")).Path
$repoRoot = (Resolve-Path (Join-Path $backendRoot "..")).Path
$samplerScript = Join-Path $scriptRoot "resource_sampler.ps1"
$locustFile = Join-Path $backendRoot "tests\benchmarks\sse_load.py"
$pythonPath = $Python
if (-not [System.IO.Path]::IsPathRooted($pythonPath)) {
    $pythonPath = Join-Path $repoRoot $pythonPath
}
$pythonPath = (Resolve-Path $pythonPath).Path

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$outputRootPath = (Resolve-Path $OutputRoot).Path

$previousOutput = $env:SMARTCLASS_BENCHMARK_OUTPUT
$previousPythonUtf8 = $env:PYTHONUTF8
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = $backendRoot

function Restore-BenchmarkEnvironment {
    if ($null -eq $script:previousOutput) {
        Remove-Item Env:SMARTCLASS_BENCHMARK_OUTPUT -ErrorAction SilentlyContinue
    } else {
        $env:SMARTCLASS_BENCHMARK_OUTPUT = $script:previousOutput
    }
    if ($null -eq $script:previousPythonUtf8) {
        Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONUTF8 = $script:previousPythonUtf8
    }
    if ($null -eq $script:previousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $script:previousPythonPath
    }
}

try {
    foreach ($round in $StartRound..$Rounds) {
        foreach ($users in $ConcurrencyStages) {
            if ($users -lt 1) {
                throw "Concurrency stages must be positive; got $users."
            }
            if (-not (Get-Process -Id $BackendPid -ErrorAction SilentlyContinue)) {
                throw "Backend PID $BackendPid stopped before $Mode round $round ${users}u."
            }

            $stem = "$Mode-r$round-${users}u"
            $outputPath = Join-Path $outputRootPath "$stem.json"
            $resourcePath = Join-Path $outputRootPath "$stem.resources.csv"
            $manifestPath = Join-Path $outputRootPath "$stem.window.json"

            $startedAt = [DateTime]::UtcNow
            $samplerArgs = @(
                "-NoProfile",
                "-File",
                $samplerScript,
                "-ProcessId",
                "$BackendPid",
                "-Output",
                $resourcePath,
                "-DurationSeconds",
                "$DurationSeconds"
            )
            $sampler = Start-Process -WindowStyle Hidden -FilePath "pwsh" -ArgumentList $samplerArgs -PassThru
            $locustExitCode = 0
            try {
                $env:SMARTCLASS_BENCHMARK_OUTPUT = $outputPath
                Write-Output ("[{0}] start mode={1} round={2}/{3} users={4} duration={5}s" -f `
                    $startedAt.ToString("o"), $Mode, $round, $Rounds, $users, $DurationSeconds)
                & $pythonPath -m locust `
                    -f $locustFile `
                    --headless `
                    -H $BaseUrl `
                    -u $users `
                    -r $users `
                    --run-time "$($DurationSeconds)s" `
                    --only-summary `
                    --exit-code-on-error 0
                $locustExitCode = $LASTEXITCODE
            } finally {
                $sampler | Wait-Process -Timeout ($DurationSeconds + 30) -ErrorAction SilentlyContinue
                if (Get-Process -Id $sampler.Id -ErrorAction SilentlyContinue) {
                    Stop-Process -Id $sampler.Id -Force -ErrorAction SilentlyContinue
                }
            }

            $finishedAt = [DateTime]::UtcNow
            $window = [ordered]@{
                schema_version = "1.0"
                benchmark = "sse-chat-load"
                mode = $Mode
                round = $round
                users = $users
                duration_seconds = $DurationSeconds
                backend_pid = $BackendPid
                started_at = $startedAt.ToString("o")
                finished_at = $finishedAt.ToString("o")
                locust_exit_code = $locustExitCode
                output_file = [System.IO.Path]::GetFileName($outputPath)
                resource_file = [System.IO.Path]::GetFileName($resourcePath)
            }
            $window | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8
            Write-Output ("[{0}] done mode={1} round={2}/{3} users={4} locust_exit={5}" -f `
                $finishedAt.ToString("o"), $Mode, $round, $Rounds, $users, $locustExitCode)
        }
    }
    if ($LlmStatsUrl) {
        $statsPath = Join-Path $outputRootPath "mock-stats.json"
        $stats = Invoke-RestMethod -Uri ($LlmStatsUrl.TrimEnd("/") + "/stats") -TimeoutSec 10
        $stats | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statsPath -Encoding utf8
    }
} finally {
    Restore-BenchmarkEnvironment
}
