# -*- coding: utf-8 -*-
"""和 webtest.py 一样的验收，但用 file:// 打开成品网页（平时双击就是这个用法）。

素材以 data URL 内嵌进临时测试页，结果通过 http POST 回本机小服务。
用法： python webtest_file.py [素材图] [对照目录]
"""

import base64
import functools
import http.server
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
# QIEPING_TOOL 可以指定别的成品路径（比如刚解压出来的那份）
TOOL = os.environ.get("QIEPING_TOOL") or os.path.abspath(os.path.join(HERE, "..", "QiePing_WebTool.html"))
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SCREENS = ("A", "B", "D", "F")

DEFAULT_ART = "W:/2026/20260701_LangJiu_ShanGuGuangYingXiu/comp/QiePingSuCai/1004/C/001.jpg"
DEFAULT_REF = "D:/codex/_qieping_bake/ref1004C"


class H(http.server.BaseHTTPRequestHandler):
    uploads = None
    done = None

    def log_message(self, *a):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        name = self.path.rsplit("/", 1)[1]
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n)
        with open(os.path.join(self.uploads, name + ".png"), "wb") as fh:
            fh.write(body)
        print("[filetest] got %s.png (%d bytes)" % (name, len(body)))
        self.send_response(200)
        self._cors()
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")
        if len(os.listdir(self.uploads)) >= 4:
            self.done.set()


AUTO = """
<script>
(async () => {
  const POST = "__POST__";
  try {
    // file:// 下不要依赖 fetch，用 <img> + canvas 把素材变成 File
    const src = new Image();
    src.src = "__ART__";
    await src.decode();
    const cv = document.createElement("canvas");
    cv.width = src.naturalWidth; cv.height = src.naturalHeight;
    cv.getContext("2d").drawImage(src, 0, 0);
    const blob = await new Promise((r) => cv.toBlob(r, "image/png"));
    const file = new File([blob], "art.png", { type: "image/png" });
    const dt = new DataTransfer(); dt.items.add(file);
    document.getElementById("drop").dispatchEvent(new DragEvent("drop", {dataTransfer: dt, bubbles:true, cancelable:true}));
    for (let i = 0; i < 200 && document.getElementById("run").disabled; i++) await new Promise(r => setTimeout(r, 100));
    document.getElementById("run").click();
    for (let i = 0; i < 1200; i++) { if (document.querySelectorAll(".shot img").length === 4) break; await new Promise(r => setTimeout(r, 250)); }
    const imgs = document.querySelectorAll(".shot img");
    if (imgs.length !== 4) { document.title = "FAIL:" + imgs.length; return; }
    const names = ["A","B","D","F"];
    for (let i = 0; i < 4; i++) {
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


def main():
    art = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ART
    ref_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_REF

    work = tempfile.mkdtemp(prefix="qieping_filetest_")
    uploads = os.path.join(work, "uploads")
    os.makedirs(uploads)

    # 素材先转成 PNG data URL（浏览器不需要再猜文件类型）
    art_png = os.path.join(work, "art.png")
    Image.open(art).convert("RGB").save(art_png, optimize=True)
    with open(art_png, "rb") as fh:
        art_url = "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")

    done = threading.Event()
    H.uploads, H.done = uploads, done
    httpd = socketserver.TCPServer(("127.0.0.1", 0), H)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    html = open(TOOL, "r", encoding="utf-8").read()
    inject = AUTO.replace("__POST__", "http://127.0.0.1:%d" % port).replace("__ART__", art_url)
    page = os.path.join(work, "tool.html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(html.replace("</body>", inject + "</body>"))
    print("[filetest] opening file://%s" % page)

    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--no-first-run", "--no-default-browser-check",
         "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
         "--allow-file-access-from-files",
         "--user-data-dir=" + os.path.join(work, "prof"),
         "file:///" + page.replace("\\", "/")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    t0 = time.time()
    ok = done.wait(timeout=300)
    print("[filetest] complete=%s after %.1fs" % (ok, time.time() - t0))
    proc.terminate()
    httpd.shutdown()
    if not ok:
        raise RuntimeError("file:// run did not deliver 4 images")

    worst = 0.0
    for s in SCREENS:
        a = np.asarray(Image.open(os.path.join(uploads, s + ".png")).convert("RGB"), dtype=np.float32)
        b = np.asarray(Image.open(os.path.join(ref_dir, s + ".png")).convert("RGB"), dtype=np.float32)
        d = np.abs(a - b).max(axis=2)
        worst = max(worst, float(d.mean()))
        print("   %s%-1s file-vs-nuke: mean=%.3f p90=%.2f >2:%.2f%%"
              % ("OK " if d.mean() <= 2.0 else "!! ", s, d.mean(),
                 np.percentile(d, 90), (d > 2).mean() * 100))
    print("PASS" if worst <= 2.0 else "CHECK", "worst mean =", round(worst, 3))


if __name__ == "__main__":
    main()
