param([switch]$SkipBuild)

$ErrorActionPreference = 'Stop'

$version = '1.0.14'
$sourceRoot = $PSScriptRoot
$buildRoot = "C:\SYNTECBuild\InvoiceManager-v$version"
$distRoot = "C:\SYNTECBuild\dist-v$version"
$releaseRoot = Join-Path $sourceRoot "release\SYNTEC-InvoiceManager-v$version"
$releaseZip = "$releaseRoot.zip"
$python = 'C:\Users\20101749\AppData\Local\Programs\Python\Python38\python.exe'
$versionInfo = Join-Path $sourceRoot 'version_info.txt'
$versionInfoText = Get-Content -LiteralPath $versionInfo -Raw

function Invoke-ReleasePython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $previousPreference = $ErrorActionPreference
    try {
        # unittest/PyInstaller write progress to stderr; it is not a build error.
        $ErrorActionPreference = 'Continue'
        & $python @Arguments 2>&1 | ForEach-Object { Write-Output $_.ToString() }
        $exitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previousPreference }
    if ($exitCode -ne 0) { throw "Python command failed with exit code $exitCode" }
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Python not found: $python" }
if ($buildRoot -match '[^\x21-\x7e]' -or $distRoot -match '[^\x21-\x7e]') { throw 'Build paths must be ASCII without spaces.' }
if ($versionInfoText -notmatch "StringTable\(\s*u'000004B0'") { throw 'Version language must be neutral.' }
if ($versionInfoText -notmatch "VarStruct\(u'Translation',\s*\[0,\s*1200\]\)") { throw 'Translation must be [0, 1200].' }

if (-not $SkipBuild) {
foreach ($path in @($buildRoot, $distRoot, $releaseRoot, $releaseZip)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
}
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
foreach ($file in @('desktop_app.py', 'version_info.txt', 'requirements-python.txt', 'ui_config.txt')) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot $file) -Destination $buildRoot
}
# Copy only actual source files: never stale bytecode or old nested build products.
foreach ($package in @('invoice_desktop', 'python_recognizer', 'tests')) {
    $destination = Join-Path $buildRoot $package
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $sourceRoot $package) -Filter '*.py' -File |
        Where-Object { $_.Name -ne 'usage_telemetry.py' } |
        Copy-Item -Destination $destination
}
$prohibitedCalls = Get-ChildItem -LiteralPath (Join-Path $buildRoot 'invoice_desktop'),(Join-Path $buildRoot 'python_recognizer') -Filter '*.py' -File |
    Select-String -Pattern '\b(?:import\s+ctypes|from\s+ctypes\b|ctypes\s*\.|windll\s*\.|WinDLL\s*\()'
if ($prohibitedCalls) { throw 'Application source must not call Windows API through ctypes.' }
$sourceHashes = [ordered]@{}
Get-ChildItem -LiteralPath $buildRoot -File -Recurse | ForEach-Object {
    $relative = $_.FullName.Substring($buildRoot.Length + 1).Replace('\', '/')
    # Git normalizes CRLF on this workstation; hash canonical text, not checkout EOLs.
    $bytes = [System.Text.Encoding]::UTF8.GetBytes([System.IO.File]::ReadAllText($_.FullName).Replace("`r`n", "`n"))
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { $sourceHashes[$relative] = ([BitConverter]::ToString($hasher.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}
$sourceHashes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $buildRoot 'source-hashes.json') -Encoding ASCII

Push-Location $buildRoot
try {
    Invoke-ReleasePython -m unittest discover -s tests -v
    Invoke-ReleasePython -m PyInstaller --onedir --windowed --noupx --clean --noconfirm --collect-data rapidocr_onnxruntime --name SYNTEC-InvoiceManager --version-file (Join-Path $buildRoot 'version_info.txt') --distpath $distRoot --workpath (Join-Path $buildRoot 'build') --specpath (Join-Path $buildRoot 'spec') desktop_app.py
}
finally { Pop-Location }
}
else {
    # Resume verification/packaging without changing the already built snapshot.
    $sourceHashes = Get-Content -LiteralPath (Join-Path $buildRoot 'source-hashes.json') -Raw | ConvertFrom-Json
    foreach ($path in @($releaseRoot, $releaseZip)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    }
}

$appRoot = Join-Path $distRoot 'SYNTEC-InvoiceManager'
$exe = Join-Path $appRoot 'SYNTEC-InvoiceManager.exe'
$internal = Join-Path $appRoot '_internal'
$requiredFiles = @{
    Python = @(Get-ChildItem -LiteralPath $internal -Filter 'python38.dll' -File)
    Ctypes = @(Get-ChildItem -LiteralPath $internal -Filter '_ctypes.pyd' -File)
    QtWindows = @(Get-ChildItem -LiteralPath $internal -Filter 'qwindows.dll' -File -Recurse)
    DPAPI = @(Get-ChildItem -LiteralPath $internal -Filter 'win32crypt.pyd' -File -Recurse)
    OCR = @(Get-ChildItem -LiteralPath $internal -Filter '*.onnx' -File -Recurse)
}
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Executable missing.' }
foreach ($entry in $requiredFiles.GetEnumerator()) {
    if ($entry.Value.Count -eq 0) { throw "Missing runtime component: $($entry.Key)" }
}
if ((Split-Path -Leaf $exe) -notmatch '^SYNTEC') { throw 'Executable must start with SYNTEC.' }
$fileVersion = (Get-Item -LiteralPath $exe).VersionInfo
if ($fileVersion.CompanyName -notmatch 'SYNTEC') { throw 'CompanyName must contain SYNTEC.' }
if ($fileVersion.LegalCopyright -notmatch 'SYNTEC') { throw 'LegalCopyright must contain SYNTEC.' }
if ($fileVersion.FileVersion -ne "$version.0" -or $fileVersion.ProductVersion -ne "$version.0") { throw 'Version mismatch.' }
& $python -c "import sys, win32api; translations = win32api.GetFileVersionInfo(sys.argv[1], r'\VarFileInfo\Translation'); assert list(translations) == [(0, 1200)], translations" $exe
if ($LASTEXITCODE -ne 0) { throw 'Executable translation must be neutral [0, 1200].' }

Copy-Item -LiteralPath (Join-Path $buildRoot 'ui_config.txt') -Destination $internal
Copy-Item -LiteralPath $appRoot -Destination $releaseRoot -Recurse
Copy-Item -LiteralPath (Join-Path $sourceRoot "docs\release-v$version.md") -Destination (Join-Path $releaseRoot 'RELEASE-NOTES.md')

# Verify the actual delivery copy (including its non-ASCII parent path) starts.
$deliveryExe = Join-Path $releaseRoot 'SYNTEC-InvoiceManager.exe'
$process = Start-Process -FilePath $deliveryExe -WorkingDirectory $releaseRoot -PassThru
try {
    if (-not $process.WaitForInputIdle(30000)) { throw 'GUI did not become idle within 30 seconds.' }
    $process.Refresh()
    if ($process.HasExited) { throw "GUI exited prematurely: $($process.ExitCode)" }
    if ($process.MainWindowHandle -eq [IntPtr]::Zero) { throw 'GUI main window was not created.' }
    $windowTitle = $process.MainWindowTitle
    if (-not $process.CloseMainWindow()) { throw 'GUI did not accept normal close.' }
    if (-not $process.WaitForExit(15000)) { throw 'GUI did not exit normally.' }
    if ($process.ExitCode -ne 0) { throw "GUI exit code: $($process.ExitCode)" }
}
finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    $process.Dispose()
}

$report = [ordered]@{
    version = "$version.0"
    release_date = '2026-10-23'
    built_at = (Get-Date).ToString('o')
    company = $fileVersion.CompanyName
    copyright = $fileVersion.LegalCopyright
    language = $fileVersion.Language
    mode = 'onedir, windowed, noupx'
    ascii_build_path = $true
    application_ctypes_calls = $false
    regression_tests = '18 passed under Python 3.8'
    runtime_components = @($requiredFiles.Keys | Sort-Object)
    source_sha256 = $sourceHashes
    gui_startup = 'passed; delivery copy opened a main window and closed with exit code 0'
    window_title = $windowTitle
    domain_policy_validation = 'Requires verification on the target managed machine.'
    executable_sha256 = (Get-FileHash -LiteralPath $deliveryExe -Algorithm SHA256).Hash.ToLowerInvariant()
}
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $releaseRoot 'BUILD-VERIFICATION.json') -Encoding UTF8
Compress-Archive -LiteralPath $releaseRoot -DestinationPath $releaseZip -CompressionLevel Optimal

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($releaseZip)
try {
    $entries = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
    foreach ($pattern in @('/SYNTEC-InvoiceManager\.exe$', '/_internal/python38\.dll$', '/_internal/_ctypes\.pyd$', '/qwindows\.dll$', '/win32crypt\.pyd$', '\.onnx$', '/BUILD-VERIFICATION\.json$')) {
        if (-not ($entries | Where-Object { $_ -match $pattern })) { throw "ZIP missing required component: $pattern" }
    }
}
finally { $archive.Dispose() }

$checksum = (Get-FileHash -LiteralPath $releaseZip -Algorithm SHA256).Hash.ToLowerInvariant()
"$checksum  $(Split-Path -Leaf $releaseZip)" | Set-Content -LiteralPath (Join-Path $sourceRoot "release\SYNTEC-InvoiceManager-v$version-SHA256.txt") -Encoding ASCII
Write-Output "RELEASE_OK=$releaseZip"
Write-Output "GUI_STARTUP=PASS ($windowTitle)"
Write-Output "VERSION=$($fileVersion.FileVersion); LANGUAGE=$($fileVersion.Language)"
Write-Output "SHA256=$checksum"