# -*- coding: utf-8 -*-
"""采购订单 PDF：包容不同表头，提取蔬菜/食材名称列。"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

import pdfplumber

# 表头优先级：越靠前越优先
_NAME_HEADER_KEYS = (
    "食材名称",
    "食材名",
    "商品名称",
    "商品名",
    "蔬菜名称",
    "蔬菜名",
    "菜品名称",
    "菜品名",
    "物料名称",
    "物料名",
    "产品名称",
    "产品名",
    "品名",
    "名称",
    "样品名称",
    "样品",
)

_SKIP_CELL = {
    "--",
    "-",
    "—",
    "－",
    "/",
    "合计",
    "小计",
    "总计",
    "备注",
    "无",
    "null",
    "none",
}

_UNIT_WORDS = {
    "斤",
    "公斤",
    "kg",
    "KG",
    "g",
    "G",
    "克",
    "份",
    "袋",
    "箱",
    "筐",
    "把",
    "个",
    "只",
    "条",
    "棵",
    "捆",
    "包",
    "瓶",
    "桶",
}


def _norm_cell(text: Optional[str]) -> str:
    t = (text or "").replace("\n", "").strip()
    t = re.sub(r"\s+", "", t)
    return t


def _header_score(cell: str) -> int:
    """表头匹配分，越高越好；0 表示不是名称列。"""
    t = _norm_cell(cell)
    if not t:
        return 0
    for i, key in enumerate(_NAME_HEADER_KEYS):
        if t == key:
            return 100 - i
        if key in t and len(t) <= len(key) + 6:
            # 如「食材名称/规格」这类拼接
            return 80 - i
    return 0


def _is_veg_name(text: str) -> bool:
    t = _norm_cell(text)
    if not t or t.lower() in _SKIP_CELL:
        return False
    if t in _UNIT_WORDS:
        return False
    if re.fullmatch(r"[\d./\-￥¥元]+", t):
        return False
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return False
    # 电话、订单号、日期
    if re.search(r"(订单|编号|电话|地址|时间|状态|备注|配送|收货|发货|单价|总价|数量)", t):
        return False
    if re.fullmatch(r"1\d{10}", t):
        return False
    if re.search(r"\d{4}-\d{1,2}-\d{1,2}", t):
        return False
    # 至少含汉字
    if not re.search(r"[\u4e00-\u9fff]", t):
        return False
    if len(t) > 16:
        return False
    return True


def _score_column(rows: Sequence[Sequence[Optional[str]]], col: int, start: int) -> Tuple[int, List[str]]:
    """评估某列作为蔬菜名列的质量，返回 (分数, 名称列表)。"""
    names: List[str] = []
    veg_count = 0
    num_count = 0
    empty_count = 0
    for row in rows[start:]:
        if col >= len(row):
            empty_count += 1
            continue
        cell = _norm_cell(row[col])
        if not cell or cell in _SKIP_CELL:
            empty_count += 1
            continue
        if re.fullmatch(r"\d+(\.\d+)?", cell) or cell in _UNIT_WORDS:
            num_count += 1
            continue
        if _is_veg_name(cell):
            veg_count += 1
            if cell not in names:
                names.append(cell)
    total = max(1, len(rows) - start)
    score = veg_count * 10 - num_count * 3 - empty_count
    # 蔬菜占比
    score += int(30 * veg_count / total)
    return score, names


def _extract_from_table(table: Sequence[Sequence[Optional[str]]]) -> List[str]:
    if not table:
        return []

    # 1) 按表头关键词找列
    best: Tuple[int, int, int, List[str]] = (-1, -1, -1, [])  # score, header_idx, col, names
    for i, row in enumerate(table):
        cells = [_norm_cell(c) for c in row]
        for j, cell in enumerate(cells):
            hs = _header_score(cell)
            if hs <= 0:
                continue
            col_score, names = _score_column(table, j, i + 1)
            total = hs * 10 + col_score
            if total > best[0] and names:
                best = (total, i, j, names)

    if best[3]:
        return best[3]

    # 2) 无明确表头：在疑似数据区选“最像菜名”的列
    # 跳过前几行元信息，从可能的表头附近开始
    start_candidates = list(range(min(8, len(table))))
    fallback_best: Tuple[int, List[str]] = (-10**9, [])
    for start in start_candidates:
        if not table[start]:
            continue
        width = max(len(r) for r in table[start:] if r) if table[start:] else 0
        for j in range(width):
            # 若该行该列本身是表头词，从下一行计
            data_start = start + (1 if _header_score(table[start][j] if j < len(table[start]) else "") > 0 else 0)
            col_score, names = _score_column(table, j, data_start)
            if names and col_score > fallback_best[0]:
                fallback_best = (col_score, names)

    return fallback_best[1]


def _extract_from_words(page) -> List[str]:
    """表格解析失败时，用文本词做弱兜底（仅作补充）。"""
    words = page.extract_words() or []
    if not words:
        return []
    # 找到名称类表头词的 x 中心
    header_xs = []
    for w in words:
        if _header_score(w.get("text", "")) > 0:
            header_xs.append((w["x0"] + w["x1"]) / 2)
    if not header_xs:
        return []
    hx = sorted(header_xs)[len(header_xs) // 2]
    names: List[str] = []
    for w in words:
        cx = (w["x0"] + w["x1"]) / 2
        if abs(cx - hx) > 45:
            continue
        t = _norm_cell(w.get("text", ""))
        if _header_score(t) > 0:
            continue
        if _is_veg_name(t) and t not in names:
            names.append(t)
    return names


def extract_vegetables(pdf_path: str) -> List[str]:
    """从订单 PDF 提取蔬菜/食材名称列表（包容表头差异）。"""
    vegetables: List[str] = []
    with pdfplumber.open(pdf_path) as doc:
        if not doc.pages:
            raise ValueError("PDF没有任何页面")
        for page in doc.pages:
            tables = page.extract_tables() or []
            for table in tables:
                for name in _extract_from_table(table):
                    if name not in vegetables:
                        vegetables.append(name)
            if not vegetables:
                for name in _extract_from_words(page):
                    if name not in vegetables:
                        vegetables.append(name)
    if not vegetables:
        raise ValueError(
            "未能提取到蔬菜/食材名称列。请确认是采购订单PDF，且表格含「食材名称/名称/品名」等列。"
        )
    return vegetables
