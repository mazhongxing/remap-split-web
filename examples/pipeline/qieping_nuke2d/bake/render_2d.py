# -*- coding: utf-8 -*-
"""无头渲染 2D 版工程（给验收用）。

参数通过环境变量传（Nuke 的 -t 不会把额外命令行参数交给 sys.argv）：

    QIEPING_NK     要打开的 .nk（放在纯英文路径下的副本）
    QIEPING_OUT    可选：把四个 Write 改写到这个目录；不给就用 .nk 里写好的路径
    QIEPING_FIRST / QIEPING_LAST   帧范围
    QIEPING_ART    可选：换成另一套素材做交叉验证

渲染时会把四个 Write 的输出改写到 QIEPING_OUT，不会碰到 .nk 里写的现网路径。
"""

import os
import sys
import traceback

import nuke

SCREENS = ("A", "B", "D", "F")


def log(m):
    sys.stdout.write("[r2d] %s\n" % m)
    sys.stdout.flush()


def main():
    def env(key, default=None):
        v = os.environ.get(key, default)
        return v.replace("\\", "/") if isinstance(v, str) else v

    nk = env("QIEPING_NK")
    outdir = env("QIEPING_OUT")
    if not nk:
        raise RuntimeError("需要环境变量 QIEPING_NK")
    # abspath 在 Windows 上会把 / 换回 \，而 Nuke 的 file 旋钮会把 \ 吃掉，
    # 所以这里再统一换回正斜杠（这个坑在网页版那边也踩过一次）。
    nk = os.path.abspath(nk).replace("\\", "/")
    if outdir:
        outdir = os.path.abspath(outdir).replace("\\", "/")
    log("nk=%s" % nk)
    log("out=%s" % (outdir or "(用 .nk 自带路径)"))
    first, last = int(env("QIEPING_FIRST", "1")), int(env("QIEPING_LAST", "1"))
    artwork = env("QIEPING_ART")
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    log("opening %s" % nk)
    nuke.scriptOpen(nk)

    if artwork:
        src = nuke.toNode("SrcArtwork")
        if src is None:
            raise RuntimeError("脚本里找不到 SrcArtwork 节点")
        src["file"].setValue(artwork)
        src["file_type"].setValue("png" if artwork.lower().endswith(".png") or "###" in artwork and artwork.lower().endswith("png") else "jpeg")
        src["colorspace"].setValue("default")
        src["first"].setValue(first)
        src["last"].setValue(last)
        src["origfirst"].setValue(first)
        src["origlast"].setValue(last)
        src["reload"].execute()
        log("素材换成 %s" % artwork)

    for s in SCREENS:
        w = nuke.toNode("Write%s" % s)
        if w is None:
            raise RuntimeError("脚本里找不到 Write%s 节点" % s)
        if outdir:
            w["file"].setValue("%s/%s.%s.####.png" % (outdir, s, s))
        w["create_directories"].setValue(True)
        log("Write%s -> %s" % (s, w["file"].value()))

    for s in SCREENS:
        w = nuke.toNode("Write%s" % s)
        log("rendering %s 帧 %d-%d ..." % (s, first, last))
        nuke.execute(w, first, last)
    log("done -> %s" % outdir)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)
