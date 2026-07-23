param(
    [string]$App = "mezo-ai",
    [string]$ExpectedControlMachineId = "781232da224d98",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "fly-json.ps1")

function Invoke-Fly([string[]]$Arguments) {
    & fly @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "fly command failed: $($Arguments -join ' ')"
    }
}

function Get-Machines {
    $result = @(Invoke-FlyJson @("machines", "list", "--app", $App, "--json") "fly machines list")
    if ($result.Count -eq 1 -and $result[0] -is [System.Array]) {
        return @($result[0])
    }
    return @($result)
}

function Get-RoleMachine([object[]]$Machines, [string]$Role) {
    return @($Machines | Where-Object { $_.config.metadata.role -eq $Role } | Select-Object -First 1)[0]
}

function Internal-Host($Machine) {
    return "$($Machine.id).vm.$App.internal"
}

$whoami = (& fly auth whoami).Trim()
if ($LASTEXITCODE -ne 0 -or $whoami -ne "neomos.eg@gmail.com") {
    throw "Unexpected Fly account: $whoami"
}

Push-Location $root
try {
    $machines = @(Get-Machines)
    $controlMatches = @($machines | Where-Object { $_.config.metadata.role -eq "control" })
    if ($controlMatches.Count -ne 1) {
        throw "Expected exactly one control Machine, found $($controlMatches.Count)"
    }

    $control = $controlMatches[0]
    if ($ExpectedControlMachineId -and $control.id -ne $ExpectedControlMachineId) {
        throw "Control Machine mismatch. Expected $ExpectedControlMachineId, found $($control.id)"
    }
    if (-not $control.config.mounts -or $control.config.mounts.Count -ne 1) {
        throw "Control Machine must keep exactly one existing volume mount"
    }

    $utility = Get-RoleMachine $machines "utility"
    $coder1 = Get-RoleMachine $machines "coder-1"
    $coder2 = Get-RoleMachine $machines "coder-2"
    $reasoning = Get-RoleMachine $machines "reasoning"
    $reviewer = Get-RoleMachine $machines "reviewer"
    $vision = Get-RoleMachine $machines "vision"

    if (-not $utility) {
        throw "Utility Machine is required before updating Control"
    }
    if (-not $coder1) {
        throw "Coder-1 Machine is required before updating Control"
    }

    $environment = [ordered]@{
        MEZO_APP_NAME = $App
        MEZO_MACHINE_ROLE = "control"
        MEZO_MACHINE_SIZE = "performance-16x"
        MEZO_MACHINE_MEMORY_MB = "131072"
        MEZO_MAX_MACHINES = "20"
        MEZO_CORE_MACHINE_COUNT = "9"
        MEZO_MAX_CONCURRENT_TASKS = "4"
        ROUTER_URL = "http://127.0.0.1:8081/v1"
        INDEXER_URL = "http://127.0.0.1:8082"
        FAST_URL = "http://$(Internal-Host $utility):8101/v1"
        EMBEDDING_URL = "http://$(Internal-Host $utility):8102/v1"
        RERANKER_URL = "http://$(Internal-Host $utility):8103/v1"
    }

    $coders = @($coder1, $coder2) |
        Where-Object { $_ } |
        ForEach-Object { "http://$(Internal-Host $_):8080/v1" }
    $environment.CODER_ENDPOINTS = $coders -join ","

    if ($reasoning) { $environment.REASONING_URL = "http://$(Internal-Host $reasoning):8080/v1" }
    if ($reviewer) { $environment.REVIEWER_URL = "http://$(Internal-Host $reviewer):8080/v1" }
    if ($vision) { $environment.VISION_URL = "http://$(Internal-Host $vision):8080/v1" }

    $imageLabel = "control-runtime"
    $image = "registry.fly.io/$App`:$imageLabel"
    if (-not $SkipBuild) {
        Invoke-Fly @(
            "deploy", ".",
            "--config", "mezo-deployment/fly.toml",
            "--app", $App,
            "--dockerfile", "mezo-control/Dockerfile",
            "--build-only",
            "--push",
            "--remote-only",
            "--image-label", $imageLabel
        )
    }

    $arguments = @(
        "machine", "update", $control.id,
        "--app", $App,
        "--image", $image,
        "--wait-timeout", "900",
        "--yes"
    )
    foreach ($entry in $environment.GetEnumerator()) {
        $arguments += @("--env", "$($entry.Key)=$($entry.Value)")
    }

    Write-Output "UPDATING role=control machine=$($control.id) image=$image volume=$($control.config.mounts[0].volume)"
    Invoke-Fly $arguments
    Invoke-Fly @("machine", "status", $control.id, "--app", $App)
    Write-Output "READY role=control machine=$($control.id) image=$image"
    Write-Output "REOPEN_PROXY fly proxy 8787:8080 -a $App --select"
} finally {
    Pop-Location
}
