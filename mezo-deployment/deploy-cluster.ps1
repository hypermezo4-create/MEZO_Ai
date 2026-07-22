param([ValidateSet("1", "2", "3", "all")][string]$Stage = "all")
$ErrorActionPreference = "Stop"
$org = "personal"
$root = Split-Path -Parent $PSScriptRoot

function Invoke-Fly([string[]]$Arguments) {
    & fly @Arguments
    if ($LASTEXITCODE -ne 0) { throw "fly command failed" }
}
function New-Secret([int]$Bytes = 48) {
    $buffer = New-Object byte[] $Bytes
    [Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    [Convert]::ToBase64String($buffer).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}
function Import-Secrets([string]$App, [hashtable]$Values) {
    $payload = ($Values.GetEnumerator() | ForEach-Object { $_.Key + "=" + $_.Value }) -join "`n"
    $payload | & fly secrets import --app $App
    if ($LASTEXITCODE -ne 0) { throw "Could not import secrets for $App" }
}
function Import-IfExists([string]$App, [hashtable]$Values) {
    if (App-Exists $App) { Import-Secrets $App $Values }
}
function App-Exists([string]$Name) {
    @(& fly apps list --org $org --json | ConvertFrom-Json | Where-Object { $_.Name -eq $Name }).Count -eq 1
}
function Ensure-App([string]$Name) {
    if (-not (App-Exists $Name)) { Invoke-Fly @("apps", "create", $Name, "--org", $org) }
}
function Ensure-Volumes([string]$App, [string]$Name, [int]$Size, [int]$Count) {
    $existing = @(& fly volumes list --app $App --json | ConvertFrom-Json | Where-Object { $_.name -eq $Name })
    foreach ($volume in $existing) {
        if ($volume.size_gb -ne $Size -or $volume.region -notin @("ams", "fra", "cdg")) { throw "Conflicting volume for $App/$Name" }
    }
    $missing = $Count - $existing.Count
    if ($missing -gt 0) { Invoke-Fly @("volumes", "create", $Name, "--app", $App, "--region", "ams", "--size", "$Size", "--count", "$missing", "--yes") }
}
function Deploy-One([string]$Config) {
    Invoke-Fly @("deploy", "--config", (Join-Path $root $Config), "--ha=false", "--remote-only", "--wait-timeout", "2h", "--yes")
}
function Scale([string]$App, [int]$Count) { Invoke-Fly @("scale", "count", "$Count", "--app", $App, "--region", "ams", "--yes") }
function Cluster-MachineCount {
    $apps = @("mezo-web","mezo-router","mezo-queue","mezo-indexer","mezo-runner","mezo-qwen-coder","mezo-glm","mezo-deepseek","mezo-vision","mezo-fast","mezo-embedding","mezo-reranker")
    $count = 0
    foreach ($app in $apps) { if (App-Exists $app) { $count += @(& fly machines list --app $app --json | ConvertFrom-Json).Count } }
    $count
}

if ((& fly auth whoami).Trim() -ne "neomos.eg@gmail.com") { throw "Unexpected Fly account" }
if ((Cluster-MachineCount) -gt 20) { throw "MEZO cluster already exceeds 20 Machines" }

$modelToken = New-Secret
$runnerToken = New-Secret
$orchestratorToken = New-Secret
$valkeyPassword = New-Secret
$escapedValkey = [Uri]::EscapeDataString($valkeyPassword)
$valkeyUrl = "redis://default:${escapedValkey}@mezo-queue.internal:6379/0"

if ($Stage -in @("1", "all")) {
    @("mezo-web","mezo-router","mezo-queue","mezo-indexer","mezo-runner","mezo-fast","mezo-qwen-coder") | ForEach-Object { Ensure-App $_ }
    Ensure-Volumes "mezo-queue" "mezo_queue_data" 20 1
    Ensure-Volumes "mezo-indexer" "mezo_index_data" 100 1
    Ensure-Volumes "mezo-runner" "mezo_runner_data" 500 1
    Ensure-Volumes "mezo-fast" "mezo_fast_models" 100 1
    Ensure-Volumes "mezo-qwen-coder" "mezo_qwen_coder_models" 250 1
    Import-Secrets "mezo-queue" @{ VALKEY_PASSWORD = $valkeyPassword }
    Import-Secrets "mezo-web" @{ RUNNER_INTERNAL_TOKEN = $runnerToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken; VALKEY_URL = $valkeyUrl }
    Import-Secrets "mezo-router" @{ MODEL_INTERNAL_TOKEN = $modelToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken }
    Import-Secrets "mezo-indexer" @{ MODEL_INTERNAL_TOKEN = $modelToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken }
    Import-Secrets "mezo-runner" @{ RUNNER_INTERNAL_TOKEN = $runnerToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken }
    Import-Secrets "mezo-fast" @{ MODEL_INTERNAL_TOKEN = $modelToken }
    Import-Secrets "mezo-qwen-coder" @{ MODEL_INTERNAL_TOKEN = $modelToken }

    $clusters = @(& fly mpg list --org $org --json | ConvertFrom-Json)
    $postgres = $clusters | Where-Object { $_.name -eq "mezo-postgres" } | Select-Object -First 1
    if (-not $postgres) {
        Invoke-Fly @("mpg", "create", "--name", "mezo-postgres", "--org", $org, "--region", "ams", "--plan", "Launch", "--volume-size", "100", "--pg-major-version", "17")
        $postgres = @(& fly mpg list --org $org --json | ConvertFrom-Json) | Where-Object { $_.name -eq "mezo-postgres" } | Select-Object -First 1
    }
    if (-not $postgres) { throw "Managed Postgres creation could not be verified" }
    Invoke-Fly @("mpg", "attach", $postgres.id, "--app", "mezo-web")
    Invoke-Fly @("mpg", "attach", $postgres.id, "--app", "mezo-indexer")

    Deploy-One "mezo-deployment/fly/mezo-queue.toml"
    Deploy-One "mezo-deployment/fly/mezo-fast.toml"
    Deploy-One "mezo-deployment/fly/mezo-qwen-coder.toml"
    Deploy-One "mezo-deployment/fly/mezo-router.toml"
    Deploy-One "mezo-deployment/fly/mezo-indexer.toml"
    Deploy-One "mezo-deployment/fly/mezo-web.toml"
    Deploy-One "mezo-deployment/fly/mezo-runner.toml"
}

if ($Stage -in @("2", "all")) {
    @("mezo-deepseek","mezo-embedding","mezo-reranker") | ForEach-Object { Ensure-App $_ }
    Import-IfExists "mezo-queue" @{ VALKEY_PASSWORD = $valkeyPassword }
    Import-IfExists "mezo-web" @{ RUNNER_INTERNAL_TOKEN = $runnerToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken; VALKEY_URL = $valkeyUrl }
    Import-IfExists "mezo-router" @{ MODEL_INTERNAL_TOKEN = $modelToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken }
    Import-IfExists "mezo-indexer" @{ MODEL_INTERNAL_TOKEN = $modelToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken }
    Import-IfExists "mezo-runner" @{ RUNNER_INTERNAL_TOKEN = $runnerToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken }
    Import-IfExists "mezo-fast" @{ MODEL_INTERNAL_TOKEN = $modelToken }
    Import-IfExists "mezo-qwen-coder" @{ MODEL_INTERNAL_TOKEN = $modelToken }
    Ensure-Volumes "mezo-runner" "mezo_runner_data" 500 4
    Ensure-Volumes "mezo-qwen-coder" "mezo_qwen_coder_models" 250 2
    Ensure-Volumes "mezo-deepseek" "mezo_deepseek_models" 200 2
    Ensure-Volumes "mezo-embedding" "mezo_embedding_models" 100 1
    Ensure-Volumes "mezo-reranker" "mezo_reranker_models" 100 1
    Import-Secrets "mezo-deepseek" @{ MODEL_INTERNAL_TOKEN = $modelToken }
    Import-Secrets "mezo-embedding" @{ MODEL_INTERNAL_TOKEN = $modelToken }
    Import-Secrets "mezo-reranker" @{ MODEL_INTERNAL_TOKEN = $modelToken }
    Deploy-One "mezo-deployment/fly/mezo-deepseek.toml"
    Deploy-One "mezo-deployment/fly/mezo-embedding.toml"
    Deploy-One "mezo-deployment/fly/mezo-reranker.toml"
    Scale "mezo-runner" 4
    Scale "mezo-qwen-coder" 2
    Scale "mezo-deepseek" 2
}

if ($Stage -in @("3", "all")) {
    @("mezo-glm","mezo-vision") | ForEach-Object { Ensure-App $_ }
    Import-IfExists "mezo-queue" @{ VALKEY_PASSWORD = $valkeyPassword }
    Import-IfExists "mezo-web" @{ RUNNER_INTERNAL_TOKEN = $runnerToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken; VALKEY_URL = $valkeyUrl }
    Import-IfExists "mezo-router" @{ MODEL_INTERNAL_TOKEN = $modelToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken }
    Import-IfExists "mezo-indexer" @{ MODEL_INTERNAL_TOKEN = $modelToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken }
    Import-IfExists "mezo-runner" @{ RUNNER_INTERNAL_TOKEN = $runnerToken; ORCHESTRATOR_INTERNAL_TOKEN = $orchestratorToken }
    @("mezo-fast","mezo-qwen-coder","mezo-deepseek","mezo-embedding","mezo-reranker") | ForEach-Object { Import-IfExists $_ @{ MODEL_INTERNAL_TOKEN = $modelToken } }
    Ensure-Volumes "mezo-glm" "mezo_glm_models" 300 2
    Ensure-Volumes "mezo-vision" "mezo_vision_models" 250 2
    Ensure-Volumes "mezo-fast" "mezo_fast_models" 100 2
    Import-Secrets "mezo-glm" @{ MODEL_INTERNAL_TOKEN = $modelToken }
    Import-Secrets "mezo-vision" @{ MODEL_INTERNAL_TOKEN = $modelToken }
    Deploy-One "mezo-deployment/fly/mezo-glm.toml"
    Deploy-One "mezo-deployment/fly/mezo-vision.toml"
    Scale "mezo-glm" 2
    Scale "mezo-vision" 2
    Scale "mezo-fast" 2
}

$finalCount = Cluster-MachineCount
if ($Stage -eq "all" -and $finalCount -ne 20) { throw "Expected exactly 20 Machines; found $finalCount" }
Write-Output "MEZO cluster stage completed; Machine count: $finalCount"
