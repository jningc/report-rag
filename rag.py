"""
RAG：检索 + 生成，返回答案与出处。

流程:
  1. retriever.search 召回相关 chunk
  2. 拼 prompt，调用 DashScope LLM
  3. 返回答案 + 引用来源（source / page）
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import HumanMessage, SystemMessage

from retriever import search_with_scores

load_dotenv(Path(__file__).resolve().parent / ".env")

DEFAULT_MODEL = "qwen-plus"
# 最高相关度低于此阈值时拒答（0~1，越高表示要求越严）
MIN_RELEVANCE_SCORE = 0.3
REFUSE_ANSWER = "根据现有资料无法回答。"

SYSTEM_PROMPT = """你是企业内部制度助手。请仅根据用户提供的「参考资料」回答问题。
规则：
1. 只使用参考资料中的信息，不要编造。
2. 若资料不足以回答，请明确说「根据现有资料无法回答」。
3. 回答末尾列出引用，格式：[来源文件名 第N页]。"""


def _get_llm(model=DEFAULT_MODEL):
    """创建 DashScope 对话模型客户端。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("请先在环境变量或 .env 中设置 DASHSCOPE_API_KEY")
    return ChatTongyi(model=model, dashscope_api_key=api_key)


def _format_context(docs) -> str:
    """把检索到的 Document 列表格式化为 prompt 中的参考资料块。"""
    parts = []
    for i, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "未知")
        page = doc.metadata.get("page", "?")
        parts.append(f"[{i}] 来源: {source} 第{page}页\n{doc.page_content}")
    return "\n\n".join(parts) #把参考资料块拼接成一个字符串,每块之间用两个换行符隔开


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


def ask(question: str, k: int = 3, model=DEFAULT_MODEL) -> dict:
    """RAG 问答：检索 → 生成 → 返回结构化结果。

    返回:
        {
            "question": str,
            "answer": str,
            "sources": [{"source": ..., "page": ...}, ...],
        }
    """
    if not question.strip():
        raise ValueError("question 不能为空")

    hits = search_with_scores(question, k=k)

    # 拒答：无结果，或最高相关度不够
    if not hits or hits[0][1] < MIN_RELEVANCE_SCORE:
        return {
            "question": question,
            "answer": REFUSE_ANSWER,
            "sources": [],
        }

    docs = [doc for doc, _ in hits]

    context = _format_context(docs) #把检索到的 Document 列表格式化为 prompt 中的参考资料块
    user_prompt = f"参考资料：\n\n{context}\n\n问题：{question}"

    llm = _get_llm(model=model)
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT), #系统提示词
        HumanMessage(content=user_prompt), #用户提示词
    ])
    #返回结构化结果
    return {
        "question": question,
        "answer": response.content,
        "sources": _extract_sources(docs),
    }


if __name__ == "__main__":
    result = ask("年假怎么请？")
    print("问题:", result["question"])
    print("回答:", result["answer"])
    print("出处:", result["sources"])
