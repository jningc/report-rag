"""
制度变更影响面：同一批题对旧库、新库各问一遍，打出对照表。

用法:
  python main.py index-impact
  python main.py impact
  python impact.py
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CASES_FILE = PROJECT_ROOT / "data" / "eval_impact.json"

# 旧版 / 新版各一份报销 PDF，分别入库，不要混进请假 / IT / FAQ
OLD_PDF = PROJECT_ROOT / "data" / "raw_pdfs_v12" / "02_reimbursement_v12.pdf"
NEW_PDF = PROJECT_ROOT / "data" / "raw_pdfs" / "02_reimbursement.pdf"
OLD_INDEX_DIR = PROJECT_ROOT / "data" / "faiss_index_v12"
NEW_INDEX_DIR = PROJECT_ROOT / "data" / "faiss_index_v13"
OLD_SOURCE = "02_reimbursement_v12.pdf"
NEW_SOURCE = "02_reimbursement.pdf"

# 制度外、缺槽允许两库都拒答，不记进检索偏题清单
ALLOW_MISS_IDS = {"bitcoin_out_of_policy", "vague_meal"}


def load_cases(cases_file=DEFAULT_CASES_FILE) -> list[dict]:
    """加载影响面题集。"""
    with open(cases_file, encoding="utf-8") as f:
        return json.load(f)


def build_impact_indexes():
    """用现有 load_pdf → 切分 → 入库，分别写出 v12 / v13 两个目录。"""
    from chunker import chunk_pages
    from docs_loader import load_pdf
    from indexer import build_index
    from retriever import clear_cache

    jobs = [
        ("v1.2", OLD_PDF, OLD_INDEX_DIR),
        ("v1.3", NEW_PDF, NEW_INDEX_DIR),
    ]
    for label, pdf_path, index_dir in jobs:
        if not pdf_path.exists():
            raise FileNotFoundError(f"{label} PDF 不存在: {pdf_path}")
        pages = load_pdf(pdf_path)
        chunks = chunk_pages(pages)
        print(f"{label} {pdf_path.name}：{len(pages)} 页 → {len(chunks)} 块，开始入库…")
        build_index(chunks, index_dir=index_dir)
        print(f"已写入: {index_dir}")
    clear_cache()


def _format_sources(sources: list[dict]) -> str:
    if not sources:
        return "（无）"
    return "；".join(f"{s.get('source')} 第{s.get('page')}页" for s in sources)


def _hit_source(sources: list[dict], expect_name: str) -> bool:
    return any(s.get("source") == expect_name for s in sources)


def _retrieval_ok(case: dict, sources: list[dict], expect_name: str) -> bool:
    """是否落到对应报销稿；制度外/缺槽允许拒答。"""
    if _hit_source(sources, expect_name):
        return True
    return (not sources) and case["id"] in ALLOW_MISS_IDS


def run_impact(k: int = 3, cases_file=DEFAULT_CASES_FILE) -> list[dict]:
    """对两库各 ask 一次，打印对照表并返回行数据。本批不做自动判分。"""
    from rag import ask

    if not OLD_INDEX_DIR.exists() or not NEW_INDEX_DIR.exists():
        raise FileNotFoundError(
            f"影响面索引不存在。请先运行: python main.py index-impact\n"
            f"  旧库: {OLD_INDEX_DIR}\n"
            f"  新库: {NEW_INDEX_DIR}"
        )

    cases = load_cases(cases_file)
    rows = []
    miss_list = []

    print(f"影响面对照（k={k}，旧库 v1.2 / 新库 v1.3）\n")
    for i, case in enumerate(cases, start=1):
        question = case["question"]
        old_result = ask(question, k=k, index_dir=OLD_INDEX_DIR)
        new_result = ask(question, k=k, index_dir=NEW_INDEX_DIR)

        old_ok = _retrieval_ok(case, old_result["sources"], OLD_SOURCE)
        new_ok = _retrieval_ok(case, new_result["sources"], NEW_SOURCE)
        flip_label = "该变" if case["should_flip"] else "不该变"

        row = {
            "id": case["id"],
            "question": question,
            "should_flip": case["should_flip"],
            "risk": case["risk"],
            "old_conclusion": case["old_conclusion"],
            "new_conclusion": case["new_conclusion"],
            "old_answer": old_result["answer"],
            "new_answer": new_result["answer"],
            "old_sources": old_result["sources"],
            "new_sources": new_result["sources"],
            "old_retrieval_ok": old_ok,
            "new_retrieval_ok": new_ok,
        }
        rows.append(row)

        print("=" * 72)
        print(f"#{i} [{flip_label}/{case['risk']}] {case['id']}")
        print(f"问: {question}")
        print(f"标注旧结论: {case['old_conclusion']}")
        print(f"标注新结论: {case['new_conclusion']}")
        print(f"旧答: {old_result['answer']}")
        print(f"新答: {new_result['answer']}")
        print(f"出处旧: {_format_sources(old_result['sources'])}")
        print(f"出处新: {_format_sources(new_result['sources'])}")
        print(f"检索旧: {'命中报销稿' if old_ok else '偏题/未命中'}")
        print(f"检索新: {'命中报销稿' if new_ok else '偏题/未命中'}")

        if not old_ok:
            miss_list.append(f"{case['id']} 旧库 出处={_format_sources(old_result['sources'])}")
        if not new_ok:
            miss_list.append(f"{case['id']} 新库 出处={_format_sources(new_result['sources'])}")

    print("=" * 72)
    print(f"\n共 {len(rows)} 题。该变 {sum(1 for r in rows if r['should_flip'])} 题，"
          f"不该变 {sum(1 for r in rows if not r['should_flip'])} 题。")
    print("本批不自动判生成对错，请先看住宿、餐补是否变了，通勤是否没变。")
    if miss_list:
        print("\n检索偏题/未命中清单（本批不上父文档、不改写查询）：")
        for item in miss_list:
            print(f"  - {item}")
    else:
        print("\n检索全部落到对应报销稿（或制度外/缺槽按约定拒答）。")
    return rows


if __name__ == "__main__":
    run_impact()
