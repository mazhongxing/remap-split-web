# -*- coding: utf-8 -*-
"""在 Nuke 里烤出 A/B/D/F 四块屏的映射表（离线一次性）。

用法（务必经由 run_bake.ps1，或先把本脚本所在目录拷到纯英文路径）：
    "C:\\Program Files\\Nuke14.0v2\\Nuke14.0.exe" -t bake_maps.py

做两遍渲染：

  第一遍  输入替换成 ref/uv_ref.png（R=(x+0.5)/W、G=(y+0.5)/H），
          每块屏各输出两张 16-bit 单通道 PNG：u_<屏>.png（red）、v_<屏>.png（green）。
          数值就是"该输出像素要去素材的哪个位置取色"。
  第二遍  输入替换成 ref/white.png，每块屏输出 mask_<屏>.png（8-bit），
          亮度＝覆盖度，也就是每块屏的 alpha（含抗锯齿边缘）。

原始工程与现网素材/成片全程只读；写入只落在本目录 scratch/。
"""

import os
import sys
import traceback

import nuke

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
TEMPLATE = HERE + "/template.nk"
REF_UV = HERE + "/ref/uv_ref.png"
REF_WHITE = HERE + "/ref/white.png"
SCRATCH = HERE + "/scratch"

FRAME = 1
SCREENS = ("A", "B", "D", "F")


def log(msg):
    sys.stdout.write("[bake] %s\n" % msg)
    sys.stdout.flush()


def find_input_read():
    """输入素材那个 Read（区别于 ReadGeo）。"""
    reads = nuke.allNodes("Read")
    hits = [n for n in reads if "QiePingSuCai" in n["file"].value()]
    if len(hits) != 1:
        raise RuntimeError("expected exactly 1 input Read, found %d in %s"
                           % (len(hits), [(n.name(), n["file"].value()) for n in reads]))
    return hits[0]


def find_writes():
    """按输出路径认出 A/B/D/F 四个 Write。"""
    found = {}
    for n in nuke.allNodes("Write"):
        path = n["file"].value().replace("\\", "/")
        for s in SCREENS:
            if "QiePing1004C_%s/" % s in path:
                found[s] = n
    missing = [s for s in SCREENS if s not in found]
    if missing:
        raise RuntimeError("missing Write nodes for %s (found %s)"
                           % (missing, sorted(found)))
    return found


def setup_input(node, image):
    node["file"].setValue(image)
    node["file_type"].setValue("png")
    node["colorspace"].setValue("linear")  # 工作空间本身就是 linear，等于不做转换
    for k in ("first", "last", "origfirst", "origlast"):
        if k in node.knobs():
            node[k].setValue(FRAME)
    if "origset" in node.knobs():
        node["origset"].setValue(True)
    node["reload"].execute()


def new_write(source, path, channel, datatype):
    w = nuke.createNode("Write", inpanel=False)
    w.setInput(0, source)
    w["file"].setValue(path)
    w["file_type"].setValue("png")
    w["datatype"].setValue(datatype)
    w["channels"].setValue(channel)
    w["colorspace"].setValue("linear")
    w["create_directories"].setValue(True)
    if "checkHashOnRead" in w.knobs():
        w["checkHashOnRead"].setValue(False)
    return w


def render_and_verify(node, path, expect_size):
    if not os.path.exists(path):
        raise RuntimeError("render did not produce %s" % path)
    size = os.path.getsize(path)
    if size < 64:
        raise RuntimeError("suspiciously small output %s (%d bytes)" % (path, size))
    return size


def main():
    os.makedirs(SCRATCH, exist_ok=True)
    for need in (TEMPLATE, REF_UV, REF_WHITE):
        if not os.path.exists(need):
            raise RuntimeError("missing %s (run gen_ref.py first)" % need)

    log("opening %s" % TEMPLATE)
    nuke.scriptOpen(TEMPLATE)
    nuke.root()["frame"].setValue(FRAME)

    reads = find_input_read()
    writes = find_writes()
    log("input Read: %s" % reads.name())
    log("Writes: %s" % {s: writes[s].name() for s in SCREENS})

    # ---- 第一遍：UV ----
    setup_input(reads, REF_UV)
    for s in SCREENS:
        source = writes[s].input(0)
        if source is None:
            raise RuntimeError("Write for %s has no input" % s)
        for ch, tag in (("red", "u"), ("green", "v")):
            path = "%s/%s_%s.png" % (SCRATCH, tag, s)
            node = new_write(source, path, ch, "16 bit")
            log("rendering %s_%s ..." % (tag, s))
            nuke.execute(node, FRAME, FRAME)
            log("  %s -> %d bytes" % (os.path.basename(path), render_and_verify(node, path, 0)))

    # ---- 第二遍：覆盖度 ----
    setup_input(reads, REF_WHITE)
    for s in SCREENS:
        source = writes[s].input(0)
        path = "%s/mask_%s.png" % (SCRATCH, s)
        node = new_write(source, path, "red", "8 bit")
        log("rendering mask_%s ..." % s)
        nuke.execute(node, FRAME, FRAME)
        log("  mask_%s -> %d bytes" % (s, render_and_verify(node, path, 0)))

    log("bake OK")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)
