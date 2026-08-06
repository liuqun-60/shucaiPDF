# -*- coding: utf-8 -*-
"""按「模板湖北合盛源-农药残留检验报告」版式绘制 PDF（不依赖 Microsoft Excel）。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF

BASE_DIR = Path(__file__).resolve().parent

PAGE_W, PAGE_H = fitz.paper_size("a4")
MARGIN_L = 48
MARGIN_R = 48
MARGIN_T = 36
MARGIN_B = 40

COL_RATIOS = [5.89, 18.66, 20.44, 17.44, 26.78]
HEADERS = ["NQ", "样品", "抑制率", "衣药未残留标准", "栓测结果"]

SIZE_COMPANY = 22
SIZE_TITLE = 14
SIZE_METHOD_DATE = 11
SIZE_STANDARD = 10
SIZE_TABLE = 10
SIZE_FOOTER = 10
SIZE_INSPECTOR = 11

LINE_W = 0.7
FONT_NAME = "reportfont"


def _font_supports_chinese(font_path: Path) -> bool:
    try:
        font = fitz.Font(fontfile=str(font_path))
        return bool(font.has_glyph(ord("湖")) and font.has_glyph(ord("检")))
    except Exception:
        return False


def resolve_font() -> Path:
    """优先项目根目录 simsunb；若无常用汉字则回退可用宋体。"""
    preferred = [
        BASE_DIR / "simsunb.ttf",
        BASE_DIR / "fonts" / "simsunb.ttf",
    ]
    fallbacks = [
        BASE_DIR / "fonts" / "simsun.ttc",
        BASE_DIR / "simsun.ttc",
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\simsun.ttf"),
    ]
    for path in preferred:
        if path.exists() and _font_supports_chinese(path):
            return path
    for path in preferred:
        if path.exists() and not _font_supports_chinese(path):
            break
    for path in fallbacks:
        if path.exists() and _font_supports_chinese(path):
            return path
    raise FileNotFoundError(
        "未找到可用中文字体。请将含常用汉字的宋体文件放到项目目录"
        "（推荐 fonts/simsun.ttc）。注意：部分 simsunb.ttf 实际是 ExtB 扩展字库，无法显示常用汉字。"
    )


def _col_widths(table_width: float) -> List[float]:
    total = sum(COL_RATIOS)
    return [table_width * r / total for r in COL_RATIOS]


def _register_font(page: fitz.Page, font_path: Path) -> str:
    page.insert_font(fontname=FONT_NAME, fontfile=str(font_path))
    return FONT_NAME


def _tb_vcenter(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    fontsize: float,
    fontname: str,
    align: int = fitz.TEXT_ALIGN_LEFT,
) -> None:
    """单元格内文字水平按 align，垂直居中。"""
    lines = max(1, str(text).count("\n") + 1)
    content_h = fontsize * 1.35 * lines
    pad_y = max(1.0, (rect.height - content_h) / 2.0)
    inner = fitz.Rect(rect.x0 + 3, rect.y0 + pad_y, rect.x1 - 3, rect.y1 - 1)
    page.insert_textbox(
        inner,
        text,
        fontname=fontname,
        fontsize=fontsize,
        align=align,
        render_mode=0,
    )


def _line(page: fitz.Page, x0: float, y0: float, x1: float, y1: float) -> None:
    page.draw_line(
        fitz.Point(x0, y0),
        fitz.Point(x1, y1),
        color=(0, 0, 0),
        width=LINE_W,
    )


def render_report_pdf(
    rows: List[Dict],
    inspect_date: str,
    output_pdf: str | Path,
    stamp_image: str | Path | None = None,
    stamp_width: float = 110,
) -> Path:
    """生成 PDF：表内文字垂直居中；「只对本次检验样品负责」在表格内。"""
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    font_path = resolve_font()

    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    fontname = _register_font(page, font_path)

    table_x0 = MARGIN_L
    table_x1 = PAGE_W - MARGIN_R
    table_w = table_x1 - table_x0
    widths = _col_widths(table_w)
    col_x = [table_x0]
    for w in widths:
        col_x.append(col_x[-1] + w)

    y = MARGIN_T

    # 标题（表外）
    h1 = 40
    _tb_vcenter(
        page,
        fitz.Rect(table_x0, y, table_x1, y + h1),
        "湖北合盛源餐饮管理有限公司",
        SIZE_COMPANY,
        fontname,
        align=fitz.TEXT_ALIGN_CENTER,
    )
    y += h1

    h2 = 26
    _tb_vcenter(
        page,
        fitz.Rect(table_x0, y, table_x1, y + h2),
        "农药残留检验报告（自检）",
        SIZE_TITLE,
        fontname,
        align=fitz.TEXT_ALIGN_CENTER,
    )
    y += h2 + 6

    table_top = y
    method = "检验方法：蔬菜中有机磷和氨基甲酸酯类农药残留的检测"
    date_line = (
        inspect_date
        if str(inspect_date).startswith("检验时间")
        else f"检验时间：{inspect_date}"
    )
    std_text = (
        "执行标准：GB/T 5009.199-2003\n"
        "判定结果：当酶抑制率≤50%时，表示样品农残未超标：当抑制率≥50%时，表示样品农残超标。"
    )

    # 表格第1行：检验方法 | 检验时间
    row1_h = 28
    row1_y0, row1_y1 = y, y + row1_h
    split = col_x[4]
    _tb_vcenter(
        page,
        fitz.Rect(table_x0, row1_y0, split, row1_y1),
        method,
        SIZE_METHOD_DATE,
        fontname,
        align=fitz.TEXT_ALIGN_LEFT,
    )
    _tb_vcenter(
        page,
        fitz.Rect(split, row1_y0, table_x1, row1_y1),
        date_line,
        SIZE_METHOD_DATE,
        fontname,
        align=fitz.TEXT_ALIGN_LEFT,
    )
    y = row1_y1

    # 表格第2行：执行标准（整行）
    row2_h = 42
    row2_y0, row2_y1 = y, y + row2_h
    _tb_vcenter(
        page,
        fitz.Rect(table_x0, row2_y0, table_x1, row2_y1),
        std_text,
        SIZE_STANDARD,
        fontname,
        align=fitz.TEXT_ALIGN_LEFT,
    )
    y = row2_y1

    # 表格第3行：列头
    header_h = 22
    header_y0, header_y1 = y, y + header_h
    for i, header in enumerate(HEADERS):
        _tb_vcenter(
            page,
            fitz.Rect(col_x[i], header_y0, col_x[i + 1], header_y1),
            header,
            SIZE_TABLE,
            fontname,
            align=fitz.TEXT_ALIGN_CENTER,
        )
    y = header_y1

    # 数据行
    row_h = 22
    data_ys = [y]
    for row in rows:
        if y + row_h + 100 > PAGE_H - MARGIN_B:
            row_h = max(16, row_h - 1)
        values = [
            str(row["seq"]),
            str(row["name"]),
            str(row["rate"]),
            str(row["standard"]),
            str(row["result"]),
        ]
        for i, val in enumerate(values):
            _tb_vcenter(
                page,
                fitz.Rect(col_x[i], y, col_x[i + 1], y + row_h),
                val,
                SIZE_TABLE,
                fontname,
                align=fitz.TEXT_ALIGN_CENTER,
            )
        y += row_h
        data_ys.append(y)

    data_bottom = y

    # 表格末行：只对本次检验样品负责（整行合并，在表格内）
    foot_h = 24
    foot_y0, foot_y1 = y, y + foot_h
    _tb_vcenter(
        page,
        fitz.Rect(table_x0, foot_y0, table_x1, foot_y1),
        "只对本次检验样品负责",
        SIZE_FOOTER,
        fontname,
        align=fitz.TEXT_ALIGN_LEFT,
    )
    y = foot_y1
    table_bottom = y

    # ===== 统一框线 =====
    page.draw_rect(
        fitz.Rect(table_x0, table_top, table_x1, table_bottom),
        color=(0, 0, 0),
        width=LINE_W,
        fill=None,
    )
    # 水平线
    for hy in [row1_y1, row2_y1, header_y1] + data_ys[1:] + [foot_y0]:
        if hy < table_bottom:
            _line(page, table_x0, hy, table_x1, hy)
    # 第1行方法/时间分隔竖线
    _line(page, split, row1_y0, split, row1_y1)
    # 表头+数据区列竖线（不到页脚合并行）
    for cx in col_x[1:-1]:
        _line(page, cx, header_y0, cx, data_bottom)

    # 表外：检测人
    y = table_bottom + 12
    _tb_vcenter(
        page,
        fitz.Rect(col_x[1], y, table_x1, y + 22),
        "检测人：陈少明",
        SIZE_INSPECTOR,
        fontname,
        align=fitz.TEXT_ALIGN_LEFT,
    )

    if stamp_image is not None:
        stamp_path = Path(stamp_image)
        if stamp_path.exists():
            # 与 Excel 一致：上沿对齐第9行（第4条数据行）中线；水平中心对齐 C 列右沿
            if len(data_ys) > 4:
                row9_mid = (data_ys[3] + data_ys[4]) / 2.0
            elif len(data_ys) > 3:
                row9_mid = data_ys[3] + row_h / 2.0
            else:
                row9_mid = header_y1 + 3 * row_h + row_h / 2.0
            stamp_x0 = col_x[3] - stamp_width / 2.0  # C 列右沿 = col_x[3]
            stamp_y0 = row9_mid
            stamp_rect = fitz.Rect(
                stamp_x0, stamp_y0, stamp_x0 + stamp_width, stamp_y0 + stamp_width
            )
            page.insert_image(
                stamp_rect,
                filename=str(stamp_path),
                keep_proportion=True,
                overlay=True,
            )

    # 只嵌入实际用到的汉字字形，避免整份宋体（十余 MB）打进 PDF
    try:
        doc.subset_fonts()
    except Exception:
        pass
    doc.save(str(output_pdf), garbage=4, deflate=True, clean=True)
    doc.close()
    return output_pdf
