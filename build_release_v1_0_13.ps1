$ErrorActionPreference = 'Stop'

$version = '1.0.13'
$sourceRoot = $PSScriptRoot
$buildRoot = "C:\SYNTECBuild\InvoiceManager-v$version"
$distRoot = "C:\SYNTECBuild\dist-v$version"
$releaseRoot = Join-Path $sourceRoot "release\SYNTEC-InvoiceManager-v$version"
$releaseZip = Join-Path $sourceRoot "release\SYNTEC-InvoiceManager-v$version.zip"
$python = 'C:\Users\20101749\AppData\Local\Programs\Python\Python38\python.exe'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Python interpreter not found: $python" }

$versionInfo = Join-Path $sourceRoot 'version_info.txt'
$versionInfoText = Get-Content -LiteralPath $versionInfo -Raw
if ($versionInfoText -notmatch "StringTable\(\s*u'000004B0'") { throw 'Version language must be neutral (000004B0).' }
if ($versionInfoText -notmatch "VarStruct\(u'Translation',\s*\[0,\s*1200\]\)") { throw 'Version translation must be [0, 1200].' }

Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $distRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $releaseRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $releaseZip -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null

# Build only from this ASCII-only staging path for SYNTEC domain-controller compatibility.
Copy-Item -LiteralPath (Join-Path $sourceRoot 'desktop_app.py') -Destination $buildRoot -Force
Copy-Item -LiteralPath $versionInfo -Destination $buildRoot -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'invoice_desktop') -Destination $buildRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'python_recognizer') -Destination $buildRoot -Recurse -Force

Push-Location $buildRoot
try {
    & $python -m PyInstaller --onedir --windowed --noupx --clean --noconfirm --name SYNTEC-InvoiceManager --version-file (Join-Path $buildRoot 'version_info.txt') --distpath $distRoot --workpath (Join-Path $buildRoot 'build') --specpath (Join-Path $buildRoot 'spec') desktop_app.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }
}
finally {
    Pop-Location
}

$appRoot = Join-Path $distRoot 'SYNTEC-InvoiceManager'
$exe = Join-Path $appRoot 'SYNTEC-InvoiceManager.exe'
$internal = Join-Path $appRoot '_internal'
$pythonDll = Get-ChildItem -Path $internal -Filter 'python*.dll' -File | Select-Object -First 1
$ctypesPyd = Get-ChildItem -Path $internal -Filter '_ctypes*.pyd' -File | Select-Object -First 1
$qtPlatformPlugin = Get-ChildItem -Path $internal -Filter 'qwindows.dll' -File -Recurse | Select-Object -First 1
$dpapiModule = Get-ChildItem -Path $internal -Filter 'win32crypt.pyd' -File -Recurse | Select-Object -First 1
$config = Join-Path $sourceRoot 'ui_config.txt'

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Executable was not created.' }
if (-not $pythonDll) { throw 'Embedded Python DLL is missing.' }
if (-not $ctypesPyd) { throw 'Embedded _ctypes extension is missing.' }
if (-not $qtPlatformPlugin) { throw 'Embedded Qt Windows platform plugin is missing.' }
if (-not $dpapiModule) { throw 'Embedded PyWin32 DPAPI module is missing.' }
if ((Split-Path -Leaf $exe) -notmatch '^SYNTEC') { throw 'Executable name must start with SYNTEC.' }
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) { throw 'UI config file is missing.' }

$fileVersion = (Get-Item -LiteralPath $exe).VersionInfo
if ($fileVersion.CompanyName -notmatch 'SYNTEC') { throw 'CompanyName must include SYNTEC.' }
if ($fileVersion.LegalCopyright -notmatch 'SYNTEC') { throw 'LegalCopyright must include SYNTEC.' }
if ($fileVersion.FileVersion -ne "$version.0") { throw "Unexpected file version: $($fileVersion.FileVersion)" }
if ($fileVersion.ProductVersion -ne "$version.0") { throw "Unexpected product version: $($fileVersion.ProductVersion)" }
if ($fileVersion.Language -notmatch '语言中性|Neutral Language') { throw "Unexpected version resource language: $($fileVersion.Language)" }

Copy-Item -LiteralPath $config -Destination $internal -Force
Copy-Item -LiteralPath $appRoot -Destination $releaseRoot -Recurse -Force
Compress-Archive -LiteralPath $releaseRoot -DestinationPath $releaseZip -CompressionLevel Optimal -Force
if (-not (Test-Path -LiteralPath $releaseZip -PathType Leaf)) { throw 'Release ZIP was not created.' }

$null = Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($releaseZip)
try {
    $archiveEntries = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    if (-not ($archiveEntries | Where-Object { $_ -match '(^|/)SYNTEC-InvoiceManager\.exe$' })) { throw 'Release ZIP does not contain the executable.' }
    if (-not ($archiveEntries | Where-Object { $_ -match '(^|/)_internal/.*/qwindows\.dll$' })) { throw 'Release ZIP does not contain the Qt Windows platform plugin.' }
    if (-not ($archiveEntries | Where-Object { $_ -match '(^|/)_internal/win32/win32crypt\.pyd$' })) { throw 'Release ZIP does not contain the PyWin32 DPAPI module.' }
} finally {
    $archive.Dispose()
}

Write-Output "Build succeeded: $exe"
Write-Output "Release directory: $releaseRoot"
Write-Output "Release package: $releaseZip"
Write-Output "Embedded Python: $($pythonDll.Name)"
Write-Output "Embedded ctypes: $($ctypesPyd.Name)"
Write-Output "Qt Windows plugin: $($qtPlatformPlugin.FullName)"
Write-Output "DPAPI module: $($dpapiModule.FullName)"
Write-Output "Version: $($fileVersion.CompanyName) | $($fileVersion.LegalCopyright) | $($fileVersion.FileVersion)"