# -*- coding: utf-8 -*-
"""农残检测报告图片 OCR：包容不同表头/版式，提取 {菜名: 抑制率}。"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# 样品列常见表头（包容同义写法）
_NAME_HEADER_KEYS = (
    "样品名称",
    "样品名",
    "样品",
    "名称",
    "品名",
    "蔬菜名称",
    "蔬菜名",
    "食材名称",
    "食材",
    "检测样品",
    "抽检样品",
    "商品名称",
    "商品名",
)

_SKIP_NAME_WORDS = {
    "合格",
    "不合格",
    "散户",
    "序号",
    "产地",
    "摊位",
    "摊位号",
    "结果",
    "检测结果",
    "判定",
    "判定结果",
    "抑制率",
    "名称",
    "样品",
    "品名",
    "NO",
    "NQ",
}


def normalize_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", "", name)
    name = name.replace("（", "(").replace("）", ")")
    return name


def clean_ocr_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())


def is_rate_header(text: str) -> bool:
    """只要识别到「抑制率」且不像长说明句，即视为抑制率列表头。"""
    t = clean_ocr_text(text)
    if "抑制率" not in t:
        return False
    if len(t) > 16:
        return False
    if any(w in t for w in ("判定", "表示", "超标", "方法", "当酶")):
        return False
    return True


def is_name_header(text: str) -> bool:
    t = clean_ocr_text(text)
    if not t or len(t) > 12:
        return False
    for key in _NAME_HEADER_KEYS:
        if t == key or t.startswith(key) or t.endswith(key):
            return True
    return False


def parse_rate_value(text: str) -> Optional[float]:
    t = clean_ocr_text(text).replace("%", "").replace("％", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", t):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def is_veg_like_text(text: str) -> bool:
    t = clean_ocr_text(text)
    if not t or t in _SKIP_NAME_WORDS:
        return False
    if parse_rate_value(t) is not None:
        return False
    if re.search(r"(摊位|产地|判定|结果|检验|标准|合格|不合格|序号|抑制)", t):
        return False
    if not re.search(r"[\u4e00-\u9fff]", t):
        return False
    if len(t) > 12:
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9\-（）()]+", t))


def name_match_score(order_name: str, ocr_text: str, aliases: Optional[Dict[str, List[str]]] = None) -> float:
    """订单菜名与 OCR 文本相似度。"""
    a = normalize_name(order_name)
    b = normalize_name(ocr_text)
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0
    aliases = aliases or {}
    for alias in aliases.get(a, []):
        alias_n = normalize_name(alias)
        if not alias_n:
            continue
        if alias_n == b:
            return 95.0
        if (alias_n in b or b in alias_n) and min(len(alias_n), len(b)) >= 2:
            return 80.0 + min(len(alias_n), len(b))
    if a in b or b in a:
        return 70.0 + min(len(a), len(b))
    inter = len(set(a) & set(b))
    if inter >= 2 and inter / max(len(set(a)), len(set(b))) >= 0.6:
        return 50.0 + inter
    return 0.0


def cluster_x(values: List[float], tol: float = 80.0) -> List[float]:
    if not values:
        return []
    values = sorted(values)
    clusters: List[List[float]] = [[values[0]]]
    for v in values[1:]:
        if abs(v - clusters[-1][-1]) <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def build_inhibition_map_from_ocr(
    ocr_result,
    order_vegetables: Optional[List[str]] = None,
    aliases: Optional[Dict[str, List[str]]] = None,
) -> Tuple[Dict[str, float], Optional[str]]:
    """从 RapidOCR 结果构建映射。"""
    if not ocr_result:
        return {}, None

    aliases = aliases or {}
    order_vegetables = order_vegetables or []

    inspect_date: Optional[str] = None
    items = []
    for box, text, score in ocr_result:
        text = (text or "").strip()
        if not text:
            continue
        if inspect_date is None:
            m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
            if m:
                inspect_date = f"{int(m.group(1))}年{int(m.group(2))}月{int(m.group(3))}日"
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append(
            {
                "text": text,
                "raw": clean_ocr_text(text),
                "score": float(score),
                "x": sum(xs) / len(xs),
                "y": sum(ys) / len(ys),
            }
        )

    rate_headers = [it for it in items if is_rate_header(it["text"])]
    if not rate_headers:
        raise ValueError("未找到含「抑制率」的表头")

    rate_cols = cluster_x([it["x"] for it in rate_headers], tol=100)
    rate_header_y = min(it["y"] for it in rate_headers)

    name_headers = [it for it in items if is_name_header(it["text"])]
    name_cols = cluster_x([it["x"] for it in name_headers], tol=100) if name_headers else []

    # 用订单菜名反推名称列（表头叫什么都不要紧）
    if order_vegetables:
        hit_xs = []
        for it in items:
            if it["y"] <= rate_header_y + 10:
                continue
            for veg in order_vegetables:
                if name_match_score(veg, it["text"], aliases) >= 70:
                    hit_xs.append(it["x"])
                    break
        for cx in cluster_x(hit_xs, tol=90) if hit_xs else []:
            if not any(abs(cx - nx) < 90 for nx in name_cols):
                name_cols.append(cx)
        name_cols = sorted(name_cols)

    if not name_cols:
        left_xs = []
        for it in items:
            if it["y"] <= rate_header_y + 10:
                continue
            if not is_veg_like_text(it["text"]):
                continue
            if any(it["x"] < rx - 40 for rx in rate_cols):
                left_xs.append(it["x"])
        name_cols = cluster_x(left_xs, tol=90)

    if not name_cols:
        raise ValueError("未能定位蔬菜名称列")

    # 每个名称列配对右侧最近抑制率列
    pairs: List[Tuple[float, float]] = []
    for nx in name_cols:
        right_rates = [rx for rx in rate_cols if rx >= nx - 30]
        if right_rates:
            pairs.append((nx, min(right_rates, key=lambda r: r - nx)))
        else:
            pairs.append((nx, min(rate_cols, key=lambda r: abs(r - nx))))

    mapping: Dict[str, float] = {}

    for name_x, rate_x in pairs:
        names = []
        rates = []
        for it in items:
            if it["y"] <= rate_header_y + 15:
                continue
            if abs(it["x"] - name_x) <= 110 and is_veg_like_text(it["text"]):
                names.append(it)
            val = parse_rate_value(it["text"])
            if val is not None and abs(it["x"] - rate_x) <= 120:
                rates.append({**it, "value": val})

        names.sort(key=lambda x: x["y"])
        rates.sort(key=lambda x: x["y"])
        used = set()
        for name_it in names:
            best = None
            best_dy = 1e9
            for i, rate_it in enumerate(rates):
                if i in used:
                    continue
                dy = abs(rate_it["y"] - name_it["y"])
                if dy < best_dy and dy < 55:
                    best_dy = dy
                    best = (i, rate_it)
            if best is None:
                continue
            used.add(best[0])
            mapping[normalize_name(name_it["text"])] = round(best[1]["value"], 2)

    # 订单菜名增强：即使表头变化，也能按菜名找同行抑制率
    def already_has(veg: str) -> bool:
        key = normalize_name(veg)
        if key in mapping:
            return True
        for k in mapping:
            if name_match_score(veg, k, aliases) >= 70:
                return True
        return False

    for veg in order_vegetables:
        if already_has(veg):
            continue
        candidates = []
        for it in items:
            score = name_match_score(veg, it["text"], aliases)
            if score >= 70:
                candidates.append((score, it))
        if not candidates:
            continue
        candidates.sort(key=lambda x: (-x[0], x[1]["y"]))
        name_it = candidates[0][1]

        best_rate = None
        best_cost = 1e9
        for it in items:
            val = parse_rate_value(it["text"])
            if val is None:
                continue
            dy = abs(it["y"] - name_it["y"])
            if dy > 55:
                continue
            near_rate_col = any(abs(it["x"] - rx) <= 140 for rx in rate_cols)
            col_pen = 0 if near_rate_col else 80
            side_pen = 0 if it["x"] >= name_it["x"] - 20 else 60
            cost = dy + col_pen + side_pen
            if cost < best_cost:
                best_cost = cost
                best_rate = val
        if best_rate is not None:
            rate = round(best_rate, 2)
            mapping[normalize_name(veg)] = rate
            mapping[normalize_name(name_it["text"])] = rate

    if not mapping:
        raise ValueError("未能解析出蔬菜名称与抑制率对应关系")
    return mapping, inspect_date


def lookup_rate_in_map(
    veg: str,
    rate_map: Dict[str, float],
    aliases: Optional[Dict[str, List[str]]] = None,
) -> Optional[float]:
    key = normalize_name(veg)
    if key in rate_map:
        return rate_map[key]
    aliases = aliases or {}
    for alias in aliases.get(key, []):
        alias_n = normalize_name(alias)
        if alias_n in rate_map:
            return rate_map[alias_n]
    candidates: List[Tuple[float, str, float]] = []
    for k, v in rate_map.items():
        score = name_match_score(key, k, aliases)
        if score >= 70:
            candidates.append((score, k, v))
    if candidates:
        candidates.sort(key=lambda x: (-x[0], -len(x[1]), x[1]))
        return candidates[0][2]
    return None
