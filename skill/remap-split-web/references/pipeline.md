# 完整流水线与命令

目录约定：

```
<项目>/
  bake/          本技能的 scripts/（拷过来用）
  sets/<集合>/
    raw/         u_<路>.png / v_<路>.png（16-bit 单通道）、mask_<路>.png（8-bit）
    gridU_<路>.png gridV_<路>.png mask_<路>.png uvset.json
  <集合>.html    成品
```

## ① 导出坐标素材（在 Nuke 里跑）

输入可以是两种：

* **32-bit float EXR**——精度源头，最稳；
* **16-bit RGBA PNG**——Nuke 直接产出、体积小。约定 **R=u、G=v、B=0、A=覆盖率**。

```powershell
# 先看 run_export.ps1 顶部的默认值，或用参数覆盖
powershell -ExecutionPolicy Bypass -File run_export.ps1 `
    -SetName MySet -UvDir "W:/.../UV" -Screens A,B,D,F -Pattern "UV_{screen}.exr"
```

环境变量（Nuke 的 `-t` **不会**把额外命令行参数交给 `sys.argv`，所以走环境变量）：

| 变量 | 说明 |
| --- | --- |
| `UV2D_SET_NAME` | 集合名 |
| `UV2D_UV_DIR` | 坐标图所在目录 |
| `UV2D_PATTERN` | 文件名模板，如 `UV_{screen}.exr` / `QingPing_UV_{screen}.png` |
| `UV2D_SCREENS` | 路名，逗号分隔 |
| `UV2D_OUT_DIR` | 输出目录（脚本在里面建 `raw/`） |

产出：`raw/u_<路>.png`（16-bit 单通道）、`raw/v_<路>.png`、`raw/mask_<路>.png`（8-bit）。

> Nuke 的 `-t` **打不开带中文路径的 `.py`**（`UnicodeDecodeError`），
> 所以 `run_export.ps1` 会先把脚本拷到纯英文目录再执行；读中文路径的**数据文件**没问题。

## ② 打包

```bash
python pack_uvset.py <集合目录> [集合名] [网格倍率]
```

降采样用**普通盒式平均**（坐标场全画面连续，不做覆盖率加权、不做边缘扩展）。
网格倍率默认 4；质量/体积权衡见 `runtime-contract.md`。

## ③ 出网页

```bash
python build_page.py <集合目录> [输出 html]
```

把素材 base64 内嵌进 `assets/page_template.html`，产出单文件网页。
**一套集合一个 html**，双击即用。

## ④ 验收

先准备对照图：用原工程现渲一遍，或直接取现网成片。

```bash
# 纯 Python 复算 vs 对照，并自动跑一条"只用高 8 位"的对照组
python verify_uv2d.py <集合目录> <素材图> "<对照模板，含 {screen}>"

# 无头 Edge 跑真页面，两种打开方式都要过
python browser_test.py --mode http
python browser_test.py --mode file
```

门槛：**平均 ≤2/255 且 p90 ≤6/255**；同时 8-bit 对照组的平均误差必须显著更大
（差的倍数太小说明对照写错了，不是打包没用）。

要拿任意素材现渲一份对照，用 `render_ref.py`（在 Nuke 里跑）：

```powershell
powershell -ExecutionPolicy Bypass -File run_render_ref.ps1 `
    -Art "W:/.../artwork.jpg" -OutDir "D:/tmp/ref"
```

## ⑤ 换机位/屏体

映射是"这套机位 + 这块屏"的，换了就要重来：重烤坐标图 → 重跑 ①②③ → 用 ④ 验收一次。
**只换素材不用重跑任何一步。**

## 环境前提

* Nuke 14（烤图那一步）；Python 3.10+ 带 Pillow、numpy；
* 验收用无头 Edge（`msedge.exe`）——路径写在 `browser_test.py` 顶部；
* 全程只读原始工程与素材，所有中间产物落在工作目录。
