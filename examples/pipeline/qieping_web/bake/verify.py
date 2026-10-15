# -*- coding: utf-8 -*-
"""验收：用烤好的素材（assets/）重算 A/B/D/F，和 Nuke 的成片逐像素比对。

这里走的是和网页完全一样的算法：
  1. 用 grid_<屏>.png 双线性插值出每个输出像素的素材坐标 (u, v)；
  2. 在**线性空间**对素材做双线性采样（Nuke 的 ScanlineRender 也在线性空间）；
  3. 乘上 mask_<屏>.png 的覆盖度；
  4. 转回 sRGB 8-bit。

用法：
    python verify.py                 # 校验 1004/C 全 4 帧（对照现网成片）
    python verify.py <素材> <成片模板>  # 自定义：模板里用 {screen} 和 {frame}
"""

import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

W_ROOT = "W:/2026/20260701_LangJiu_ShanGuGuangYingXiu"
SCREENS = ("A", "B", "D", "F")
CELL = 8


def to_linear(a):
    a = np.asarray(a, dtype=np.float32) / 255.0
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4).astype(np.float32)


def to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return (np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1.0 / 2.4) - 0.055) * 255.0).astype(np.float32)


def bilinear(img, x, y):
    """img (H,W,C)；x/y 是连续像素坐标，0.5 代表第一个像素的中心。"""
    h, w = img.shape[:2]
    x = np.clip(x, 0.0, w - 1.0001)
    y = np.clip(y, 0.0, h - 1.0001)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    a = img[y0, x0]
    b = img[y0, x0 + 1]
    c = img[y0 + 1, x0]
    d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def load_grid(screen):
    rgba = np.asarray(Image.open(os.path.join(ASSETS, "grid_%s.png" % screen)), dtype=np.uint8)
    ku = (rgba[..., 0].astype(np.uint16) << 8) | rgba[..., 1].astype(np.uint16)
    kv = (rgba[..., 2].astype(np.uint16) << 8) | rgba[..., 3].astype(np.uint16)
    return ku.astype(np.float32) / 65535.0, kv.astype(np.float32) / 65535.0


def load_mask(screen):
    return np.asarray(Image.open(os.path.join(ASSETS, "mask_%s.png" % screen)).convert("L"),
                      dtype=np.float32) / 255.0


def reconstruct(art_linear, out_w, out_h, gu, gv, mask, step=64):
    gh, gw = gu.shape
    pad_w, pad_h = gw * CELL, gh * CELL
    ah, aw = art_linear.shape[:2]
    rec = np.empty((out_h, out_w, 3), dtype=np.float32)
    for y0 in range(0, out_h, step):
        y1 = min(y0 + step, out_h)
        fy = (np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5) / pad_h * gh - 0.5
        fx = (np.arange(0, out_w, dtype=np.float32)[None, :] + 0.5) / pad_w * gw - 0.5
        u = bilinear(gu[..., None], np.broadcast_to(fx, (y1 - y0, out_w)),
                     np.broadcast_to(fy, (y1 - y0, out_w)))[..., 0]
        v = bilinear(gv[..., None], np.broadcast_to(fx, (y1 - y0, out_w)),
                     np.broadcast_to(fy, (y1 - y0, out_w)))[..., 0]
        rgb = bilinear(art_linear, u * aw - 0.5, v * ah - 0.5)
        rec[y0:y1] = to_srgb(rgb * mask[y0:y1, :, None])
    return rec


def stats(rec, target_path):
    tgt = np.asarray(Image.open(target_path).convert("RGB"), dtype=np.float32)
    if tgt.shape != rec.shape:
        raise RuntimeError("size %s vs %s" % (tgt.shape, rec.shape))
    d = np.abs(tgt - rec).max(axis=2)
    return dict(mean=float(d.mean()), p50=float(np.percentile(d, 50)),
                p90=float(np.percentile(d, 90)), p99=float(np.percentile(d, 99)),
                mx=float(d.max()), gt2=float((d > 2).mean() * 100.0))


def run_case(label, artworks, target_pattern, frames):
    """artworks: {frame: path}；target_pattern: 带 {screen}/{frame} 的路径模板。"""
    print("== %s" % label)
    worst = 0.0
    for frame in frames:
        art_path = artworks(frame)
        if art_path is None or not os.path.exists(art_path):
            print("   skip frame %d: missing %s" % (frame, art_path))
            continue
        art = to_linear(np.asarray(Image.open(art_path).convert("RGB")))
        for s in SCREENS:
            tgt = target_pattern.format(screen=s, frame=frame)
            if not os.path.exists(tgt):
                continue
            gu, gv = load_grid(s)
            m = load_mask(s)
            im = Image.open(tgt)
            rec = reconstruct(art, im.width, im.height, gu, gv, m)
            st = stats(rec, tgt)
            worst = max(worst, st["mean"])
            ok = st["mean"] <= 2.0 and st["p90"] <= 6.0
            print("   %s%-1s f%d: mean=%.3f p50=%.2f p90=%.2f p99=%.2f max=%.0f >2:%5.2f%%"
                  % ("OK " if ok else "!! ", s, frame, st["mean"], st["p50"], st["p90"],
                     st["p99"], st["mx"], st["gt2"]))
    print("   worst mean = %.3f" % worst)
    return worst


def main():
    args = sys.argv[1:]
    if len(args) >= 2:
        art_dir, tpl = args[0], args[1]
        frames = [int(x) for x in (args[2].split(",") if len(args) > 2 else ["1"])]

        def artworks(f):
            for ext in (".png", ".jpg"):
                p = os.path.join(art_dir, "%03d%s" % (f, ext))
                if os.path.exists(p):
                    return p
            cands = sorted(os.listdir(art_dir))
            return os.path.join(art_dir, cands[f - 1]) if cands else None

        worst = run_case("自定义校验", artworks, tpl, frames)
    else:
        case = W_ROOT + "/comp/QiePingSuCai/1004/C"
        out = (W_ROOT + "/comp/Out_QiePing/QiePing1004C/QiePing1004C_{screen}"
                          "/QiePing1004C_{screen}.{frame:06d}.png")
        worst = run_case("LangJiu 1004/C（素材 001-004，对照现网成片）",
                         lambda f: "%s/%03d.jpg" % (case, f), out, [1, 2, 3, 4])
    print("PASS" if worst <= 2.0 else "CHECK", "worst mean =", round(worst, 3))


if __name__ == "__main__":
    main()
