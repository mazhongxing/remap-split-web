# 把导出脚本挪到纯英文路径再交给 Nuke 跑。
#
# Nuke 14 的 -t 无法加载带中文路径的 .py（UnicodeDecodeError），
# 所以先整体拷到 D:\codex\_qieping_uv2d\stage，跑完再把 raw/ 拷回来。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File run_export.ps1
#   powershell -ExecutionPolicy Bypass -File run_export.ps1 -SetName MySet -UvDir "W:/.../UV"

param(
    [string]$SetName = 'LangJiu_1014_ABCD',
    [string]$UvDir   = 'W:/2026/20260701_LangJiu_ShanGuGuangYingXiu/comp/Nuke/UV',
    [string]$Screens  = 'A,B,D,F'
)

$ErrorActionPreference = 'Stop'

$here    = $PSScriptRoot
$root    = Split-Path $here -Parent
$stage   = 'D:\codex\_qieping_uv2d\stage'
$nuke    = 'C:\Program Files\Nuke14.0v2\Nuke14.0.exe'
$rawStage = Join-Path $stage 'out\raw'
$setDir  = Join-Path (Join-Path $root 'sets') $SetName

if (-not (Test-Path $nuke)) { throw "找不到 Nuke: $nuke" }

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage, $rawStage | Out-Null
Copy-Item -LiteralPath (Join-Path $here 'export_uvset.py') -Destination $stage

$env:UV2D_SET_NAME = $SetName
$env:UV2D_UV_DIR   = $UvDir
$env:UV2D_SCREENS  = $Screens
$env:UV2D_OUT_DIR  = (Join-Path $stage 'out')

Write-Host "导出 UV 集合 $SetName ..."
& $nuke -t (Join-Path $stage 'export_uvset.py')
if ($LASTEXITCODE -ne 0) { throw "Nuke 导出失败，退出码 $LASTEXITCODE" }

$rawOut = Join-Path $setDir 'raw'
New-Item -ItemType Directory -Force -Path $rawOut | Out-Null
Copy-Item -Path (Join-Path $rawStage '*') -Destination $rawOut -Force
Copy-Item -LiteralPath (Join-Path $stage 'out\screens.txt') -Destination $setDir -Force

Get-ChildItem -LiteralPath $rawOut | Select-Object Name, Length | Format-Table -AutoSize
Write-Host "原料已就绪: $rawOut"
Write-Host "下一步: python pack_uvset.py `"$setDir`""
