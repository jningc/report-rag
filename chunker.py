"""
切分：把 docs_loader 的按页文本切成更短的块，供后续向量化。

输入: list[dict]，每条 {"source": "文件名.pdf", "page": 1, "text": "..."}
输出: list[dict]，同结构；source/page 原样保留，text 为切出的子串。
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_pages(pages, chunk_size=100, chunk_overlap=50):
    """对每一页单独切分，不跨页合并（保证页码出处准确）。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # 默认大致是：\n\n → \n → 空格 → 字符
        # PDF 抽出来的 text 常常没有换行，会落到「空格 / 字符」继续切
    )

    chunks = []
    for page in pages:
        text = (page.get("text") or "").strip()
        if not text:
            # 空页不产出块
            continue

        # split_text: str → list[str]
        for piece in splitter.split_text(text):
            chunks.append({
                "source": page["source"],
                "page": page["page"],
                "text": piece,
            })
    return chunks


if __name__ == "__main__":
    from docs_loader import load_pdfs

    folder_path = "/Users/ning/Desktop/report-rag/data/raw_pdfs"
    pages = load_pdfs(folder_path)
    chunks = chunk_pages(pages)

    print(f"共 {len(pages)} 页 → {len(chunks)} 块\n")
    for i, item in enumerate(chunks[:5], start=1):
        print("=" * 60)
        print(f"#{i}  source: {item['source']}  |  page: {item['page']}")
        print("-" * 60)
        print(item["text"][:300])
        print()
