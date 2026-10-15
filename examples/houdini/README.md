# Houdini 工程：把现场屏体做成网页可用的 GLB

网页工具 2.0 的 3D 预览要用一个"和投影相机同一套坐标"的屏体模型。
这份工程就是**从现场 FBX/ABC 资产做出那个 GLB** 的地方。

```
examples/houdini/
  web_make_ass_v010.hip            原始工程（资产路径指向 W:/…，与我们手上那份逐字节一致）
  web_make_ass_v010_relinked.hip   同一工程，7 条资产引用改成 $HIP 相对路径，克隆下来即可打开
  WP/fbx/                          工程用到的全部现场资产（见下表）
  GLB/Scenes_v011.glb              导出结果（4.95 MB，网页工具的输入）
```

## 工程里有什么

| 节点 | 类型 | 作用 |
| --- | --- | --- |
| `/obj/geo1/fbxskinimport1..5` | FBX Skin Import | 读入五块现场屏体/结构 FBX |
| `/obj/Came_new_V01` (+ `/cam_new01`) | Alembic Archive | 读入观众机位相机 `Came_new_V01.abc` |
| `/obj/geo1/QiePingA·B·D·F` | Object Merge 等 | 把 FBX 里的四块屏（`QiePingA/B/D/F`）整理成四个对象 |
| `/obj/OUT_glb/QiePingA·B·D·F`、`/cam` | Object Merge | 汇出到 GLB 的四块屏 + 一台相机 |
| `/out/gltf1` | glTF Export | 输出 `$HIP/GLB/Scenes_v011.glb`（对象 `/obj/OUT_glb`） |

共 72 个节点。网页侧要的三样东西（四块屏的名字、`TEXCOORD_0`、观众相机）全在这里定下来。

## 工程用到的资产

| 文件 | 大小 | 原路径（W 盘） |
| --- | --- | --- |
| `WP/fbx/A/A_ping_A_A.fbx` | 36 KB | `hip/WP/fbx/A/A_ping_A_A.fbx` |
| `WP/fbx/A/A_ping_C_E.fbx` | 1.44 MB | `hip/WP/fbx/A/A_ping_C_E.fbx` |
| `WP/fbx/A/DpingE0102/D_ping_E_v03.fbx` | 48 KB | `hip/WP/fbx/A/DpingE0102/D_ping_E_v03.fbx` |
| `WP/fbx/B_ping_D.fbx` | 1.60 MB | `hip/WP/fbx/B_ping_D.fbx` |
| `WP/fbx/F_ping_B.fbx` | 46 KB | `hip/WP/fbx/F_ping_B.fbx` |
| `WP/fbx/Came_new_V01.abc` | 2 KB | `hip/WP/fbx/Came_new_V01.abc` |

合计 3.1 MB。原工程在 `hip/Mars/web_make/` 下，所以从工程看资产是 `../../WP/fbx/…`；
本仓库把资产放在工程旁边，`*_relinked.hip` 里写的是 `$HIP/WP/fbx/…`。

> 几个 FBX 内部还挂着贴图引用（`6600X1700.jpg`、`3750X750.jpg` 以及一张
> `source/0930/*.png`）。这份工程只取几何，不取材质，所以那些贴图不需要。

## 怎么用

**直接看/改**：用 Houdini 打开 `web_make_ass_v010_relinked.hip`（验证过：7 条输入资产引用
全部命中，0 缺失）。想重新导出 GLB，选中 `/out/gltf1` 点 Render，输出到 `GLB/Scenes_v011.glb`。

**命令行重导**（不需要图形界面）：

```bash
hython run_rop.py examples/houdini/web_make_ass_v010_relinked.hip /out/gltf1
```

**把别的工程也整理成"拷到哪都能打开"**：

```bash
# 先看清它依赖什么（节点树 / 资产引用 / 是否缺失 / ROP 输出）
hython inspect_hip.py <工程.hip> [--json 报告.json]

# 再改写成 $HIP 相对路径
hython relink_hip_assets.py <源.hip> <目标.hip> <资产根目录> [--assets-dir WP]
```

它会遍历 `hou.fileReferences()`，把落在资产根目录下的绝对路径改成 `$HIP/<相对路径>`，
保存后重新打开逐条校验；ROP 的输出路径和渲染画廊的数据库会被跳过（那不是输入资产）。

## 复现验证

用 `*_relinked.hip` 重新导出一次，结果与 W 盘上那份原始 GLB **逐字节一致**：

| 文件 | SHA256 |
| --- | --- |
| 原始 `Scenes_v011.glb`（W 盘） | `0F1A9A856A417FE1C2EE3DADC35DFFFD6A788EE9E6E9C4999953E4C40A5ED404` |
| 本仓库从 `*_relinked.hip` 重导 | `0F1A9A856A417FE1C2EE3DADC35DFFFD6A788EE9E6E9C4999953E4C40A5ED404` |
| 原始 `web_make_ass_v010.hip` | `656EAE730BB9C1B1FB8BDACE4FD8F7767D730E69B8C6606A8A64CDA25B33E44C` |

也就是说：**克隆这个仓库，不依赖 W 盘，也能得到一模一样、能喂给网页工具的 GLB。**

## 网页侧怎么用这个 GLB

```bash
python examples/pipeline/qieping_3d/glb_web.py examples/houdini/GLB/Scenes_v011.glb \
    --out /tmp/scene --set examples/pipeline/qieping_uv2d/sets/LangJiu_1014_ABCD
```

4.95 MB 会被精简量化成 0.82 MB（剔 7 个场景外孤立节点、丢法线切线、位置与 UV 走 16-bit），
具体做法与标定方法见 `docs/3D预览方案说明.md`。

## 版权

`WP/` 下的模型与 `GLB/` 是真实商业项目的资产，**版权归原客户**，仅作技术演示；
代码（`*.py`）按仓库的 MIT 授权。
