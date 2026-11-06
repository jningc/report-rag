"""
招标文件核对界面：左表右页图，解析文本为第二档。
"""

from io import BytesIO
from pathlib import Path

import streamlit as st
import yaml
from openpyxl import Workbook

from tender.parse import render_page_png
from tender.sections import TYPE_LABEL
from tender.tools import set_context
from tender.workflow import print_tables, run_check

SAMPLE = {
    "东城道路监理": "sample/beijing_road.pdf",
    "崇左国土绿化": "sample/chongzuo_green.pdf",
    "温岭雪亮工程": "sample/wenling_video.pdf",
}

TABS = [
    ("feibiao", "废标对照"),
    ("pingfen", "评分对照"),
    ("cailiao", "材料对照"),
    ("kongwei", "空位对照"),
    ("shijian", "时间节点"),
    ("hetong", "合同要点"),
]


def _verdict_style(v: str) -> str:
    if v == "不满足":
        return "不满足"
    if v == "满足":
        return "满足"
    if v == "无须提供":
        return "无须提供"
    return "人工看"


def _export_xlsx(result: dict) -> bytes:
    wb = Workbook()
    first = True
    for key, title in TABS:
        ws = wb.active if first else wb.create_sheet(title)
        if first:
            ws.title = title
            first = False
        rows = result.get(key) or []
        if not rows:
            ws.append(["空"])
            continue
        cols = [c for c in rows[0].keys() if c != "refs"]
        ws.append(cols + ["出处"])
        for row in rows:
            src = "；".join(
                f"p.{r.get('page')} {r.get('chapter')}"
                for r in (row.get("refs") or [])
                if r.get("page")
            )
            ws.append([str(row.get(c, "")) for c in cols] + [src])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _show_refs(pdf_path: str, refs: list, mode: str) -> None:
    usable = [r for r in refs if r.get("page")]
    if not usable:
        st.info("没有页码或块坐标，标「人工看」，不翻页、不画框。")
        return
    if mode == "text":
        by_ch = {}
        for r in usable:
            by_ch.setdefault(r.get("chapter") or "未分章", []).append(r)
        for ch, items in by_ch.items():
            pages = [i.get("page") for i in items]
            st.markdown(f"**{ch} · p.{min(pages)}–{max(pages)}**")
            for r in items:
                st.caption(r.get("clause") or "")
                st.write(r.get("text") or "")
        return
    for i, r in enumerate(usable):
        if i:
            st.caption("follow_reference 跳转")
        png = render_page_png(pdf_path, int(r["page"]), [r.get("bbox")] if r.get("bbox") else None)
        st.image(png, caption=f"第 {r['page']} 页 {r.get('chapter') or ''}", use_container_width=True)
        if r.get("bbox"):
            st.caption("bbox=" + ",".join(f"{x:.1f}" for x in r["bbox"]))


def main():
    st.set_page_config(page_title="招标文件核对", layout="wide")
    st.title("招标文件核对")
    st.caption("投标前把招标文件读一遍：废标、评分、材料、空位。点一行看原件黄框。演示数据，不是真投标。")

    if "result" not in st.session_state:
        st.session_state.result = None
    if "picked" not in st.session_state:
        st.session_state.picked = None

    with st.sidebar:
        st.header("输入")
        sample_name = st.selectbox("样本", list(SAMPLE.keys()))
        uploaded = st.file_uploader("或上传招标 PDF", type=["pdf"])
        company_text = st.text_area(
            "company.yaml",
            value=Path_read_company(),
            height=220,
        )
        k_run = st.button("运行核对", type="primary")
        view_mode = st.radio("原文", ["原件按页", "解析文本"], horizontal=True)

    pdf_path = SAMPLE[sample_name]
    if uploaded is not None:
        tmp = Path_write_upload(uploaded)
        pdf_path = str(tmp)

    if k_run:
        yaml.safe_load(company_text)
        company_file = Path_write_yaml(company_text)
        with st.spinner("切章并四步出表，需要调用模型…"):
            result = run_check(pdf_path, company_file)
        set_context(result["index"], result["company"])
        # index 不能放进可序列化缓存之外的展示字段
        st.session_state.result = {k: v for k, v in result.items() if k not in ("index", "pages")}
        st.session_state.result["_pdf"] = result["pdf_path"]
        st.session_state.result["_index"] = result["index"]
        st.session_state.picked = None
        print_tables(result)

    result = st.session_state.result
    if not result:
        st.info("选择样本或上传 PDF 后点「运行核对」。样本 PDF 需先按 sample/sources.md 下载。")
        return

    left, right = st.columns([1.15, 0.85])
    with left:
        names = [t[1] for t in TABS] + ["提问"]
        tab_objs = st.tabs(names)
        for i, (key, title) in enumerate(TABS):
            with tab_objs[i]:
                rows = result.get(key) or []
                st.caption(f"{title} {len(rows)} 条")
                for j, row in enumerate(rows):
                    label = row.get("condition") or row.get("item") or row.get("material") or row.get("form") or row.get("name") or f"第{j+1}行"
                    verdict = row.get("verdict")
                    prefix = "★ " if row.get("star") else ""
                    head = f"{prefix}{_verdict_style(verdict) + ' · ' if verdict else ''}{label}"
                    if st.button(head, key=f"{key}-{j}", use_container_width=True):
                        st.session_state.picked = row
        with tab_objs[-1]:
            q = st.text_input("只问这份文件", placeholder="例如：投标保证金多少？能不能联合体投标？")
            if st.button("提问") and q.strip():
                from tender.ask_box import ask_question
                if result.get("_index") is not None:
                    set_context(result["_index"], result["company"])
                out = ask_question(q.strip())
                for step in out["trace"]:
                    st.code(f"{step['tool']} {step['args']}")
                st.write(out["answer"])
        st.download_button(
            "导出 Excel",
            data=_export_xlsx(result),
            file_name="tender-check.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with right:
        st.subheader("原文")
        picked = st.session_state.picked
        if not picked:
            st.caption("点左侧一行，这里翻到对应页并画框")
        else:
            mode = "text" if view_mode == "解析文本" else "page"
            _show_refs(result["_pdf"], picked.get("refs") or [], mode)

    with st.expander("切出的章节"):
        for s in result.get("sections") or []:
            st.write(f"{TYPE_LABEL.get(s['type'], s['type'])} {s['title']} p.{s['start_page']}-{s['end_page']}")


def Path_read_company() -> str:
    p = Path("sample/company.yaml")
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "name: 示例公司\n"


def Path_write_yaml(text: str):
    p = Path("data/tender_last_company.yaml")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def Path_write_upload(uploaded):
    p = Path("data/tender_upload.pdf")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(uploaded.getvalue())
    return p


if __name__ == "__main__":
    main()
