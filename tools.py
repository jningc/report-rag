"""
LangChain Tools：可被 Agent 调用或单独 invoke 的工具。

用法:
  python tools.py
  from tools import search_docs
  search_docs.invoke({"query": "年假怎么请", "k": 3})
"""

from langchain_core.tools import tool

from rag import MIN_RELEVANCE_SCORE, REFUSE_ANSWER, format_docs
from retriever import search_with_scores


@tool
def search_docs(query: str, k: int = 3) -> str:
    """在企业制度文档库中检索与 query 相关的段落，返回文本及来源页码。"""
    hits = search_with_scores(query, k=k)
    if not hits or hits[0][1] < MIN_RELEVANCE_SCORE:
        return REFUSE_ANSWER
    docs = [doc for doc, _ in hits]
    return format_docs(docs)


if __name__ == "__main__":
    result = search_docs.invoke({"query": "出差打车怎么报销", "k": 2})
    print("Tool 返回:\n", result)
