# 切屏切图工具 2.0（UV 重映射 + 3D 预览）

1.0（`examples/pipeline/qieping_uv2d/`）只出四张切图；2.0 在旁边多了一个 **3D 视口**：
把切好的图直接贴回真实屏体模型上，用场景文件里的**观众机位**看效果，也可以自由环绕、
就像在 Sketchfab 上看模型一样。**1.0 的文件一个字节都没动**（当初做完前后各记了一次
SHA256，五个文件哈希完全一致）。

## 怎么用

双击 `examples/web/QiePing_3D_LangJiu_1014_ABCD.html`（单个文件，2.42 MB，离线、不联网、不需要 Nuke）：

1. 把整幅画面拖进去（或点"选择文件…"、或 Ctrl+V 粘贴）；
2. 点「生成成片」→ 上面出四张切图（可放大到 1:1、逐张下载、打包 ZIP）；
3. 下面的 3D 视口自动贴上切好的图：

| 操作 | 效果 |
| --- | --- |
| 观众机位（默认） | 场景文件里的相机，按 6000×1538 成片门框取景，和 Nuke 里看到的构图一致 |
| 环绕展示 | 绕场景自动旋转，看整体效果 |
| 重置视角 | 回到观众机位 |
| 左键拖 / 右键拖 / 滚轮 | 环绕 / 平移 / 缩放（一拖就自动切到自由视角） |
| 显示：A B D F | 单块屏显隐；旁边的「看」把镜头对准那块屏 |
| 全屏 | 3D 区铺满窗口（Esc 退出） |

屏上的**黑块**是该区域不在投影覆盖范围内（烤图覆盖度 A 69% / B 78% / D 100% / F 89%），
和切出来的成片一致，不是渲染错误。

## 目录

```
qieping_3d\                        （本仓库里的 examples/pipeline/qieping_3d/）
  bake\                             （本仓库里脚本直接摊平在这一层）
    glb_web.py          场景 GLB → 精简 + 量化（4.95 MB → 0.82 MB），带自检
    build_page_v2.py    2D 素材 + scene.glb → 单文件网页
    page_template_v2.html  2.0 模板（含内置 glTF 解析器 + WebGL2 视口）
    verify_3d_cpu.py    CPU 黄金对照：切图贴回模型、用观众相机渲一帧
    browser_test_v2.py  无头 Edge 端到端（http 与 file:// 各跑一遍）
    shot_page.mjs       CDP 整页截图（人眼验收用）
    shot_page.py        同一个截图的旧版（虚拟时钟，不可靠，留作对照）
  scene\    scene.glb + scene_report.json
  dist\     成品网页 + 分享 zip
  _verify\  验收输出（对照图、浏览器回传结果、整页截图）
```

## 重新构建

本仓库里带了转换好的 `examples/scene/scene.glb`，所以不依赖原始 GLB 也能跑：

```bash
SET=examples/pipeline/qieping_uv2d/sets/LangJiu_1014_ABCD

# ① 场景：换机位/屏体时才需要重跑（源 GLB 只读）
python examples/pipeline/qieping_3d/glb_web.py examples/scene/scene.glb --out /tmp/scene --set $SET

# ② 出网页（2D 素材从 1.0 的 sets 目录只读读取）
python examples/pipeline/qieping_3d/build_page_v2.py $SET /tmp/scene /tmp/out.html

# ③ 验收
python examples/pipeline/qieping_3d/verify_3d_cpu.py /tmp/scene/scene.glb $SET <素材.jpg> /tmp/cpu --frame 1560x400 --panel-scale 4
python examples/pipeline/qieping_3d/browser_test_v2.py --tool /tmp/out.html --art <素材.jpg> \
    --ref2d <Nuke 成片目录> --ref3d /tmp/cpu/audience.png --mode http
```

换一套 UV 集合：`build_page_v2.py <UV集合目录> <场景目录> <输出html>`。
换机位或屏体：改 `glb_web.py` 的 `--camera` / `--node-prefix` 后重跑 ① ②。

## 关键做法（为什么这么做）

**1. 场景 GLB 的网格 UV 就是切图的像素栅格，不用重烘。**
拿 GLB 的观众相机把每个 mesh 顶点投影到 6000×1538 帧，再和 Nuke 的 u/v 贴图预测的位置逐顶点比：

| 屏 | 顶点 | 三角形 | 覆盖区平均误差 |
| --- | --- | --- | --- |
| A | 31379 | 61800 | 0.42 px |
| B | 6036 | 11386 | 0.46 px（另有 1 行接缝，见下） |
| D | 121 | 200 | 0.45 px |
| F | 121 | 200 | 0.66 px |

所以：**切图直接按 TEXCOORD_0 贴上去，用场景里的相机看，就是观众看到的画面**。
GLB 的几何和相机是自洽的（比例 0.9314 一致），不需要任何缩放补偿。

**2. 场景 GLB 先瘦身再内嵌。** Houdini 导出的文件里有 7 个场景外孤立节点（`geo1` 是 A 屏
的完整副本，另有一台多余的相机），剔掉之后再做量化：
POSITION → normalized uint16（真实尺寸/偏移写进节点矩阵）、TEXCOORD_0 → uint16、
索引 → uint16、丢掉 NORMAL/TANGENT（屏体自发光用不上法线）。
**4.95 MB → 0.82 MB**，位置量化误差 7.7e-6 场景单位（约 0.046 px / 6000 帧）。
刻意**不用 Draco**：单文件网页不想再背一个解码器。

**3. 16-bit 量化坐标不能靠 min/max 语义还原，写进节点矩阵最稳。**
不同加载器对 `KHR_mesh_quantization` 的理解不一致，本工具统一把
`世界坐标 = pmin + q/65535 × span` 这一步放进节点矩阵，任何加载器算出来都一样。
`glb_web.py` 结尾会把刚写出的文件重读一遍，核对相机位姿和网格包围盒。

## 验收基线（1004/C/001.jpg）

| 项目 | 门槛 | 本次实测 |
| --- | --- | --- |
| 2D：网页出图 vs Nuke 成片 | 平均 ≤2/255、p90 ≤6/255 | A 0.881 / B 0.941 / D 0.738 / F 1.543 |
| 3D：网页视口 vs CPU 黄金对照（降 8 倍后比结构） | 平均 ≤3、p90 ≤7.5 | 2.216 / 5.0 |
| 3D：视口重建 vs 原图 | ≤ CPU 对照 + 3 | 网页 8.13 ／ CPU 10.26 |
| 3D：素材上下翻转对照 | > 3 倍 | 10.6 倍 |
| 3D：环绕后画面必须变化 | 平均 >1 | 79.0 |
| 打开方式 | http 与 file:// 都要过 | 两种都 PASS、数值一致 |

CPU 黄金对照 `_verify\cpu_1560\compare.png` 是"左原图 / 右 3D 重建"的并排图，可以直接看。

## 坑（都踩过）

* **glTF 矩阵是列主序**。`np.array(m).reshape(4,4,order="F")` 读 1 维数组是对的，
  但对已经是 4×4 的数组再用同样写法**不会转置**（同形状 reshape 是恒等），相机矩阵会写反。
  写出去要用 `m.flatten(order="F")`。这个 bug 让 3D 视口一开始完全对不上。
* **量化顶点自己算包围盒要除以 65535**。`normalized` 标志只对 GPU 生效，
  JS 里用原始 0..65535 算场景中心会把中心算到几万米外，near/far 跟着飞走，画面全空。
* **不能给屏体贴图省掉 mipmap**。6600 宽的屏在画面上只占几百像素，
  不做 mipmap 缩小后全是噪点。
* **关闭背面剔除**。屏体网格是带厚度的双面壳，剔除会漏面。
* **`file://` 页面往 `http://127.0.0.1` POST 图片会先发跨域预检**，
  验收服务器必须实现 `do_OPTIONS`，否则 file:// 模式静默卡死。
* **别用 `msedge --screenshot --virtual-time-budget` 抓这种页面**：
  虚拟时钟会抢在 `createImageBitmap`/`toBlob` 前面跑完，截到的是半成品。
  用 CDP（`shot_page.mjs`）。
* 视口贴图默认按长边 4096 降采样（四张全分辨率上传要 ~115 MB 显存）；
  `MAX_TEXTURE_SIZE` 不够时会自动再降。

## 版权

代码 MIT；案例素材（狼九山谷的工程、UV 映射、画面）版权归原客户，仅供演示。
W 盘上的工程、UV、素材与成片全程只读。
