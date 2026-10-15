# 切屏出图工具（A / B / D / F）

把 LangJiu 那套切屏工程（`Scenes_Final_v02.nk`）做成一个**单文件网页**：
双击打开、拖一张画面进去，浏览器本地算出四块屏各自的成片并下载。
运行时不联网、不上传、不需要 Nuke。

## 怎么用

双击 `QiePing_WebTool.html`（Edge / Chrome 都行，需要较新版本，要有 WebGL2）。
给画面有三条路，哪条顺手用哪条：**拖进左边虚线框**、点「选择文件…」（虚线框本身也能点）、
或者直接 **Ctrl+V 粘贴**。载入后点「生成 A / B / D / F」，四张图依次出来；
可以逐张下载，也可以「打包下载 ZIP」。文件名前缀可以自己改。

> 如果点「选择文件…」没弹出选择框，多半是页面被塞在某个内嵌预览窗口里跑（那种窗口
> 常常禁用系统文件框）。用系统的 Edge / Chrome 直接打开这个 html 文件就正常了；
> 拖拽和 Ctrl+V 在大多数情况下也照样能用。

出图规格固定为现网四块屏的像素尺寸，8-bit sRGB PNG、黑底：

| 屏 | 分辨率 | 现网输出目录 |
| --- | --- | --- |
| A | 6600 × 1700 | `Out_QiePing/QiePing1004C/QiePing1004C_A` |
| B | 6600 × 1580 | `…/QiePing1004C_B` |
| D | 3400 × 1300 | `…/QiePing1004C_D` |
| F | 3750 × 750 | `…/QiePing1004C_F` |

## 原理

原工程里相机（`Came_new_V01.abc`，静态）和几块屏体 FBX 都是固定的，每次只换输入
素材，所以「输入画面 → A/B/D/F」是一张**固定映射**。于是只要离线烤一次映射表，
之后任意素材都只是毫秒级的贴图重采样。

烤出来的东西分两种：

* `gridU_<屏>.png` / `gridV_<屏>.png`——1/8 分辨率的素材坐标网格（16-bit 精度拆成
  两个 8-bit 通道存），浏览器里插值出每个输出像素该去哪取色；
* `mask_<屏>.png`——全分辨率的覆盖度，就是每块屏的 alpha（自带抗锯齿）。

四屏一共 **0.25 MB**，全部以 base64 内嵌进 HTML，所以成品只有一个文件。

## 复算一遍（换素材不用做，只有换机位/屏体才需要）

前提：本机装了 Nuke 14；脚本目录必须是**纯英文路径**（Nuke 的 `-t` 打不开带中文的
`.py`，所以 `run_bake.ps1` 会自动把脚本拷到 `D:\codex\_qieping_bake\stage` 再跑）。

```powershell
$py = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
cd D:\codex\Nuke插件\qieping_web\bake

& $py gen_ref.py                                         # 1. 生成 UV 参考图 / 纯白图
powershell -ExecutionPolicy Bypass -File run_bake.ps1    # 2. Nuke 烤图（约 25 秒）
& $py make_assets.py                                     # 3. 压成网页素材
& $py build_page.py                                      # 4. 生成单文件网页
& $py verify.py                                          # 5. 和现网成片逐像素比对
```

可选的两步验收：

```powershell
# 换一张完全不同的素材，让 Nuke 现渲一遍再比对
powershell -ExecutionPolicy Bypass -File run_render.ps1 -Image "W:\…\QiePingSuCai\1001B\B001.png" -OutDir "D:\codex\_qieping_bake\ref1001B"
& $py verify.py "W:\…\QiePingSuCai\1001B" "D:/codex/_qieping_bake/ref1001B/{screen}.png" 1

& $py webtest.py         # 无头 Edge 真跑网页（http），和 Nuke 成片比对
& $py webtest_file.py    # 同上，但用 file:// 打开，也就是双击的用法
```

要发给别人用就打一个包（成品网页 + 使用说明 + 界面预览，不含维护脚本）：

```powershell
& $py pack_release.py    # 产出 切屏出图工具_QiePing_WebTool.zip
```

## 验收结果

用现成的 `1004/C/001–004.jpg` 反推，和 W 盘上已有的 Nuke 成片逐像素比（单位 8-bit/255）：

| 屏 | 平均误差 | 中位 | p90 | 说明 |
| --- | --- | --- | --- | --- |
| A | 1.02 | 0.60 | 2.2 | 4 帧都在这个量级 |
| B | 1.03 | 0.64 | 2.0 | |
| D | 0.75 | 0.52 | 1.6 | |
| F | 1.37 | 0.78 | 2.8 | |

换成另一套素材（`1001B/B001.png`，Nuke 现渲对照）误差 0.70–1.27，同样通过。
无头 Edge 跑网页本体：A 1.03 / B 1.04 / D 0.75 / F 1.38，和 Python 复算一致；
ZIP 包能正常解开，四个 PNG 都能读。

剩下的零点几到一档的误差来自：Nuke 输出是 8-bit 取整、素材 JPEG 解码器不同、
以及原工程 ScanlineRender 用 cubic 纹理过滤而这里是线性空间双线性。肉眼不可辨。

## 目录

| 路径 | 用途 |
| --- | --- |
| `QiePing_WebTool.html` | **成品**，单文件，双击即用 |
| `bake/gen_ref.py` | 生成 UV 参考图（16-bit，手写 PNG）和纯白图 |
| `bake/bake_maps.py` | 在 Nuke 里跑：把素材换成参考图，渲出 u/v 和覆盖度 |
| `bake/run_bake.ps1` | 把脚本挪到纯英文路径再调 Nuke 跑 bake_maps.py |
| `bake/make_assets.py` | 反预乘、加权降采样、打包成网页素材 |
| `bake/build_page.py` | 把素材内嵌进模板，产出单文件网页 |
| `bake/verify.py` | 与 Nuke 成片逐像素比对 |
| `bake/render_case.py` + `run_render.ps1` | 用任意素材现渲一遍做交叉验证 |
| `bake/webtest.py` / `webtest_file.py` | 无头 Edge 跑成品网页并核对结果 |
| `bake/pack_release.py` | 打发布用的 zip（HTML + 使用说明 + 界面预览） |
| `bake/page_template.html` | 网页模板（改界面改这里，再重跑 build_page.py） |
| `bake/template.nk` | 原工程副本，烤图只读它，不动 W 盘原件 |
| `bake/assets/` | 烤图成品素材（已内嵌进 HTML） |
| `bake/scratch/` | 烤图中间产物（u/v/mask 的全分辨率 PNG） |

## 踩过的坑（改代码前先看一眼）

1. **Nuke 打不开中文路径下的 `.py`**，会抛 `UnicodeDecodeError`；烤图必须走
   `run_bake.ps1` 先拷到英文路径。
2. **Nuke 的 Write 会把路径里的反斜杠吃掉**（`D:\a\b.tif` 变成 `D:ab.tif`），
   脚本里一律用正斜杠。
3. **烤出来的 u/v 是预乘的**（`u_baked = u_true × 覆盖度`），必须用
   `Σu_baked / Σ覆盖度` 反算，否则屏体边缘会有一圈脏边。
4. **网格素材不能存成带 alpha 的 RGBA**：浏览器上传时会把 RGB 预乘掉。
   现在拆成 gridU / gridV 两张 RGB。
5. **16-bit 坐标不能交给硬件插值**：高低位分开存时，硬件的亚像素精度误差会被放大
   256 倍。现在是自己取 4 个格子、拆成 16-bit 之后再插值。
6. **素材采样要在线性空间做**（`sRGB→linear → 插值 → 乘覆盖率 → linear→sRGB`），
   直接在 sRGB 空间插值误差会大一倍。
7. 降采样用**有效像素加权平均**，屏外的 0 不参与，否则边界内侧会被拉向画面左上角。
8. **文件框必须是真的挂在 DOM 上的 `<input type=file>`**：临时 `new` 一个再 `click()`，
   新版 Chrome/Edge 和部分内嵌预览窗口会直接忽略，表现就是"点了没反应"。

## 假设与边界

* 只服务这一套固定机位 + A/B/D/F 四块屏；换机位/屏体要按上面的步骤重新烤一次。
* 输入整幅拉伸到画面坐标系（和 Nuke 里 Read 强制 6000×1538 的行为一致），
  宽高比不是 3.901 时页面会提示。
* 单张静帧；视频/序列批量不在范围内。
* 全程只读副本，W 盘上的原工程、素材、成片一个字节都没动。
