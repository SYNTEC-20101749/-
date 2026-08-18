$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot
& 'C:\Users\20101749\AppData\Local\Programs\Python\Python38\python.exe' (Join-Path $PSScriptRoot 'tools\publish_release_v1_0_9.py')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
