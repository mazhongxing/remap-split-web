# -*- coding: utf-8 -*-
"""用无头 Edge 给成品网页拍一张整页截图（自动投图 → 生成 → 3D 视口切到指定视角）。

用法：
    python shot_page.py <成品html> <素材图> <输出png> [--view audience|orbit|free]
                        [--size 1600x2000] [--wait 25]

纯粹是给人看的验收图，不参与判定。
"""

import argparse
import functools
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading

from PIL import Image

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

AUTO = """
<script>
(async () => {
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  try {
    const blob = await (await fetch("/art.png")).blob();
    const file = new File([blob], "art.png", { type: "image/png" });
    const dt = new DataTransfer(); dt.items.add(file);
    document.getElementById("drop").dispatchEvent(new DragEvent("drop", {
      dataTransfer: dt, bubbles: true, cancelable: true }));
    for (let i = 0; i < 600 && document.getElementById("run").disabled; i++) await wait(100);
    document.getElementById("run").click();
    for (let i = 0; i < 2400; i++) {
      if (document.querySelectorAll(".shot img").length >= 4) break;
      await wait(250);
    }
    await wait(1000);
    if (typeof V3D !== "undefined" && V3D.ready) {
      const view = "__VIEW__";
      if (view === "orbit") {
        setOrbitFromEye(cameraEye(), V3D.center.ctr);
        V3D.mode = "free";
        V3D.orbit.yaw += 0.62; V3D.orbit.pitch = Math.max(V3D.orbit.pitch, 0.22);
        V3D.orbit.dist *= 1.15;
      } else if (view === "free") {
        setOrbitFromEye(cameraEye(), V3D.center.ctr);
        V3D.mode = "free";
        V3D.orbit.yaw -= 0.5; V3D.orbit.dist *= 1.9;
      }
      syncMode(); resize3D(); draw3D();
    }
    await wait(1200);
    document.title = "SHOT_READY";
  } catch (e) { document.title = "SHOT_FAIL:" + e.message; }
})();
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tool")
    ap.add_argument("art")
    ap.add_argument("out")
    ap.add_argument("--view", default="orbit", choices=("audience", "orbit", "free"))
    ap.add_argument("--size", default="1600x2000")
    ap.add_argument("--wait", type=int, default=25, help="virtual-time-budget（秒）")
    args = ap.parse_args()

    w, h = [int(x) for x in args.size.lower().split("x")]
    work = tempfile.mkdtemp(prefix="qieping_shot_")
    Image.open(args.art).convert("RGB").save(os.path.join(work, "art.png"), optimize=True)
    html = open(args.tool, encoding="utf-8").read()
    inject = AUTO.replace("__VIEW__", args.view)
    open(os.path.join(work, "index.html"), "w", encoding="utf-8").write(
        html.replace("</body>", inject + "</body>"))

    httpd = socketserver.TCPServer(
        ("127.0.0.1", 0),
        functools.partial(http.server.SimpleHTTPRequestHandler, directory=work))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    edge = next((p for p in EDGE_CANDIDATES if os.path.exists(p)), None)
    if not edge:
        raise SystemExit("找不到 msedge.exe")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    subprocess.run([edge, "--headless=new", "--no-first-run", "--no-default-browser-check",
                    "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars",
                    "--window-size=%d,%d" % (w, h),
                    "--virtual-time-budget=%d" % (args.wait * 1000),
                    "--screenshot=" + os.path.abspath(args.out),
                    "--user-data-dir=" + os.path.join(work, "prof"),
                    "http://127.0.0.1:%d/index.html" % port],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    httpd.shutdown()
    shutil.rmtree(work, ignore_errors=True)
    print("截图 %s" % args.out)


if __name__ == "__main__":
    sys.exit(main())
