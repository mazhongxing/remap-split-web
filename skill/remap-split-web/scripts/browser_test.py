# -*- coding: utf-8 -*-
"""把成品网页丢进无头 Edge 真跑一遍，和 DCC 成片逐像素比。

两种打开方式都要过（用户双击走的是 file://，和 http 的限制不同）：
    python browser_test.py --mode http --tool X.html --art art.jpg --ref <对照目录> --screens A,B,D,F
    python browser_test.py --mode file --tool X.html --art art.jpg --ref <对照目录> --screens A,B,D,F

对照目录里放 <路名>.png。

做法：给网页注入一段"自动测试"脚本（成品本身不动）——模拟拖入素材、点生成，
再把每路 PNG POST 回来比对。
"""

import argparse
import base64
import functools
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
from PIL import Image

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

MEAN_LIMIT = 2.0
P90_LIMIT = 6.0


class Handler(http.server.SimpleHTTPRequestHandler):
    uploads = None
    done = None
    cors = False
    expected = 4

    def log_message(self, *a):
        pass

    def _hdr(self):
        if self.cors:
            self.send_header("Access-Control-Allow-Origin", "*")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        name = self.path.rsplit("/", 1)[1]
        n = int(self.headers.get("Content-Length", "0"))
        with open(os.path.join(self.uploads, name + ".png"), "wb") as fh:
            fh.write(self.rfile.read(n))
        self.send_response(200)
        self._hdr()
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")
        if len([f for f in os.listdir(self.uploads) if f.endswith(".png")]) >= self.expected:
            self.done.set()


AUTO_HTTP = """
<script>
(async () => {
  try {
    const blob = await (await fetch("/art.png")).blob();
    const file = new File([blob], "art.png", { type: "image/png" });
    const dt = new DataTransfer(); dt.items.add(file);
    document.getElementById("drop").dispatchEvent(new DragEvent("drop", {dataTransfer: dt, bubbles:true, cancelable:true}));
    for (let i = 0; i < 300 && document.getElementById("run").disabled; i++) await new Promise(r => setTimeout(r, 100));
    document.getElementById("run").click();
    for (let i = 0; i < 2000; i++) {
      if (document.querySelectorAll(".shot img").length === __N__) break;
      await new Promise(r => setTimeout(r, 250));
    }
    const imgs = document.querySelectorAll(".shot img");
    if (imgs.length !== __N__) { document.title = "FAIL:only " + imgs.length; return; }
    const names = __NAMES__;
    for (let i = 0; i < names.length; i++) {
      const b = await (await fetch(imgs[i].src)).blob();
      await fetch("/upload/" + names[i], { method: "POST", body: b });
    }
    document.title = "DONE";
  } catch (e) { document.title = "FAIL:" + e.message; }
})();
</script>
"""

AUTO_FILE = """
<script>
(async () => {
  const POST = "__POST__";
  try {
    const src = new Image(); src.src = "__ART__"; await src.decode();
    const cv = document.createElement("canvas");
    cv.width = src.naturalWidth; cv.height = src.naturalHeight;
    cv.getContext("2d").drawImage(src, 0, 0);
    const blob = await new Promise((r) => cv.toBlob(r, "image/png"));
    const file = new File([blob], "art.png", { type: "image/png" });
    const dt = new DataTransfer(); dt.items.add(file);
    document.getElementById("drop").dispatchEvent(new DragEvent("drop", {dataTransfer: dt, bubbles:true, cancelable:true}));
    for (let i = 0; i < 300 && document.getElementById("run").disabled; i++) await new Promise(r => setTimeout(r, 100));
    document.getElementById("run").click();
    for (let i = 0; i < 2000; i++) {
      if (document.querySelectorAll(".shot img").length === __N__) break;
      await new Promise(r => setTimeout(r, 250));
    }
    const imgs = document.querySelectorAll(".shot img");
    if (imgs.length !== __N__) { document.title = "FAIL:" + imgs.length; return; }
    const names = __NAMES__;
    for (let i = 0; i < names.length; i++) {
      const bytes = await new Promise((r) => {
        const x = new XMLHttpRequest();
        x.open("GET", imgs[i].src, true);
        x.responseType = "blob";
        x.onload = () => {
          const fr = new FileReader();
          fr.onload = () => r(new Uint8Array(fr.result));
          fr.readAsArrayBuffer(x.response);
        };
        x.send();
      });
      await fetch(POST + "/upload/" + names[i], { method: "POST", body: bytes });
    }
    document.title = "DONE";
  } catch (e) { document.title = "FAIL:" + e.message; }
})();
</script>
"""


def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("找不到 msedge.exe")


def stats(rec_path, ref_path):
    a = np.asarray(Image.open(rec_path).convert("RGB"), dtype=np.float32)
    b = np.asarray(Image.open(ref_path).convert("RGB"), dtype=np.float32)
    if a.shape != b.shape:
        return None
    d = np.abs(a - b).max(axis=2)
    return dict(mean=float(d.mean()), p50=float(np.percentile(d, 50)),
                p90=float(np.percentile(d, 90)), mx=float(d.max()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("http", "file"), default="file")
    ap.add_argument("--tool", required=True, help="成品 html")
    ap.add_argument("--art", required=True, help="测试素材图")
    ap.add_argument("--ref", required=True, help="对照目录，里面放 <路名>.png")
    ap.add_argument("--screens", default="A,B,D,F")
    args = ap.parse_args()

    screens = [s.strip() for s in args.screens.split(",") if s.strip()]
    names_js = "[" + ",".join('"%s"' % s for s in screens) + "]"

    work = tempfile.mkdtemp(prefix="remap_split_webtest_")
    uploads = os.path.join(work, "uploads")
    os.makedirs(uploads)
    art_png = os.path.join(work, "art.png")
    Image.open(args.art).convert("RGB").save(art_png, optimize=True)

    html = open(args.tool, encoding="utf-8").read()
    Handler.uploads = uploads
    Handler.done = threading.Event()
    Handler.cors = (args.mode == "file")
    Handler.expected = len(screens)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Handler, directory=work))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    if args.mode == "http":
        inject = AUTO_HTTP.replace("__N__", str(len(screens))).replace("__NAMES__", names_js)
        page = os.path.join(work, "index.html")
        open(page, "w", encoding="utf-8").write(html.replace("</body>", inject + "</body>"))
        url = "http://127.0.0.1:%d/index.html" % port
    else:
        with open(art_png, "rb") as fh:
            art_url = "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")
        inject = (AUTO_FILE.replace("__POST__", "http://127.0.0.1:%d" % port)
                  .replace("__ART__", art_url).replace("__N__", str(len(screens)))
                  .replace("__NAMES__", names_js))
        page = os.path.join(work, "tool.html")
        open(page, "w", encoding="utf-8").write(html.replace("</body>", inject + "</body>"))
        url = "file:///" + page.replace("\\", "/")

    print("[browser] %s 打开 %s" % (args.mode, os.path.basename(args.tool)))
    proc = subprocess.Popen(
        [find_edge(), "--headless=new", "--no-first-run", "--no-default-browser-check",
         "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--allow-file-access-from-files",
         "--user-data-dir=" + os.path.join(work, "prof"), url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    t0 = time.time()
    ok = Handler.done.wait(timeout=420)
    proc.terminate()
    httpd.shutdown()
    print("[browser] 收到 %d 路，用时 %.1fs"
          % (len([f for f in os.listdir(uploads) if f.endswith(".png")]), time.time() - t0))
    if not ok:
        raise RuntimeError("浏览器没有回传全部结果")

    worst = 0.0
    for s in screens:
        rp = os.path.join(uploads, s + ".png")
        ref = os.path.join(args.ref, s + ".png")
        if not os.path.exists(ref):
            print("   %s: 缺对照 %s" % (s, ref))
            continue
        st = stats(rp, ref)
        if st is None:
            print("   %s: 尺寸对不上" % s)
            continue
        worst = max(worst, st["mean"])
        ok = st["mean"] <= MEAN_LIMIT and st["p90"] <= P90_LIMIT
        print("   %s%-1s 网页 vs DCC: 平均=%.3f p50=%.2f p90=%.2f max=%.0f  %s"
              % ("OK " if ok else "!! ", s, st["mean"], st["p50"], st["p90"], st["mx"],
                 "OK" if ok else "超阈值"))
    print("PASS" if worst <= MEAN_LIMIT else "FAIL", "最差平均 =", round(worst, 3))
    sys.exit(0 if worst <= MEAN_LIMIT else 1)


if __name__ == "__main__":
    main()
