# 把烤图脚本挪到纯英文路径下再交给 Nuke 执行。
#
# Nuke 14 的 -t 模式无法处理带中文的 .py 路径（会抛 UnicodeDecodeError），
# 所以先整体拷到 D:\codex\_qieping_bake\stage，跑完再把结果拷回来。
#
# 用法：  powershell -ExecutionPolicy Bypass -File run_bake.ps1

$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
$stage = 'D:\codex\_qieping_bake\stage'
$nuke = 'C:\Program Files\Nuke14.0v2\Nuke14.0.exe'

if (-not (Test-Path $nuke)) { throw "Nuke not found: $nuke" }

if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'ref') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'scratch') | Out-Null

Copy-Item -LiteralPath (Join-Path $here 'bake_maps.py') -Destination $stage
Copy-Item -LiteralPath (Join-Path $here 'template.nk') -Destination $stage
Copy-Item -Path (Join-Path $here 'ref\*') -Destination (Join-Path $stage 'ref')

Write-Host "baking in $stage ..."
& $nuke -t (Join-Path $stage 'bake_maps.py')
if ($LASTEXITCODE -ne 0) { throw "Nuke bake failed with exit code $LASTEXITCODE" }

$out = Join-Path $here 'scratch'
New-Item -ItemType Directory -Force -Path $out | Out-Null
Copy-Item -Path (Join-Path $stage 'scratch\*') -Destination $out -Force

Get-ChildItem -LiteralPath $out | Select-Object Name, Length | Format-Table -AutoSize
Write-Host "done: $out"
