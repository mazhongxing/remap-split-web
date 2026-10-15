# remap-split-web

把 **固定的重映射切分流程**（Nuke 的 STMap / 3D 投影烤图 / UV 展开）
做成**一个免安装的单文件网页工具**：一张素材进，N 张成片出。

这里既有**技能**（下次项目直接复用），也有**一整套跑通的案例**（含 Nuke 工程、坐标图、成品网页与验收脚本）。

## 仓库内容

| 路径 | 说明 |
| --- | --- |
| `skill/remap-split-web/` | **技能本体**。装到 `~/.codex/skills/` 后，下次说"把这套切分流程做成网页工具"就会自动匹配。 |
| `docs/Nuke切屏方案说明.md` | 中文使用说明（配 Nuke 界面截图）：怎么烤坐标图、怎么在 Nuke 里切屏。 |
| `docs/3D预览方案说明.md` | 网页工具 **2.0 的 3D 预览**怎么做：数值标定、模型精简、网页侧要点与验收门槛（配界面截图）。 |
| `docs/images/` | 说明书与 3D 方案里的截图。 |
| `examples/nuke/` | 两个 Nuke 工程：`Scenes_Final_v02.nk`（生成素材）、`Scenes_Final_v02_spilp.nk`（2D 切屏）。 |
| `examples/uv/` | 烤好的坐标图（16-bit PNG，R=u、G=v、A=覆盖率）。 |
| `examples/houdini/` | **做出屏体模型的 Houdini 工程** + 它用到的全部现场资产（FBX/ABC）+ 导出的 GLB；另带两个工具：`inspect_hip.py`（列出工程依赖）、`relink_hip_assets.py`（把绝对路径改成 `$HIP` 相对路径）。 |
| `examples/scene/` | 精简后的现场屏体模型 `scene.glb`（4.95 MB → 0.82 MB，含观众相机与四块屏）。 |
| `examples/web/` | 成品单文件网页，双击即用：1.0（只出图）与 **2.0（出图 + 3D 预览）**。 |
| `examples/pipeline/` | 四套案例脚本：网页版（`qieping_uv2d`）、3D 预览版（`qieping_3d`）、Nuke 2D 版（`qieping_nuke2d`）、初版 3D 烤图版（`qieping_web`）。 |

## 快速上手

### 1. 直接用网页工具

双击 `examples/web/QiePing_UV2D_LangJiu_1014_ABCD.html`（需要较新版 Edge / Chrome，WebGL2）。
拖一张画面进去、点「生成成片」，四张图就出来了；点图片可放大到 1:1 看细节。
完全离线，不联网、不上传、不需要 Nuke。

想连"贴到真实屏体上是什么样"一起看，双击 **`examples/web/QiePing_3D_LangJiu_1014_ABCD.html`**（2.0）：
出图之后下面的 3D 视口会自动把四张图贴到屏体模型上，默认为**观众机位**
（和现场看到的构图一致），也可以环绕、缩放、单屏显隐。做法与验收见
`docs/3D预览方案说明.md`。

> 如果点「选择文件…」没弹选择框，多半是文件被塞在某个软件的预览窗口里打开的
> （那种窗口常常禁用系统文件框）。用系统的 Edge / Chrome 直接打开即可；
> 拖拽和 Ctrl+V 粘贴不受影响。

### 2. 看 / 改生成 GLB 的 Houdini 工程

`examples/houdini/` 里放的是 3D 预览用的屏体模型是怎么来的：工程本体
（`web_make_ass_v010_relinked.hip`，路径已改成 `$HIP` 相对，克隆下来直接能打开）、
它引用的全部现场资产（5 个 FBX + 1 个 ABC，共 3.1 MB），以及导出的
`GLB/Scenes_v011.glb`。

```bash
hython examples/houdini/inspect_hip.py examples/houdini/web_make_ass_v010_relinked.hip
hython examples/houdini/run_rop.py     examples/houdini/web_make_ass_v010_relinked.hip /out/gltf1
```

用这个工程重导一次，得到的 GLB 与 W 盘上那份原始文件 **SHA256 完全相同**，
所以整条链（现场资产 → Houdini → GLB → 精简 → 网页）在仓库里是完整可复现的。
细节见 `examples/houdini/README.md`。

### 3. 装技能

把 `skill/remap-split-web/` 整个目录拷到：

```
~/.codex/skills/remap-split-web/        # Windows: C:\Users\<你>\.codex\skills\
```

之后在 Codex 里说"用 remap-split-web 把这套切分做成网页工具"即可。
技能里带全部脚本与网页模板，见 `skill/remap-split-web/SKILL.md`。

### 4. 从零复现（不需要原始工程）

仓库里带了烤好的 16-bit 坐标图，所以**不依赖原始 3D 工程**也能跑通整条链：

```bash
# ① 从 16-bit 坐标图导出原料（在 Nuke 里跑）
powershell -ExecutionPolicy Bypass -File skill/remap-split-web/scripts/run_export.ps1 \
    -SetDir ./example_set -UvDir ./examples/uv -Pattern "QingPing_UV_{screen}.png" -Screens A,B,D,F

# ② 降采样 + 高低位打包
python skill/remap-split-web/scripts/pack_uvset.py ./example_set MySet 4

# ③ 出单文件网页
python skill/remap-split-web/scripts/build_page.py ./example_set MySet.html
```

验收（与 Nuke 成片逐像素比，门槛：平均 ≤2/255、p90 ≤6/255）：

```bash
python skill/remap-split-web/scripts/verify_uv2d.py ./example_set <素材图> "<对照模板，含 {screen}>"
python skill/remap-split-web/scripts/browser_test.py --mode file \
    --tool MySet.html --art <素材图> --ref <对照目录> --screens A,B,D,F
```

## 这套方案的核心结论

**坐标精度必须 16-bit。** 同一个 Nuke 工程、同样节点，只换映射来源：

| 映射来源 | 平均误差 | p90 |
| --- | --- | --- |
| 16-bit 坐标 | **0.9 / 255** | 2 |
| 8-bit 坐标 | 17.9 / 255 | 51 |

原因：u 一个 8-bit 台阶 = 1/255，而某块屏横向只覆盖 Δu≈0.6，
折算到成片就是每个台阶宽约 40 像素的糊块——换任何算法都救不回来。
浏览器读不了 16-bit 多通道 PNG，所以把坐标拆成"高 8 位 / 低 8 位"两个通道存。

另外还有三条同样重要：**不要用 alpha 通道装数据**（浏览器会预乘掉）、
**v 轴原点在左下而贴图 v=0 在顶部**（要写 `1 - v`）、**插值必须在线性空间做**。
细节见 `skill/remap-split-web/references/`。

**2.0 的 3D 预览同样是"先算清楚再写代码"**：先证明模型的 UV 就是切图的像素栅格
（实测逐顶点平均误差 0.4–0.7 px / 6000 帧），再用 CPU 光栅化做一份黄金对照，
最后才让 WebGL 去比。判定 3D 不能用逐像素误差，要用"降采样后的结构比对 + 重建 vs 原图 +
素材上下翻转的敏感度对照"。细节见 `docs/3D预览方案说明.md`。

## 环境要求

* Nuke 14（只有"烤坐标图"和"从坐标图导出原料"两步需要它）
* Python 3.10+，带 Pillow、numpy
* 验收用无头 Edge（Windows 自带）

## 版权说明

* **代码与技能文档**：MIT，见 `LICENSE`。
* **案例素材**（`examples/` 下的 Nuke 工程、Houdini 工程与 `WP/` 里的 FBX/ABC、
  坐标图、成片、截图）：来自真实商业项目，
  **版权归原客户所有，仅作技术演示**，请勿用于生产或再分发。
  演示画面的设计版权同样归原客户。

如果你要用这套流程做自己的项目，请把 `examples/` 换成自己的素材，
两个 Nuke 工程里指向外部 FBX / ABC 的路径也要换成你自己的。
