# -*- coding: utf-8 -*-
"""把一套坐标集合的素材内嵌进模板，产出一个独立单文件网页。

一套集合 → 一个 html。换集合就再跑一次这个脚本。

用法：
    python build_page.py <集合目录> [输出 html] [模板路径]

模板默认用技能自带的 ../assets/page_template.html（相对本脚本）；
想改界面就改模板，不用动这个脚本。
"""

import base64
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.abspath(os.path.join(HERE, "..", "assets", "page_template.html"))

# 模板里的占位符（必须与 page_template.html 完全一致）
PLACEHOLDER = '/*__UVSET_DATA__*/{ "name": "empty", "cell": 8, "screens": [] }'


def data_url(path):
    with open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")


def build(set_dir, out_path, template_path):
    meta = json.load(open(os.path.join(set_dir, "uvset.json"), encoding="utf-8"))
    screens = []
    for sc in meta["screens"]:
        gu = os.path.join(set_dir, sc["gridU"])
        gv = os.path.join(set_dir, sc["gridV"])
        mk = os.path.join(set_dir, sc["mask"])
        for p in (gu, gv, mk):
            if not os.path.exists(p):
                raise RuntimeError("缺素材 %s（先跑 pack_uvset.py）" % p)
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
    html = open(template_path, encoding="utf-8").read()
    if PLACEHOLDER not in html:
        raise RuntimeError("模板 %s 里找不到占位符" % template_path)
    html = html.replace(PLACEHOLDER, json.dumps(payload, separators=(",", ":"), ensure_ascii=True))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("产出 %s (%.2f MB)" % (out_path, os.path.getsize(out_path) / 1e6))


def main():
    if len(sys.argv) < 2:
        raise SystemExit("用法: python build_page.py <集合目录> [输出 html] [模板路径]")
    set_dir = sys.argv[1]
    name = json.load(open(os.path.join(set_dir, "uvset.json"), encoding="utf-8"))["name"]
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.abspath("%s.html" % name)
    template = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_TEMPLATE
    print("构建 %s（模板 %s）" % (name, os.path.basename(template)))
    build(set_dir, out_path, template)


if __name__ == "__main__":
    main()
