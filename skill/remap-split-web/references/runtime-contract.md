# 数据契约与网页运行时

## 素材文件（每路输出三个文件）

| 文件 | 内容 |
| --- | --- |
| `gridU_<路>.png` | 降采样后的横向坐标，8-bit **RGB**：R=u 高 8 位、G=u 低 8 位、B=0 |
| `gridV_<路>.png` | 同上，纵向坐标 |
| `mask_<路>.png` | **全分辨率** 8-bit 灰度，覆盖率（自带抗锯齿） |

打包公式（**先降采样、再拆高低位**，顺序不能反；反了等于对高字节和低字节分别平均，进位处会崩）：

```
k = round(clamp(u,0,1) * 65535)      R = k >> 8      G = k & 255
k = round(clamp(v,0,1) * 65535)      R = k >> 8      G = k & 255
```

## uvset.json

```json
{
  "name": "MySet",
  "vAxis": "bottom",
  "cell": 4,
  "screens": [
    { "name": "A", "out": [6600, 1700], "grid": [1650, 425], "pad": [6600, 1700],
      "gridU": "gridU_A.png", "gridV": "gridV_A.png", "mask": "mask_A.png" }
  ]
}
```

* `out` = 该路输出的真实分辨率；`grid` = 坐标网格分辨率；`pad = grid * cell`。
* **所有路名、路数、分辨率都由 json 驱动**，代码里不许硬编码。
* `cell` 是质量/体积旋钮：4 是常用折中，2 更准但素材约大 4 倍，8 更小但高频素材会软。

## 算法

```
out(x,y) = src_双线性_线性空间( u*W - 0.5 , (1-v)*H - 0.5 ) * mask(x,y)
```

`u,v` 是**归一化坐标**（不是像素），v 原点在左下。

## 着色器骨架（WebGL2 / GLSL ES 3.0）

```glsl
// 帧缓冲 y 向上、图像行号向下，先翻一次
vec2 fc = vec2(gl_FragCoord.x, uOutSize.y - gl_FragCoord.y);

// 1) 查坐标网格。16-bit 必须自己拆位插值，不能交给硬件。
vec2 gt = fc / uPadSize * uGridSize - 0.5;
ivec2 gm = ivec2(uGridSize) - 1;
vec2 uv = vec2(gridAt(uGridU, gt, gm), gridAt(uGridV, gt, gm)) / 65535.0;

// 2) 采样素材：贴图 v=0 在第一行，而 uv.y 原点在左下 → 翻转
vec2 srcUV = vec2(uv.x, 1.0 - uv.y);
vec2 px = clamp(srcUV * uArtSize - 0.5, vec2(0.0), uArtSize - 1.0);
vec2 i0f = floor(px), fr = px - i0f;
ivec2 i0 = ivec2(i0f);
vec3 col = mix(mix(fetchLin(i0),                fetchLin(i0 + ivec2(1,0)), fr.x),
               mix(fetchLin(i0 + ivec2(0,1)),   fetchLin(i0 + ivec2(1,1)), fr.x), fr.y);

// 3) 乘覆盖率
col *= texture(uMask, fc / uOutSize).r;
outColor = vec4(linToSrgb(col.r), linToSrgb(col.g), linToSrgb(col.b), 1.0);
```

辅助函数：

```glsl
float srgbToLin(float c){ return c <= 0.04045 ? c/12.92 : pow((c+0.055)/1.055, 2.4); }
float linToSrgb(float c){ return c <= 0.0031308 ? c*12.92 : 1.055*pow(c, 1.0/2.4) - 0.055; }
vec3 fetchLin(ivec2 c){                       // 素材用 NEAREST，自己插值
  ivec2 m = ivec2(uArtSize) - 1;
  vec3 s = texelFetch(uArt, clamp(c, ivec2(0), m), 0).rgb;
  return vec3(srgbToLin(s.r), srgbToLin(s.g), srgbToLin(s.b));
}
float grid16(sampler2D t, ivec2 c){           // 高低位拼回 16-bit
  vec3 v = texelFetch(t, c, 0).rgb;
  return floor(v.r*255.0+0.5)*256.0 + floor(v.g*255.0+0.5);
}
float gridAt(sampler2D t, vec2 gt, ivec2 m){  // 取 4 格、拆位后再双线性
  vec2 i0f = floor(gt), f = gt - i0f;
  float a0 = grid16(t, clamp(ivec2(i0f),               ivec2(0), m));
  float a1 = grid16(t, clamp(ivec2(i0f)+ivec2(1,0),    ivec2(0), m));
  float a2 = grid16(t, clamp(ivec2(i0f)+ivec2(0,1),    ivec2(0), m));
  float a3 = grid16(t, clamp(ivec2(i0f)+ivec2(1,1),    ivec2(0), m));
  return mix(mix(a0,a1,f.x), mix(a2,a3,f.x), f.y);
}
```

## 上传贴图时的两个开关

```js
const bmp = await createImageBitmap(blob, { premultiplyAlpha: "none", colorSpaceConversion: "none" });
gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
```

素材是数据不是颜色，任何色彩管理都会毁掉它。遮罩与网格用 `NEAREST`，
素材也用 `NEAREST`（插值自己做）。
