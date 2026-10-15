# 切屏 2D 版 Nuke 工程（不用任何 3D 节点）

把原来的 `ReadGeo2 → Project3D2 → ScanlineRender → Reformat` 那条 3D 链，
换成一条纯 2D 的 `Read → STMap → Multiply → Write`：先把"输入画面到每块屏的映射"
离线烤成一张坐标图，之后渲染就只是按坐标取色。

## 怎么用

1. 用 Nuke 14 打开 `QiePing_2D_v01.nk`。
2. **换素材只改 `SrcArtwork` 这一个 Read 的路径**（默认是
   `QiePingSuCai/1004/C/###.jpg`，帧范围 1–4）。
3. 直接渲染四个 Write 即可。输出默认写到：

   `W:/…/comp/Out_QiePing/QiePing2D_1004C/QiePing2D_1004C_{A,B,D,F}/…%04d.png`

出图规格和现网一致：A 6600×1700、B 6600×1580、D 3400×1300、F 3750×750，
8-bit sRGB PNG、黑底。只用到核心 Nuke 的四个节点，**不需要 NukeX 授权**。

## 节点链

```
Read(素材)  ─────────────────────────────┐
                                          ├─ STMap ── Multiply ── Write
Read(map_<屏>.png) ───────────────────────┘   ▲          ▲
                                               │          │
Read(mask_<屏>.png) ───────────────────────────┘          │
                                                          └─ 覆盖率蒙版
```

* `STMap`：**input 0 = src（素材），input 1 = map（映射图）**；`uv` 选上承载 u/v 的通道
  （`rgba`）、`filter = Mitchell`、`premultiplied` 关。
* `Multiply`（Merge2，operation = multiply）：另一路接 `mask_<屏>`，`maskChannel = none`。
* `Write`：8-bit sRGB PNG。

对应关系：`输出 = 素材[按 map 的坐标采样] × 覆盖率`。

## 映射素材

`maps/` 下每块屏两个文件：

| 文件 | 内容 |
| --- | --- |
| `map_<屏>.png` | 16-bit RGB。R = 横向坐标 u（反预乘后），G = **1 − 纵向坐标 v**，B = 0 |
| `mask_<屏>.png` | 8-bit **RGB**（三通道同值），覆盖率，自带抗锯齿边缘 |

由 `bake/make_2d_maps.py` 从网页版那套已经验证过的烤图产物
（`qieping_web/bake/scratch/` 的 u / v / mask）生成，**不依赖 3D 工程、FBX、ABC**。

## 验收结果

用现成的 1004/C 全 4 帧渲染，和现网 3D 工程的成片逐像素比（单位 8-bit/255）：

| 屏 | 平均误差 | p90 |
| --- | --- | --- |
| A | 0.86 – 0.95 | 2 |
| B | 0.92 – 1.01 | 2 |
| D | 0.89 – 1.00 | 2 |
| F | 1.27 – 1.38 | 3 |

16 项全部通过（判定线：平均 ≤2、p90 ≤3）。换成另一套素材
（`1001B/B###.png`，Nuke 现渲对照）误差 0.78–1.32，同样通过。
上面这批 2D 成片已经按工程自带路径渲到了
`Out_QiePing/QiePing2D_1004C/`，可以和 `QiePing1004C/` 直接并排看。

## 复现与验证

```powershell
$py = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
cd D:\codex\Nuke插件\qieping_nuke2d

& $py bake\make_2d_maps.py                                   # 1. 生成 maps/
powershell -ExecutionPolicy Bypass -File bake\run_build_nk.ps1    # 2. 生成 .nk

# 3. 渲染 + 验收（先渲到本地临时目录比对，不动现网成片）
powershell -ExecutionPolicy Bypass -File bake\run_render_2d.ps1 -OutDir D:\codex\_qieping_bake\out2d_1004C -First 1 -Last 4
& $py verify_2d.py D:\codex\_qieping_bake\out2d_1004C

# 4. 确认无误后再用工程自带路径渲到目标目录（OutDir 留空即可）
powershell -ExecutionPolicy Bypass -File bake\run_render_2d.ps1 -First 1 -Last 4

# 交叉验证：换一套素材
powershell -ExecutionPolicy Bypass -File bake\run_render_2d.ps1 -OutDir D:\codex\_qieping_bake\out2d_1001B -First 1 -Last 1 -Artwork "W:\…\QiePingSuCai\1001B\B###.png"
& $py verify_2d.py D:\codex\_qieping_bake\out2d_1001B "D:/codex/_qieping_bake/ref1001B/{screen}.png"
```

## 踩过的坑（改之前先看）

**2D 版特有的：**

1. **`nuke.nodes.Multiply()` 不是 Merge 版的乘法**，它建的是 Color 菜单里"乘一个常数"
   的节点，第二路输入会被**无声忽略**。必须用 `nuke.nodes.Merge2(operation="multiply")`。
   症状是屏体外面漏出素材角落的颜色；如果素材角落恰好是纯黑（比如 1004 第 1 帧），
   会完全看不出来，非常阴。
2. **蒙版要写成 RGB**。Nuke 读单通道灰度图只填红通道，拿去 Merge 相乘时绿蓝会乘上
   "不存在的通道 = 0"，画面直接废掉。
3. **STMap 的 input 0 是 src，input 1 才是 map**（和直觉相反，接反了输出完全乱）。
4. **`uv` 通道默认是 `none`**，这时 STMap 不报错、直接把 src 原样吐出来，很容易误判成"这节点没用"。
5. **映射图的 V 以左下角为原点**，而烤出来的 v 是自上而下的，所以写进绿通道要写成 `1 - v`。
6. **不要加 Reformat**。STMap 的输出分辨率自动跟随映射图；在前面加 Reformat 等于让素材
   重采样两次，误差从 1.24 涨到 1.92。
7. **`filter` 选 Mitchell 最准**（本次数据），cubic 1.56、Lanczos4 1.98、impulse 3.85。
8. **反预乘**：烤图里的 u/v 是 ScanlineRender 的预乘输出（`u_baked = u_true × 覆盖率`），
   要逐像素除回覆盖率，否则屏体边缘一圈是脏的。除数下限取 0.05，避免放大量化误差。
9. **Nuke 的 file 旋钮会把路径里的反斜杠吃掉**（`D:\a\b.tif` → `D:ab.tif`），
   Python 里 `os.path.abspath()` 之后要再换回正斜杠。
10. **`-t` 不会把额外命令行参数交给 `sys.argv`**，所以 `render_2d.py` 用环境变量收参数。
11. **`node.inputs()` 返回的是数量不是列表**，取输入要用 `node.input(i)`。

**和网页版共通的：**

12. **Nuke 的 `-t` 加载不了带中文路径的 `.py`**（`UnicodeDecodeError`），
    所以两个 `.ps1` 都会先把脚本拷到 `D:\codex\_qieping_bake\nk2d` 再执行。
    读中文路径下的**数据文件**没问题，实测过。
13. **Windows PowerShell 5.1 会把没有 BOM 的 UTF-8 `.ps1` 当 GBK 读**，
    中文常量会变乱码。本目录的 `.ps1` 都带 UTF-8 BOM。

## 目录

| 路径 | 用途 |
| --- | --- |
| `QiePing_2D_v01.nk` | **成品**，打开即用 |
| `maps/` | 四屏的映射图 + 蒙版（8 个文件） |
| `bake/make_2d_maps.py` | 从网页版烤图产物生成 maps/ |
| `bake/build_2d_nk.py` | 生成 .nk（脚本生成而不是手写，保证序列化合法） |
| `bake/run_build_nk.ps1` | 一键生成 .nk |
| `bake/render_2d.py` + `run_render_2d.ps1` | 无头渲染（可换素材、可改输出目录） |
| `verify_2d.py` | 与现网成片逐像素比对 |

## 换机位怎么办

映射是"这台机位 + 这四块屏"的，换了机位/屏体要重新烤：

1. 用原 3D 工程重新烤一次映射（`qieping_web/bake/` 那套流程），
   更新 `qieping_web/bake/scratch/` 里的 u / v / mask；
2. 重跑 `bake/make_2d_maps.py` 和 `bake/run_build_nk.ps1`；
3. 用 `verify_2d.py` 验收一次。

## 已知遗留

* 输出目录 `Out_QiePing/QiePing2D_1004C/` 是新建的，没动任何现网成片；
  确认没问题后可以自己把 Write 路径改回现网那四个目录。
* W 盘 `Out_QiePing/_write_probe.txt` 是当初测共享盘可写性留下的探针文件，可以删。
