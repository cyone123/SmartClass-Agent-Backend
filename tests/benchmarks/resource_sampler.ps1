param(
    [Parameter(Mandatory = $true)]
    [Alias("Pid")]
    [int]$ProcessId,
    [Parameter(Mandatory = $true)]
    [string]$Output,
    [int]$DurationSeconds = 300,
    [double]$IntervalSeconds = 1.0
)

$ErrorActionPreference = "Stop"
$parent = Split-Path -Parent $Output
if ($parent) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}

$rows = [System.Collections.Generic.List[object]]::new()
$started = Get-Date
$lastTime = $started
$lastCpu = $null
$processorCount = [Environment]::ProcessorCount

while (((Get-Date) - $started).TotalSeconds -lt $DurationSeconds) {
    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
    } catch {
        break
    }

    $now = Get-Date
    $elapsed = ($now - $started).TotalSeconds
    $cpuSeconds = [double]$process.CPU
    $deltaSeconds = ($now - $lastTime).TotalSeconds
    $cpuPercent = $null
    if ($null -ne $lastCpu -and $deltaSeconds -gt 0) {
        $cpuPercent = [math]::Round(100 * ($cpuSeconds - $lastCpu) / $deltaSeconds / $processorCount, 2)
    }

    $rows.Add([pscustomobject]@{
        timestamp_utc = $now.ToUniversalTime().ToString("o")
        elapsed_seconds = [math]::Round($elapsed, 3)
        pid = $ProcessId
        cpu_seconds = [math]::Round($cpuSeconds, 3)
        cpu_percent = $cpuPercent
        working_set_mb = [math]::Round($process.WorkingSet64 / 1MB, 2)
        private_memory_mb = [math]::Round($process.PrivateMemorySize64 / 1MB, 2)
        thread_count = $process.Threads.Count
        handle_count = $process.HandleCount
    })

    $lastTime = $now
    $lastCpu = $cpuSeconds
    Start-Sleep -Milliseconds ([int]($IntervalSeconds * 1000))
}

$rows | Export-Csv -LiteralPath $Output -NoTypeInformation -Encoding utf8
