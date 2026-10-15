# -*- coding: utf-8 -*-
"""在 Houdini 里跑：列出 .hip 的节点树与全部资产引用（含输出路径）。

整理工程、准备放进版本库之前，先用它看清楚"这个工程到底依赖哪些文件"。

用法（hython）：
    hython inspect_hip.py <工程.hip> [--json 报告.json]

输出：节点总数、每条文件引用（节点 / 参数 / 原始值 / 展开后的绝对路径 / 是否存在）、
以及每个 ROP 的输出路径。
"""

import argparse
import json
import os
import sys

import hou

FILE_PARMS = ("file", "fileName", "filename", "sopoutput", "copoutput", "outputpath", "ropath")


def log(m):
    sys.stdout.write("[hip] %s\n" % m)
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hip")
    ap.add_argument("--json", default=None, help="把明细写成 JSON")
    args = ap.parse_args()

    hou.hipFile.load(os.path.abspath(args.hip), suppress_save_prompt=True, ignore_load_warnings=True)

    refs = []
    for parm, raw in hou.fileReferences():
        try:
            val = hou.text.expandString(raw)
        except Exception:
            continue
        p = parm if isinstance(parm, hou.Parm) else parm[0]
        refs.append({
            "node": p.node().path(), "node_type": p.node().type().name(), "parm": p.name(),
            "raw": raw, "path": val,
            "exists": os.path.exists(val),
            # ROP 的输出、以及渲染画廊的数据库都不是"输入资产"
            "is_output": isinstance(p.node(), hou.RopNode) or "/galleries/" in val.replace("\\", "/"),
        })

    rops = []
    for node in hou.node("/").allSubChildren():
        if not isinstance(node, hou.RopNode):
            continue
        entry = {"path": node.path(), "type": node.type().name()}
        for name in FILE_PARMS:
            if node.parm(name) is None:
                continue
            try:
                entry[name] = node.parm(name).eval()
            except Exception:
                pass
        rops.append(entry)

    nodes = hou.node("/").allSubChildren()
    log("节点 %d，文件引用 %d 条，ROP %d 个" % (len(nodes), len(refs), len(rops)))
    log("—— 输入资产 ——")
    missing = 0
    for r in refs:
        if r["is_output"]:
            continue
        flag = "OK " if r["exists"] else "缺失"
        if not r["exists"]:
            missing += 1
        log("  %s %-34s %-9s %s" % (flag, r["node"], r["parm"], r["path"]))
    log("—— 输出 / 会话文件 ——")
    for r in refs:
        if r["is_output"]:
            log("      %-34s %-9s %s" % (r["node"], r["parm"], r["path"]))
    log("—— ROP ——")
    for r in rops:
        log("  %s (%s) %s" % (r["path"], r["type"],
                              ", ".join("%s=%s" % (k, v) for k, v in r.items() if k not in ("path", "type"))))
    if missing:
        log("注意：有 %d 条输入资产缺失" % missing)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"hip": os.path.abspath(args.hip), "hfs": hou.getenv("HFS"),
                       "fps": hou.fps(), "refs": refs, "rops": rops},
                      fh, ensure_ascii=False, indent=1)
        log("明细写入 %s" % args.json)

    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
