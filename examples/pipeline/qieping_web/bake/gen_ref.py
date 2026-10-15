# -*- coding: utf-8 -*-
"""生成烤图用的参考图（离线一次性）。

产出两张参考图，供 bake_maps.py 在 Nuke 里当作 Project3D 的输入素材：

* ref/uv_ref.png   —— 16-bit RGB，R=(x+0.5)/W、G=(y+0.5)/H、B=0。
                      渲染出来就是"每个输出像素采样到素材的哪个位置"的映射表。
* ref/white.png    —— 8-bit 纯白，用来渲染覆盖度（也就是每块屏的 alpha 遮罩）。

尺寸固定 6000x1538，和现网工程 Root/Read 强制格式一致。

Pillow 不能写多通道 16-bit PNG，所以 uv_ref.png 用标准库 zlib 手写。
"""

import os
import struct
import zlib

import numpy as np
from PIL import Image

W, H = 6000, 1538

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.join(HERE, "ref")


def write_png16_rgb(path, plane):
    """plane: (H, W, 3) uint16 ndarray -> 16-bit RGB PNG."""
    h, w, _ = plane.shape
    be = plane.astype(">u2")
    body = np.concatenate(
        [np.zeros((h, 1), dtype=np.uint8), be.view(np.uint8).reshape(h, -1)],
        axis=1,
    )

    def chunk(tag, payload):
        out = struct.pack(">I", len(payload)) + tag + payload
        return out + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(body.tobytes(), 9))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as fh:
        fh.write(data)


def main():
    os.makedirs(REF_DIR, exist_ok=True)

    u = np.round((np.arange(W, dtype=np.float64) + 0.5) / W * 65535.0).astype(np.uint16)
    v = np.round((np.arange(H, dtype=np.float64) + 0.5) / H * 65535.0).astype(np.uint16)

    plane = np.zeros((H, W, 3), dtype=np.uint16)
    plane[:, :, 0] = u[None, :]
    plane[:, :, 1] = v[:, None]

    uv_path = os.path.join(REF_DIR, "uv_ref.png")
    write_png16_rgb(uv_path, plane)
    print("wrote", uv_path, os.path.getsize(uv_path), "bytes")

    white_path = os.path.join(REF_DIR, "white.png")
    Image.fromarray(np.full((H, W, 3), 255, dtype=np.uint8), "RGB").save(white_path, optimize=True)
    print("wrote", white_path, os.path.getsize(white_path), "bytes")


if __name__ == "__main__":
    main()
