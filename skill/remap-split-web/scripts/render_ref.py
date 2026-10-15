# -*- coding: utf-8 -*-
"""交叉验证用：拿任意素材，用坐标图原样在 Nuke 里渲一遍，作为对照基准。

节点链与"方案二"一致：Read(素材) → STMap(坐标图) → Merge2(multiply, 覆盖率) → Write PNG。
坐标图直接当 STMap 的映射图（R/G 就是归一化坐标，v 原点在左下）。

环境变量：UV2D_ART / UV2D_OUT / UV2D_UV_DIR / UV2D_PATTERN / UV2D_SCREENS
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
UV_DIR = env("UV2D_UV_DIR", "")
PATTERN = env("UV2D_PATTERN", "UV_{screen}.exr")
SCREENS = [s.strip() for s in env("UV2D_SCREENS", "A,B,D,F").split(",") if s.strip()]


def log(m):
    sys.stdout.write("[ref] %s\n" % m)
    sys.stdout.flush()


def fwd(p):
    return os.path.abspath(p).replace("\\", "/")


def file_type_of(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return {"exr": "exr", "png": "png", "jpg": "jpeg", "jpeg": "jpeg",
            "tif": "tiff", "tiff": "tiff"}.get(ext, ext)


def main():
    if not ART or not OUT or not UV_DIR:
        raise RuntimeError("需要 UV2D_ART / UV2D_OUT / UV2D_UV_DIR")
    out = fwd(OUT)
    os.makedirs(out, exist_ok=True)
    nuke.scriptClear()

    art = nuke.createNode("Read", inpanel=False)
    art["file"].setValue(fwd(ART))
    art["file_type"].setValue(file_type_of(ART))
    art["first"].setValue(1)
    art["last"].setValue(1)
    art["reload"].execute()

    for s in SCREENS:
        src = "%s/%s" % (UV_DIR.rstrip("/"), PATTERN.format(screen=s))
        if not os.path.exists(src):
            raise RuntimeError("找不到坐标图: %s" % src)

        uvm = nuke.createNode("Read", inpanel=False)
        uvm["file"].setValue(src)
        uvm["file_type"].setValue(file_type_of(src))
        uvm["colorspace"].setValue("linear")
        uvm["reload"].execute()

        st = nuke.createNode("STMap", inpanel=False)
        st.setInput(0, art)      # input 0 = src
        st.setInput(1, uvm)      # input 1 = map
        st["uv"].setValue("rgba")
        st["filter"].setValue("Mitchell")

        e = nuke.createNode("Expression", inpanel=False)
        e.setInput(0, uvm)
        for k in ("expr0", "expr1", "expr2"):
            e[k].setValue("a")
        e["expr3"].setValue("1")

        mg = nuke.createNode("Merge2", inpanel=False)   # 注意：不能用 Multiply
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
