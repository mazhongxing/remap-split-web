# Stage the export script to an ASCII-only path and run it in Nuke.
#
# Nuke 14's -t mode cannot load a .py from a non-ASCII path (UnicodeDecodeError),
# so this copies the script to %TEMP%\remap_split_web_stage and copies raw/ back.
#
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads UTF-8 without BOM
# as GBK, and non-ASCII characters break the parser.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File run_export.ps1 `
#       -SetDir "D:\proj\sets\MySet" -UvDir "W:/proj/UV" -Pattern "UV_{screen}.exr" -Screens A,B,D,F

param(
    [Parameter(Mandatory = $true)][string]$SetDir,
    [Parameter(Mandatory = $true)][string]$UvDir,
    [string]$Pattern  = 'UV_{screen}.exr',
    [string]$Screens  = 'A,B,D,F',
    [string]$SetName  = '',
    [string]$NukeExe  = 'C:\Program Files\Nuke14.0v2\Nuke14.0.exe'
)

$ErrorActionPreference = 'Stop'

$here  = $PSScriptRoot
$stage = Join-Path $env:TEMP 'remap_split_web_stage'
if (-not (Test-Path $NukeExe)) { throw "找不到 Nuke: $NukeExe" }
if ([string]::IsNullOrWhiteSpace($SetName)) { $SetName = Split-Path $SetDir -Leaf }

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'out\raw') | Out-Null
Copy-Item -LiteralPath (Join-Path $here 'export_uvset.py') -Destination $stage

$env:UV2D_SET_NAME = $SetName
$env:UV2D_UV_DIR   = $UvDir
$env:UV2D_PATTERN  = $Pattern
$env:UV2D_SCREENS  = $Screens
$env:UV2D_OUT_DIR  = (Join-Path $stage 'out')

Write-Host "Exporting coordinate map set: $SetName"
& $NukeExe -t (Join-Path $stage 'export_uvset.py')
if ($LASTEXITCODE -ne 0) { throw "Nuke export failed with exit code $LASTEXITCODE" }

$rawOut = Join-Path $SetDir 'raw'
New-Item -ItemType Directory -Force -Path $rawOut | Out-Null
Copy-Item -Path (Join-Path $stage 'out\raw\*') -Destination $rawOut -Force
Copy-Item -LiteralPath (Join-Path $stage 'out\screens.txt') -Destination $SetDir -Force

Get-ChildItem -LiteralPath $rawOut | Select-Object Name, Length | Format-Table -AutoSize
Write-Host "Raw materials ready: $rawOut"
Write-Host "Next: python pack_uvset.py `"$SetDir`" $SetName 4"
