$ErrorActionPreference = 'Stop'

$sourceRoot = $PSScriptRoot
$buildRoot = 'C:\SYNTECBuild\InvoiceManager-v1.0.7'
$distRoot = 'C:\SYNTECBuild\dist-v1.0.7'
$releaseZip = Join-Path $sourceRoot 'release\SYNTEC-InvoiceManager-v1.0.7.zip'
$python = 'C:\Users\20101749\AppData\Local\Programs\Python\Python38\python.exe'

Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $distRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null

# 域控环境要求：在纯英文路径中直接执行 PyInstaller，并禁用 UPX。
Copy-Item -LiteralPath (Join-Path $sourceRoot 'desktop_app.py') -Destination $buildRoot -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'version_info.txt') -Destination $buildRoot -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'invoice_desktop') -Destination $buildRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'python_recognizer') -Destination $buildRoot -Recurse -Force

Push-Location $buildRoot
try {
    & $python -m PyInstaller --onedir --windowed --noupx --clean --noconfirm --name SYNTEC-InvoiceManager --version-file (Join-Path $buildRoot 'version_info.txt') --distpath $distRoot --workpath (Join-Path $buildRoot 'build') --specpath (Join-Path $buildRoot 'spec') desktop_app.py
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

$appRoot = Join-Path $distRoot 'SYNTEC-InvoiceManager'
$exe = Join-Path $appRoot 'SYNTEC-InvoiceManager.exe'
$internal = Join-Path $appRoot '_internal'
$pythonDll = Get-ChildItem -Path $internal -Filter 'python*.dll' -File | Select-Object -First 1
$ctypesPyd = Get-ChildItem -Path $internal -Filter '_ctypes*.pyd' -File | Select-Object -First 1
$version = (Get-Item -LiteralPath $exe).VersionInfo
$manual = Join-Path $sourceRoot 'docs\发票管理系统操作说明书-v1.0.7.docx'

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Executable was not created.' }
if (-not $pythonDll) { throw 'Embedded Python DLL is missing.' }
if (-not $ctypesPyd) { throw 'Embedded ctypes extension is missing.' }
if ((Split-Path -Leaf $exe) -notmatch '^SYNTEC') { throw 'Executable name must start with SYNTEC.' }
if ($version.CompanyName -notmatch 'SYNTEC') { throw 'CompanyName must include SYNTEC.' }
if ($version.LegalCopyright -notmatch 'SYNTEC') { throw 'LegalCopyright must include SYNTEC.' }
if ($version.FileVersion -notmatch '^1\.0\.7\.0') { throw 'Unexpected file version.' }
if (-not (Test-Path -LiteralPath $manual -PathType Leaf)) { throw 'User manual is missing.' }

Copy-Item -LiteralPath $manual -Destination $appRoot -Force
Remove-Item -LiteralPath $releaseZip -Force -ErrorAction SilentlyContinue
Compress-Archive -LiteralPath $appRoot -DestinationPath $releaseZip -CompressionLevel Optimal -Force
if (-not (Test-Path -LiteralPath $releaseZip -PathType Leaf)) { throw 'Release ZIP was not created.' }

Write-Output "Build succeeded: $exe"
Write-Output "Release package: $releaseZip"
Write-Output "Embedded Python: $($pythonDll.Name)"
Write-Output "Embedded ctypes: $($ctypesPyd.Name)"
Write-Output "Version: $($version.CompanyName) | $($version.LegalCopyright) | $($version.FileVersion)"