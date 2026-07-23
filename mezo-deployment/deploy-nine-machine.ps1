param(
    [ValidateSet("all","control","utility","coder-1","runner-1","coder-2","runner-2","reasoning","reviewer","vision")]
    [string]$Role = "all"
)
$ErrorActionPreference = "Stop"
$app = "mezo-ai"
$org = "personal"
$region = "ord"
$root = Split-Path -Parent $PSScriptRoot
$topology = Get-Content (Join-Path $PSScriptRoot "nine-machine-topology.json") -Raw | ConvertFrom-Json
. (Join-Path $PSScriptRoot "fly-json.ps1")

function Invoke-Fly([string[]]$Arguments) {
    & fly @Arguments
    if ($LASTEXITCODE -ne 0) { throw "fly command failed: $($Arguments -join ' ')" }
}
function Read-FlyJson([string[]]$Arguments, [string]$CommandName) {
    $raw = @(Invoke-FlyJson $Arguments $CommandName)
    if ($raw.Count -eq 1 -and $raw[0] -is [System.Array]) { return @($raw[0]) }
    @($raw)
}
function New-RandomSecret([int]$Bytes = 48) {
    $value = New-Object byte[] $Bytes
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($value) } finally { $generator.Dispose() }
    [Convert]::ToBase64String($value).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}
function Import-NewSecrets {
    $existing = @(Read-FlyJson @("secrets","list","--app",$app,"--json") "fly secrets list" | ForEach-Object name)
    $values = @{}
    foreach ($name in @("MODEL_INTERNAL_TOKEN","RUNNER_INTERNAL_TOKEN","ORCHESTRATOR_INTERNAL_TOKEN","VALKEY_PASSWORD")) {
        if ($name -notin $existing) { $values[$name] = New-RandomSecret }
    }
    if ($values.Count -eq 0) { return }
    $payload = ($values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "`n"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
    $previous = $env:MEZO_SECRET_IMPORT_B64
    try {
        $env:MEZO_SECRET_IMPORT_B64 = $encoded
        & python -c "import base64,os,subprocess; raise SystemExit(subprocess.run(['fly','secrets','import','--app','mezo-ai'],input=base64.b64decode(os.environ['MEZO_SECRET_IMPORT_B64']),stdout=subprocess.DEVNULL).returncode)"
        if ($LASTEXITCODE -ne 0) { throw "Fly secret import failed" }
    } finally {
        if ($null -eq $previous) { Remove-Item Env:MEZO_SECRET_IMPORT_B64 -ErrorAction SilentlyContinue } else { $env:MEZO_SECRET_IMPORT_B64 = $previous }
    }
}
function Get-Machines { @(Read-FlyJson @("machines","list","--app",$app,"--json") "fly machines list") }
function Get-RoleMachine([string]$Name) {
    @(Get-Machines | Where-Object { $_.config.metadata.role -eq $Name } | Select-Object -First 1)
}
function Ensure-App {
    $apps = @(Read-FlyJson @("apps","list","--org",$org,"--json") "fly apps list")
    if (-not ($apps | Where-Object Name -eq $app)) { Invoke-Fly @("apps","create",$app,"--org",$org) }
}
function Ensure-Postgres {
    $clusters = @(Read-FlyJson @("mpg","list","--org",$org,"--json") "fly mpg list")
    $cluster = $clusters | Where-Object { $_.name -eq "mezo-postgres-ord" -and $_.region -eq $region -and $_.status -ne "deleting" } | Select-Object -First 1
    if (-not $cluster) {
        $null = & fly mpg create --name mezo-postgres-ord --org $org --region $region --plan Performance --volume-size 500 --pg-major-version 17 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Managed Postgres creation failed" }
        $cluster = @(Read-FlyJson @("mpg","list","--org",$org,"--json") "fly mpg list") | Where-Object { $_.name -eq "mezo-postgres-ord" -and $_.status -ne "deleting" } | Select-Object -First 1
    }
    if (-not $cluster) { throw "Managed Postgres could not be verified" }
    $secretNames = @(Read-FlyJson @("secrets","list","--app",$app,"--json") "fly secrets list" | ForEach-Object name)
    if ("DATABASE_URL" -notin $secretNames) {
        $null = & fly mpg attach $cluster.id --app $app 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Managed Postgres attachment failed" }
    }
    $cluster
}
function Ensure-Volume($Spec) {
    $volumes = @(Read-FlyJson @("volumes","list","--app",$app,"--json") "fly volumes list")
    $volume = $volumes | Where-Object name -eq $Spec.volume | Select-Object -First 1
    if ($volume) {
        if ($volume.region -ne $region -or [int]$volume.size_gb -ne 500) { throw "Conflicting volume $($Spec.volume)" }
        return $volume
    }
    Invoke-Fly @("volumes","create",$Spec.volume,"--app",$app,"--region",$region,"--size","500","--vm-size","performance-16x","--vm-memory","131072","--yes")
    @(Read-FlyJson @("volumes","list","--app",$app,"--json") "fly volumes list" | Where-Object name -eq $Spec.volume | Select-Object -First 1)
}
function Ensure-Machine($Spec) {
    $machine = Get-RoleMachine $Spec.role
    if ($machine) { return $machine }
    $volume = Ensure-Volume $Spec
    Invoke-Fly @("deploy","--config","mezo-deployment/fly.toml","--app",$app,"--dockerfile",$Spec.dockerfile,"--build-only","--push","--remote-only","--image-label",$Spec.role)
    $image = "registry.fly.io/$app`:$($Spec.role)"
    $arguments = @(
        "machine","run",$image,"--app",$app,"--org",$org,"--region",$region,
        "--vm-size","performance-16x","--vm-memory","131072",
        "--metadata","fly_platform_version=v2","--metadata","role=$($Spec.role)",
        "--restart","always","--volume","$($volume.id):$($Spec.mount)",
        "--env","MEZO_APP_NAME=$app","--env","MEZO_BIND_HOST=::",
        "--env","MEZO_MACHINE_ROLE=$($Spec.role)",
        "--env","MEZO_MACHINE_SIZE=performance-16x",
        "--env","MEZO_MACHINE_MEMORY_MB=131072",
        "--env","MEZO_MAX_MACHINES=20"
    )
    if ($Spec.manifest) { $arguments += @("--env","MODEL_MANIFEST=$($Spec.manifest)","--env","MODEL_CONTEXT=32768") }
    Invoke-Fly $arguments
    $machine = Get-RoleMachine $Spec.role
    if (-not $machine) { throw "Machine $($Spec.role) was not created" }
    $machine
}
function Hostname($Machine) { "$($Machine.id).vm.$app.internal" }
function Refresh-Registry {
    $roles = @{}
    foreach ($machine in Get-Machines) { $roles[$machine.config.metadata.role] = $machine }
    if (-not $roles.control) { return }
    $values = @{
        CONTROL_URL = "http://$(Hostname $roles.control):8080"
        ROUTER_URL = "http://$(Hostname $roles.control):8081/v1"
        MEZO_MAX_MACHINES = "20"
        MEZO_CORE_MACHINE_COUNT = "9"
        MEZO_MAX_CONCURRENT_TASKS = "4"
    }
    if ($roles.utility) {
        $values.FAST_URL = "http://$(Hostname $roles.utility):8101/v1"
        $values.EMBEDDING_URL = "http://$(Hostname $roles.utility):8102/v1"
        $values.RERANKER_URL = "http://$(Hostname $roles.utility):8103/v1"
    }
    if ($roles.'coder-1') {
        $coders = @($roles.'coder-1', $roles.'coder-2') | Where-Object { $_ } | ForEach-Object { "http://$(Hostname $_):8080/v1" }
        $values.CODER_ENDPOINTS = $coders -join ","
    }
    if ($roles.reasoning) { $values.REASONING_URL = "http://$(Hostname $roles.reasoning):8080/v1" }
    if ($roles.reviewer) { $values.REVIEWER_URL = "http://$(Hostname $roles.reviewer):8080/v1" }
    if ($roles.vision) { $values.VISION_URL = "http://$(Hostname $roles.vision):8080/v1" }
    foreach ($dependent in @($roles.control, $roles.'runner-1', $roles.'runner-2') | Where-Object { $_ }) {
        $arguments = @("machine","update",$dependent.id,"--app",$app,"--yes")
        foreach ($entry in $values.GetEnumerator()) { $arguments += @("--env","$($entry.Key)=$($entry.Value)") }
        $dependentRole = [string]$dependent.config.metadata.role
        if ($dependentRole) {
            $arguments += @("--env","MEZO_MACHINE_ROLE=$dependentRole")
        }
        Invoke-Fly $arguments
    }
}

if ((& fly auth whoami).Trim() -ne "neomos.eg@gmail.com") { throw "Unexpected Fly account" }
Ensure-App
Import-NewSecrets
$postgres = Ensure-Postgres
$selected = if ($Role -eq "all") { @($topology.roles) } else { @($topology.roles | Where-Object role -eq $Role) }
foreach ($spec in $selected) {
    $machine = Ensure-Machine $spec
    Write-Output "READY role=$($spec.role) machine=$($machine.id) volume=$($spec.volume)"
    Refresh-Registry
}
$machines = Get-Machines
if ($machines.Count -gt 20) { throw "mezo-ai exceeds the configured 20-Machine capacity" }
if ($Role -eq "all") {
    $missing = @($topology.roles | Where-Object { -not (Get-RoleMachine $_.role) } | ForEach-Object role)
    if ($missing.Count -gt 0) { throw "Missing core Machines: $($missing -join ', ')" }
}
Write-Output "CAPACITY machines=$($machines.Count)/20 core=9"
Write-Output "POSTGRES name=$($postgres.name) id=$($postgres.id) status=$($postgres.status)"
