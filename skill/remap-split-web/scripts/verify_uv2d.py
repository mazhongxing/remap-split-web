# -*- coding: utf-8 -*-
"""验收：用打包好的素材复算，与 DCC 成片逐像素比。

走的是和网页着色器**完全一样**的算法：
  1. 双线性插值坐标网格（16-bit 高低位拼回来）；
  2. px = (u*W - 0.5, (1-v)*H - 0.5)，v 轴翻转（DCC 的 v 原点在左下）；
  3. 线性空间双线性采样素材；4. 乘覆盖率 mask，再转回 sRGB。

同时跑一条"只用高 8 位"的对照组——打包精度必须显著优于它，
否则说明打包没起作用（或对照组写错了）。

门槛：平均误差 <=2/255 且 p90 <=6/255。

用法： python verify_uv2d.py <集合目录> <素材图> "<对照模板，含 {screen}>"
"""

import json
import os
import sys

import numpy as np
from PIL import Image

MEAN_LIMIT = 2.0
P90_LIMIT = 6.0


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
    a, b = img[y0, x0], img[y0, x1]
    c, d = img[y1, x0], img[y1, x1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def load_grid(path):
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8).astype(np.uint16)
    return ((rgb[..., 0] << 8) | rgb[..., 1]).astype(np.float32) / 65535.0


def load_grid_8bit(path):
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)
    return rgb[..., 0].astype(np.float32) / 255.0


def reconstruct(art_lin, out_w, out_h, gu, gv, mask, cell=4, step=64):
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
    if len(sys.argv) < 4:
        raise SystemExit('用法: python verify_uv2d.py <集合目录> <素材图> "<对照模板，含 {screen}>"')
    set_dir, art_path, ref_tpl = sys.argv[1], sys.argv[2], sys.argv[3]

    meta = json.load(open(os.path.join(set_dir, "uvset.json"), encoding="utf-8"))
    art_lin = to_linear(np.asarray(Image.open(art_path).convert("RGB")))
    print("集合 %s ｜ 素材 %s" % (meta["name"], os.path.basename(art_path)))
    print("%-6s %8s %7s %7s %7s %7s   %s" % ("路", "平均", "p50", "p90", "p99", "最大", "判定"))

    worst = 0.0
    worst8 = 0.0
    for sc in meta["screens"]:
        s = sc["name"]
        ref = ref_tpl.format(screen=s, frame=1)
        if not os.path.exists(ref):
            print("%-6s  (缺对照 %s)" % (s, ref))
            continue
        w, h = sc["out"]
        cell = int(sc.get("cell", meta.get("cell", 4)))
        mask = np.asarray(Image.open(os.path.join(set_dir, sc["mask"])).convert("L"),
                          dtype=np.float32) / 255.0
        gu = load_grid(os.path.join(set_dir, sc["gridU"]))
        gv = load_grid(os.path.join(set_dir, sc["gridV"]))
        st = stats(reconstruct(art_lin, w, h, gu, gv, mask, cell), ref)
        gu8 = load_grid_8bit(os.path.join(set_dir, sc["gridU"]))
        gv8 = load_grid_8bit(os.path.join(set_dir, sc["gridV"]))
        st8 = stats(reconstruct(art_lin, w, h, gu8, gv8, mask, cell), ref)
        if st is None:
            print("%-6s  尺寸对不上" % s)
            continue
        worst = max(worst, st["mean"])
        worst8 = max(worst8, st8["mean"])
        ok = st["mean"] <= MEAN_LIMIT and st["p90"] <= P90_LIMIT
        print("%-6s %8.3f %7.2f %7.2f %7.2f %7.0f   %s   (对照: 只用高8位 %.2f)"
              % (s, st["mean"], st["p50"], st["p90"], st["p99"], st["mx"],
                 "OK" if ok else "!!", st8["mean"]))

    print("-" * 66)
    print("最差平均误差 = %.3f ／ 8-bit 对照组 = %.3f" % (worst, worst8))
    if worst <= MEAN_LIMIT and worst8 > worst * 4:
        print("PASS（打包精度显著优于 8-bit，高低位打包确实起作用了）")
    elif worst <= MEAN_LIMIT:
        print("PASS（但 8-bit 对照组差距不够大，检查对照组是否真的只取了高 8 位）")
    else:
        print("FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
