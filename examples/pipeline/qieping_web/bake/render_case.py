# -*- coding: utf-8 -*-
"""交叉验证用：拿任意一张素材，让 Nuke 按原工程渲一遍 A/B/D/F（8-bit sRGB PNG）。

只用于验收——证明烤好的映射表换一张完全不同的素材也对得上。
用法（经 run_render.ps1，或先把目录拷到纯英文路径）：
    Nuke14.0.exe -t render_case.py <素材图> <输出目录>
"""

import os
import sys
import traceback

import nuke

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
TEMPLATE = HERE + "/template.nk"

FRAME = 1
SCREENS = ("A", "B", "D", "F")


def log(m):
    sys.stdout.write("[render] %s\n" % m)
    sys.stdout.flush()


def main():
    if len(sys.argv) < 3:
        raise RuntimeError("usage: render_case.py <image> <out_dir>")
    image = os.path.abspath(sys.argv[1]).replace("\\", "/")
    out_dir = os.path.abspath(sys.argv[2]).replace("\\", "/")
    os.makedirs(out_dir, exist_ok=True)
    if not os.path.exists(image):
        raise RuntimeError("missing image %s" % image)

    nuke.scriptOpen(TEMPLATE)
    nuke.root()["frame"].setValue(FRAME)

    reads = [n for n in nuke.allNodes("Read") if "QiePingSuCai" in n["file"].value()]
    if len(reads) != 1:
        raise RuntimeError("expected 1 input Read")
    r = reads[0]
    r["file"].setValue(image)
    r["file_type"].setValue("png" if image.lower().endswith(".png") else "jpeg")
    r["colorspace"].setValue("default")
    for k in ("first", "last", "origfirst", "origlast"):
        if k in r.knobs():
            r[k].setValue(FRAME)
    r["reload"].execute()

    writes = {}
    for n in nuke.allNodes("Write"):
        p = n["file"].value().replace("\\", "/")
        for s in SCREENS:
            if "QiePing1004C_%s/" % s in p:
                writes[s] = n

    for s in SCREENS:
        w = writes[s]
        w["file"].setValue("%s/%s.png" % (out_dir, s))
        w["file_type"].setValue("png")
        w["datatype"].setValue("8 bit")
        w["colorspace"].setValue("default")
        w["create_directories"].setValue(True)
        log("rendering %s ..." % s)
        nuke.execute(w, FRAME, FRAME)
    log("done -> %s" % out_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)
