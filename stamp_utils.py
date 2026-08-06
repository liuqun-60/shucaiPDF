# -*- coding: utf-8 -*-
"""媒体资源压缩：缩小红章体积，避免 Excel/PDF 膨胀。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def optimize_stamp_image(
    src: str | Path,
    dst: str | Path,
    max_side: int = 360,
) -> Path:
    """将红章压缩为小尺寸透明 PNG，通常可降到几 KB～几十 KB。"""
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    im = Image.open(src)
    if im.mode not in ("RGBA", "LA"):
        im = im.convert("RGBA")
    else:
        im = im.convert("RGBA")

    w, h = im.size
    scale = max_side / float(max(w, h))
    if scale < 1.0:
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        im = im.resize(new_size, Image.Resampling.LANCZOS)

    # 透明通道二值化，利于 PNG 压缩（红章边缘干净即可）
    r, g, b, a = im.split()
    a = a.point(lambda x: 255 if x >= 128 else 0)
    im = Image.merge("RGBA", (r, g, b, a))

    im.save(dst, format="PNG", optimize=True, compress_level=9)
    return dst
