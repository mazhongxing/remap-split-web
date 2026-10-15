# -*- coding: utf-8 -*-
"""把成品网页丢进无头 Edge 真跑一遍，验证 WebGL 那条路和 Python 复算一致。

做法：
  1. 起一个本地小服务，目录里放成品网页 + 一张测试素材；
  2. 服务出去的那份网页在末尾多注入一段“自动测试”脚本（成品本身不动），
     它模拟拖拽放入素材、点生成、再把四张 PNG POST 回来；
  3. 用 Nuke 渲出来的同一张素材的成片做对照，报误差。

用法： python webtest.py [素材图] [对照目录]
"""

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

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.abspath(os.path.join(HERE, "..", "QiePing_WebTool.html"))

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

DEFAULT_ART = ("W:/2026/20260701_LangJiu_ShanGuGuangYingXiu/comp/QiePingSuCai/1004/C/001.jpg")
DEFAULT_REF = "D:/codex/_qieping_bake/ref1004C"
SCREENS = ("A", "B", "D", "F")

AUTO = """
<script>
(async () => {
  const say = (t) => { document.title = t; console.log(t); };
  try {
    say("BOOT");
    const blob = await (await fetch("/art.png")).blob();
    const file = new File([blob], "art.png", { type: "image/png" });
    const dt = new DataTransfer();
    dt.items.add(file);
    const drop = document.getElementById("drop");
    drop.dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
    for (let i = 0; i < 200 && document.getElementById("run").disabled; i++) await new Promise(r => setTimeout(r, 100));
    say("READY");
    document.getElementById("run").click();
    for (let i = 0; i < 1200; i++) {
      if (document.querySelectorAll(".shot img").length === 4) break;
      await new Promise(r => setTimeout(r, 250));
    }
    const imgs = document.querySelectorAll(".shot img");
    if (imgs.length !== 4) { say("FAIL:only " + imgs.length + " images"); return; }
    const names = ["A", "B", "D", "F"];
    for (let i = 0; i < 4; i++) {
      const b = await (await fetch(imgs[i].src)).blob();
      await fetch("/upload/" + names[i], { method: "POST", body: b });
    }
    for (let i = 0; i < 4; i++) {
      const b = await (await fetch(imgs[i].src)).blob();
      await fetch("/upload/" + names[i], { method: "POST", body: b });
    }
    const files = [];
    for (let i = 0; i < 4; i++) {
      const b = await (await fetch(imgs[i].src)).blob();
      files.push({ name: names[i] + ".png", data: new Uint8Array(await b.arrayBuffer()) });
    }
    await fetch("/upload/zip", { method: "POST", body: buildZip(files) });
    say("DONE");
  } catch (e) {
    say("FAIL:" + e.message);
  }
})();
</script>
"""


def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("msedge.exe not found")


class Handler(http.server.SimpleHTTPRequestHandler):
    uploads = None
    done = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        if not self.path.startswith("/upload/"):
            self.send_error(404)
            return
        name = self.path.rsplit("/", 1)[1]
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n)
        ext = ".zip" if name == "zip" else ".png"
        with open(os.path.join(self.uploads, name + ext), "wb") as fh:
            fh.write(body)
        print("[webtest] got %s%s (%d bytes)" % (name, ext, len(body)))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")
        if name == "zip":
            self.done.set()


def stats(rec_path, ref_path):
    a = np.asarray(Image.open(rec_path).convert("RGB"), dtype=np.float32)
    b = np.asarray(Image.open(ref_path).convert("RGB"), dtype=np.float32)
    if a.shape != b.shape:
        return None
    d = np.abs(a - b).max(axis=2)
    return dict(mean=float(d.mean()), p90=float(np.percentile(d, 90)),
                mx=float(d.max()), gt2=float((d > 2).mean() * 100.0))


def main():
    art = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ART
    ref_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_REF
    if not os.path.exists(art):
        raise RuntimeError("missing artwork: %s" % art)

    work = tempfile.mkdtemp(prefix="qieping_webtest_")
    uploads = os.path.join(work, "uploads")
    os.makedirs(uploads)

    with open(TOOL, "r", encoding="utf-8") as fh:
        html = fh.read()
    with open(os.path.join(work, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html.replace("</body>", AUTO + "</body>"))
    shutil.copyfile(art, os.path.join(work, "art.png"))

    done = threading.Event()
    Handler.uploads = uploads
    Handler.done = done
    httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Handler, directory=work))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print("[webtest] serving on http://127.0.0.1:%d/" % port)

    edge = find_edge()
    ndir = os.path.join(work, "edgeprofile")
    cmd = [
        edge, "--headless=new", "--no-first-run", "--no-default-browser-check",
        "--disable-extensions", "--mute-audio",
        "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        "--user-data-dir=" + ndir,
        "--window-size=1280,900",
        "http://127.0.0.1:%d/index.html" % port,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    t0 = time.time()
    ok = done.wait(timeout=300)
    print("[webtest] uploads complete=%s after %.1fs" % (ok, time.time() - t0))
    proc.terminate()
    httpd.shutdown()

    if not ok:
        raise RuntimeError("browser did not deliver results")

    import zipfile
    zpath = os.path.join(uploads, "zip.zip")
    with zipfile.ZipFile(zpath) as zf:
        bad = zf.testzip()
        print("   zip: %d entries, testzip=%s, names=%s"
              % (len(zf.namelist()), bad, zf.namelist()))
        for n in zf.namelist():
            Image.open(zf.open(n)).verify()

    worst = 0.0
    for s in SCREENS:
        rp = os.path.join(uploads, s + ".png")
        ref = os.path.join(ref_dir, s + ".png")
        if not os.path.exists(ref):
            print("   %s: no reference at %s" % (s, ref))
            continue
        st = stats(rp, ref)
        if st is None:
            print("   %s: size mismatch" % s)
            continue
        worst = max(worst, st["mean"])
        print("   %s%-1s web-vs-nuke: mean=%.3f p90=%.2f max=%.0f >2:%.2f%%  (%s)"
              % ("OK " if st["mean"] <= 2.0 else "!! ", s, st["mean"], st["p90"], st["mx"],
                 st["gt2"], os.path.basename(Image.open(rp).filename)))
    print("PASS" if worst <= 2.0 else "CHECK", "worst mean =", round(worst, 3))


if __name__ == "__main__":
    main()
