# 交叉验证：用 UV EXR 原样渲一遍指定素材（放到纯英文路径下跑）。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File run_render_ref.ps1 `
#       -Art "W:/.../source/1006/water.jpg" -OutDir "D:\codex\_qieping_uv2d\ref_water"

param(
    [Parameter(Mandatory = $true)][string]$Art,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$UvDir  = 'W:/2026/20260701_LangJiu_ShanGuGuangYingXiu/comp/Nuke/UV',
    [string]$Screens = 'A,B,D,F'
)

$ErrorActionPreference = 'Stop'

$here  = $PSScriptRoot
$stage = 'D:\codex\_qieping_uv2d\stage_ref'
$nuke  = 'C:\Program Files\Nuke14.0v2\Nuke14.0.exe'

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item -LiteralPath (Join-Path $here 'render_ref.py') -Destination $stage

$env:UV2D_ART     = $Art
$env:UV2D_OUT     = $OutDir
$env:UV2D_UV_DIR  = $UvDir
$env:UV2D_SCREENS = $Screens

Write-Host "参考渲染: $Art"
& $nuke -t (Join-Path $stage 'render_ref.py')
if ($LASTEXITCODE -ne 0) { throw "Nuke 渲染失败，退出码 $LASTEXITCODE" }

Get-ChildItem -LiteralPath $OutDir | Select-Object Name, Length | Format-Table -AutoSize
