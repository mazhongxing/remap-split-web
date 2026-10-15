# -*- coding: utf-8 -*-
"""在 Nuke 里跑：把坐标图导成网页素材的"原料"。

用法（经 run_export.ps1，或先把本目录拷到纯英文路径再跑）：
    "C:\\Program Files\\Nuke14.0v2\\Nuke14.0.exe" -t export_uvset.py

参数用**环境变量**传（Nuke 的 -t 不会把额外命令行参数交给 sys.argv）：
    UV2D_SET_NAME   集合名，默认 MySet
    UV2D_UV_DIR     坐标图所在目录
    UV2D_PATTERN    文件名模板，默认 UV_{screen}.exr；也支持 UV_{screen}.png
    UV2D_SCREENS    路名，逗号分隔，默认 A,B,D,F
    UV2D_OUT_DIR    输出目录（脚本在里面建 raw/）

输入格式任选其一：
    * 32-bit float EXR（精度源头）—— 约定 R=u、G=v、A=覆盖率
    * 16-bit RGBA PNG（Nuke 直接产出）—— 约定 R=u、G=v、B=0、A=覆盖率

每路产出（写到 <OUT>/raw/）：
    u_<路>.png     16-bit 单通道，横向坐标（归一化 0..1，原样不翻转）
    v_<路>.png     16-bit 单通道，纵向坐标（**原点在左下**）
    mask_<路>.png  8-bit 单通道，覆盖率

只读坐标图，不碰任何工程与成片。
"""

import os
import sys
import traceback

import nuke


def env(name, default):
    v = os.environ.get(name)
    return v if v else default


SET_NAME = env("UV2D_SET_NAME", "MySet")
UV_DIR = env("UV2D_UV_DIR", "")
PATTERN = env("UV2D_PATTERN", "UV_{screen}.exr")
SCREENS = [s.strip() for s in env("UV2D_SCREENS", "A,B,D,F").split(",") if s.strip()]
OUT_DIR = env("UV2D_OUT_DIR", "")


def log(m):
    sys.stdout.write("[export] %s\n" % m)
    sys.stdout.flush()


def fwd(p):
    """Nuke 的 file 旋钮会吃掉路径里的反斜杠，一律用正斜杠。"""
    return os.path.abspath(p).replace("\\", "/")


def file_type_of(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return {"exr": "exr", "png": "png", "tif": "tiff", "tiff": "tiff"}.get(ext, ext)


def main():
    if not UV_DIR or not OUT_DIR:
        raise RuntimeError("需要 UV2D_UV_DIR 与 UV2D_OUT_DIR")
    raw = fwd(os.path.join(OUT_DIR, "raw"))
    os.makedirs(raw, exist_ok=True)
    nuke.scriptClear()

    summary = []
    for s in SCREENS:
        src = "%s/%s" % (UV_DIR.rstrip("/"), PATTERN.format(screen=s))
        if not os.path.exists(src):
            raise RuntimeError("找不到坐标图: %s" % src)

        r = nuke.createNode("Read", inpanel=False)
        r["file"].setValue(src)
        r["file_type"].setValue(file_type_of(src))
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

        # 覆盖率：把 alpha 铺成黑白再写 8-bit 单通道
        e = nuke.createNode("Expression", inpanel=False)
        e.setInput(0, r)
        for k in ("expr0", "expr1", "expr2"):
            e[k].setValue("a")
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
