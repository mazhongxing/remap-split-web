# -*- coding: utf-8 -*-
"""验收：把 2D 版渲出来的图和现网 3D 工程的成片逐像素比。

用法：
    python verify_2d.py [2D 渲染目录] [现网成片模板]

默认比较 work 目录里那批（`run_render_2d.ps1` 的产物）和
`Out_QiePing/QiePing1004C/*`。模板里可用 {screen} 和 {frame} 占位。

判定标准：每屏每帧 **平均误差 ≤ 2/255 且 p90 ≤ 3/255** 才算通过。
"""

import os
import sys

import numpy as np
from PIL import Image

W_ROOT = "W:/2026/20260701_LangJiu_ShanGuGuangYingXiu"
SCREENS = ("A", "B", "D", "F")

DEFAULT_RENDERED = r"D:\codex\_qieping_bake\out2d_1004C"
DEFAULT_REF = (W_ROOT + "/comp/Out_QiePing/QiePing1004C/QiePing1004C_{screen}"
                         "/QiePing1004C_{screen}.{frame:06d}.png")

MEAN_LIMIT = 2.0
P90_LIMIT = 3.0


def compare(a_path, b_path):
    a = np.asarray(Image.open(a_path).convert("RGB"), dtype=np.float32)
    b = np.asarray(Image.open(b_path).convert("RGB"), dtype=np.float32)
    if a.shape != b.shape:
        return None, "%s vs %s 尺寸不一致" % (a.shape, b.shape)
    d = np.abs(a - b).max(axis=2)
    return (float(d.mean()), float(np.percentile(d, 90)), float(np.percentile(d, 99)),
            float(d.max())), None


def main():
    rendered = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RENDERED
    ref_tpl = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_REF

    frames = sorted({int(os.path.splitext(f)[0].split(".")[-1])
                     for f in os.listdir(rendered) if f.lower().endswith(".png")})
    if not frames:
        raise SystemExit("渲染目录里没有 PNG：%s" % rendered)

    print("对比 %s  <->  %s" % (rendered, ref_tpl))
    print("%-4s %-5s %8s %7s %7s %7s %7s  %s" % ("屏", "帧", "平均", "p90", "p99", "最大", "", "判定"))
    worst = 0.0
    failed = []
    for s in SCREENS:
        for f in frames:
            rp = os.path.join(rendered, "%s.%s.%04d.png" % (s, s, f))
            ref = ref_tpl.format(screen=s, frame=f)
            if not os.path.exists(rp):
                print("%-4s %-5d  (缺 %s)" % (s, f, os.path.basename(rp)))
                failed.append((s, f, "缺文件"))
                continue
            if not os.path.exists(ref):
                print("%-4s %-5d  (缺对照 %s)" % (s, f, ref))
                failed.append((s, f, "缺对照"))
                continue
            st, err = compare(rp, ref)
            if err:
                print("%-4s %-5d  %s" % (s, f, err))
                failed.append((s, f, err))
                continue
            mean, p90, p99, mx = st
            worst = max(worst, mean)
            ok = mean <= MEAN_LIMIT and p90 <= P90_LIMIT
            if not ok:
                failed.append((s, f, "mean=%.2f p90=%.2f" % (mean, p90)))
            print("%-4s %-5d %8.3f %7.2f %7.2f %7.0f  %s" % (s, f, mean, p90, p99, mx, "OK" if ok else "!!"))

    print("-" * 62)
    print("最差平均误差 = %.3f / %d 帧组" % (worst, len(SCREENS) * len(frames)))
    if failed:
        print("未通过 %d 项：%s" % (len(failed), failed))
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
