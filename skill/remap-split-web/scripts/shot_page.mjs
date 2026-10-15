// 用 CDP 给成品网页拍整页截图：自动投图 → 生成 → 3D 视口切到指定视角 → 截全页。
//
// 用法： node shot_page.mjs <成品html> <素材图> <输出png> [view] [宽x高]
//   view: audience（观众机位，默认） / orbit（环绕展示） / free（拉远的自由视角）
//
// 比 `msedge --screenshot --virtual-time-budget` 可靠：那条路虚拟时钟会抢在
// generateImageBitmap / toBlob 这些真实异步任务前面跑完，截到的是半成品。

import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

const [tool, art, out, view = "audience", size = "1500x1750"] = process.argv.slice(2);
if (!tool || !art || !out) {
  console.error("用法: node shot_page.mjs <html> <素材图> <输出png> [audience|orbit|free] [宽x高]");
  process.exit(2);
}
const [VW, VH] = size.toLowerCase().split("x").map(Number);
const artData = "data:image/png;base64," + readFileSync(art).toString("base64");

const EDGE = [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
].find((p) => { try { readFileSync(p); return true; } catch { return false; } });
if (!EDGE) { console.error("找不到 msedge.exe"); process.exit(2); }

const port = 9200 + Math.floor(Math.random() * 300);
const profile = join(tmpdir(), "qieping_shot_" + randomUUID());
const proc = spawn(EDGE, [
  "--headless=new", "--no-first-run", "--no-default-browser-check",
  "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
  "--allow-file-access-from-files", "--hide-scrollbars",
  `--window-size=${VW || 1500},${VH || 1750}`,
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function targets() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/list`);
      return await r.json();
    } catch { await sleep(250); }
  }
  throw new Error("连不上调试端口");
}

const AUTO = `
(async () => {
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  try {
    const img = new Image(); img.src = ${JSON.stringify(artData)}; await img.decode();
    const cv = document.createElement("canvas");
    cv.width = img.naturalWidth; cv.height = img.naturalHeight;
    cv.getContext("2d").drawImage(img, 0, 0);
    const blob = await new Promise(r => cv.toBlob(r, "image/png"));
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
    for (let i = 0; i < 240 && document.querySelectorAll(".shot img").length < 4; i++) await wait(250);
    await wait(800);
    const view = ${JSON.stringify(view)};
    if (typeof V3D !== "undefined" && V3D.ready) {
      if (view === "orbit") {
        setOrbitFromEye(cameraEye(), V3D.center.ctr);
        V3D.mode = "free"; V3D.orbit.yaw += 0.7;
        V3D.orbit.pitch = 0.28;
        V3D.orbit.dist = V3D.center.rad * 2.35;
      } else if (view === "free") {
        setOrbitFromEye(cameraEye(), V3D.center.ctr);
        V3D.mode = "free"; V3D.orbit.yaw -= 0.5; V3D.orbit.dist = V3D.center.rad * 3.2;
      }
      syncMode(); resize3D(); draw3D();
    }
    await wait(1500);
    document.title = "SHOT_READY";
  } catch (e) { document.title = "SHOT_FAIL:" + (e && e.message ? e.message : e); }
})();`;

async function main() {
  await targets();
  const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = list.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  const send = (method, params = {}) => new Promise((res, rej) => {
    const mid = ++id;
    pending.set(mid, { res, rej });
    ws.send(JSON.stringify({ id: mid, method, params }));
  });
  await new Promise((r) => ws.addEventListener("open", r));
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const p = pending.get(m.id); pending.delete(m.id);
      m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
    }
  });
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.addScriptToEvaluateOnNewDocument", { source: AUTO });
  await send("Page.navigate", { url: pathToFileURL(tool).href });
  let title = "";
  for (let i = 0; i < 240; i++) {
    await sleep(500);
    const r = await send("Runtime.evaluate", { expression: "document.title", returnByValue: true });
    title = r.result.value || "";
    if (title.startsWith("SHOT_READY") || title.startsWith("SHOT_FAIL")) break;
  }
  console.log("页面标题:", title);
  const shot = await send("Page.captureScreenshot", {
    format: "png", captureBeyondViewport: true, fromSurface: true,
  });
  writeFileSync(out, Buffer.from(shot.data, "base64"));
  console.log("截图:", out);
  ws.close();
  if (title.startsWith("SHOT_FAIL")) process.exitCode = 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; })
  .finally(() => { proc.kill(); });
