# -*- coding: utf-8 -*-
"""把坐标集合的 2D 素材 + 精简好的场景 GLB 内嵌进模板，产出带 3D 预览的单文件网页。

用法：
    python build_page_v2.py <集合目录> [场景目录] [输出html] [--template x.html]
                            [--tex-max 4096] [--camera cam] [--node-prefix QiePing]

默认用技能自带的 ../assets/page_template_v2.html；
场景目录里放 scene.glb（由 glb_web.py 产出），没有就出一版没有 3D 预览的网页。

只读源素材，不写回集合目录。
"""

import argparse
import base64
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.abspath(os.path.join(HERE, "..", "assets", "page_template_v2.html"))
PLACEHOLDER = '/*__UVSET_DATA__*/{ "name": "empty", "cell": 8, "screens": [], "scene": null }'


def data_url(path, mime):
    with open(path, "rb") as fh:
        return "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode("ascii"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set_dir")
    ap.add_argument("scene_dir", nargs="?", default=None)
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    ap.add_argument("--tex-max", type=int, default=4096, help="3D 视口贴图的长边上限")
    ap.add_argument("--camera", default="cam", help="场景里的观众相机节点名")
    ap.add_argument("--node-prefix", default="QiePing")
    args = ap.parse_args()

    meta = json.load(open(os.path.join(args.set_dir, "uvset.json"), encoding="utf-8"))
    name = meta["name"]
    out_path = args.out or os.path.abspath("%s_3D.html" % name)

    screens = []
    for sc in meta["screens"]:
        gu = os.path.join(args.set_dir, sc["gridU"])
        gv = os.path.join(args.set_dir, sc["gridV"])
        mk = os.path.join(args.set_dir, sc["mask"])
        gw, gh = Image.open(gu).size
        w, h = Image.open(mk).size
        screens.append({
            "name": sc["name"],
            "out": [w, h],
            "grid": [gw, gh],
            "pad": sc.get("pad", [gw * meta.get("cell", 8), gh * meta.get("cell", 8)]),
            "gridUUrl": data_url(gu, "image/png"),
            "gridVUrl": data_url(gv, "image/png"),
            "maskUrl": data_url(mk, "image/png"),
        })
        print("  %s: 输出 %dx%d, 网格 %dx%d" % (sc["name"], w, h, gw, gh))

    scene = None
    glb = os.path.join(args.scene_dir, "scene.glb") if args.scene_dir else None
    if glb and os.path.exists(glb):
        scene = {
            "url": data_url(glb, "model/gltf-binary"),
            "camera": args.camera,
            "screens": {s["name"]: "%s%s" % (args.node_prefix, s["name"]) for s in meta["screens"]},
            "frame": [6000, 1538],
            "texMax": args.tex_max,
        }
        print("  场景 %s (%.2f MB)" % (glb, os.path.getsize(glb) / 1e6))
    else:
        print("  !! 找不到 %s，这一版网页不会有 3D 预览" % glb)

    payload = {"name": name, "cell": meta.get("cell", 8), "screens": screens, "scene": scene}
    html = open(args.template, encoding="utf-8").read()
    if PLACEHOLDER not in html:
        raise SystemExit("模板 %s 里找不到占位符" % args.template)
    html = html.replace(PLACEHOLDER, json.dumps(payload, separators=(",", ":"), ensure_ascii=True))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    mb = os.path.getsize(out_path) / 1e6
    print("产出 %s (%.2f MB)" % (out_path, mb))
    if mb > 8:
        print("  提示：超过 8 MB 了，考虑调小 --tex-max 或把网格抽稀")


if __name__ == "__main__":
    sys.exit(main())
