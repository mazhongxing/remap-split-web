# Cross-check: render an arbitrary artwork through the coordinate maps in Nuke,
# producing the reference images to compare against. Run from an ASCII-only path.
#
# NOTE: keep this file ASCII-only (PowerShell 5.1 reads UTF-8 without BOM as GBK).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File run_render_ref.ps1 `
#       -Art "W:/proj/artwork.jpg" -OutDir "D:/tmp/ref" -UvDir "W:/proj/UV" -Pattern "UV_{screen}.exr"

param(
    [Parameter(Mandatory = $true)][string]$Art,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [Parameter(Mandatory = $true)][string]$UvDir,
    [string]$Pattern  = 'UV_{screen}.exr',
    [string]$Screens  = 'A,B,D,F',
    [string]$NukeExe  = 'C:\Program Files\Nuke14.0v2\Nuke14.0.exe'
)

$ErrorActionPreference = 'Stop'

$here  = $PSScriptRoot
$stage = Join-Path $env:TEMP 'remap_split_web_stage_ref'
if (-not (Test-Path $NukeExe)) { throw "找不到 Nuke: $NukeExe" }

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item -LiteralPath (Join-Path $here 'render_ref.py') -Destination $stage

$env:UV2D_ART     = $Art
$env:UV2D_OUT     = $OutDir
$env:UV2D_UV_DIR  = $UvDir
$env:UV2D_PATTERN = $Pattern
$env:UV2D_SCREENS = $Screens

Write-Host "Reference render: $Art"
& $NukeExe -t (Join-Path $stage 'render_ref.py')
if ($LASTEXITCODE -ne 0) { throw "Nuke render failed with exit code $LASTEXITCODE" }

Get-ChildItem -LiteralPath $OutDir | Select-Object Name, Length | Format-Table -AutoSize
