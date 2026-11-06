"""
从pdf 按页提取文本
输入: pdf路径
输出: list[dict]，一页一条，例如：
    {"source": "文件名.pdf", "page": 1, "text": "该页文字"}
source / page 留给后面出处引用；text 留给切分与向量化。
"""

import pdfplumber
from pathlib import Path
def load_pdf(pdf_path):
    """读取单个 PDF，返回带页码的文本列表。"""
    path = Path(pdf_path) # path得到的是啥样?


    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            #pdf.pages [<Page:1>, <Page:2>, <Page:3>, <Page:4>, <Page:5>, <Page:6>]
            text = page.extract_text() or ""
            pages.append({
                "source": path.name,
                "page": i, 
                "text": text,
            })
    return pages    

def load_pdfs(folder_path):
    """读某文件夹下所有 PDF，返回扁平列表（一页一条）。

    每条格式与 load_pdf 相同：
        {"source": "文件名.pdf", "page": 1, "text": "..."}
    """
    folder = Path(folder_path)
    all_pages = []
    # 排序后顺序稳定，方便调试对照
    for pdf_file in sorted(folder.glob("*.pdf")):
        all_pages.extend(load_pdf(pdf_file))
    return all_pages


if __name__ == "__main__":
    folder_path = "/Users/ning/Desktop/report-rag/data/raw_pdfs"
    pages = load_pdfs(folder_path)
    print(f"共 {len(pages)} 页（来自多个 PDF）\n")
    for item in pages:
        print("=" * 60)
        print(f"source: {item['source']}  |  page: {item['page']}")
        print("-" * 60)
        print(item["text"])
        print()

