function ConvertFrom-FlyJsonOutput {
    param(
        [AllowEmptyString()][string]$Stdout,
        [AllowEmptyString()][string]$Stderr,
        [string]$CommandName,
        [int]$ExitCode = 0
    )
    $text = if ($null -eq $Stdout) { '' } else { $Stdout.Trim() }
    if ($ExitCode -ne 0) {
        $errorSource = if ($null -ne $Stderr -and $Stderr.Trim()) { $Stderr } else { $Stdout }
        $errorText = ($errorSource -replace '\s+', ' ').Trim()
        throw "Fly command '$CommandName' failed (exit $ExitCode): $errorText"
    }
    if (-not $text -or $text -in @('null', '[]') -or $text -match '(?i)^no\s+.*(managed\s+postgres|resources?|machines?|volumes?|apps?).*found(?:\s+.*)?\.?$') {
        return @()
    }
    if ($text[0] -notin @('{', '[')) {
        $sanitized = (($text -replace '\s+', ' ').Trim())
        if ($sanitized.Length -gt 500) { $sanitized = $sanitized.Substring(0, 500) + '...' }
        throw "Fly command '$CommandName' returned unexpected non-JSON output: $sanitized"
    }
    try {
        return @($text | ConvertFrom-Json)
    } catch {
        throw "Fly command '$CommandName' returned invalid JSON: $($_.Exception.Message)"
    }
}

function ConvertTo-FlyProcessArgument([string]$Value) {
    if ($Value -notmatch '[\s"]') { return $Value }
    '"' + $Value.Replace('"', '\"') + '"'
}

function Invoke-FlyJson {
    param([string[]]$Arguments, [string]$CommandName = 'fly')
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = 'fly'
    $start.Arguments = (($Arguments | ForEach-Object { ConvertTo-FlyProcessArgument $_ }) -join ' ')
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    ConvertFrom-FlyJsonOutput -Stdout $stdout -Stderr $stderr -CommandName $CommandName -ExitCode $process.ExitCode
}
