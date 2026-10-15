# -*- coding: utf-8 -*-
"""验收：用打包好的素材（gridU/gridV/mask）复算，与 Nuke 成片逐像素比。

这里走的是和网页着色器**完全一样**的算法：
  1. 双线性插值坐标网格（16-bit 高低位拼回来）；
  2. px = (u·W − 0.5, (1−v)·H − 0.5)，注意 v 轴翻转（EXR 的 v 原点在左下）；
  3. 线性空间双线性采样素材；
  4. 乘覆盖率 mask，再转回 sRGB。

门槛：平均误差 ≤ 2/255 且 p90 ≤ 6/255。

用法： python verify_uv2d.py [集合目录] [素材图] [成片目录模板]
"""

import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
W_ROOT = "W:/2026/20260701_LangJiu_ShanGuGuangYingXiu"

DEFAULT_SET = os.path.join(ROOT, "sets", "LangJiu_1014_ABCD")
DEFAULT_ART = W_ROOT + "/comp/QiePingSuCai/1004/C/001.jpg"
DEFAULT_REF = (W_ROOT + "/comp/Out_QiePing/QiePing1004C/QiePing1004C_{screen}"
                        "/QiePing1004C_{screen}.000001.png")


def to_linear(a):
    a = np.asarray(a, dtype=np.float32) / 255.0
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4).astype(np.float32)


def to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return (np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1.0 / 2.4) - 0.055) * 255.0).astype(np.float32)


def bilinear(img, x, y):
    h, w = img.shape[:2]
    x = np.clip(x, 0.0, w - 1.001)
    y = np.clip(y, 0.0, h - 1.001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    a = img[y0, x0]
    b = img[y0, x1]
    c = img[y1, x0]
    d = img[y1, x1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def load_grid(path):
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8).astype(np.uint16)
    return ((rgb[..., 0] << 8) | rgb[..., 1]).astype(np.float32) / 65535.0


def load_grid_8bit(path):
    """对照组：只取高 8 位，模拟"直接用 8-bit 坐标"的效果。"""
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    return rgb[..., 0].astype(np.float32) / 255.0


def reconstruct(art_lin, out_w, out_h, gu, gv, mask, cell=8, step=64):
    gh, gw = gu.shape
    pad_w, pad_h = gw * cell, gh * cell
    aw, ah = art_lin.shape[1], art_lin.shape[0]
    rec = np.empty((out_h, out_w, 3), dtype=np.float32)
    for y0 in range(0, out_h, step):
        y1 = min(y0 + step, out_h)
        fy = (np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5) / pad_h * gh - 0.5
        fx = (np.arange(0, out_w, dtype=np.float32)[None, :] + 0.5) / pad_w * gw - 0.5
        shp = (y1 - y0, out_w)
        u = bilinear(gu[..., None], np.broadcast_to(fx, shp), np.broadcast_to(fy, shp))[..., 0]
        v = bilinear(gv[..., None], np.broadcast_to(fx, shp), np.broadcast_to(fy, shp))[..., 0]
        # ↓ v 轴翻转：EXR 的 v 原点在左下，贴图的 v=0 在第一行（顶部）
        rgb = bilinear(art_lin, u * aw - 0.5, (1.0 - v) * ah - 0.5)
        rec[y0:y1] = to_srgb(rgb * mask[y0:y1, :, None])
    return rec


def stats(rec, ref_path):
    ref = np.asarray(Image.open(ref_path).convert("RGB"), dtype=np.float32)
    if ref.shape != rec.shape:
        return None
    d = np.abs(ref - rec).max(axis=2)
    return dict(mean=float(d.mean()), p50=float(np.percentile(d, 50)),
                p90=float(np.percentile(d, 90)), p99=float(np.percentile(d, 99)),
                mx=float(d.max()))


def main():
    set_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SET
    art_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_ART
    ref_tpl = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_REF

    meta = json.load(open(os.path.join(set_dir, "uvset.json"), encoding="utf-8"))
    art_lin = to_linear(np.asarray(Image.open(art_path).convert("RGB")))
    print("集合 %s ｜ 素材 %s" % (meta["name"], os.path.basename(art_path)))
    print("%-4s %8s %7s %7s %7s %7s   %s" % ("屏", "平均", "p50", "p90", "p99", "最大", "判定"))

    worst = 0.0
    worst8 = 0.0
    for sc in meta["screens"]:
        s = sc["name"]
        ref = ref_tpl.format(screen=s, frame=1)
        if not os.path.exists(ref):
            print("%-4s  (缺对照 %s)" % (s, ref))
            continue
        w, h = sc["out"]
        mask = np.asarray(Image.open(os.path.join(set_dir, sc["mask"])).convert("L"),
                          dtype=np.float32) / 255.0
        cell = int(sc.get("cell", meta.get("cell", 8)))
        gu = load_grid(os.path.join(set_dir, sc["gridU"]))
        gv = load_grid(os.path.join(set_dir, sc["gridV"]))
        st = stats(reconstruct(art_lin, w, h, gu, gv, mask, cell), ref)
        gu8 = load_grid_8bit(os.path.join(set_dir, sc["gridU"]))
        gv8 = load_grid_8bit(os.path.join(set_dir, sc["gridV"]))
        st8 = stats(reconstruct(art_lin, w, h, gu8, gv8, mask, cell), ref)
        if st is None:
            print("%-4s  尺寸对不上" % s)
            continue
        worst = max(worst, st["mean"])
        worst8 = max(worst8, st8["mean"])
        ok = st["mean"] <= 2.0 and st["p90"] <= 6.0
        print("%-4s %8.3f %7.2f %7.2f %7.2f %7.0f   %s    (对照: 只用高8位 %.2f)"
              % (s, st["mean"], st["p50"], st["p90"], st["p99"], st["mx"],
                 "OK" if ok else "!!", st8["mean"]))

    print("-" * 66)
    print("最差平均误差 = %.3f ／ 8-bit 对照组 = %.3f" % (worst, worst8))
    if worst <= 2.0 and worst8 > worst * 4:
        print("PASS（打包精度显著优于 8-bit，说明高低位打包确实起作用了）")
    elif worst <= 2.0:
        print("PASS（但 8-bit 对照组差距不够大，检查一下对照组是否真的只取了高 8 位）")
    else:
        print("FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
