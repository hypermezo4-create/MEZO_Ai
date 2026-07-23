$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "MEZO AI\bin"
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot "mezo.py") (Join-Path $installRoot "mezo.py")
$python = (Get-Command python).Source
$wrapper = "@echo off`r`n`"$python`" `"$installRoot\mezo.py`" %*`r`n"
Set-Content -Encoding Ascii -Path (Join-Path $installRoot "mezo.cmd") -Value $wrapper
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $installRoot) {
    [Environment]::SetEnvironmentVariable("Path", (($userPath.TrimEnd(";") + ";" + $installRoot).TrimStart(";")), "User")
}
Write-Output (Join-Path $installRoot "mezo.cmd")
