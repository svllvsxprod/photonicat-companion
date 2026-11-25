$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..\mobile')
flutter pub get
if ($LASTEXITCODE -ne 0) { throw 'Flutter dependencies failed' }
flutter build windows --release
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$folder = Join-Path $project 'releases\private\0.7.7-beta.1'
New-Item -ItemType Directory -Force $folder | Out-Null
$release = (Resolve-Path 'build\windows\x64\runner\Release').Path
# App-local release CRT deployment; use the toolchain's redistributable files.
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $visualStudio) { throw 'Visual Studio C++ toolchain not found' }
$crt = Get-ChildItem (Join-Path $visualStudio 'VC\Redist\MSVC') -Directory | Sort-Object Name -Descending | ForEach-Object {
  Get-ChildItem (Join-Path $_.FullName 'x64') -Directory -Filter '*.CRT' -ErrorAction SilentlyContinue
} | Select-Object -First 1
if (-not $crt) { throw 'Install the Visual C++ redistributable component in Visual Studio first' }
Copy-Item (Join-Path $crt.FullName '*.dll') $release
Compress-Archive -Path (Join-Path $release '*') -DestinationPath (Join-Path $folder 'Photonicat-0.7.7-Windows-x64.zip') -Force
$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) { throw 'Portable ZIP created. Install Inno Setup 6.3+ and add ISCC.exe to PATH to build Setup.exe.' }
& $iscc.Source "/DReleaseDir=$release" "/DArtifactDir=$folder" '/DAppVersion=0.7.7' (Join-Path $project 'installer\windows.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
