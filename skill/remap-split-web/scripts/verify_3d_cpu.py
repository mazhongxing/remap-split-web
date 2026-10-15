# -*- coding: utf-8 -*-
"""CPU 黄金对照：素材 → 切图 → 贴到场景模型上 → 用观众相机渲染一帧。

这是 3D 预览的"标准答案"：网页（WebGL2）渲出来的结果要和这张图对齐。
同时给出"观众机位重建 vs 原图"的误差，用来证明切图贴回真实屏体确实能还原画面。

用法：
    python verify_3d_cpu.py <scene.glb> <UV集合目录> <素材图> <输出目录>
                            [--frame 3000x769] [--panel-scale 1] [--node-prefix QiePing]
"""

import argparse
import json
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

CT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def load_glb(path):
    d = open(path, "rb").read()
    off, chunks = 12, []
    length = struct.unpack_from("<I", d, 8)[0]
    while off < length:
        clen, ctype = struct.unpack_from("<II", d, off)
        chunks.append((ctype, off + 8, clen))
        off += 8 + clen
    js = json.loads(d[chunks[0][1]:chunks[0][1] + chunks[0][2]].decode("utf-8"))
    return js, d[chunks[1][1]:chunks[1][1] + chunks[1][2]]


def acc(js, bin_, i):
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    fmt, sz = CT[a["componentType"]]
    n = NC[a["type"]]
    stride = bv.get("byteStride") or sz * n
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    out = np.zeros((a["count"], n))
    for k in range(a["count"]):
        out[k] = struct.unpack_from("<" + fmt * n, bin_, base + k * stride)
    if a.get("normalized"):
        out = out / {5121: 255.0, 5123: 65535.0, 5120: 127.0, 5122: 32767.0}[a["componentType"]]
    return out.reshape(-1) if n == 1 else out


def mat4(m):
    return np.array(m, dtype=np.float64).reshape(4, 4, order="F")


def world_transforms(js):
    out = {}

    def rec(i, parent):
        n = js["nodes"][i]
        M = parent
        if "matrix" in n:
            M = parent @ mat4(n["matrix"])
        out[i] = M
        for c in n.get("children", []):
            rec(c, M)

    for i in js["scenes"][js.get("scene", 0)]["nodes"]:
        rec(i, np.eye(4))
    return out


def to_linear(a):
    x = np.asarray(a, dtype=np.float32) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return (np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1.0 / 2.4) - 0.055) * 255.0).astype(np.uint8)


def bilinear(img, x, y):
    h, w = img.shape[:2]
    x = np.clip(x, 0.0, w - 1.001)
    y = np.clip(y, 0.0, h - 1.001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    return ((img[y0, x0] * (1 - fx) + img[y0, x1] * fx) * (1 - fy)
            + (img[y1, x0] * (1 - fx) + img[y1, x1] * fx) * fy)


def load_grid(path):
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8).astype(np.uint16)
    return ((rgb[..., 0] << 8) | rgb[..., 1]).astype(np.float32) / 65535.0


def make_panel(art_lin, sc, set_dir, scale, cell):
    """复算切图（与网页着色器同算法）；返回 8-bit sRGB 图与覆盖率图。"""
    w = max(1, sc["out"][0] // scale)
    h = max(1, sc["out"][1] // scale)
    gu = load_grid(os.path.join(set_dir, sc["gridU"]))
    gv = load_grid(os.path.join(set_dir, sc["gridV"]))
    mask = np.asarray(Image.open(os.path.join(set_dir, sc["mask"])).convert("L"),
                      dtype=np.float32) / 255.0
    gh, gw = gu.shape
    # 归一化位置直接乘网格尺寸；不能混用 pad（pad 是全分辨率的）
    fy = ((np.arange(h, dtype=np.float32)[:, None] + 0.5) / h * gh - 0.5)
    fx = ((np.arange(w, dtype=np.float32)[None, :] + 0.5) / w * gw - 0.5)
    shp = (h, w)
    u = bilinear(gu[..., None], np.broadcast_to(fx, shp), np.broadcast_to(fy, shp))[..., 0]
    v = bilinear(gv[..., None], np.broadcast_to(fx, shp), np.broadcast_to(fy, shp))[..., 0]
    aw, ah = art_lin.shape[1], art_lin.shape[0]
    rgb = bilinear(art_lin, u * aw - 0.5, (1.0 - v) * ah - 0.5)
    mx = ((np.arange(w, dtype=np.float32)[None, :] + 0.5) / w * mask.shape[1] - 0.5)
    my = ((np.arange(h, dtype=np.float32)[:, None] + 0.5) / h * mask.shape[0] - 0.5)
    mk = bilinear(mask[..., None], np.broadcast_to(mx, shp), np.broadcast_to(my, shp))[..., 0]
    return to_srgb(rgb * mk[..., None]), mk


def rasterize(v2, depth, uvs, tris, tex, texmask, fb, zb, cov):
    h, w = fb.shape[:2]
    th, tw = tex.shape[:2]
    P, Z, T = v2[tris], depth[tris], uvs[tris]
    for i in range(len(tris)):
        p, z, t = P[i], Z[i], T[i]
        if z.min() <= 1e-6:
            continue
        minx = max(int(np.floor(p[:, 0].min())), 0)
        maxx = min(int(np.ceil(p[:, 0].max())), w - 1)
        miny = max(int(np.floor(p[:, 1].min())), 0)
        maxy = min(int(np.ceil(p[:, 1].max())), h - 1)
        if minx > maxx or miny > maxy:
            continue
        xs = np.arange(minx, maxx + 1) + 0.5
        ys = np.arange(miny, maxy + 1) + 0.5
        X, Y = np.meshgrid(xs, ys)
        (x0, y0), (x1, y1), (x2, y2) = p
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-12:
            continue
        l0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / den
        l1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / den
        l2 = 1.0 - l0 - l1
        inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if not inside.any():
            continue
        iz = l0 / z[0] + l1 / z[1] + l2 / z[2]
        zz = 1.0 / iz
        uu = (l0 * t[0, 0] / z[0] + l1 * t[1, 0] / z[1] + l2 * t[2, 0] / z[2]) * zz
        vv = (l0 * t[0, 1] / z[0] + l1 * t[1, 1] / z[1] + l2 * t[2, 1] / z[2]) * zz
        subz = zb[miny:maxy + 1, minx:maxx + 1]
        m = inside & (zz < subz)
        if not m.any():
            continue
        tx = np.clip((uu * tw).astype(np.int64), 0, tw - 1)
        ty = np.clip((vv * th).astype(np.int64), 0, th - 1)
        fb[miny:maxy + 1, minx:maxx + 1][m] = tex[ty, tx][m]
        cov[miny:maxy + 1, minx:maxx + 1][m] = texmask[ty, tx][m]
        subz[m] = zz[m]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("set_dir")
    ap.add_argument("art")
    ap.add_argument("out_dir")
    ap.add_argument("--frame", default="3000x769")
    ap.add_argument("--panel-scale", type=int, default=1)
    ap.add_argument("--node-prefix", default="QiePing")
    ap.add_argument("--camera", default="cam")
    ap.add_argument("--flip-art", action="store_true",
                    help="反向对照：只把送进切图的素材上下翻转，仍与原始画面比（误差应该明显变大）")
    args = ap.parse_args()

    FW, FH = [int(x) for x in args.frame.lower().split("x")]
    js, bin_ = load_glb(args.glb)
    meta = json.load(open(os.path.join(args.set_dir, "uvset.json"), encoding="utf-8"))
    wm = world_transforms(js)
    cam_i = next(i for i, n in enumerate(js["nodes"])
                 if n.get("camera") is not None and n.get("name") == args.camera)
    m = wm[cam_i]
    R, t = m[:3, :3], m[:3, 3]
    yfov = js["cameras"][js["nodes"][cam_i]["camera"]]["perspective"]["yfov"]
    node_i = {}
    for i, n in enumerate(js["nodes"]):
        if n.get("mesh") is not None and n.get("name", "").startswith(args.node_prefix):
            node_i[n["name"][len(args.node_prefix):]] = i

    art = np.asarray(Image.open(args.art).convert("RGB"))
    if args.flip_art:
        art = art[::-1].copy()
    art_lin = to_linear(art)
    art_small = np.asarray(Image.open(args.art).convert("RGB").resize((FW, FH), Image.LANCZOS),
                           dtype=np.float32)

    fb = np.zeros((FH, FW, 3), dtype=np.uint8)
    zb = np.full((FH, FW), 1e9, dtype=np.float32)
    cov = np.zeros((FH, FW), dtype=np.float32)
    os.makedirs(args.out_dir, exist_ok=True)
    asp = FW / FH

    for sc in meta["screens"]:
        nm = sc["name"]
        ni = node_i[nm]
        pr = js["meshes"][js["nodes"][ni]["mesh"]]["primitives"][0]
        pos = acc(js, bin_, pr["attributes"]["POSITION"])
        uv = acc(js, bin_, pr["attributes"]["TEXCOORD_0"])
        tris = acc(js, bin_, pr["indices"]).astype(np.int64).reshape(-1, 3)
        ph = np.concatenate([pos, np.ones((len(pos), 1))], axis=1)
        pos = (ph @ wm[ni].T)[:, :3]
        panel, pmask = make_panel(art_lin, sc, args.set_dir, args.panel_scale,
                                  int(sc.get("cell", meta.get("cell", 8))))
        Image.fromarray(panel).save(os.path.join(args.out_dir, "split_%s.png" % nm))
        vc = (pos - t) @ R
        depth = -vc[:, 2]
        x = (vc[:, 0] / depth) / (math.tan(yfov / 2) * asp)
        y = (vc[:, 1] / depth) / math.tan(yfov / 2)
        v2 = np.stack([(x * .5 + .5) * FW, (.5 - y * .5) * FH], axis=1)
        rasterize(v2, depth, uv, tris, panel, pmask, fb, zb, cov)
        print("  %s: %d 三角形，贴图 %s" % (nm, len(tris), panel.shape[:2]))

    tag = "flip" if args.flip_art else "audience"
    Image.fromarray(fb).save(os.path.join(args.out_dir, "%s.png" % tag))
    Image.fromarray((np.clip(cov, 0, 1) * 255).astype(np.uint8)).save(
        os.path.join(args.out_dir, "coverage.png"))
    cmp_img = np.zeros((FH, FW * 2 + 8, 3), dtype=np.uint8)
    cmp_img[:, :FW] = art_small.astype(np.uint8)
    cmp_img[:, FW + 8:] = fb
    Image.fromarray(cmp_img).save(os.path.join(args.out_dir, "compare.png"))

    covered = cov > 0.5
    err = np.abs(fb.astype(np.float32) - art_small).max(axis=2)
    print("覆盖像素 %.1f%%" % (100 * covered.mean()))
    if covered.any():
        e = err[covered]
        print("%s vs 原图：平均 %.2f  p50 %.2f  p90 %.2f  p99 %.2f  最大 %.0f (0..255)"
              % (tag, e.mean(), np.percentile(e, 50), np.percentile(e, 90),
                 np.percentile(e, 99), e.max()))
        with open(os.path.join(args.out_dir, "%s_stats.txt" % tag), "w", encoding="utf-8") as fh:
            fh.write("mean=%.4f p50=%.2f p90=%.2f covered=%.4f\n"
                     % (e.mean(), np.percentile(e, 50), np.percentile(e, 90), covered.mean()))


if __name__ == "__main__":
    sys.exit(main())
