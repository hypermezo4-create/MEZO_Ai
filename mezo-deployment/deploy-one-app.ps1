param([ValidateSet("1")][string]$Stage = "1")
$ErrorActionPreference = "Stop"
$org = "personal"
$app = "mezo-ai"
$region = "ord"
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "fly-json.ps1")

function Fly([string[]]$Args) { & fly @Args; if ($LASTEXITCODE -ne 0) { throw "fly command failed: $($Args -join ' ')" } }
function Secret([int]$Bytes = 48) {
    $b = New-Object byte[] $Bytes; $r = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $r.GetBytes($b) } finally { $r.Dispose() }
    [Convert]::ToBase64String($b).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}
function Import-Secrets([hashtable]$Values) {
    $payload = ($Values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "`n"
    $old = $env:MEZO_SECRET_IMPORT_B64
    try {
        $env:MEZO_SECRET_IMPORT_B64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
        & python -c "import base64,os,subprocess; raise SystemExit(subprocess.run(['fly','secrets','import','--app',os.environ['MEZO_APP']],input=base64.b64decode(os.environ['MEZO_SECRET_IMPORT_B64'])).returncode)"
        if ($LASTEXITCODE -ne 0) { throw "secret import failed" }
    } finally {
        if ($null -eq $old) { Remove-Item Env:MEZO_SECRET_IMPORT_B64 -ErrorAction SilentlyContinue } else { $env:MEZO_SECRET_IMPORT_B64 = $old }
    }
}
function Ensure-App {
    $apps = @(Invoke-FlyJson @("apps","list","--org",$org,"--json") "fly apps list")
    if (@($apps | Where-Object { $_.Name -eq $app }).Count -eq 0) { Fly @("apps","create",$app,"--org",$org) }
}
function Ensure-Volume([string]$Name, [int]$Size, [string]$Mount, [string]$VmSize, [int]$Memory) {
    $v = @(Invoke-FlyJson @("volumes","list","--app",$app,"--json") "fly volumes list" | Where-Object { $_.name -eq $Name })
    foreach ($x in $v) { if ($x.size_gb -ne $Size -or $x.region -ne $region) { throw "Conflicting volume $Name" } }
    if ($v.Count -eq 0) { Fly @("volumes","create",$Name,"--app",$app,"--region",$region,"--size","$Size","--vm-size",$VmSize,"--vm-memory","$Memory","--yes") }
}
function Role-Machine([string]$Role) {
    @(Invoke-FlyJson @("machines","list","--app",$app,"--json") "fly machines list" | Where-Object {
        $_.region -eq $region -and $_.config.metadata.fly_process_group -eq $Role
    } | Select-Object -First 1)
}
function Run-Role([hashtable]$Spec) {
    if (Role-Machine $Spec.role) { Write-Output "Reusing $($Spec.role)"; return }
    $args = @("machine","run",".","--app",$app,"--org",$org,"--region",$region,"--dockerfile",$Spec.dockerfile,"--vm-size",$Spec.size,"--vm-memory","$($Spec.memory)","--metadata","fly_platform_version=v2","--metadata","fly_process_group=$($Spec.role)","--env","MEZO_APP_NAME=$app","--restart","always")
    foreach ($e in $Spec.env.GetEnumerator()) { $args += @("--env","$($e.Key)=$($e.Value)") }
    if ($Spec.volume) { $args += @("--volume","$($Spec.volume):$($Spec.mount)") }
    Fly $args
    Write-Output "Created $($Spec.role)"
}

if ((& fly auth whoami).Trim() -ne "neomos.eg@gmail.com") { throw "Unexpected Fly account" }
$env:MEZO_APP = $app
Ensure-App
$names = @(Invoke-FlyJson @("secrets","list","--app",$app,"--json") "fly secrets list" | ForEach-Object { $_.name })
$secrets = @{}
foreach ($n in @("MODEL_INTERNAL_TOKEN","RUNNER_INTERNAL_TOKEN","ORCHESTRATOR_INTERNAL_TOKEN","VALKEY_PASSWORD")) { if ($n -notin $names) { $secrets[$n] = Secret } }
if ($secrets.Count -gt 0) { Import-Secrets $secrets }

$clusters = @(Invoke-FlyJson @("mpg","list","--org",$org,"--json") "fly mpg list")
$pg = $clusters | Where-Object { $_.name -eq "mezo-postgres-ord" -and $_.region -eq $region } | Select-Object -First 1
if (-not $pg) { Fly @("mpg","create","--name","mezo-postgres-ord","--org",$org,"--region",$region,"--plan","Launch","--volume-size","100","--pg-major-version","17"); $pg = @(Invoke-FlyJson @("mpg","list","--org",$org,"--json") "fly mpg list") | Where-Object { $_.name -eq "mezo-postgres-ord" } | Select-Object -First 1 }
if (-not $pg) { throw "Could not verify ord MPG" }
if ('DATABASE_URL' -notin $names) { Fly @("mpg","attach",$pg.id,"--app",$app) }

Ensure-Volume "mezo_queue_data" 20 "data" "shared-cpu-2x" 4096
Ensure-Volume "mezo_index_data" 100 "index" "performance-4x" 32768
Ensure-Volume "mezo_runner_data" 500 "workspaces" "performance-8x" 65536
Ensure-Volume "mezo_fast_models" 100 "models" "performance-8x" 65536
Ensure-Volume "mezo_coder_models" 250 "models" "performance-16x" 131072

$common = @{ MODEL_INTERNAL_TOKEN="`$MODEL_INTERNAL_TOKEN"; RUNNER_INTERNAL_TOKEN="`$RUNNER_INTERNAL_TOKEN"; ORCHESTRATOR_INTERNAL_TOKEN="`$ORCHESTRATOR_INTERNAL_TOKEN"; VALKEY_PASSWORD="`$VALKEY_PASSWORD" }
Run-Role @{ role="queue"; dockerfile="mezo-queue/Dockerfile"; size="shared-cpu-2x"; memory=4096; volume="mezo_queue_data"; mount="/data"; env=@{} }
Run-Role @{ role="fast"; dockerfile="mezo-model-server/Dockerfile"; size="performance-8x"; memory=65536; volume="mezo_fast_models"; mount="/models"; env=@{ MODEL_MANIFEST="fast"; MODEL_CONTEXT="32768" } }
Run-Role @{ role="coder"; dockerfile="mezo-model-server/Dockerfile"; size="performance-16x"; memory=131072; volume="mezo_coder_models"; mount="/models"; env=@{ MODEL_MANIFEST="qwen-coder"; MODEL_CONTEXT="32768" } }
Run-Role @{ role="router"; dockerfile="mezo-router/Dockerfile"; size="performance-4x"; memory=32768; env=@{} }
Run-Role @{ role="indexer"; dockerfile="mezo-indexer/Dockerfile"; size="performance-4x"; memory=32768; volume="mezo_index_data"; mount="/index"; env=@{} }
Run-Role @{ role="web"; dockerfile="mezo-control-plane/Dockerfile"; size="shared-cpu-4x"; memory=8192; env=@{} }
Run-Role @{ role="runner"; dockerfile="mezo-runner/Dockerfile"; size="performance-8x"; memory=65536; volume="mezo_runner_data"; mount="/workspaces"; env=@{} }

$machines = @(Invoke-FlyJson @("machines","list","--app",$app,"--json") "fly machines list")
if ($machines.Count -gt 20) { throw "MEZO app exceeds 20 machines" }
Write-Output "Stage 1 one-app deployment complete: $($machines.Count) machine(s)"
