# -*- coding: utf-8 -*-
"""在 Houdini 里跑：把 .hip 里的绝对资产路径改写成 $HIP 相对路径，另存一份。

目的：把一个依赖 W:/... 绝对路径的工程整理成"拷到哪都能打开"的干净工程，
方便放进版本库或发给别人。

用法（hython）：
    hython relink_hip_assets.py <源.hip> <目标.hip> <源资产根目录> [--assets-dir 目标相对目录]

例：
    hython relink_hip_assets.py W:/proj/hip/Mars/web_make/a.hip ./a_relinked.hip W:/proj/hip --assets-dir WP

行为：
  * 遍历 hou.fileReferences()，把落在 <源资产根目录> 下的路径改成 $HIP/<相对路径>；
  * 落在根目录之外的引用保持原样并打印出来（提醒你手工处理）；
  * 保存后重新打开目标文件，逐条确认引用文件真实存在。

只读源文件，不覆盖它。
"""

import argparse
import os
import sys

import hou


def log(m):
    sys.stdout.write("[relink] %s\n" % m)
    sys.stdout.flush()


def set_ref(parm_or_tuple, value):
    """hou.fileReferences() 在不同版本里给的是 Parm 或 Parm 元组，这里都兜住。"""
    if isinstance(parm_or_tuple, hou.Parm):
        parm_or_tuple.set(value)
    else:
        for pt in parm_or_tuple:
            pt.set(value)


def is_output_ref(parm_or_tuple):
    """区分"输入资产"和"输出/会话文件"：ROP 的输出路径、渲染画廊的数据库都不算缺失。"""
    p = parm_or_tuple if isinstance(parm_or_tuple, hou.Parm) else parm_or_tuple[0]
    if isinstance(p.node(), hou.RopNode):
        return True
    return "/galleries/" in p.eval().replace("\\", "/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_hip")
    ap.add_argument("dst_hip")
    ap.add_argument("src_root", help="源资产根目录（绝对路径），它下面的引用会被改写成 $HIP 相对路径")
    ap.add_argument("--assets-dir", default=None,
                    help="资产在新工程里的相对目录名（默认按源根目录下的相对位置保持原样）")
    args = ap.parse_args()

    src_hip = os.path.abspath(args.src_hip)
    dst_hip = os.path.abspath(args.dst_hip)
    src_root = os.path.abspath(args.src_root).rstrip("\\/")

    hou.hipFile.load(src_hip, suppress_save_prompt=True, ignore_load_warnings=True)

    changed, outside = [], []
    for parm_tuples, raw in hou.fileReferences():
        try:
            val = hou.text.expandString(raw)
        except Exception:
            continue
        if not val or not os.path.isabs(val):
            continue
        norm = os.path.normpath(val)
        if norm.lower().startswith(src_root.lower()):
            rel = os.path.relpath(norm, src_root).replace("\\", "/")
            if args.assets_dir:
                rel = "%s/%s" % (args.assets_dir.strip("/"), rel)
            newval = "$HIP/" + rel
            set_ref(parm_tuples, newval)
            changed.append((raw, newval))
        else:
            outside.append((raw, norm))

    hou.hipFile.save(dst_hip, save_to_recent_files=False)
    log("改写 %d 条引用 -> %s" % (len(changed), dst_hip))
    for a, b in changed:
        log("   %s  ->  %s" % (a, b))
    if outside:
        log("以下 %d 条不在资产根目录下，保持原样（需要你自己处理）：" % len(outside))
        for a, b in outside:
            log("   %s" % b)

    hou.hipFile.load(dst_hip, suppress_save_prompt=True, ignore_load_warnings=True)
    missing = []
    total, skipped = 0, 0
    for parm_tuples, raw in hou.fileReferences():
        try:
            val = hou.text.expandString(raw)
        except Exception:
            continue
        if not val or val.startswith("op:") or val == "defcam.bgeo":
            continue
        if is_output_ref(parm_tuples):
            skipped += 1
            continue
        total += 1
        if not os.path.exists(val):
            missing.append((raw, val))
    log("校验：%d 条输入资产引用，缺失 %d 条（另有 %d 条输出/会话文件已跳过）"
        % (total, len(missing), skipped))
    for raw, val in missing:
        log("   缺 %s" % val)
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
