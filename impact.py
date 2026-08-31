"""
制度变更影响面：同一批题对旧库、新库各问一遍，打出对照表。

用法:
  python main.py index-impact
  python main.py impact
  python impact.py
"""

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CASES_FILE = PROJECT_ROOT / "data" / "eval_impact.json"
LAST_RESULTS_FILE = PROJECT_ROOT / "data" / "impact_last.json"

# 旧版 / 新版各一份报销 PDF，分别入库，不要混进请假 / IT / FAQ
OLD_PDF = PROJECT_ROOT / "data" / "raw_pdfs_v12" / "02_reimbursement_v12.pdf"
NEW_PDF = PROJECT_ROOT / "data" / "raw_pdfs" / "02_reimbursement.pdf"
OLD_INDEX_DIR = PROJECT_ROOT / "data" / "faiss_index_v12"
NEW_INDEX_DIR = PROJECT_ROOT / "data" / "faiss_index_v13"
OLD_SOURCE = "02_reimbursement_v12.pdf"
NEW_SOURCE = "02_reimbursement.pdf"

# 制度外、缺槽允许两库都拒答，不记进检索偏题清单
ALLOW_MISS_IDS = {"bitcoin_out_of_policy", "vague_meal"}

# 演示四题：两题该变、两题没变
DEMO_IDS = ["hotel_cap", "meal_after_hospitality", "overtime_commute", "invoice_title"]
SHORT_PREFIX = "结论："
# 与 rag.SYSTEM_PROMPT 五种短结论对齐
KIND_ALLOW = "可报"
KIND_CAP = "可报上限"
KIND_DENY = "不可报"
KIND_COND = "条件分支"
KIND_REFUSE = "拒答"
# 可报上限：允许空格和「元」，数字才进 amount
_CAP_RE = re.compile(r"^可报上限\s*(\d+)\s*元?")


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


def _first_line_body(answer: str) -> str:
    """取第一行、去掉「结论：」前缀，供解析；不在这里删全部空白。"""
    # 与 rag.REFUSE_ANSWER 同文；此处不 import rag，对照测试不加载 LLM 依赖
    refuse = "根据现有资料无法回答。"
    text = (answer or "").strip()
    if not text:
        return ""
    if text == refuse or text.startswith(refuse):
        return KIND_REFUSE
    first = text.splitlines()[0].strip().rstrip("。.;；")
    if first.startswith(SHORT_PREFIX):
        first = first[len(SHORT_PREFIX):].strip()
    return first


def parse_short_conclusion(answer: str) -> dict:
    """把短结论解析成 kind / amount，对照只比这两个槽。"""
    first = _first_line_body(answer)
    if not first:
        return {"kind": "", "amount": None}
    if first == KIND_REFUSE or first.startswith(KIND_REFUSE):
        return {"kind": KIND_REFUSE, "amount": None}
    cap = _CAP_RE.match(first)
    if cap:
        return {"kind": KIND_CAP, "amount": int(cap.group(1))}
    if first.startswith(KIND_DENY):
        return {"kind": KIND_DENY, "amount": None}
    if first.startswith(KIND_COND):
        return {"kind": KIND_COND, "amount": None}
    if first.startswith(KIND_ALLOW):
        return {"kind": KIND_ALLOW, "amount": None}
    return {"kind": "".join(first.split()), "amount": None}


def format_short_conclusion(parsed: dict) -> str:
    """展示用规范短句；上限只保留数字，不带「元」。"""
    kind = parsed.get("kind") or ""
    amount = parsed.get("amount")
    if kind == KIND_CAP and amount is not None:
        return f"{KIND_CAP}{amount}"
    return kind


def extract_short_conclusion(answer: str) -> str:
    """第一行短结论的规范展示串，供界面和落盘。"""
    return format_short_conclusion(parse_short_conclusion(answer))


def conclusions_flipped(old_parsed: dict, new_parsed: dict) -> bool:
    """仅当 kind 或 amount 不同时视为翻转。"""
    return (old_parsed.get("kind"), old_parsed.get("amount")) != (
        new_parsed.get("kind"),
        new_parsed.get("amount"),
    )


def score_flip(old_text: str, new_text: str, should_flip: bool) -> bool:
    """字段对齐：两版是否变化 与 should_flip 一致即算过。"""
    return conclusions_flipped(
        parse_short_conclusion(old_text),
        parse_short_conclusion(new_text),
    ) == should_flip


def impact_indexes_ready() -> bool:
    """两个影响面索引是否都已建好。"""
    return (OLD_INDEX_DIR / "index.faiss").exists() and (NEW_INDEX_DIR / "index.faiss").exists()


def save_last_results(rows: list[dict], path=LAST_RESULTS_FILE):
    """把最近一次对照结果写成 JSON，供界面直接展示。"""
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def load_last_results(path=LAST_RESULTS_FILE) -> list[dict] | None:
    """读取最近一次对照结果；没有文件则返回 None。"""
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_impact(k: int = 3, cases_file=DEFAULT_CASES_FILE) -> list[dict]:
    """对两库各 ask 一次，打印对照表，用短结论对齐 should_flip。"""
    from rag import ask

    if not impact_indexes_ready():
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
        old_parsed = parse_short_conclusion(old_result["answer"])
        new_parsed = parse_short_conclusion(new_result["answer"])
        old_short = format_short_conclusion(old_parsed)
        new_short = format_short_conclusion(new_parsed)
        flipped = conclusions_flipped(old_parsed, new_parsed)
        aligned = flipped == case["should_flip"]

        row = {
            "id": case["id"],
            "question": question,
            "should_flip": case["should_flip"],
            "risk": case["risk"],
            "old_conclusion": case["old_conclusion"],
            "new_conclusion": case["new_conclusion"],
            "old_answer": old_result["answer"],
            "new_answer": new_result["answer"],
            "old_short": old_short,
            "new_short": new_short,
            "flipped": flipped,
            "aligned": aligned,
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
        print(f"短结论旧: {old_short}")
        print(f"短结论新: {new_short}")
        print(f"对齐: {'过' if aligned else '未过'}（标注{flip_label}，实判{'变了' if flipped else '没变'}）")
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

    n_flip = sum(1 for r in rows if r["should_flip"])
    n_ok = sum(1 for r in rows if r["aligned"])
    print("=" * 72)
    print(f"\n共 {len(rows)} 题。该变 {n_flip} 题，不该变 {len(rows) - n_flip} 题。")
    print(f"短结论对齐 {n_ok}/{len(rows)} 题（should_flip 对上算过）。")
    if miss_list:
        print("\n检索偏题/未命中清单（本批不上父文档、不改写查询）：")
        for item in miss_list:
            print(f"  - {item}")
    else:
        print("\n检索全部落到对应报销稿（或制度外/缺槽按约定拒答）。")
    save_last_results(rows)
    print(f"已写入: {LAST_RESULTS_FILE}")
    return rows


if __name__ == "__main__":
    run_impact()
