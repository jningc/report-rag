"""
检索：从 FAISS 索引中按问题召回相关 chunk。

输入: 用户问题 str
输出: list[Document]，每条含 page_content 与 metadata（source / page）
"""

from pathlib import Path

from indexer import DEFAULT_INDEX_DIR, load_index


def search_with_scores(query: str, k: int = 3, index_dir=DEFAULT_INDEX_DIR):
    """相似度检索，返回 (Document, 相关度) 列表；相关度 0~1，越高越相关。"""
    if not query.strip():
        raise ValueError("query 不能为空")

    vs = load_index(index_dir=index_dir)
    return vs.similarity_search_with_relevance_scores(query, k=k)


def search(query: str, k: int = 3, index_dir=DEFAULT_INDEX_DIR):
    """相似度检索，返回 top-k 文档块。"""
    return [doc for doc, _ in search_with_scores(query, k=k, index_dir=index_dir)]


if __name__ == "__main__":
    query = "出差打车怎么报销？"
    hits = search(query, k=2)
    print(f"查询: {query}\n")
    for i, doc in enumerate(hits, start=1):
        print("=" * 60)
        print(f"#{i}  source: {doc.metadata.get('source')}  |  page: {doc.metadata.get('page')}")
        print("-" * 60)
        print(doc.page_content[:200])
        print()
