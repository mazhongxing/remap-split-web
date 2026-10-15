# -*- coding: utf-8 -*-
"""生成 2D 版切屏工程 QiePing_2D_v01.nk。

只用 Read / STMap / Multiply / Write 四个核心 2D 节点，不碰任何 3D 节点。
在 Nuke 里跑（编辑器生成而不是手写 .nk，保证序列化绝对合法）：

    Nuke14.0.exe -t build_2d_nk.py

要点（都是实测出来的，改之前先看 README）：
  * STMap 的 input 0 = src（素材），input 1 = map（映射图）
  * uv 通道必须选上，默认 none 时 STMap 会静默地原样输出
  * 输出分辨率自动跟随映射图，**不要加 Reformat**
  * Multiply（Merge）的 maskChannel 默认是 alpha，我们的图没有 alpha，要设成 none
"""

import os
import sys
import traceback

import nuke

# 注意：这个脚本会被拷到纯英文目录里再执行（Nuke 的 -t 加载不了中文路径的 .py），
# 所以不能拿 __file__ 推工程目录，直接写死工程根，必要时用环境变量覆盖。
ROOT = os.environ.get("QIEPING_NK2D", r"D:\codex\Nuke插件\qieping_nuke2d").replace("\\", "/")
MAPS = ROOT + "/maps"
OUT_NK = ROOT + "/QiePing_2D_v01.nk"

ARTWORK = "W:/2026/20260701_LangJiu_ShanGuGuangYingXiu/comp/QiePingSuCai/1004/C/###.jpg"
OUT_BASE = "W:/2026/20260701_LangJiu_ShanGuGuangYingXiu/comp/Out_QiePing/QiePing2D_1004C"

SCREENS = ("A", "B", "D", "F")
FIRST, LAST = 1, 4
SRC_FORMAT = "QP_SRC"


def log(m):
    sys.stdout.write("[nk] %s\n" % m)
    sys.stdout.flush()


def make_read(name, path, colorspace, x, y, sequence):
    r = nuke.nodes.Read(name=name, xpos=x, ypos=y)
    r["file"].setValue(path)
    r["colorspace"].setValue(colorspace)
    if sequence:
        r["first"].setValue(FIRST)
        r["last"].setValue(LAST)
        r["origfirst"].setValue(FIRST)
        r["origlast"].setValue(LAST)
    else:
        for k in ("first", "last", "origfirst", "origlast"):
            r[k].setValue(1)
    if "origset" in r.knobs():
        r["origset"].setValue(True)
    return r


def build():
    nuke.scriptClear()
    nuke.addFormat("6000 1538 0 0 6000 1538 1 %s" % SRC_FORMAT)
    root = nuke.root()
    root["format"].setValue(SRC_FORMAT)
    root["first_frame"].setValue(FIRST)
    root["last_frame"].setValue(LAST)
    root["fps"].setValue(25)
    root["lock_range"].setValue(True)

    src = make_read("SrcArtwork", ARTWORK, "default", -400, 0, True)

    for i, s in enumerate(SCREENS):
        x = i * 500
        mp = make_read("Map%s" % s, "%s/map_%s.png" % (MAPS, s), "linear", x - 120, 250, False)
        mk = make_read("Mask%s" % s, "%s/mask_%s.png" % (MAPS, s), "linear", x + 130, 250, False)

        a1 = nuke.nodes.Dot(xpos=x - 60, ypos=120)
        a1.setInput(0, src)
        a2 = nuke.nodes.Dot(xpos=x - 60, ypos=-80)
        a2.setInput(0, a1)

        # STMap: input0 = src, input1 = map
        st = nuke.nodes.STMap(name="Remap%s" % s, xpos=x, ypos=0)
        st.setInput(0, a2)
        st.setInput(1, mp)
        st["uv"].setValue("rgba")
        st["filter"].setValue("Mitchell")
        st["premultiplied"].setValue(False)

        # 必须用 Merge 版的乘法。注意 nuke.nodes.Multiply() 建的是 Color 菜单里
        # "乘一个常数"的那个节点——它只有效于第一个输入，第二路会被无声忽略，
        # 屏体外面就会漏出素材角落的颜色。
        mul = nuke.nodes.Merge2(name="Coverage%s" % s, operation="multiply", xpos=x, ypos=-250)
        mul.setInput(0, st)          # Merge 的 input0 = B
        mul.setInput(1, mk)          # input1 = A
        mul["maskChannel"].setValue("none")
        mul["bbox"].setValue("union")

        w = nuke.nodes.Write(name="Write%s" % s, xpos=x, ypos=-500)
        w.setInput(0, mul)
        w["file"].setValue("%s/QiePing2D_1004C_%s/QiePing2D_1004C_%s.####.png" % (OUT_BASE, s, s))
        w["file_type"].setValue("png")
        w["datatype"].setValue("8 bit")
        w["colorspace"].setValue("default")
        w["create_directories"].setValue(True)
        w["checkHashOnRead"].setValue(False)

        bd = nuke.nodes.BackdropNode(name="Backdrop_%s" % s, xpos=x - 200, ypos=-620,
                                     bdwidth=440, bdheight=1000, label="%s 屏" % s)
        bd["note_font_size"].setValue(90)

    bd = nuke.nodes.BackdropNode(name="Backdrop_Src", xpos=-520, ypos=-160,
                                 bdwidth=360, bdheight=400, label="换素材只改这里")
    bd["note_font_size"].setValue(60)

    log("saving %s" % OUT_NK)
    nuke.scriptSaveAs(OUT_NK, overwrite=True)
    log("saved, %d bytes" % os.path.getsize(OUT_NK))
    log("nodes: %s" % ", ".join(sorted(n.name() for n in nuke.allNodes())))


if __name__ == "__main__":
    try:
        build()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)
