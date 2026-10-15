# -*- coding: utf-8 -*-
"""在 Houdini 里跑：无界面执行一个 ROP（导出 GLB / 渲染等）。

用法（hython）：
    hython run_rop.py <工程.hip> [ROP 路径，默认 /out/gltf1] [--out 输出文件] [--frame 1]

用途：验证"克隆下来的工程能不能真的导出"，以及批量重导。
只读源工程；输出文件按 --out 覆盖 ROP 上的 file/sopoutput 参数。
"""

import argparse
import os
import sys
import time

import hou


def log(m):
    sys.stdout.write("[rop] %s\n" % m)
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hip")
    ap.add_argument("rop", nargs="?", default="/out/gltf1")
    ap.add_argument("--out", default=None)
    ap.add_argument("--frame", type=int, default=1)
    args = ap.parse_args()

    hou.hipFile.load(os.path.abspath(args.hip), suppress_save_prompt=True, ignore_load_warnings=True)
    node = hou.node(args.rop)
    if node is None:
        raise SystemExit("找不到 ROP %s" % args.rop)
    if not isinstance(node, hou.RopNode):
        raise SystemExit("%s 不是 ROP（是 %s）" % (args.rop, node.type().name()))
    for name in ("file", "filename", "sopoutput", "copoutput", "outputpath"):
        if args.out and node.parm(name) is not None:
            node.parm(name).set(args.out)
            log("设置 %s = %s" % (name, args.out))
    t0 = time.time()
    node.render(frame_range=(args.frame, args.frame), output_progress=False, verbose=False)
    log("%s 执行完成，用时 %.1fs" % (args.rop, time.time() - t0))
    for name in ("file", "filename", "sopoutput", "copoutput", "outputpath"):
        if node.parm(name) is not None:
            p = hou.text.expandString(node.parm(name).eval())
            if p and os.path.exists(p):
                log("产出 %s（%.2f MB）" % (p, os.path.getsize(p) / 1e6))
                return
    log("执行完成，但没找到输出文件（检查 ROP 的输出参数）")


if __name__ == "__main__":
    main()
