"""
CLI 入口：建库 / 问答 / 影响面对照

用法:
  python main.py index              # 从 PDF 建库
  python main.py ask "年假怎么请"    # RAG 问答
  python main.py index-impact       # 旧/新报销稿各建一个库
  python main.py impact             # 同一批题对两库各问一遍
"""

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PDF_DIR = PROJECT_ROOT / "data" / "raw_pdfs"


def cmd_index(args):
    """读取 PDF → 切分 → 向量化入库。"""
    from chunker import chunk_pages
    from docs_loader import load_pdfs
    from indexer import DEFAULT_INDEX_DIR, build_index

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF 目录不存在: {pdf_dir}")

    pages = load_pdfs(pdf_dir)
    chunks = chunk_pages(pages)
    print(f"共 {len(pages)} 页 → {len(chunks)} 块，开始入库…")

    build_index(chunks, index_dir=DEFAULT_INDEX_DIR)
    print(f"已写入: {DEFAULT_INDEX_DIR}")


def cmd_ask(args):
    """RAG 问答。"""
    from indexer import DEFAULT_INDEX_DIR
    from rag import ask

    index_dir = args.index_dir or DEFAULT_INDEX_DIR
    result = ask(args.question, k=args.k, index_dir=index_dir)
    print(f"\n问题: {result['question']}\n")
    print(result["answer"])
    if result["sources"]:
        print("\n引用出处:")
        for s in result["sources"]:
            print(f"  - {s['source']} 第{s['page']}页")


def cmd_eval(args):
    """检索层测评。"""
    from eval import run_eval

    failures = run_eval(k=args.k)
    if failures:
        raise SystemExit(1)


def cmd_index_impact(args):
    """旧版、新版报销稿分别入库。"""
    from impact import build_impact_indexes

    build_impact_indexes()


def cmd_impact(args):
    """同一批题对两库各问一遍，打印对照表。"""
    from impact import run_impact

    run_impact(k=args.k)


def main():
#   parser = argparse.ArgumentParser(...)   # 1. 创建解析器
#   parser.add_argument("command", help="命令")   # 2. 声明参数
#   args = parser.parse_args()              # 3. 解析 sys.argv
#   # 4. 用 args.xxx
    parser = argparse.ArgumentParser(description="report-rag 企业内部制度知识库")
    sub = parser.add_subparsers(dest="command", required=True)
# 子命令 index
    p_index = sub.add_parser("index", help="从 PDF 建库")
    p_index.add_argument(
        "--pdf-dir",
        default=str(DEFAULT_PDF_DIR),
        help=f"PDF 目录，默认 {DEFAULT_PDF_DIR}",
    )
    p_index.set_defaults(func=cmd_index)
# 子命令 ask

    p_ask = sub.add_parser("ask", help="RAG 问答")
    p_ask.add_argument("question", help="用户问题")
    p_ask.add_argument("-k", type=int, default=3, help="检索条数，默认 3")
    p_ask.add_argument(
        "--index-dir",
        default=None,
        help="索引目录，默认 data/faiss_index",
    )
    p_ask.set_defaults(func=cmd_ask)
# 子命令 eval
    p_eval = sub.add_parser("eval", help="检索层测评（不调 LLM）")
    p_eval.add_argument("-k", type=int, default=3, help="检索条数，默认 3")
    p_eval.set_defaults(func=cmd_eval)
# 子命令 index-impact
    p_index_impact = sub.add_parser("index-impact", help="旧/新报销稿各建一个库")
    p_index_impact.set_defaults(func=cmd_index_impact)
# 子命令 impact
    p_impact = sub.add_parser("impact", help="同一批题对两库各问一遍，打出对照表")
    p_impact.add_argument("-k", type=int, default=3, help="检索条数，默认 3")
    p_impact.set_defaults(func=cmd_impact)

    args = parser.parse_args()
    args.func(args)# 根据子命令调用对应函数


if __name__ == "__main__":
    main()
