# -*- coding: utf-8 -*-
"""交叉验证用：用 UV EXR 原样渲一遍任意素材，作为对照基准。

节点链与现网 2D 工程一致：Read(素材) → STMap(UV EXR) → Merge2(multiply, 蒙版) → Write PNG。
UV EXR 直接当 STMap 的映射图（它的 R/G 就是归一化坐标，v 原点在左下）。

环境变量：UV2D_ART / UV2D_OUT / UV2D_UV_DIR / UV2D_SCREENS
"""

import os
import sys
import traceback

import nuke


def env(name, default):
    v = os.environ.get(name)
    return v if v else default


ART = env("UV2D_ART", "")
OUT = env("UV2D_OUT", "")
UV_DIR = env("UV2D_UV_DIR", "W:/2026/20260701_LangJiu_ShanGuGuangYingXiu/comp/Nuke/UV")
SCREENS = [s.strip() for s in env("UV2D_SCREENS", "A,B,D,F").split(",") if s.strip()]


def log(m):
    sys.stdout.write("[ref] %s\n" % m)
    sys.stdout.flush()


def fwd(p):
    return os.path.abspath(p).replace("\\", "/")


def main():
    if not ART or not OUT:
        raise RuntimeError("需要 UV2D_ART 与 UV2D_OUT")
    out = fwd(OUT)
    os.makedirs(out, exist_ok=True)
    nuke.scriptClear()

    art = nuke.createNode("Read", inpanel=False)
    art["file"].setValue(fwd(ART))
    art["file_type"].setValue("jpeg" if ART.lower().endswith((".jpg", ".jpeg")) else "png")
    art["first"].setValue(1)
    art["last"].setValue(1)
    art["reload"].execute()

    for s in SCREENS:
        exr = "%s/UV_%s.exr" % (UV_DIR.rstrip("/"), s)
        uvm = nuke.createNode("Read", inpanel=False)
        uvm["file"].setValue(exr)
        uvm["colorspace"].setValue("linear")
        uvm["reload"].execute()

        st = nuke.createNode("STMap", inpanel=False)
        st.setInput(0, art)
        st.setInput(1, uvm)
        st["uv"].setValue("rgba")
        st["filter"].setValue("Mitchell")

        e = nuke.createNode("Expression", inpanel=False)
        e.setInput(0, uvm)
        e["expr0"].setValue("a")
        e["expr1"].setValue("a")
        e["expr2"].setValue("a")
        e["expr3"].setValue("1")

        mg = nuke.createNode("Merge2", inpanel=False)
        mg["operation"].setValue("multiply")
        mg["maskChannelMask"].setValue("none")
        mg.setInput(0, st)
        mg.setInput(1, e)

        w = nuke.createNode("Write", inpanel=False)
        w.setInput(0, mg)
        w["file"].setValue("%s/%s.png" % (out, s))
        w["file_type"].setValue("png")
        w["datatype"].setValue("8 bit")
        w["create_directories"].setValue(True)
        nuke.execute(w, 1, 1)
        log("%s -> %dx%d" % (s, mg.format().width(), mg.format().height()))
    log("done -> %s" % out)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)
