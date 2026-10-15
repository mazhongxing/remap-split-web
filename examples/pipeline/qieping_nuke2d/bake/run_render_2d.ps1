# 无头渲染 2D 版工程
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File run_render_2d.ps1 `
#       -OutDir "D:\codex\_qieping_bake\out2d_1004C" -First 1 -Last 4
#
# 可选 -Artwork 做交叉验证，例如：
#   -Artwork "W:\...\QiePingSuCai\1001B\B###.png"

# 注意：脚本里不要出现中文常量。Windows PowerShell 5.1 会把没有 BOM 的 .ps1
# 当成 ANSI 读，中文会变成乱码。路径一律从 $PSScriptRoot 推。
# OutDir 不给就用 .nk 里写好的现网路径（OutDir 为空时把输出改写到指定目录）
param(
    [string]$OutDir = '',
    [string]$Nk = '',
    [int]$First = 1,
    [int]$Last = 4,
    [string]$Artwork = ''
)

$ErrorActionPreference = 'Stop'

$here  = $PSScriptRoot
$proj  = Split-Path $here -Parent
$stage = 'D:\codex\_qieping_bake\nk2d'
$nuke  = 'C:\Program Files\Nuke14.0v2\Nuke14.0.exe'

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item -LiteralPath (Join-Path $here 'render_2d.py') -Destination $stage
if ($Nk -eq '') { $Nk = Join-Path $proj 'QiePing_2D_v01.nk' }
Copy-Item -LiteralPath $Nk -Destination $stage
$stagedNk = Join-Path $stage (Split-Path $Nk -Leaf)

# Nuke 的 -t 不会把额外命令行参数交给脚本，所以走环境变量
$env:QIEPING_NK    = $stagedNk
$env:QIEPING_FIRST = "$First"
$env:QIEPING_LAST  = "$Last"
if ($OutDir -ne '') { $env:QIEPING_OUT = $OutDir } else { Remove-Item Env:\QIEPING_OUT -ErrorAction SilentlyContinue }
if ($Artwork -ne '') { $env:QIEPING_ART = $Artwork } else { Remove-Item Env:\QIEPING_ART -ErrorAction SilentlyContinue }

& $nuke -t (Join-Path $stage 'render_2d.py')
if ($LASTEXITCODE -ne 0) { throw "渲染失败，退出码 $LASTEXITCODE" }

Get-ChildItem -LiteralPath $OutDir -Recurse -File | Measure-Object -Property Length -Sum |
    Select-Object Count, @{n='MB'; e={[math]::Round($_.Sum / 1MB, 1)}} | Format-List
