---
name: remap-split-web
description: Turn a fixed remap/split pipeline from a DCC (Nuke STMap, 3D projection bake, UV unwrap) into a self-contained browser tool — one artwork in, several screen/part images out. Use when the geometry, camera and output specs are fixed and only the artwork changes, and non-CG people need a no-install way to produce the split outputs. Not for pipelines whose camera or geometry changes per job, or that need real lighting, particles or complex compositing.
metadata:
  short-description: DCC 重映射切分流程 → 单文件网页工具
---

# Remap Split Web

把「固定映射」的切分流程从 DCC 搬进浏览器：**一张素材进，N 张成片出**，
网页单文件、离线、不需要 Nuke、不需要授权。

## 先判断能不能这么做

只问一句：**流程里什么会变、什么是死的？**

* 死的：相机、机位、屏体/几何、投影方式、每路输出的分辨率与格式；
* 活的：输入素材（每次交付换一张）。

活的那部分如果**只是贴图**，那"输入 → 各路输出"就是一张**固定映射**，可以一次性烤出来，
之后每张素材只是毫秒级的贴图重采样。

**不要用这个技能**：相机逐帧运动、几何逐帧变形、有真实光照/粒子/合成、需要 32-bit float 交付。
那些情况下映射是逐帧的，老老实实服务端跑原软件。

侦察技巧：把同一套模板的多个 `.nk`/工程副本 diff 一遍——差异越小，越说明结构是死的。

## 三步流水线

1. **导出坐标素材**——在 DCC 里把映射烤成"坐标图 + 覆盖率"（Nuke 见
   [references/nuke-side.md](references/nuke-side.md)），再导成网页可用的小素材。
2. **打包**——降采样 + 高低位打包，产出 `uvset.json` 与每路两三张小 PNG。
3. **出网页**——把素材内嵌进 [assets/page_template.html](assets/page_template.html)，
   产出一个独立 html，双击即用。

完整命令、参数与环境变量见 [references/pipeline.md](references/pipeline.md)。

## 还想让人看到"贴到真实屏体上是什么样" → 加 3D 视口

多出一个活的输入：**现场屏体的模型**（GLB，和投影相机同一套坐标）。

先做一次数值验证再动手：用 GLB 里的相机把 mesh 顶点投影到成片帧，
和坐标图预测的位置逐顶点比——实测能到 0.4–0.7 px / 6000 帧。
对上了就说明**模型的 UV 就是切图的像素栅格，切图可以直接贴，不用重烘、不用缩放补偿**。

```bash
python scripts/glb_web.py <场景.glb> --out scene --set <集合目录>   # 剔孤立节点 + 量化，5 MB → 0.8 MB
python scripts/build_page_v2.py <集合目录> scene <输出.html>        # 用 assets/page_template_v2.html
python scripts/verify_3d_cpu.py scene/scene.glb <集合目录> <素材> _verify/cpu --frame 1560x400
python scripts/browser_test_v2.py --tool <html> --art <素材> --ref2d <成片目录> --ref3d _verify/cpu/audience.png
```

三条经验值：观众机位用**场景相机 + 成片门框画幅比**取景；判定别用逐像素
（GPU 与 CPU 采样方式不同，高频素材上能差 30/255），用**降 8 倍的结构比对 + 重建 vs 原图 +
素材上下翻转的敏感度对照**；屏体自发光、关背面剔除、贴图要生成 mipmap。

要连"模型是怎么来的"一起交付（工程 + 资产进版本库），用 `scripts/inspect_hip.py`
看清依赖、`scripts/relink_hip_assets.py` 把绝对路径改成 `$HIP` 相对路径，
再用 `scripts/run_rop.py` 从整理后的工程重导一次——**输出应与原文件逐字节一致**。

细节、数据契约与踩过的坑见 [references/3d-viewport.md](references/3d-viewport.md)。

## 四条必须守住的不变式

这几条是踩过坑换来的，写错了不会报错，只会画面对不上或悄悄变糊：

1. **坐标必须 16-bit**。8-bit 坐标在大幅面上会产生几十像素的糊块（实测误差 18–27/255，
   vs 16-bit 的 0.9/255）。浏览器读不了 16-bit 多通道 PNG，所以**拆成高 8 位 / 低 8 位两个通道**。
2. **不要用 alpha 通道装数据**。浏览器上传带 alpha 的贴图时会把 RGB 按 alpha 预乘，数据直接毁；
   拆成两张 RGB，遮罩单独一张灰度图。
3. **v 轴原点在左下**（Nuke 惯例）。浏览器贴图的 `v=0` 是图像第一行（顶部），
   所以采样素材要写 `1.0 - uv.y`。漏了就是整张图上下颠倒。
4. **插值在线性空间做**（sRGB→linear→插值→乘遮罩→linear→sRGB）；
   16-bit 坐标**不能交给硬件插值**（高低位分开存时 GPU 的亚像素误差会放大 256 倍），
   必须自己 `texelFetch` 取 4 格、拆位后再插值。

数据契约（文件命名、`uvset.json` 字段、打包公式）与着色器骨架见
[references/runtime-contract.md](references/runtime-contract.md)。

## 交付前必须验收

**分层对齐，不要一上来就比最终图**：先纯 Python 复算 vs DCC 成片，再中间量对照
（坐标场、遮罩、重采样结果分别比），最后才是无头浏览器跑真页面。
门槛：平均误差 ≤2/255 且 p90 ≤6/255；同时保留一条"只用高 8 位"的对照组，
证明高低位打包确实在起作用（不给这条，以后有人会悄悄退回 8-bit）。

验收脚本与两种打开方式（http 与 `file://`）的端到端测试见
[references/pipeline.md](references/pipeline.md)。踩过的坑清单见
[references/pitfalls.md](references/pitfalls.md)——动手前先把那份读一遍。
