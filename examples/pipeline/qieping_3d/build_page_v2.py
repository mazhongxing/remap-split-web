# -*- coding: utf-8 -*-
"""把 UV 集合的 2D 素材 + 精简好的场景 GLB 内嵌进模板，产出 2.0 单文件网页。

用法：
    python build_page_v2.py [UV集合目录] [场景目录] [输出html] [--tex-max 4096]

默认（本机布局）：
    UV集合目录 = D:\\codex\\Nuke插件\\qieping_uv2d\\sets\\LangJiu_1014_ABCD   （只读）
    场景目录   = D:\\codex\\Nuke插件\\qieping_3d\\scene
    输出       = D:\\codex\\Nuke插件\\qieping_3d\\dist\\QiePing_3D_<集合名>.html

只读源素材，不写回 qieping_uv2d。
"""

import argparse
import base64
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))          # qieping_3d
DEFAULT_SET = os.path.abspath(os.path.join(ROOT, "..", "qieping_uv2d", "sets", "LangJiu_1014_ABCD"))
DEFAULT_SCENE = os.path.join(ROOT, "scene")
TEMPLATE = os.path.join(HERE, "page_template_v2.html")
PLACEHOLDER = '/*__UVSET_DATA__*/{ "name": "empty", "cell": 8, "screens": [], "scene": null }'


def data_url(path, mime):
    with open(path, "rb") as fh:
        return "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode("ascii"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set_dir", nargs="?", default=DEFAULT_SET)
    ap.add_argument("scene_dir", nargs="?", default=DEFAULT_SCENE)
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--tex-max", type=int, default=4096, help="3D 视口贴图的长边上限")
    ap.add_argument("--camera", default="cam", help="场景里的观众相机节点名")
    ap.add_argument("--node-prefix", default="QiePing")
    args = ap.parse_args()

    meta = json.load(open(os.path.join(args.set_dir, "uvset.json"), encoding="utf-8"))
    name = meta["name"]
    out_path = args.out or os.path.join(ROOT, "dist", "QiePing_3D_%s.html" % name)

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
    glb = os.path.join(args.scene_dir, "scene.glb")
    if os.path.exists(glb):
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
    html = open(TEMPLATE, encoding="utf-8").read()
    if PLACEHOLDER not in html:
        raise SystemExit("模板里的占位符对不上，检查 page_template_v2.html")
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
