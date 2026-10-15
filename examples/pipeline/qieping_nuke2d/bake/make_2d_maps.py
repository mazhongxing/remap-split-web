# -*- coding: utf-8 -*-
"""给 2D 版 Nuke 工程准备映射素材。

数据源是网页版那套已经验证过的烤图产物（全分辨率）：
    qieping_web/bake/scratch/u_<屏>.png     16-bit 单通道，横向素材坐标
    qieping_web/bake/scratch/v_<屏>.png     16-bit 单通道，纵向素材坐标
    qieping_web/bake/scratch/mask_<屏>.png  8-bit  单通道，覆盖率

产出（本目录上一级的 maps/）：
    map_<屏>.png    16-bit RGB，R = u（反预乘后）、G = 1 - v、B = 0
    mask_<屏>.png   覆盖率蒙版（**RGB 三通道都写同一个值**）

两个关键点：

1. **反预乘**。烤图里的 u/v 是 ScanlineRender 的预乘输出
   （u_baked = u_true × 覆盖率），直接当坐标用，屏体边缘会有一圈脏边。
   这里逐像素除回覆盖率；覆盖率极小的地方（只有几个像素的边）除数不低于
   MIN_COVER，避免把量化误差放大成可见的偏移——那些像素本来也被蒙版压到接近全黑。
2. **翻转 V**。STMap 的坐标以图像**左下角**为原点，而烤出来的 v 是自上而下的，
   所以写进绿通道时要写成 1 - v。
3. **蒙版要写成 RGB**，不能只写单通道灰度。Nuke 读单通道图只会填红通道，
   用它去 Merge 相乘时绿蓝通道会乘上"不存在的通道 = 0"，画面直接废掉。

用法： python make_2d_maps.py
"""

import os
import struct
import sys
import zlib

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
MAPS = os.path.join(ROOT, "maps")
SCRATCH = os.path.abspath(os.path.join(HERE, "..", "..", "qieping_web", "bake", "scratch"))

SCREENS = ("A", "B", "D", "F")
MIN_COVER = 0.05      # 反预乘时分母的下限


def log(m):
    sys.stdout.write("[maps] %s\n" % m)
    sys.stdout.flush()


def load16(path):
    im = Image.open(path)
    a = np.asarray(im)
    if a.dtype != np.uint16:
        raise RuntimeError("%s: 期望 16-bit，实际 %s/%s" % (path, im.mode, a.dtype))
    return a.astype(np.float64) / 65535.0


def write_png16_rgb(path, plane):
    """plane: (H, W, 3) uint16 -> 16-bit RGB PNG（Pillow 写不了多通道 16-bit）。"""
    h, w, _ = plane.shape
    be = plane.astype(">u2")
    body = np.concatenate(
        [np.zeros((h, 1), dtype=np.uint8), be.view(np.uint8).reshape(h, -1)], axis=1)

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    data = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(body.tobytes(), 6))
            + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(data)


def build(screen):
    u_b = load16(os.path.join(SCRATCH, "u_%s.png" % screen))
    v_b = load16(os.path.join(SCRATCH, "v_%s.png" % screen))
    mask = np.asarray(Image.open(os.path.join(SCRATCH, "mask_%s.png" % screen)).convert("L"),
                      dtype=np.uint8)
    coverage = mask.astype(np.float64) / 255.0
    if u_b.shape != v_b.shape or u_b.shape != coverage.shape:
        raise RuntimeError("%s: 尺寸对不上 %s %s %s" % (screen, u_b.shape, v_b.shape, coverage.shape))

    denom = np.maximum(coverage, MIN_COVER)
    u_true = np.clip(u_b / denom, 0.0, 1.0)
    v_true = np.clip(v_b / denom, 0.0, 1.0)
    g = 1.0 - v_true

    plane = np.zeros(u_true.shape + (3,), dtype=np.uint16)
    plane[..., 0] = np.round(u_true * 65535.0).astype(np.uint16)
    plane[..., 1] = np.round(g * 65535.0).astype(np.uint16)

    map_path = os.path.join(MAPS, "map_%s.png" % screen)
    write_png16_rgb(map_path, plane)

    # 三通道写同一个值：Merge 逐通道相乘，单通道图会让绿蓝变 0
    mask_path = os.path.join(MAPS, "mask_%s.png" % screen)
    Image.fromarray(np.repeat(mask[:, :, None], 3, axis=2), "RGB").save(mask_path, optimize=True)

    log("%s: %dx%d  覆盖率 %.1f%%  u∈[%.3f,%.3f] v∈[%.3f,%.3f]"
        % (screen, plane.shape[1], plane.shape[0], coverage.mean() * 100.0,
           u_true.min(), u_true.max(), v_true.min(), v_true.max()))
    return map_path, mask_path


def main():
    if not os.path.isdir(SCRATCH):
        raise RuntimeError("找不到烤图目录：%s" % SCRATCH)
    os.makedirs(MAPS, exist_ok=True)
    for s in SCREENS:
        for p in build(s):
            log("  %-14s %9d bytes" % (os.path.basename(p), os.path.getsize(p)))


if __name__ == "__main__":
    main()
