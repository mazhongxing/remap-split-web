# -*- coding: utf-8 -*-
"""把 export_uvset.py 的原料打成网页素材。

输入（<集合>/raw/）：u_<屏>.png、v_<屏>.png（16-bit 单通道）、mask_<屏>.png（8-bit）
输出（<集合>/）：
    gridU_<屏>.png  1/8 分辨率，8-bit RGB：R=u 高 8 位、G=u 低 8 位、B=0
    gridV_<屏>.png  1/8 分辨率，8-bit RGB：R=v 高 8 位、G=v 低 8 位、B=0
    mask_<屏>.png   全分辨率，8-bit 灰度
    uvset.json      屏幕清单与尺寸

两个必须守住的点：
1. **先降采样、再拆高低位**。反过来先打包再平均，等于对高字节和低字节分别平均，
   进位的地方会崩。
2. **不能把坐标写进 alpha 通道**。浏览器上传带 alpha 的贴图时会把 RGB 按 alpha
   预乘掉，数据直接毁——所以是 gridU + gridV 两张 RGB。

坐标场是全画面连续的（UV EXR 里屏外也有有效坐标），所以这里用**普通盒式平均**，
不做覆盖率加权、也不做边缘扩展。

用法： python pack_uvset.py <集合目录> [集合名]
"""

import json
import os
import sys

import numpy as np
from PIL import Image

DEFAULT_CELL = 4      # 网格降采样倍数：越小越准、素材越大（见 README 的权衡表）


def log(m):
    sys.stdout.write("[pack] %s\n" % m)
    sys.stdout.flush()


def load16(path):
    im = Image.open(path)
    a = np.asarray(im)
    if a.dtype != np.uint16:
        raise RuntimeError("%s: 期望 16-bit 单通道，实际 %s/%s" % (path, im.mode, a.dtype))
    return a.astype(np.float64) / 65535.0


def box_mean(arr, cell):
    """按 cell x cell 分块求均值；不足一格的地方用边缘复制补齐。"""
    h, w = arr.shape
    pad_h = (-h) % cell
    pad_w = (-w) % cell
    if pad_h or pad_w:
        arr = np.pad(arr, ((0, pad_h), (0, pad_w)), mode="edge")
    hh, ww = arr.shape
    return arr.reshape(hh // cell, cell, ww // cell, cell).mean(axis=(1, 3)), hh, ww


def pack16(vals):
    """把 0..1 的坐标拆成 高8位/低8位 两个通道（RGB，第三通道留 0）。"""
    k = np.clip(np.round(vals * 65535.0), 0, 65535).astype(np.uint16)
    rgb = np.zeros(vals.shape + (3,), dtype=np.uint8)
    rgb[..., 0] = (k >> 8).astype(np.uint8)
    rgb[..., 1] = (k & 0xFF).astype(np.uint8)
    return rgb


def build(set_dir, screens, name, cell=DEFAULT_CELL):
    raw = os.path.join(set_dir, "raw")
    entries = []
    total = 0
    for s in screens:
        u = load16(os.path.join(raw, "u_%s.png" % s))
        v = load16(os.path.join(raw, "v_%s.png" % s))
        mask_path = os.path.join(raw, "mask_%s.png" % s)
        mask = np.asarray(Image.open(mask_path).convert("L"), dtype=np.uint8)
        if u.shape != v.shape or u.shape != mask.shape:
            raise RuntimeError("%s: 尺寸不一致 %s %s %s" % (s, u.shape, v.shape, mask.shape))

        gu, hh, ww = box_mean(u, cell)
        gv, _, _ = box_mean(v, cell)
        gh, gw = gu.shape

        gu_path = os.path.join(set_dir, "gridU_%s.png" % s)
        gv_path = os.path.join(set_dir, "gridV_%s.png" % s)
        out_mask = os.path.join(set_dir, "mask_%s.png" % s)
        Image.fromarray(pack16(gu), "RGB").save(gu_path, optimize=True)
        Image.fromarray(pack16(gv), "RGB").save(gv_path, optimize=True)
        Image.fromarray(mask, "L").save(out_mask, optimize=True)

        for p in (gu_path, gv_path, out_mask):
            total += os.path.getsize(p)
        log("%s: 输出 %dx%d -> 网格 %dx%d（补齐到 %dx%d）"
            % (s, mask.shape[1], mask.shape[0], gw, gh, ww, hh))
        entries.append({
            "name": s,
            "out": [int(mask.shape[1]), int(mask.shape[0])],
            "grid": [int(gw), int(gh)],
            "pad": [int(gw * cell), int(gh * cell)],
            "gridU": "gridU_%s.png" % s,
            "gridV": "gridV_%s.png" % s,
            "mask": "mask_%s.png" % s,
        })

    meta = {"name": name, "vAxis": "bottom", "cell": cell, "screens": entries}
    with open(os.path.join(set_dir, "uvset.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    log("uvset.json 写好，%d 屏，素材合计 %.2f MB" % (len(entries), total / 1e6))


def detect_screens(raw):
    """屏幕清单从 raw/ 里有哪些 u_<屏>.png 推出来，不写死 A/B/D/F。"""
    names = []
    for f in sorted(os.listdir(raw)):
        if f.startswith("u_") and f.endswith(".png"):
            s = f[2:-4]
            if os.path.exists(os.path.join(raw, "v_%s.png" % s)) and \
               os.path.exists(os.path.join(raw, "mask_%s.png" % s)):
                names.append(s)
    return names


def main():
    if len(sys.argv) < 2:
        raise SystemExit("用法: python pack_uvset.py <集合目录> [集合名] [网格倍率]")
    set_dir = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(os.path.normpath(set_dir))
    cell = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_CELL
    if not os.path.isdir(os.path.join(set_dir, "raw")):
        raise SystemExit("找不到 %s/raw，先跑 run_export.ps1" % set_dir)
    screens = detect_screens(os.path.join(set_dir, "raw"))
    if not screens:
        raise SystemExit("raw/ 里没有找到 u_<屏>.png / v_<屏>.png / mask_<屏>.png")
    build(set_dir, screens, name, cell)


if __name__ == "__main__":
    main()
