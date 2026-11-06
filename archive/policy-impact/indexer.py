"""
向量化 + 入库：把 chunker 产出的文本块写入 FAISS。

输入: list[dict]，每条 {"source": "文件名.pdf", "page": 1, "text": "..."}
选型:
   - embedding: HuggingFace BAAI/bge-small-zh-v1.5（本地）
   - 旧方案: DashScopeEmbeddings(model="text-embedding-v3")
  - 向量库: FAISS（LangChain 封装，metadata 随 Document 一并保存）
"""

import os
from pathlib import Path

from dotenv import load_dotenv
# from langchain_community.embeddings import DashScopeEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

# 从项目根目录 .env 读取 DASHSCOPE_API_KEY
load_dotenv(Path(__file__).resolve().parent / ".env")

# 默认落盘目录
DEFAULT_INDEX_DIR = Path(__file__).resolve().parent / "data" / "faiss_index"
# DEFAULT_MODEL = "text-embedding-v3"
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"

# def get_embeddings(model=DEFAULT_MODEL):
#     """创建 DashScope embedding 客户端；需设置环境变量 DASHSCOPE_API_KEY。"""
#     api_key = os.environ.get("DASHSCOPE_API_KEY")
#     if not api_key:
#         raise RuntimeError("请先在环境变量或 .env 中设置 DASHSCOPE_API_KEY")
#     return DashScopeEmbeddings(model=model, dashscope_api_key=api_key)
def get_embeddings(model=DEFAULT_MODEL):
    """创建本地 BGE embedding；无需 API Key。"""
    return HuggingFaceEmbeddings(
        model_name=model,
        model_kwargs={"device": "cpu"},  # 有 NVIDIA GPU 可改为 "cuda"
        encode_kwargs={"normalize_embeddings": True},
    )

def build_index(chunks, index_dir=DEFAULT_INDEX_DIR, model=DEFAULT_MODEL):
    """将 chunks 向量化并写入 FAISS，同时持久化到本地目录。
    返回: FAISS 向量库实例
    """
    if not chunks:
        raise ValueError("chunks 为空，无法建库")

    texts = [c["text"] for c in chunks]
    metadatas = [{"source": c["source"], "page": c["page"]} for c in chunks]

    embeddings = get_embeddings(model=model)
    # LangChain 的 FAISS 会把 text + metadata 存在 docstore，与向量下标对齐
    vectorstore = FAISS.from_texts(texts, embeddings, metadatas=metadatas)

    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(index_dir))
    return vectorstore


def load_index(index_dir=DEFAULT_INDEX_DIR, model=DEFAULT_MODEL):
    """从本地目录加载已保存的 FAISS 索引。"""
    index_dir = Path(index_dir)
    if not index_dir.exists():
        raise FileNotFoundError(f"索引目录不存在: {index_dir}")

    embeddings = get_embeddings(model=model)
    # allow_dangerous_deserialization: 加载本地自己生成的 pkl 元数据
    return FAISS.load_local(
        str(index_dir),
        embeddings,
        allow_dangerous_deserialization=True,
    )


if __name__ == "__main__":
    from docs_loader import load_pdfs
    from chunker import chunk_pages

    folder_path = "/Users/ning/Desktop/report-rag/data/raw_pdfs"
    pages = load_pdfs(folder_path)
    chunks = chunk_pages(pages)
    print(f"共 {len(pages)} 页 → {len(chunks)} 块，开始入库…")

    vs = build_index(chunks)
    print(f"已写入: {DEFAULT_INDEX_DIR}")

    # 冒烟：检索一条，确认能带回 source / page
    query = "出差打车怎么报销？"
    hits = vs.similarity_search(query, k=3)
    print(f"\n查询: {query}\n")
    for i, doc in enumerate(hits, start=1):
        print("=" * 60)
        print(f"#{i}  source: {doc.metadata.get('source')}  |  page: {doc.metadata.get('page')}")
        print("-" * 60)
        print(doc.page_content[:200])
        print()
