"""
RAG：检索 + 生成，返回答案与出处。

流程:
  1. search_with_scores 召回相关 chunk（含拒答判断）
  2. LangChain LCEL Chain：retriever → format_docs → prompt → LLM
  3. 返回答案 + 引用来源（source / page）
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI

from indexer import DEFAULT_INDEX_DIR
from retriever import get_retriever, search_with_scores

load_dotenv(Path(__file__).resolve().parent / ".env")

# 最高相关度低于此阈值时拒答（0~1，越高表示要求越严）
MIN_RELEVANCE_SCORE = 0.4
REFUSE_ANSWER = "根据现有资料无法回答。"

SYSTEM_PROMPT = """你是企业内部制度助手。请仅根据用户提供的「参考资料」回答问题。
规则：
1. 只使用参考资料中的信息，不要编造。
2. 若资料不足以回答，第一行写「结论：拒答」，第二行写「根据现有资料无法回答」。
3. 第一行必须是短结论，格式为「结论：…」，只能是：
   - 可报
   - 可报上限N（涉及金额上限时必须写出阿拉伯数字 N，不加「元」或空格）
   - 不可报
   - 条件分支（制度写「可否决」「须先申请」，或关键信息不足时）
   - 拒答
4. 资料里已有明确可否报或限额时，必须给出可报 / 不可报 / 可报上限N，不要写成拒答。
5. 第一行之后写依据。回答末尾列出引用，格式：[来源文件名 第N页]。"""


# def _get_llm(model=DEFAULT_MODEL):
#     """创建 DashScope 对话模型客户端。"""
#     api_key = os.environ.get("DASHSCOPE_API_KEY")
#     if not api_key:
#         raise RuntimeError("请先在环境变量或 .env 中设置 DASHSCOPE_API_KEY")
#     return ChatTongyi(model=model, dashscope_api_key=api_key)


RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "参考资料：\n\n{context}\n\n问题：{question}"),
])


def _get_llm(model=None):
    """创建 LLM 客户端。"""
    api_key = os.environ.get("DEVAGI_API_KEY")
    base_url = os.environ.get("DEVAGI_BASE_URL", "https://api.fe8.cn/v1")
    model = model or os.environ.get("DEVAGI_MODEL", "gpt-3.5-turbo")
    if not api_key:
        raise RuntimeError("请设置 DEVAGI_API_KEY")
    return ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=base_url,
    )


def format_docs(docs) -> str:
    """把检索到的 Document 列表格式化为 prompt 中的参考资料块。"""
    parts = []
    for i, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "未知")
        page = doc.metadata.get("page", "?")
        parts.append(f"[{i}] 来源: {source} 第{page}页\n{doc.page_content}")
    return "\n\n".join(parts)


def _extract_sources(docs) -> list[dict]:
    """从 Document 列表提取出处，供上层展示。"""
    sources = []
    seen = set()
    for doc in docs:
        item = {
            "source": doc.metadata.get("source"),
            "page": doc.metadata.get("page"),
        }
        key = (item["source"], item["page"])
        if key not in seen:
            seen.add(key)
            sources.append(item)
    return sources


def build_rag_chain(retriever, llm=None):
    """LangChain LCEL：检索 → 拼 prompt → LLM → 字符串。"""
    if llm is None:
        llm = _get_llm()
    return (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )


def ask(question: str, k: int = 3, model=None, index_dir=DEFAULT_INDEX_DIR) -> dict:
    """RAG 问答：拒答判断 → LCEL 生成 → 返回结构化结果。

    index_dir 指定检索库，默认主库，原有调用不用改。
    """
    if not question.strip():
        raise ValueError("question 不能为空")

    hits = search_with_scores(question, k=k, index_dir=index_dir)

    if not hits or hits[0][1] < MIN_RELEVANCE_SCORE:
        return {
            "question": question,
            "answer": REFUSE_ANSWER,
            "sources": [],
        }

    docs = [doc for doc, _ in hits]
    chain = build_rag_chain(
        get_retriever(k=k, index_dir=index_dir),
        llm=_get_llm(model=model),
    )
    answer = chain.invoke(question)

    return {
        "question": question,
        "answer": answer,
        "sources": _extract_sources(docs),
    }

if __name__ == "__main__":
    result = ask("年假怎么请？")
    print("问题:", result["question"])
    print("回答:", result["answer"])
    print("出处:", result["sources"])

