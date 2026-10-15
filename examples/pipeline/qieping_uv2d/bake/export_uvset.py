# -*- coding: utf-8 -*-
"""在 Nuke 里跑：把 UV EXR 导成网页素材的"原料"。

用法（经 run_export.ps1，或先把本目录拷到纯英文路径再跑）：
    "C:\\Program Files\\Nuke14.0v2\\Nuke14.0.exe" -t export_uvset.py

参数用**环境变量**传（Nuke 的 -t 不会把额外命令行参数交给 sys.argv）：
    UV2D_SET_NAME   集合名，默认 LangJiu_1014_ABCD
    UV2D_UV_DIR     UV EXR 所在目录
    UV2D_SCREENS    屏名，逗号分隔，默认 A,B,D,F
    UV2D_OUT_DIR    输出目录（会在里面建 raw/ 与 misc/）

每屏产出（写到 <OUT>/raw/）：
    u_<屏>.png     16-bit 单通道，横向坐标（归一化 0..1，原样不翻转）
    v_<屏>.png     16-bit 单通道，纵向坐标（**原点在左下**，Nuke 惯例）
    mask_<屏>.png  8-bit 单通道，覆盖度（UV 图的 alpha）

只读 UV EXR，不碰任何工程与成片。
"""

import os
import sys
import traceback

import nuke


def env(name, default):
    v = os.environ.get(name)
    return v if v else default


SET_NAME = env("UV2D_SET_NAME", "LangJiu_1014_ABCD")
UV_DIR = env("UV2D_UV_DIR", "W:/2026/20260701_LangJiu_ShanGuGuangYingXiu/comp/Nuke/UV")
SCREENS = [s.strip() for s in env("UV2D_SCREENS", "A,B,D,F").split(",") if s.strip()]
OUT_DIR = env("UV2D_OUT_DIR", "D:/codex/Nuke_uv2d_out")


def log(m):
    sys.stdout.write("[export] %s\n" % m)
    sys.stdout.flush()


def fwd(p):
    """Nuke 的 Write 会吃掉路径里的反斜杠，一律用正斜杠。"""
    return os.path.abspath(p).replace("\\", "/")


def main():
    raw = fwd(os.path.join(OUT_DIR, "raw"))
    os.makedirs(raw, exist_ok=True)
    nuke.scriptClear()

    summary = []
    for s in SCREENS:
        exr = "%s/UV_%s.exr" % (UV_DIR.rstrip("/"), s)
        if not os.path.exists(exr):
            raise RuntimeError("找不到 UV EXR: %s" % exr)

        r = nuke.createNode("Read", inpanel=False)
        r["file"].setValue(exr)
        r["colorspace"].setValue("linear")     # 坐标是数据，不能做色彩转换
        r["reload"].execute()
        fmt = r.format()
        W, H = int(fmt.width()), int(fmt.height())

        # u（红通道）与 v（绿通道）各写一张 16-bit 单通道 PNG
        for chan, tag in (("red", "u"), ("green", "v")):
            w = nuke.createNode("Write", inpanel=False)
            w.setInput(0, r)
            w["file"].setValue("%s/%s_%s.png" % (raw, tag, s))
            w["file_type"].setValue("png")
            w["datatype"].setValue("16 bit")
            w["channels"].setValue(chan)
            w["colorspace"].setValue("linear")
            w["create_directories"].setValue(True)
            if "checkHashOnRead" in w.knobs():
                w["checkHashOnRead"].setValue(False)
            nuke.execute(w, 1, 1)

        # 覆盖度：把 alpha 铺成黑白再写 8-bit 单通道
        e = nuke.createNode("Expression", inpanel=False)
        e.setInput(0, r)
        e["expr0"].setValue("a")
        e["expr1"].setValue("a")
        e["expr2"].setValue("a")
        e["expr3"].setValue("1")
        w = nuke.createNode("Write", inpanel=False)
        w.setInput(0, e)
        w["file"].setValue("%s/mask_%s.png" % (raw, s))
        w["file_type"].setValue("png")
        w["datatype"].setValue("8 bit")
        w["channels"].setValue("red")
        w["colorspace"].setValue("linear")
        w["create_directories"].setValue(True)
        nuke.execute(w, 1, 1)

        summary.append((s, W, H))
        log("%s: %dx%d  u/v/mask 已写出" % (s, W, H))

    # 供后面的 pack 步骤读取
    with open(fwd(os.path.join(OUT_DIR, "screens.txt")), "w", encoding="utf-8") as fh:
        fh.write("# screen\twidth\theight\n")
        for s, W, H in summary:
            fh.write("%s\t%d\t%d\n" % (s, W, H))
    log("集合 %s 导出完成 -> %s" % (SET_NAME, raw))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)
