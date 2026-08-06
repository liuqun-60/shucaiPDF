# -*- coding: utf-8 -*-
"""食堂农残数据自动整理助手 - Streamlit 界面。"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import streamlit as st

from pipeline import (
    DEFAULT_STAMP,
    DEFAULT_TEMPLATE,
    USER_STAMP,
    run_pipeline,
    save_user_stamp,
)

st.set_page_config(page_title="食堂农残报告自动生成", page_icon="🥬", layout="centered")
st.title("食堂农残报告自动生成")
st.caption("上传红章（可复用）、检测报告图片（可多选）、订单PDF（可多选），自动生成盖章报告")


def _load_saved_stamp() -> bytes | None:
    for path in (USER_STAMP, DEFAULT_STAMP):
        if path.exists():
            return path.read_bytes()
    return None


def _sig(stamp: bytes, reports: list[bytes], orders: list[bytes]) -> str:
    h = hashlib.md5()
    h.update(stamp)
    for b in reports:
        h.update(b)
    for b in orders:
        h.update(b)
    return h.hexdigest()


for key, default in (
    ("stamp_bytes", None),
    ("report_files", None),  # list[(name, bytes)]
    ("order_files", None),
    ("result_pdf", None),
    ("result_xlsx", None),
    ("result_msg", ""),
    ("input_sig", None),
    ("last_missing", None),
):
    if key not in st.session_state:
        st.session_state[key] = default

if st.session_state.stamp_bytes is None:
    st.session_state.stamp_bytes = _load_saved_stamp()

stamp_file = st.file_uploader(
    "① 上传默认红章（只需上传一次，再次上传会替换）",
    type=["png", "jpg", "jpeg"],
)
if stamp_file is not None:
    data = stamp_file.getvalue()
    st.session_state.stamp_bytes = data
    suffix = Path(stamp_file.name).suffix.lower() or ".png"
    save_user_stamp(data, suffix=suffix)
    st.success("红章已保存，下次打开将自动使用。")

if st.session_state.stamp_bytes:
    source = "上次保存的红章" if USER_STAMP.exists() else "默认红章"
    st.caption(f"当前红章来源：{source}")
    st.image(st.session_state.stamp_bytes, caption="当前红章预览", width=140)
else:
    st.warning("尚未设置红章，请先上传一张红章图片。")

report_files = st.file_uploader(
    "② 上传检测报告（可一次选多张图片）",
    type=["png", "jpg", "jpeg", "bmp", "webp"],
    accept_multiple_files=True,
)
if report_files:
    st.session_state.report_files = [
        (f.name, f.getvalue()) for f in report_files
    ]
    st.caption(f"已选检测报告 {len(st.session_state.report_files)} 张")

order_files = st.file_uploader(
    "③ 上传订单PDF（可一次选多份）",
    type=["pdf"],
    accept_multiple_files=True,
)
if order_files:
    st.session_state.order_files = [
        (f.name, f.getvalue()) for f in order_files
    ]
    st.caption(f"已选订单PDF {len(st.session_state.order_files)} 份")

ready = bool(
    st.session_state.stamp_bytes
    and st.session_state.report_files
    and st.session_state.order_files
    and DEFAULT_TEMPLATE.exists()
)

if not DEFAULT_TEMPLATE.exists():
    st.error(
        "【准备模板失败】缺少模板文件："
        f"{DEFAULT_TEMPLATE.name}。请把它和程序放在同一目录。"
    )

if ready:
    report_bytes_list = [b for _, b in st.session_state.report_files]
    order_bytes_list = [b for _, b in st.session_state.order_files]
    current_sig = _sig(
        st.session_state.stamp_bytes,
        report_bytes_list,
        order_bytes_list,
    )
    need_rebuild = (
        st.session_state.result_xlsx is None
        or st.session_state.input_sig != current_sig
    )
    if need_rebuild:
        with st.spinner("正在识别、填表、盖章并导出…"):
            try:
                with tempfile.TemporaryDirectory(prefix="nongcan_ui_") as tmp:
                    tmp_path = Path(tmp)
                    stamp_path = tmp_path / "stamp.png"
                    stamp_path.write_bytes(st.session_state.stamp_bytes)

                    report_paths = []
                    for i, (name, data) in enumerate(st.session_state.report_files):
                        ext = Path(name).suffix.lower() or ".jpg"
                        p = tmp_path / f"report_{i}{ext}"
                        p.write_bytes(data)
                        report_paths.append(p)

                    order_paths = []
                    for i, (name, data) in enumerate(st.session_state.order_files):
                        p = tmp_path / f"order_{i}.pdf"
                        p.write_bytes(data)
                        order_paths.append(p)

                    result = run_pipeline(
                        order_pdf=order_paths,
                        report_image=report_paths,
                        stamp_image=stamp_path,
                        template_path=DEFAULT_TEMPLATE,
                        work_dir=tmp_path / "out",
                    )
                    st.session_state.result_xlsx = Path(
                        result["xlsx_path"]
                    ).read_bytes()
                    if result.get("pdf_path"):
                        st.session_state.result_pdf = Path(
                            result["pdf_path"]
                        ).read_bytes()
                    else:
                        st.session_state.result_pdf = None
                    st.session_state.result_msg = result["message"]
                    st.session_state.input_sig = current_sig
                    st.session_state.last_missing = result.get("missing") or []
                if st.session_state.last_missing:
                    st.warning(st.session_state.result_msg)
                else:
                    st.success(st.session_state.result_msg)
            except Exception as e:
                st.session_state.result_pdf = None
                st.session_state.result_xlsx = None
                st.session_state.input_sig = None
                st.session_state.last_missing = None
                st.error("生成失败，详细说明如下：")
                st.code(str(e), language=None)

col_a, col_b = st.columns(2)
has_xlsx = bool(st.session_state.result_xlsx)
has_pdf = bool(st.session_state.result_pdf)

with col_a:
    st.download_button(
        "④ 下载盖章Excel报告",
        data=st.session_state.result_xlsx or b"",
        file_name="湖北合盛源-农药残留检验报告.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=not has_xlsx,
        use_container_width=True,
    )
with col_b:
    st.download_button(
        "⑤ 下载盖章PDF报告",
        data=st.session_state.result_pdf or b"",
        file_name="湖北合盛源-农药残留检验报告.pdf",
        mime="application/pdf",
        disabled=not has_pdf,
        use_container_width=True,
    )

if has_xlsx and st.session_state.get("last_missing"):
    st.info(
        "以下蔬菜在检测报告中未找到，抑制率已留空，请从历史报告中查找补全："
        + "、".join(st.session_state.last_missing)
        + "（未生成 PDF，仅可下载 Excel）"
    )
