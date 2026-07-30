"""
Streamlit Web 界面：企业内部制度知识库问答

用法:
  streamlit run app.py
"""

import streamlit as st

from indexer import DEFAULT_INDEX_DIR
from rag import ask

# 侧边栏示例问题
EXAMPLE_QUESTIONS = [
    "年假怎么请",
    "出差打车怎么报销",
    "IT 问题找谁",
    "产品常见问题有哪些",
]


def _index_ready() -> bool:
    """检查 FAISS 索引是否已建。"""
    return (DEFAULT_INDEX_DIR / "index.faiss").exists()


def _render_result(result: dict) -> None:
    """展示问答结果。"""
    st.subheader("回答")
    st.markdown(result["answer"])

    if result["sources"]:
        st.subheader("引用出处")
        for s in result["sources"]:
            st.markdown(f"- **{s['source']}** 第 {s['page']} 页")


def main():
    st.set_page_config(page_title="制度知识库", layout="wide")

    st.title("企业内部制度知识库")
    st.caption("基于 PDF 制度文档的 RAG 问答，回答附带出处页码。")

    if not _index_ready():
        st.error(
            "向量索引不存在，请先在终端执行建库：\n\n"
            "`python main.py index`"
        )
        st.stop()

    if "input_question" not in st.session_state:
        st.session_state.input_question = ""

    # 侧边栏：检索参数与示例
    with st.sidebar:
        st.header("设置")
        k = st.slider("检索条数 (top-k)", min_value=1, max_value=10, value=3)

        st.header("示例问题")
        for i, q in enumerate(EXAMPLE_QUESTIONS):
            if st.button(q, use_container_width=True, key=f"example_{i}"):
                st.session_state.input_question = q
                st.session_state.trigger_ask = True

    question = st.text_input(
        "请输入问题",
        key="input_question",
        placeholder="例如：年假怎么请？",
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


if __name__ == "__main__":
    main()
