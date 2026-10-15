# -*- coding: utf-8 -*-
"""把 assets/ 里的映射素材内嵌进 page_template.html，产出单文件网页。

用法： python build_page.py
产出： <工程根>/QiePing_WebTool.html
"""

import base64
import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
OUT = os.path.abspath(os.path.join(HERE, "..", "QiePing_WebTool.html"))
TEMPLATE = os.path.join(HERE, "page_template.html")

SCREENS = ("A", "B", "D", "F")
CELL = 8
PLACEHOLDER = "/*__ASSET_DATA__*/{}"


def data_url(path):
    with open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")


def main():
    payload = {}
    for s in SCREENS:
        gu_path = os.path.join(ASSETS, "gridU_%s.png" % s)
        gv_path = os.path.join(ASSETS, "gridV_%s.png" % s)
        mask_path = os.path.join(ASSETS, "mask_%s.png" % s)
        gw, gh = Image.open(gu_path).size
        w, h = Image.open(mask_path).size
        payload[s] = {
            "out": [w, h],
            "gridSize": [gw, gh],
            "pad": [gw * CELL, gh * CELL],
            "gridUUrl": data_url(gu_path),
            "gridVUrl": data_url(gv_path),
            "maskUrl": data_url(mask_path),
        }
        print("%s: out %dx%d, grid %dx%d" % (s, w, h, gw, gh))

    with open(TEMPLATE, "r", encoding="utf-8") as fh:
        html = fh.read()
    if PLACEHOLDER not in html:
        raise RuntimeError("template placeholder missing")

    js = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    html = html.replace(PLACEHOLDER, js)

    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("wrote %s (%.2f MB)" % (OUT, os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
