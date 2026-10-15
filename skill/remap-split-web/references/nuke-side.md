# Nuke 侧：两套工程

一套流程拆成两个工程，一份烤图、一份切屏。案例里的文件名是
`Scenes_Final_v02.nk`（生成素材）和 `Scenes_Final_v02_spilp.nk`（切屏实现）。

---

## 方案一：生成素材（3D 投影烤出坐标图）

每块屏一条链，最终写出该屏的"坐标图 + 覆盖率"：

```
Read(素材) ─┐
           ├─ Project3D2 ─ ReadGeo2(屏体 FBX) ─ Scene ─ ScanlineRender ─ Reformat ─ EdgeExtend ─ Write
Camera3 ───┘
```

节点要点：

* **`UV_Map` Group**（Nuke 自带的 UV Map gizmo）：核心是一个 `Expression`，
  `expr0 = (x+0.5)/width`、`expr1 = (y+0.5)/height`，把画面变成归一化坐标场。
  接在屏体几何前的投影链上，让 ScanlineRender 输出坐标而不是颜色。
* **`Camera3`**：从 ABC 读的真实机位（`read_from_file true`）。
* **`ReadGeo2`**：每块屏一个 FBX。`read_on_each_frame` 视屏体是否动画而定。
* **`Project3D2`**：把素材按机位投影到屏体上。
* **`ScanlineRender`**：`projection_mode uv`、`antialiasing high`、
  `conservative_shader_sampling false`。
* **`Reformat`**：`resize distort`，format 设成该屏的真实分辨率——
  **输出分辨率就由这里决定**。
* **`EdgeExtend`**：`sourceIsPremultiplied true`、`premultiply false`，
  把屏体轮廓外的坐标往外延，避免边缘一圈脏。
* **`Write`**：`file_type png`、`datatype 16 bit`、`channels rgba`、
  `colorspace linear`（坐标是数据，**绝不能被色彩管理动过**）。

产物规格：每张 PNG 的分辨率 = 该屏分辨率；**R=u、G=v、B=0、A=覆盖率**；
u/v 归一化、v 原点在左下（Nuke 惯例）。

换机位/屏体：改 `Camera3.file`、各 `ReadGeo2.file`、各 `Reformat.format`，
然后重渲一遍素材。

---

## 方案二：Nuke 内切屏（2D STMap）

每块屏一条链，纯 2D，只用核心节点、不需要 NukeX：

```
Read(素材) ────────────────┐
                           ├─ STMap ─ Merge2(operation=multiply) ─ Write
Read(UV_<屏>.png) ─────────┘    ▲                ▲
                                └── Shuffle2     └── 覆盖率
                                    (alpha → rgb)
```

节点要点（**每一条都踩过坑**）：

1. **`STMap` 的 input 0 是 src、input 1 才是 map**——和直觉相反，接反了输出完全乱。
2. **`uv` 通道默认是 `none`**，这时 STMap 不报错、直接把 src 原样吐出来，
   极易误判成"这节点没用"。必须设成承载 u/v 的通道（`rgba`）。
3. `filter` 选 **Mitchell** 最贴合（实测 cubic / Lanczos4 / impulse 都更差）。
4. 坐标图要按 **`colorspace linear`** 读——它是数据，不是颜色。
5. 覆盖率：用 `Shuffle2` 把 UV 图的 alpha 铺到 RGB（三通道同值），
   再用 **`Merge2`（operation=multiply）** 乘上去。
6. **`nuke.nodes.Multiply()` 不是 Merge 版的乘法**——它建的是 Color 菜单里
   "乘常数"的节点，第二路输入会被**无声忽略**。症状是屏体外面漏出素材角落的颜色；
   素材角落恰好是纯黑时完全看不出来，非常阴。
7. 遮罩要写成 **RGB**。Nuke 读单通道灰度图只填红通道，拿去 Merge 相乘时
   绿蓝会乘上"不存在的通道 = 0"，画面直接废掉。
8. **不要在前面加 Reformat**。STMap 的输出分辨率自动跟随映射图；
   加 Reformat 等于让素材重采样两次，误差明显变大。
9. 案例里 `Read` 的 `format` 被强制成该屏分辨率，是为了让输出尺寸确定；
   STMap 本身从映射图取格式。

换素材只改那一个 `Read` 的路径；换机位要重烤映射图。

---

## 两个方案的取舍

| | 3D 投影烤图 | 2D STMap 切屏 |
| --- | --- | --- |
| 需要 NukeX | 是（Project3D/ScanlineRender 之外还常用 EdgeExtend） | 否，核心节点即可 |
| 每帧成本 | 高（每次都要过 3D 渲染） | 低（纯贴图重映射） |
| 适用 | 生成映射素材、需要几何精度 | 量产切屏、批量换素材 |
| 产出 | 坐标图（给方案二或网页工具吃） | 直接出成片 |

网页工具走的是方案二的等价实现：拿方案一的坐标图，在浏览器里做同一件事。
