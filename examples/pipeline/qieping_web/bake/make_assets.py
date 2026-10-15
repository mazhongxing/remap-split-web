# -*- coding: utf-8 -*-
"""把 bake_maps.py 的烤图产物压成网页要用的素材。

输入（scratch/，由 Nuke 产出）：
    u_<屏>.png     16-bit 单通道，横向素材坐标 0..1
    v_<屏>.png     16-bit 单通道，纵向素材坐标 0..1
    mask_<屏>.png  8-bit  单通道，覆盖度（alpha）

输出（assets/）：
    gridU_<屏>.png / gridV_<屏>.png
                   1/8 分辨率的坐标网格，RGB 8-bit（**故意不带 alpha**：
                   带 alpha 的话浏览器会把 RGB 预乘掉，数据就毁了）。
                   R=高 8 位、G=低 8 位，两通道拼成 16-bit 坐标。
    mask_<屏>.png  全分辨率 8-bit 灰度，覆盖度。

两个关键处理：

1. **反预乘**。ScanlineRender 输出的是预乘结果，所以烤图里
   u_baked = u_true * 覆盖度。直接拿 u_baked 当坐标用，屏边一圈会偏。
   一格的平均坐标 = Σu_baked / Σ覆盖度，正好就是 u_true 的覆盖度加权平均。
2. **整格无效就补邻近格**。屏外整格没有有效像素，用最近的有效格填，
   免得双线性插值把屏外那圈坐标带进来。补的时候不要跨边界回绕。
"""

import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.join(HERE, "scratch")
ASSETS = os.path.join(HERE, "assets")

SCREENS = ("A", "B", "D", "F")
CELL = 8


def log(m):
    sys.stdout.write("[assets] %s\n" % m)
    sys.stdout.flush()


def load16(path):
    im = Image.open(path)
    a = np.asarray(im)
    if a.dtype != np.uint16:
        raise RuntimeError("%s: expected 16-bit, got %s/%s" % (path, im.mode, a.dtype))
    return a


def load8(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.uint8)


def box_sum(arr, cell):
    """按 cell x cell 分块求和，返回 (网格, 补齐后的高, 补齐后的宽)。"""
    h, w = arr.shape
    pad_h = (-h) % cell
    pad_w = (-w) % cell
    if pad_h or pad_w:
        arr = np.pad(arr, ((0, pad_h), (0, pad_w)), mode="edge")
    hh, ww = arr.shape
    grid = arr.reshape(hh // cell, cell, ww // cell, cell).sum(axis=(1, 3))
    return grid, hh, ww


def fill_nearest(grid, valid, rounds=512):
    """把 valid=False 的格子用最近的有效格子补上（迭代膨胀，不跨边界回绕）。"""
    g = grid.astype(np.float64).copy()
    v = valid.copy()
    if not v.any():
        raise RuntimeError("no valid cells at all")
    for _ in range(rounds):
        if v.all():
            break
        vp = np.pad(v.astype(np.float64), 1, mode="constant")
        gp = np.pad(np.where(v, g, 0.0), 1, mode="constant")
        acc = np.zeros_like(g)
        cnt = np.zeros_like(g)
        for dy in (0, 1, 2):
            for dx in (0, 1, 2):
                if dx == 1 and dy == 1:
                    continue
                acc += gp[dy:dy + g.shape[0], dx:dx + g.shape[1]]
                cnt += vp[dy:dy + g.shape[0], dx:dx + g.shape[1]]
        newly = (~v) & (cnt > 0)
        g[newly] = acc[newly] / cnt[newly]
        v = v | newly
    return g, v


def build_screen(screen):
    u = load16(os.path.join(SCRATCH, "u_%s.png" % screen)).astype(np.float64) / 65535.0
    v = load16(os.path.join(SCRATCH, "v_%s.png" % screen)).astype(np.float64) / 65535.0
    mask = load8(os.path.join(SCRATCH, "mask_%s.png" % screen))
    if u.shape != v.shape or u.shape != mask.shape:
        raise RuntimeError("%s: size mismatch %s %s %s" % (screen, u.shape, v.shape, mask.shape))

    # u/v 是 ScanlineRender 的预乘输出（已乘过覆盖度），覆盖度就是 alpha。
    coverage = mask.astype(np.float64) / 255.0
    num_u, hh, ww = box_sum(u, CELL)
    num_v, _, _ = box_sum(v, CELL)
    den, _, _ = box_sum(coverage, CELL)
    gw, gh = ww // CELL, hh // CELL

    have = den > 0.25
    gu = np.zeros_like(num_u)
    gv = np.zeros_like(num_v)
    gu[have] = num_u[have] / den[have]
    gv[have] = num_v[have] / den[have]
    gu, _ = fill_nearest(gu, have)
    gv, _ = fill_nearest(gv, have)

    log("%s: output %dx%d -> grid %dx%d, covered cells %.1f%%"
        % (screen, ww, hh, gw, gh, have.mean() * 100.0))

    def pack16(vals):
        k = np.clip(np.round(vals * 65535.0), 0, 65535).astype(np.uint16)
        rgb = np.zeros((gh, gw, 3), dtype=np.uint8)
        rgb[..., 0] = (k >> 8).astype(np.uint8)
        rgb[..., 1] = (k & 0xFF).astype(np.uint8)
        return rgb

    grid_u_path = os.path.join(ASSETS, "gridU_%s.png" % screen)
    grid_v_path = os.path.join(ASSETS, "gridV_%s.png" % screen)
    Image.fromarray(pack16(gu), "RGB").save(grid_u_path, optimize=True)
    Image.fromarray(pack16(gv), "RGB").save(grid_v_path, optimize=True)

    mask_path = os.path.join(ASSETS, "mask_%s.png" % screen)
    Image.fromarray(mask, "L").save(mask_path, optimize=True)

    return grid_u_path, grid_v_path, mask_path


def main():
    os.makedirs(ASSETS, exist_ok=True)
    total = 0
    for s in SCREENS:
        for p in build_screen(s):
            size = os.path.getsize(p)
            total += size
            log("  %-12s %7d bytes" % (os.path.basename(p), size))
    log("total %.2f MB" % (total / 1e6))


if __name__ == "__main__":
    main()
