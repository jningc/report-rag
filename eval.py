"""
检索层测评：验证 source 命中与相似度拒答，不调用 LLM。

用法:
  python eval.py
  python main.py eval
"""

import json
from pathlib import Path

from indexer import DEFAULT_INDEX_DIR
from rag import MIN_RELEVANCE_SCORE
from retriever import search_with_scores

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CASES_FILE = PROJECT_ROOT / "data" / "eval_cases.json"


def load_cases(cases_file=DEFAULT_CASES_FILE) -> list[dict]:
    """加载测评用例。"""
    with open(cases_file, encoding="utf-8") as f:
        return json.load(f)


def check_case(case: dict, k: int = 3) -> tuple[bool, str]:
    """单条用例判定，返回 (是否通过, 说明)。"""
    hits = search_with_scores(case["question"], k=k)
    top_score = hits[0][1] if hits else 0.0
    sources = [doc.metadata.get("source") for doc, _ in hits]

    if case["should_refuse"]:
        passed = not hits or top_score < MIN_RELEVANCE_SCORE
        reason = f"top_score={top_score:.3f}, sources={sources}"
        return passed, reason

    expect_source = case["expect_source"]
    if not hits or top_score < MIN_RELEVANCE_SCORE:
        return False, f"未达阈值 top_score={top_score:.3f}, sources={sources}"
    passed = expect_source in sources
    reason = f"expect={expect_source}, top_score={top_score:.3f}, sources={sources}"
    return passed, reason


def run_eval(k: int = 3, cases_file=DEFAULT_CASES_FILE) -> int:
    """运行全部用例，打印结果并返回失败条数。"""
    if not DEFAULT_INDEX_DIR.exists():
        raise FileNotFoundError(
            f"索引目录不存在: {DEFAULT_INDEX_DIR}\n请先运行: python main.py index"
        )

    cases = load_cases(cases_file)
    passed_count = 0

    print(f"检索层测评（k={k}, 阈值={MIN_RELEVANCE_SCORE}）\n")
    for i, case in enumerate(cases, start=1):
        ok, reason = check_case(case, k=k)
        status = "PASS" if ok else "FAIL"
        if ok:
            passed_count += 1
        label = "应拒答" if case["should_refuse"] else "应命中"
        print(f"[{status}] #{i} ({label}) {case['question']}")
        print(f"       {reason}\n")

    total = len(cases)
    print(f"通过 {passed_count}/{total}")
    return total - passed_count


if __name__ == "__main__":
    failures = run_eval()
    raise SystemExit(1 if failures else 0)
