# 交叉验证：让 Nuke 按原工程把指定素材渲成 A/B/D/F，再用 verify.py 对比。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File run_render.ps1 `
#       -Image "W:\...\QiePingSuCai\1001B\B001.png" -OutDir "D:\codex\_qieping_bake\ref1001B"

param(
    [Parameter(Mandatory = $true)][string]$Image,
    [Parameter(Mandatory = $true)][string]$OutDir
)

$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
$stage = 'D:\codex\_qieping_bake\stage'
$nuke = 'C:\Program Files\Nuke14.0v2\Nuke14.0.exe'

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'ref') | Out-Null

Copy-Item -LiteralPath (Join-Path $here 'render_case.py') -Destination $stage
Copy-Item -LiteralPath (Join-Path $here 'template.nk') -Destination $stage

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "rendering $Image -> $OutDir"
& $nuke -t (Join-Path $stage 'render_case.py') $Image $OutDir
if ($LASTEXITCODE -ne 0) { throw "Nuke render failed with exit code $LASTEXITCODE" }

Get-ChildItem -LiteralPath $OutDir | Select-Object Name, Length | Format-Table -AutoSize
