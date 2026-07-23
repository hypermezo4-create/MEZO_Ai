$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\fly-json.ps1')
function Assert-Count($Value, [int]$Expected) { if (@($Value | Where-Object { $null -ne $_ }).Count -ne $Expected) { throw "Expected $Expected result(s)" } }
Assert-Count (ConvertFrom-FlyJsonOutput '[{"name":"one"}]' '' 'test array') 1
Assert-Count (ConvertFrom-FlyJsonOutput '{"name":"one"}' '' 'test object') 1
Assert-Count (ConvertFrom-FlyJsonOutput '' '' 'test empty') 0
Assert-Count (ConvertFrom-FlyJsonOutput '[]' '' 'test brackets') 0
Assert-Count (ConvertFrom-FlyJsonOutput 'null' '' 'test null') 0
Assert-Count (ConvertFrom-FlyJsonOutput 'No managed postgres clusters found' '' 'test no MPG') 0
Assert-Count (ConvertFrom-FlyJsonOutput 'No managed postgres clusters found in organization personal' '' 'test no MPG org') 0
$thrown = $false; try { ConvertFrom-FlyJsonOutput 'billing required' '' 'test unexpected' } catch { $thrown = $true }; if (-not $thrown) { throw 'Unexpected non-JSON output was accepted' }
$thrown = $false; try { ConvertFrom-FlyJsonOutput '' 'quota exceeded' 'test nonzero' 2 } catch { $thrown = $true }; if (-not $thrown) { throw 'Nonzero command was accepted' }
'fly JSON parser tests passed'
