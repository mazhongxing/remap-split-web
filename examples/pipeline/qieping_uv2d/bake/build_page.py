# -*- coding: utf-8 -*-
"""把一套 UV 集合的素材内嵌进模板，产出一个独立单文件网页。

一套 UV 集合 → 一个 HTML。换集合就再跑一次这个脚本。

用法： python build_page.py [集合目录] [输出 html 路径]
默认： sets/LangJiu_1014_ABCD  ->  <工程根>/QiePing_UV2D_LangJiu_1014_ABCD.html
"""

import base64
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TEMPLATE = os.path.join(HERE, "page_template.html")
PLACEHOLDER = "/*__UVSET_DATA__*/{ \"name\": \"empty\", \"cell\": 8, \"screens\": [] }"


def data_url(path):
    with open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")


def build(set_dir, out_path):
    meta = json.load(open(os.path.join(set_dir, "uvset.json"), encoding="utf-8"))
    screens = []
    for sc in meta["screens"]:
        gu = os.path.join(set_dir, sc["gridU"])
        gv = os.path.join(set_dir, sc["gridV"])
        mk = os.path.join(set_dir, sc["mask"])
        gw, gh = Image.open(gu).size
        w, h = Image.open(mk).size
        screens.append({
            "name": sc["name"],
            "out": [w, h],
            "grid": [gw, gh],
            "pad": sc.get("pad", [gw * meta.get("cell", 8), gh * meta.get("cell", 8)]),
            "gridUUrl": data_url(gu),
            "gridVUrl": data_url(gv),
            "maskUrl": data_url(mk),
        })
        print("  %s: 输出 %dx%d, 网格 %dx%d" % (sc["name"], w, h, gw, gh))

    payload = {"name": meta["name"], "cell": meta.get("cell", 8), "screens": screens}
    html = open(TEMPLATE, encoding="utf-8").read()
    if PLACEHOLDER not in html:
        raise RuntimeError("模板里的占位符对不上，检查 page_template.html")
    html = html.replace(PLACEHOLDER, json.dumps(payload, separators=(",", ":"), ensure_ascii=True))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("产出 %s (%.2f MB)" % (out_path, os.path.getsize(out_path) / 1e6))


def main():
    set_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "sets", "LangJiu_1014_ABCD")
    name = json.load(open(os.path.join(set_dir, "uvset.json"), encoding="utf-8"))["name"]
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "QiePing_UV2D_%s.html" % name)
    print("构建 %s" % name)
    build(set_dir, out_path)


if __name__ == "__main__":
    main()
