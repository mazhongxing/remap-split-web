# 生成 QiePing_2D_v01.nk
#
# Nuke 的 -t 无法加载带中文路径的 .py（UnicodeDecodeError），所以先把脚本
# 拷到一个纯英文目录再执行；生成的 .nk 会写回工程目录。
#
# 用法： powershell -ExecutionPolicy Bypass -File run_build_nk.ps1

$ErrorActionPreference = 'Stop'

$here  = $PSScriptRoot
$stage = 'D:\codex\_qieping_bake\nk2d'
$nuke  = 'C:\Program Files\Nuke14.0v2\Nuke14.0.exe'

if (-not (Test-Path $nuke)) { throw "找不到 Nuke: $nuke" }
if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item -LiteralPath (Join-Path $here 'build_2d_nk.py') -Destination $stage

& $nuke -t (Join-Path $stage 'build_2d_nk.py')
if ($LASTEXITCODE -ne 0) { throw "生成 .nk 失败，退出码 $LASTEXITCODE" }

Get-Item (Join-Path $here '..\QiePing_2D_v01.nk') | Select-Object FullName, Length | Format-List
