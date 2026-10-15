# -*- coding: utf-8 -*-
"""把场景 GLB 精简 + 量化成网页能直接内嵌的小 GLB（scene.glb）。

做什么：
  1. 校验：读场景图、列出所有节点、检查每块屏有 POSITION/TEXCOORD_0、检查观众相机存在；
  2. 精简：丢掉场景里不可达的孤立节点（Houdini 常导出重复的网格和多余的相机）；
  3. 量化：POSITION → normalized uint16（真实尺寸/偏移写进节点矩阵）、TEXCOORD_0 → uint16、
           索引 → uint16/uint32、丢掉 NORMAL/TANGENT（网页里屏体是自发光，用不到法线）。

用法：
    python glb_web.py <场景.glb> --out <输出目录> [--screens A,B,D,F] [--camera cam]
                       [--node-prefix QiePing] [--set <uvset.json>]

产出：
    <输出目录>/scene.glb          网页用的小场景
    <输出目录>/scene_report.json  校验报告（节点、三角形、包围盒、量化误差）

只读源文件，不修改任何工程。
"""

import argparse
import json
import os
import struct
import sys

import numpy as np

CT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def log(m):
    sys.stdout.write("[glb] %s\n" % m)
    sys.stdout.flush()


def read_glb(path):
    d = open(path, "rb").read()
    if len(d) < 12:
        raise RuntimeError("文件太小，不像 GLB")
    magic, ver, length = struct.unpack_from("<III", d, 0)
    if magic != 0x46546C67:
        raise RuntimeError("不是 GLB（magic 不对）")
    off, js, bin_ = 12, None, None
    while off + 8 <= length:
        clen, ctype = struct.unpack_from("<II", d, off)
        start = off + 8
        if ctype == 0x4E4F534A:
            js = json.loads(d[start:start + clen].decode("utf-8"))
        elif ctype == 0x004E4942:
            bin_ = d[start:start + clen]
        off = start + clen
    if js is None or bin_ is None:
        raise RuntimeError("GLB 里缺 JSON 或 BIN 段")
    return js, bin_


def accessor(js, bin_, i):
    """读一个 accessor → (float 数组, componentType, normalized)"""
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    fmt, sz = CT[a["componentType"]]
    n = NC[a["type"]]
    stride = bv.get("byteStride") or sz * n
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    if stride == sz * n:
        arr = np.frombuffer(bin_, dtype=np.dtype("<" + fmt), count=a["count"] * n, offset=base)
        arr = arr.reshape(a["count"], n)
    else:
        rows = []
        for k in range(a["count"]):
            rows.append(struct.unpack_from("<" + fmt * n, bin_, base + k * stride))
        arr = np.array(rows)
    arr = arr.astype(np.float64)
    if a.get("normalized"):
        # normalized 的整数属性要除满量程；POSITION 的真实范围由节点矩阵负责还原
        arr = arr / {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}[a["componentType"]]
    return arr, a["componentType"], bool(a.get("normalized")), a


def scene_nodes(js):
    """从 scene 出发收集可达节点，顺便算每个节点的世界矩阵（4x4，行优先存）"""
    def mat(node):
        if "matrix" in node:
            return np.array(node["matrix"], dtype=np.float64).reshape(4, 4, order="F")
        M = np.eye(4)
        if "scale" in node:
            M[:3, :3] = np.diag(node["scale"])
        if "rotation" in node:
            x, y, z, w = node["rotation"]
            R = np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
            M[:3, :3] = R @ M[:3, :3]
        if "translation" in node:
            M[:3, 3] = node["translation"]
        return M

    world = {}
    roots = js["scenes"][js.get("scene", 0)]["nodes"]

    def walk(i, parent):
        M = parent @ mat(js["nodes"][i])
        world[i] = M
        for c in js["nodes"][i].get("children", []):
            walk(c, M)

    for i in roots:
        walk(i, np.eye(4))
    return world


def write_glb(path, js, bin_):
    jb = json.dumps(js, separators=(",", ":")).encode("utf-8")
    jb += b" " * ((-len(jb)) % 4)
    bb = bin_ + b"\x00" * ((-len(bin_)) % 4)
    total = 12 + 8 + len(jb) + 8 + len(bb)
    out = bytearray()
    out += b"glTF" + struct.pack("<II", 2, total)
    out += struct.pack("<II", len(jb), 0x4E4F534A) + jb
    out += struct.pack("<II", len(bb), 0x004E4942) + bb
    with open(path, "wb") as fh:
        fh.write(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--set", dest="set_dir", default=None, help="uvset.json 所在目录（用来读屏名/尺寸）")
    ap.add_argument("--screens", default=None, help="屏名，逗号分隔；默认从 --set 读")
    ap.add_argument("--camera", default="cam")
    ap.add_argument("--node-prefix", default="QiePing")
    args = ap.parse_args()

    screens = None
    if args.set_dir:
        meta = json.load(open(os.path.join(args.set_dir, "uvset.json"), encoding="utf-8"))
        screens = [s["name"] for s in meta["screens"]]
    if args.screens:
        screens = [s.strip() for s in args.screens.split(",") if s.strip()]
    if not screens:
        raise SystemExit("要么给 --screens，要么给 --set")

    js, bin_ = read_glb(args.src)
    log("源文件 %.2f MB，%d 节点 / %d 网格" % (os.path.getsize(args.src) / 1e6,
                                            len(js["nodes"]), len(js.get("meshes", []))))
    world = scene_nodes(js)
    alive = sorted(world)
    dropped = [js["nodes"][i].get("name") for i in range(len(js["nodes"])) if i not in world]
    log("场景内可达节点 %d：%s" % (len(alive), [js["nodes"][i].get("name") for i in alive]))
    if dropped:
        log("剔除孤立节点 %d：%s" % (len(dropped), dropped))

    by_name = {js["nodes"][i].get("name"): i for i in alive}
    report = {"src": os.path.abspath(args.src), "camera": None, "screens": {}, "dropped": dropped,
              "nodes": len(js["nodes"]), "alive": len(alive)}

    # ---- 相机 ----
    cam_i = None
    for i in alive:
        n = js["nodes"][i]
        if n.get("camera") is not None and n.get("name") == args.camera:
            cam_i = i
            break
    if cam_i is None:
        raise SystemExit("场景里找不到叫 %r 的相机节点" % args.camera)
    cr = js["cameras"][js["nodes"][cam_i]["camera"]]
    if cr.get("type") != "perspective":
        raise SystemExit("相机不是透视相机：%s" % cr.get("type"))
    Mcam = world[cam_i]
    # 相机在 glTF 里看向 -Z、上方向 +Y
    eye = Mcam[:3, 3]
    fwd = -Mcam[:3, 2]
    report["camera"] = {"node": args.camera, "eye": [float(x) for x in eye],
                        "forward": [float(x) for x in fwd],
                        "yfov": float(cr["perspective"]["yfov"]),
                        "yfov_deg": float(np.degrees(cr["perspective"]["yfov"])),
                        "znear": float(cr["perspective"].get("znear", 0.001)),
                        "zfar": float(cr["perspective"].get("zfar", 1000.0)),
                        "matrix": [float(x) for x in Mcam.flatten(order="F")]}   # glTF 用列主序
    log("相机 %s：眼睛 %s  yfov %.4f°" % (args.camera, np.round(eye, 5),
                                          report["camera"]["yfov_deg"]))

    # ---- 收集要写的网格 ----
    picks = []
    screen_nodes = {}
    for s in screens:
        nm = "%s%s" % (args.node_prefix, s)
        i = by_name.get(nm)
        if i is None:
            raise SystemExit("场景里找不到屏节点 %r（现有：%s）" % (nm, list(by_name)))
        n = js["nodes"][i]
        if n.get("mesh") is None:
            raise SystemExit("%s 没有网格" % nm)
        prim = js["meshes"][n["mesh"]]["primitives"][0]
        if "TEXCOORD_0" not in prim["attributes"]:
            raise SystemExit("%s 的网格没有 TEXCOORD_0，贴不了图" % nm)
        pos, pct, pnorm, _ = accessor(js, bin_, prim["attributes"]["POSITION"])
        uv, uct, unorm, _ = accessor(js, bin_, prim["attributes"]["TEXCOORD_0"])
        if "indices" in prim:
            idx, ict, _, _ = accessor(js, bin_, prim["indices"])
            idx = idx.reshape(-1).astype(np.int64)
        else:
            idx = np.arange(len(pos), dtype=np.int64)
            ict = 5123
        picks.append({"screen": s, "node": i, "name": nm, "pos": pos, "uv": uv, "idx": idx,
                      "prim": prim})
        screen_nodes[i] = s
        log("  %-6s 顶点 %6d 三角形 %6d UV %.3f..%.3f / %.3f..%.3f"
            % (nm, len(pos), len(idx) // 3, uv[:, 0].min(), uv[:, 0].max(),
               uv[:, 1].min(), uv[:, 1].max()))

    # 其余（非屏体）网格：保留成不带贴图的素模，方便以后把场地一起带进来
    extras = []
    for i in alive:
        n = js["nodes"][i]
        if n.get("mesh") is None or i in screen_nodes:
            continue
        prim = js["meshes"][n["mesh"]]["primitives"][0]
        pos, _, _, _ = accessor(js, bin_, prim["attributes"]["POSITION"])
        if "indices" in prim:
            idx = accessor(js, bin_, prim["indices"])[0].reshape(-1).astype(np.int64)
        else:
            idx = np.arange(len(pos), dtype=np.int64)
        extras.append({"screen": None, "node": i, "name": n.get("name") or ("node%d" % i),
                       "pos": pos, "uv": None, "idx": idx, "prim": prim})
    if extras:
        log("另外保留 %d 个非屏体网格：%s" % (len(extras), [e["name"] for e in extras]))

    all_items = picks + extras
    # 位置可能已经被归一化过（node 矩阵带缩放），这里统一到"世界坐标"再量化
    worldpos = []
    for p in all_items:
        M = world[p["node"]]
        ph = np.concatenate([p["pos"], np.ones((len(p["pos"]), 1))], axis=1)
        worldpos.append((ph @ M.T)[:, :3])
    allpos = np.concatenate(worldpos, axis=0)
    pmin = allpos.min(axis=0)
    pmax = allpos.max(axis=0)
    span = np.where((pmax - pmin) > 0, pmax - pmin, 1.0)
    log("场景包围盒 %s .. %s（尺寸 %s）" % (np.round(pmin, 5), np.round(pmax, 5), np.round(span, 5)))
    report["bbox"] = {"min": [float(x) for x in pmin], "max": [float(x) for x in pmax]}

    # ---- 组装新 GLB ----
    out_js = {"asset": {"version": "2.0", "generator": "qieping_3d glb_web.py"},
              "extensionsUsed": ["KHR_mesh_quantization"],
              "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
              "accessors": [], "bufferViews": [], "buffers": [], "cameras": [],
              "materials": [{"name": "screen",
                             "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                                                      "metallicFactor": 0.0, "roughnessFactor": 1.0}}]}
    blobs = []
    off = [0]

    def add_view(arr, target=None):
        b = arr.tobytes()
        bv = {"buffer": 0, "byteOffset": off[0], "byteLength": len(b)}
        if target:
            bv["target"] = target
        blobs.append(b)
        off[0] += len(b)
        out_js["bufferViews"].append(bv)
        return len(out_js["bufferViews"]) - 1

    def add_acc(view, ctype, count, typ, mins=None, maxs=None, norm=False):
        a = {"bufferView": view, "componentType": ctype, "count": int(count), "type": typ}
        if mins is not None:
            a["min"] = [float(x) for x in mins]
            a["max"] = [float(x) for x in maxs]
        if norm:
            a["normalized"] = True
        out_js["accessors"].append(a)
        return len(out_js["accessors"]) - 1

    max_qerr = 0.0
    for k, p in enumerate(all_items):
        s = p["screen"]
        M = world[p["node"]]
        ph = np.concatenate([p["pos"], np.ones((len(p["pos"]), 1))], axis=1)
        wp = (ph @ M.T)[:, :3]
        q = np.clip(np.round((wp - pmin) / span * 65535.0), 0, 65535).astype("<u2")
        # 量化误差（世界单位）
        wq = pmin + q.astype(np.float64) / 65535.0 * span
        max_qerr = max(max_qerr, float(np.abs(wq - wp).max()))
        ii = p["idx"].astype("<u2" if len(p["pos"]) <= 65535 else "<u4")
        vp = add_view(q, 34962)
        vi = add_view(ii, 34963)
        ap = add_acc(vp, 5123, len(q), "VEC3", [0, 0, 0], [1, 1, 1], norm=True)
        ai = add_acc(vi, 5125 if len(p["pos"]) > 65535 else 5123, len(ii), "SCALAR")
        attrs = {"POSITION": ap}
        if p["uv"] is not None:
            quv = np.clip(np.round(p["uv"] * 65535.0), 0, 65535).astype("<u2")
            vu = add_view(quv, 34962)
            au = add_acc(vu, 5123, len(quv), "VEC2",
                         [float(quv[:, 0].min() / 65535), float(quv[:, 1].min() / 65535)],
                         [float(quv[:, 0].max() / 65535), float(quv[:, 1].max() / 65535)], norm=True)
            attrs["TEXCOORD_0"] = au
        out_js["meshes"].append({
            "name": p["name"],
            "primitives": [{"attributes": attrs,
                            "indices": ai, "mode": 4, "material": 0,
                            "extensions": {"KHR_mesh_quantization": {}}}],
        })
        if s:
            report["screens"][s] = {
                "node": p["name"], "verts": int(len(p["pos"])), "tris": int(len(p["idx"]) // 3),
                "uv": [float(p["uv"][:, 0].min()), float(p["uv"][:, 0].max()),
                       float(p["uv"][:, 1].min()), float(p["uv"][:, 1].max())],
                "index_component": 5125 if len(p["pos"]) > 65535 else 5123,
            }
    report["extra_meshes"] = [e["name"] for e in extras]
    report["max_quant_error"] = max_qerr
    log("位置量化误差 ≤ %.3e 场景单位（相当于 %.4f px / 6000 帧）"
        % (max_qerr, max_qerr / span[0] * 6000))

    # 节点：几何已经烘到世界坐标，所以全部拍平挂在场景根上（不会和父级变换重复生效）
    sx, sy, sz = [float(x) for x in span]
    dequant = [sx, 0, 0, 0, 0, sy, 0, 0, 0, 0, sz, 0,
               float(pmin[0]), float(pmin[1]), float(pmin[2]), 1]
    for k, p in enumerate(all_items):
        out_js["nodes"].append({"name": p["name"], "mesh": k, "matrix": list(dequant)})
    Mcam_w = world[cam_i]
    out_js["nodes"].append({"name": args.camera, "camera": 0,
                            "matrix": [float(x) for x in Mcam_w.flatten(order="F")]})
    out_js["scenes"] = [{"nodes": list(range(len(all_items) + 1))}]
    out_js["cameras"] = [cr]

    binout = b"".join(blobs)
    out_js["buffers"] = [{"byteLength": len(binout)}]
    os.makedirs(args.out, exist_ok=True)
    dst = os.path.join(args.out, "scene.glb")
    write_glb(dst, out_js, binout)
    report["out"] = os.path.abspath(dst)
    report["out_bytes"] = os.path.getsize(dst)
    report["src_bytes"] = os.path.getsize(args.src)
    report["tris"] = int(sum(v["tris"] for v in report["screens"].values()))
    report["verts"] = int(sum(v["verts"] for v in report["screens"].values()))
    with open(os.path.join(args.out, "scene_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    log("产出 %s：%.2f MB → %.2f MB（%.0f%%），三角形 %d"
        % (dst, report["src_bytes"] / 1e6, report["out_bytes"] / 1e6,
           100.0 * report["out_bytes"] / report["src_bytes"], report["tris"]))

    # 自检：把刚写出去的文件重新读一遍，确认相机位姿和网格包围盒都没走样
    js2, bin2 = read_glb(dst)
    w2 = scene_nodes(js2)
    cam2 = next(i for i in w2 if js2["nodes"][i].get("name") == args.camera)
    if not np.allclose(w2[cam2], Mcam_w, atol=1e-6):
        raise SystemExit("自检失败：写出的相机矩阵和源文件不一致")
    allq = []
    for i in w2:
        if js2["nodes"][i].get("mesh") is None:
            continue
        pr = js2["meshes"][js2["nodes"][i]["mesh"]]["primitives"][0]
        p, _, _, _ = accessor(js2, bin2, pr["attributes"]["POSITION"])
        ph = np.concatenate([p, np.ones((len(p), 1))], axis=1)
        allq.append((ph @ w2[i].T)[:, :3])
    allq = np.concatenate(allq, axis=0)
    if not (np.allclose(allq.min(axis=0), pmin, atol=1e-5) and
            np.allclose(allq.max(axis=0), pmax, atol=1e-5)):
        raise SystemExit("自检失败：写出的网格包围盒 %s..%s 与源 %s..%s 不一致"
                         % (np.round(allq.min(axis=0), 5), np.round(allq.max(axis=0), 5),
                            np.round(pmin, 5), np.round(pmax, 5)))
    log("自检通过：重读 scene.glb，相机位姿与网格包围盒都和源文件一致")


if __name__ == "__main__":
    main()
