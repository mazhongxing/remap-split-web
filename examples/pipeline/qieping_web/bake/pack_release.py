# -*- coding: utf-8 -*-
"""打一个可以发给别人用的工具包 zip。

包里只有"用"需要的东西（成品网页 + 使用说明 + 界面预览），
不含烤图脚本、参考图和中间产物——那些是维护用的，留在工程目录里。

用法： python pack_release.py
产出： <工程根>/切屏出图工具_QiePing_WebTool.zip
"""

import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

TOOL = os.path.join(ROOT, "QiePing_WebTool.html")
PREVIEW = os.path.join(ROOT, "preview.png")
OUT = os.path.join(ROOT, "切屏出图工具_QiePing_WebTool.zip")

GUIDE = """切屏出图工具 · 使用说明
========================================

【这是什么】
给一张整幅画面，自动算出四块屏（A / B / D / F）各自要用的成片。

【怎么用】
1. 双击 QiePing_WebTool.html，用 Edge 或 Chrome 打开（需要较新的版本）。
   工具完全离线运行：不联网、不上传、不需要装 Nuke。
2. 载入画面，三种方式任选其一：
     · 把图片拖进左边虚线框；
     · 点「选择文件…」（虚线框本身也能点）；
     · 直接按 Ctrl+V 粘贴。
3. 需要的话改一下「输出文件名前缀」（默认 QiePing）。
4. 点「生成 A / B / D / F」，几秒后四张图依次出来。
5. 逐张点「下载 PNG」，或点「打包下载 ZIP」一次拿全。

【出图规格】
  A  6600 × 1700
  B  6600 × 1580
  D  3400 × 1300
  F  3750 × 750
  统一 8-bit sRGB PNG、黑底；画面没覆盖到的地方是纯黑。

【输入要求】
  · 建议用 6000 × 1538 的画面（和现网素材一致）。
  · 其它尺寸也能用，会整幅拉伸到画面的坐标系（和 Nuke 里的行为一致）；
    宽高比不是 3.901 时页面会提示一句。
  · jpg / png 等常见图片格式都行。

【几点提醒】
  · 点「选择文件…」如果没弹出选择框，多半是文件被塞在某个软件的预览窗口里打开的
    （那种窗口常常禁用系统文件框）。请用系统的 Edge / Chrome 直接打开这个 html 文件；
    拖拽和 Ctrl+V 一般不受影响。
  · 机位和屏体是固定的，这套工具只对应现在这一台机位 + A/B/D/F 四块屏。
  · 生成的图和 Nuke 直接渲出来的成片肉眼一致（实测平均误差约 1/255）。
  · 四张 A/B/D/F 是大图（合计 35 MB 左右），生成和打包时页面会卡一下，属正常。
"""


def main():
    for p in (TOOL, PREVIEW):
        if not os.path.exists(p):
            raise RuntimeError("missing %s" % p)

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(TOOL, "QiePing_WebTool.html")
        zf.write(PREVIEW, "界面预览.png")
        info = zipfile.ZipInfo("使用说明.txt", date_time=(2026, 10, 15, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, GUIDE.encode("utf-8-sig"))

    with zipfile.ZipFile(OUT) as zf:
        print("zip: %s (%.2f MB)" % (OUT, os.path.getsize(OUT) / 1e6))
        for i in zf.infolist():
            print("   %-24s %8d bytes" % (i.filename, i.file_size))
        if zf.testzip() is not None:
            raise RuntimeError("zip integrity check failed")
    print("OK")


if __name__ == "__main__":
    main()
