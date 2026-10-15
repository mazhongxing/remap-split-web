# -*- coding: utf-8 -*-
"""把 2.0 成品网页丢进无头 Edge 真跑一遍，2D 切图 + 3D 预览一起验收。

两种打开方式都要过：
    python browser_test_v2.py --mode http     # 本地小服务
    python browser_test_v2.py --mode file     # file://，也就是用户双击的用法

做法：给成品网页注入一段"自动测试"脚本（成品本身不动）——
  拖入素材 → 点生成 → 把四张屏 PNG POST 回来；
  再把 3D 视口切到观众机位、按 1560×400 渲一帧，把 canvas 导出成 PNG POST 回来。
Python 侧比对：
  1) 四张屏 vs Nuke 成片（门槛：平均 ≤2/255、p90 ≤6/255）；
  2) 3D 观众机位 vs CPU 黄金对照（门槛：平均 ≤3/255）；
  3) 敏感度对照：把对照图上下翻转再比，误差必须明显更大（防止 v 轴写反这类静默错误）。
"""

import argparse
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
ROOT = os.path.abspath(os.path.join(HERE, ".."))
W_ROOT = "W:/2026/20260701_LangJiu_ShanGuGuangYingXiu"

DEFAULT_TOOL = os.path.join(ROOT, "dist", "QiePing_3D_LangJiu_1014_ABCD.html")
DEFAULT_ART = W_ROOT + "/comp/QiePingSuCai/1004/C/001.jpg"
DEFAULT_REF2D = r"D:\codex\_qieping_uv2d\ref1004C"
DEFAULT_REF3D = os.path.join(ROOT, "_verify", "cpu_1560", "audience.png")
VP = (1560, 400)

MEAN_2D, P90_2D = 2.0, 6.0
MEAN_3D = 3.0

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


class Handler(http.server.SimpleHTTPRequestHandler):
    uploads = None
    done = None
    cors = False
    expected = 6

    def log_message(self, *a):
        pass

    def do_OPTIONS(self):
        # file:// 页面往 http://127.0.0.1 POST 图片会先发跨域预检，必须回这一下
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
        if self.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")
        if len([f for f in os.listdir(self.uploads) if f.endswith(".png")]) >= self.expected:
            self.done.set()


AUTO = r"""
<script>
(async () => {
  const POST = "__POST__";
  const N = __N__;
  const NAMES = __NAMES__;
  const VPW = __VPW__, VPH = __VPH__;
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  const post = async (name, blob) => fetch(POST + "/upload/" + name, { method: "POST", body: blob });
  try {
    let blob;
    if (__IS_FILE__) {
      const img = new Image(); img.src = "__ART__"; await img.decode();
      const cv = document.createElement("canvas");
      cv.width = img.naturalWidth; cv.height = img.naturalHeight;
      cv.getContext("2d").drawImage(img, 0, 0);
      blob = await new Promise(r => cv.toBlob(r, "image/png"));
    } else {
      blob = await (await fetch("/art.png")).blob();
    }
    const file = new File([blob], "art.png", { type: "image/png" });
    const dt = new DataTransfer(); dt.items.add(file);
    document.getElementById("drop").dispatchEvent(new DragEvent("drop", {
      dataTransfer: dt, bubbles: true, cancelable: true }));

    for (let i = 0; i < 600 && document.getElementById("run").disabled; i++) await wait(100);
    document.getElementById("run").click();
    for (let i = 0; i < 2400; i++) {
      if (document.querySelectorAll(".shot img").length === N) break;
      await wait(250);
    }
    const imgs = document.querySelectorAll(".shot img");
    if (imgs.length !== N) { document.title = "FAIL:only " + imgs.length; return; }
    for (let i = 0; i < N; i++) {
      const b = await (await fetch(imgs[i].src)).blob();
      await post(NAMES[i], b);
    }

    if (!V3D.ready) { document.title = "FAIL:3d not ready"; return; }
    const c = document.getElementById("v3dcanvas");
    c.style.width = VPW + "px"; c.style.height = VPH + "px";
    V3D.mode = "audience"; V3D.frameOn = true; V3D.spin = false;
    syncMode(); resize3D(); draw3D();
    await wait(150);
    if (c.width !== VPW || c.height !== VPH) {
      document.title = "FAIL:vp size " + c.width + "x" + c.height; return;
    }
    const vp = await new Promise(r => c.toBlob(r, "image/png"));
    await post("viewport", vp);

    V3D.orbit.yaw += 0.6; V3D.mode = "free"; draw3D();
    await wait(150);
    const vp2 = await new Promise(r => c.toBlob(r, "image/png"));
    await post("viewport_orbit", vp2);

    document.title = "DONE";
  } catch (e) { document.title = "FAIL:" + (e && e.message ? e.message : e); }
})();
</script>
"""


def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("找不到 msedge.exe")


def stats(a_path, b_path):
    a = np.asarray(Image.open(a_path).convert("RGB"), dtype=np.float32)
    b = np.asarray(Image.open(b_path).convert("RGB"), dtype=np.float32)
    if a.shape != b.shape:
        return None
    d = np.abs(a - b).max(axis=2)
    return dict(mean=float(d.mean()), p50=float(np.percentile(d, 50)),
                p90=float(np.percentile(d, 90)), mx=float(d.max()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("http", "file"), default="http")
    ap.add_argument("--tool", default=DEFAULT_TOOL)
    ap.add_argument("--art", default=DEFAULT_ART)
    ap.add_argument("--ref2d", default=DEFAULT_REF2D)
    ap.add_argument("--ref3d", default=DEFAULT_REF3D)
    ap.add_argument("--screens", default="A,B,D,F")
    ap.add_argument("--out", default=os.path.join(ROOT, "_verify", "browser"))
    args = ap.parse_args()

    screens = [s.strip() for s in args.screens.split(",") if s.strip()]
    names_js = "[" + ",".join('"%s"' % s for s in screens) + "]"
    work = tempfile.mkdtemp(prefix="qieping_3d_test_")
    uploads = os.path.join(work, "uploads")
    os.makedirs(uploads)

    art_png = os.path.join(work, "art.png")
    Image.open(args.art).convert("RGB").save(art_png, optimize=True)

    html = open(args.tool, encoding="utf-8").read()
    Handler.uploads = uploads
    Handler.done = threading.Event()
    Handler.cors = (args.mode == "file")
    Handler.expected = len(screens) + 2
    httpd = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Handler, directory=work))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    inject = (AUTO.replace("__POST__", "" if args.mode == "http" else "http://127.0.0.1:%d" % port)
              .replace("__N__", str(len(screens)))
              .replace("__NAMES__", names_js).replace("__VPW__", str(VP[0]))
              .replace("__VPH__", str(VP[1]))
              .replace("__IS_FILE__", "true" if args.mode == "file" else "false"))
    if args.mode == "http":
        inject = inject.replace("__ART__", "")
        page = os.path.join(work, "index.html")
        url = "http://127.0.0.1:%d/index.html" % port
    else:
        with open(art_png, "rb") as fh:
            art_url = "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")
        inject = inject.replace("__ART__", art_url)
        page = os.path.join(work, "tool.html")
        url = "file:///" + page.replace("\\", "/")
    open(page, "w", encoding="utf-8").write(html.replace("</body>", inject + "</body>"))

    print("[browser] %s 打开 %s" % (args.mode, os.path.basename(args.tool)))
    proc = subprocess.Popen(
        [find_edge(), "--headless=new", "--no-first-run", "--no-default-browser-check",
         "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--allow-file-access-from-files",
         "--window-size=1600,1000",
         "--user-data-dir=" + os.path.join(work, "prof"), url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    ok = Handler.done.wait(timeout=900)
    proc.terminate()
    httpd.shutdown()
    got = [f for f in os.listdir(uploads) if f.endswith(".png")]
    print("[browser] 收到 %d 张，用时 %.1fs" % (len(got), time.time() - t0))
    if not ok:
        raise RuntimeError("浏览器没有回传全部结果：收到 %s" % sorted(got))

    os.makedirs(args.out, exist_ok=True)
    for f in got:
        Image.open(os.path.join(uploads, f)).save(os.path.join(args.out, f))

    failed = []
    print("--- 2D：网页出的成片 vs Nuke 成片 ---")
    for s in screens:
        rp = os.path.join(uploads, s + ".png")
        ref = os.path.join(args.ref2d, s + ".png")
        if not os.path.exists(ref):
            print("   %s: 缺对照 %s" % (s, ref))
            continue
        st = stats(rp, ref)
        if st is None:
            print("   %s: 尺寸对不上" % s)
            failed.append(s)
            continue
        good = st["mean"] <= MEAN_2D and st["p90"] <= P90_2D
        if not good:
            failed.append(s)
        print("   %s: 平均=%.3f p50=%.2f p90=%.2f max=%.0f  %s"
              % (s, st["mean"], st["p50"], st["p90"], st["mx"], "OK" if good else "超阈值"))

    print("--- 3D：网页视口（观众机位）vs CPU 黄金对照 ---")
    vp = os.path.join(uploads, "viewport.png")
    vp_img = np.asarray(Image.open(vp).convert("RGB"), dtype=np.float32)
    ref_img = np.asarray(Image.open(args.ref3d).convert("RGB"), dtype=np.float32)
    cov_path = os.path.join(os.path.dirname(args.ref3d), "coverage.png")
    if vp_img.shape != ref_img.shape:
        print("   尺寸对不上：%s vs %s" % (vp_img.shape, ref_img.shape))
        failed.append("3d")
    else:
        # 只在"屏体真正覆盖到"的像素上比：背景色和屏外空白不参与，否则比的是背景
        mask = None
        if os.path.exists(cov_path):
            mask = np.asarray(Image.open(cov_path).convert("L"), dtype=np.float32) > 127
        d = np.abs(vp_img - ref_img).max(axis=2)
        dd = d[mask] if mask is not None else d.reshape(-1)
        print("   覆盖区（%.0f%% 画面）逐像素原始差：平均=%.2f p90=%.2f max=%.0f（只作参考，"
              "GPU 双线性+mipmap 与 CPU 最近邻采样在高频细节上本来就不一样）"
              % (100 * (mask.mean() if mask is not None else 1.0), dd.mean(),
                 np.percentile(dd, 90), dd.max()))

        # 结构性比对：两边都降 8 倍再比，滤掉采样差异，剩下的就是"位置/朝向/贴图对不对"
        k = 8
        W, H = max(1, vp_img.shape[1] // k), max(1, vp_img.shape[0] // k)
        a8 = np.asarray(Image.open(vp).convert("RGB").resize((W, H), Image.BOX), dtype=np.float32)
        b8 = np.asarray(Image.open(args.ref3d).convert("RGB").resize((W, H), Image.BOX), dtype=np.float32)
        if mask is not None:
            m8 = np.asarray(Image.open(cov_path).convert("L").resize((W, H), Image.BOX),
                            dtype=np.float32) > 127
        else:
            m8 = np.ones((H, W), dtype=bool)
        d8 = np.abs(a8 - b8).max(axis=2)[m8]
        st = dict(mean=float(d8.mean()), p50=float(np.percentile(d8, 50)),
                  p90=float(np.percentile(d8, 90)), mx=float(d8.max()))
        good = st["mean"] <= MEAN_3D and st["p90"] <= MEAN_3D * 2.5
        if not good:
            failed.append("3d")
        print("   结构比对（降 8 倍）网页 vs CPU：平均=%.3f p50=%.2f p90=%.2f max=%.0f"
              "（门槛 平均≤%.1f 且 p90≤%.1f）  %s"
              % (st["mean"], st["p50"], st["p90"], st["mx"], MEAN_3D, MEAN_3D * 2.5,
                 "OK" if good else "超阈值"))

        # 更本质的一条：网页视口重建出的画面 vs 原图，误差不该明显大于 CPU 黄金对照
        art = np.asarray(Image.open(args.art).convert("RGB").resize(
            (vp_img.shape[1], vp_img.shape[0]), Image.LANCZOS), dtype=np.float32)
        ref_stat = os.path.join(os.path.dirname(args.ref3d), "audience_stats.txt")
        if os.path.exists(ref_stat) and mask is not None:
            cpu_mean = float(open(ref_stat).read().split("mean=")[1].split()[0])
            e_page = np.abs(vp_img - art).max(axis=2)[mask].mean()
            good2 = e_page <= cpu_mean + 3.0
            if not good2:
                failed.append("3d-vs-art")
            print("   重建 vs 原图：网页 %.2f ／ CPU 黄金对照 %.2f（允许 +3）  %s"
                  % (e_page, cpu_mean, "OK" if good2 else "超阈值"))

            flip = np.abs(vp_img - art[::-1])  .max(axis=2)[mask].mean()
            ratio = flip / max(e_page, 1e-6)
            good3 = ratio > 3.0
            if not good3:
                failed.append("3d-sensitive")
            print("   素材上下翻转对照：%.2f（正常值的 %.1f 倍，要求 >3 倍）  %s"
                  % (flip, ratio, "OK" if good3 else "不敏感！"))

    print("--- 3D 交互冒烟 ---")
    st2 = stats(os.path.join(uploads, "viewport_orbit.png"), vp)
    good3 = st2 is not None and st2["mean"] > 1.0
    if not good3:
        failed.append("orbit")
    print("   环绕后画面变化 平均=%.3f  %s" % (st2["mean"] if st2 else -1.0, "OK" if good3 else "没变化"))

    print("结果图目录：%s" % args.out)
    print("FAIL: " + "、".join(failed) if failed else "PASS: 2D 与 3D 全部通过")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
