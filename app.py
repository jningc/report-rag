"""
Streamlit Web 界面：制度变更影响面

第一屏是旧版 / 新版对照表；单题问答在第二页，当尺子。

用法:
  streamlit run app.py
"""

import streamlit as st

from impact import (
    DEMO_IDS,
    LAST_RESULTS_FILE,
    _format_sources,
    impact_indexes_ready,
    load_cases,
    load_last_results,
    run_impact,
)
from indexer import DEFAULT_INDEX_DIR
from rag import ask

# 侧边栏只放演示四题，请假 / IT / FAQ 不出现
_CASES_BY_ID = {c["id"]: c for c in load_cases()}
DEMO_QUESTIONS = [(i, _CASES_BY_ID[i]["question"]) for i in DEMO_IDS]


def _main_index_ready() -> bool:
    """检查主库 FAISS 索引是否已建。"""
    return (DEFAULT_INDEX_DIR / "index.faiss").exists()


def _render_result(result: dict) -> None:
    """展示问答结果。"""
    st.subheader("回答")
    st.markdown(result["answer"])

    if result["sources"]:
        st.subheader("引用出处")
        for s in result["sources"]:
            st.markdown(f"- **{s['source']}** 第 {s['page']} 页")


def _merge_display_rows() -> list[dict]:
    """题集为底，若有最近一次对照结果则叠上旧答 / 新答。"""
    cases = load_cases()
    last = {r["id"]: r for r in (load_last_results() or [])}
    rows = []
    for case in cases:
        row = {
            "id": case["id"],
            "question": case["question"],
            "should_flip": case["should_flip"],
            "risk": case["risk"],
            "old_conclusion": case["old_conclusion"],
            "new_conclusion": case["new_conclusion"],
        }
        saved = last.get(case["id"])
        if saved:
            row.update({
                "old_answer": saved.get("old_answer"),
                "new_answer": saved.get("new_answer"),
                "old_short": saved.get("old_short"),
                "new_short": saved.get("new_short"),
                "flipped": saved.get("flipped"),
                "aligned": saved.get("aligned"),
                "old_sources": saved.get("old_sources") or [],
                "new_sources": saved.get("new_sources") or [],
            })
        rows.append(row)
    return rows


def _flip_label(should_flip: bool) -> str:
    return "该变" if should_flip else "没变"


def _render_row_detail(row: dict, expanded: bool) -> None:
    """点开一题看旧答、新答、出处版本。"""
    title = f"{_flip_label(row['should_flip'])} · {row['risk']} · {row['question']}"
    with st.expander(title, expanded=expanded):
        st.caption(
            f"标注旧结论：{row['old_conclusion']}  |  "
            f"标注新结论：{row['new_conclusion']}"
        )
        has_answers = bool(row.get("old_answer") or row.get("new_answer"))
        if not has_answers:
            st.info("尚未生成两库回答。点击上方「运行对照」后即可看到旧答、新答。")
            return
        if row.get("old_short") is not None:
            st.caption(
                f"短结论：{row.get('old_short') or '（空）'} → "
                f"{row.get('new_short') or '（空）'}　"
                f"对齐：{'过' if row.get('aligned') else '未过'}"
            )
        col_old, col_new = st.columns(2)
        with col_old:
            st.markdown("**旧版 v1.2**")
            st.markdown(row.get("old_answer") or "")
            st.caption(f"出处：{_format_sources(row.get('old_sources') or [])}")
        with col_new:
            st.markdown("**新版 v1.3**")
            st.markdown(row.get("new_answer") or "")
            st.caption(f"出处：{_format_sources(row.get('new_sources') or [])}")


def _render_impact_table() -> None:
    """第一屏：变了 / 没变清单。"""
    if not impact_indexes_ready():
        st.error(
            "影响面索引不存在，请先在终端执行：\n\n"
            "`python main.py index-impact`"
        )
        return

    rows = _merge_display_rows()
    by_id = {r["id"]: r for r in rows}
    demo_rows = [by_id[i] for i in DEMO_IDS]
    other_rows = [r for r in rows if r["id"] not in DEMO_IDS]
    n_flip = sum(1 for r in rows if r["should_flip"])
    has_run = LAST_RESULTS_FILE.exists()
    n_aligned = sum(1 for r in rows if r.get("aligned")) if has_run else None

    c1, c2, c3 = st.columns(3)
    c1.metric("该变", f"{n_flip} 题")
    c2.metric("没变", f"{len(rows) - n_flip} 题")
    c3.metric("短结论对齐", f"{n_aligned}/{len(rows)}" if n_aligned is not None else "未跑")

    st.markdown(
        "演示只看下面四行：**住宿、餐补该变；通勤、抬头没变。** "
        "点开一题可看旧答、新答和出处版本。"
    )

    if st.button("运行对照", type="primary"):
        with st.spinner("正在对两库各问一遍，大约需要一两分钟…"):
            try:
                run_impact(k=st.session_state.get("top_k", 3))
            except RuntimeError as e:
                st.error(str(e))
                return
            except Exception as e:
                st.error(f"对照失败：{e}")
                return
        st.rerun()

    highlight_id = st.session_state.get("highlight_id")

    st.subheader("演示四题")
    table_data = []
    for row in demo_rows:
        old_s = row.get("old_short") or row["old_conclusion"]
        new_s = row.get("new_short") or row["new_conclusion"]
        table_data.append({
            "变化": _flip_label(row["should_flip"]),
            "风险": row["risk"],
            "问题": row["question"],
            "旧 → 新": f"{old_s} → {new_s}",
        })
    st.dataframe(table_data, width="stretch", hide_index=True)

    for row in demo_rows:
        _render_row_detail(row, expanded=(highlight_id == row["id"]))

    st.subheader("其余题")
    for row in other_rows:
        _render_row_detail(row, expanded=(highlight_id == row["id"]))


def _render_ask_page(k: int) -> None:
    """第二页：单题问答，当尺子，不当主产品。"""
    st.caption("聊天只是尺子。主库问答仍走原路径，用来随口验证一笔。")

    if not _main_index_ready():
        st.error(
            "主库向量索引不存在，请先在终端执行建库：\n\n"
            "`python main.py index`"
        )
        return

    question = st.text_input(
        "请输入问题",
        key="input_question",
        placeholder="例如：上海出差住了600一晚，能报多少？",
    )

    if st.button("提问", type="primary"):
        if question.strip():
            st.session_state.trigger_ask = True
        else:
            st.warning("请输入问题后再提交。")

    if st.session_state.get("trigger_ask") and question.strip():
        st.session_state.trigger_ask = False
        with st.spinner("检索并生成回答中…"):
            try:
                result = ask(question.strip(), k=k)
            except RuntimeError as e:
                st.error(str(e))
                return
            except Exception as e:
                st.error(f"请求失败：{e}")
                return
        _render_result(result)


def main():
    st.set_page_config(page_title="制度变更影响面", layout="wide")

    st.title("制度变更影响面")
    st.caption(
        "财务改完报销制度后，同一批员工常问题对旧版、新版各问一遍。"
        "变了的才需要通知；没变的不用当新闻。演示数据，不是真审批。"
    )

    if "input_question" not in st.session_state:
        st.session_state.input_question = ""

    with st.sidebar:
        st.header("设置")
        k = st.slider("检索条数 (top-k)", min_value=1, max_value=10, value=3)
        st.session_state.top_k = k

        st.header("演示四题")
        for qid, q in DEMO_QUESTIONS:
            if st.button(q, width="stretch", key=f"example_{qid}"):
                st.session_state.input_question = q
                st.session_state.highlight_id = qid

    tab_table, tab_ask = st.tabs(["影响面对照", "单题问答"])
    with tab_table:
        _render_impact_table()
    with tab_ask:
        _render_ask_page(k)


if __name__ == "__main__":
    main()
