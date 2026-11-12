"""按引擎跑三份样本并打分，产出可对比的结果目录。

用法:
  python eval/run_engine.py --engine v2
  python eval/run_engine.py --engine v1 --docs beijing_road

产物（进 Git，供逐条 diff 与门禁读）:
  eval/engine/<engine>/<doc>/tables.json   六表（compare.py 直接吃）
  eval/engine/<engine>/<doc>/compare.json  逐题结果
  eval/engine/<engine>/<doc>/compare.txt   人读的报告
  eval/engine/<engine>/summary.json        每份文档 + 合计

索引复用：默认复用 data/tender_index（要重建加 --rebuild-index）。
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tender.engine import check  # noqa: E402

TABLES = ("feibiao", "pingfen", "cailiao", "kongwei", "shijian", "hetong")
COMPANIES = {
    "beijing_road": "sample/beijing_road_company.yaml",
    "chongzuo_green": "sample/chongzuo_green_company.yaml",
    "wenling_video": "sample/wenling_video_company.yaml",
}
OUT = ROOT / "eval" / "engine"


def run_doc(engine: str, doc: str, rebuild: bool) -> dict:
    folder = OUT / engine / doc
    folder.mkdir(parents=True, exist_ok=True)
    result = check(f"sample/{doc}.pdf", COMPANIES[doc], engine=engine, reuse_index=not rebuild)
    payload = {"doc": doc, "engine": engine,
               "missing": result.get("missing") or [],
               "contracts": result.get("contracts"),
               "tables": {t: result.get(t) or [] for t in TABLES}}
    (folder / "tables.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    out = subprocess.run(
        [sys.executable, str(ROOT / "eval" / "compare.py"), str(folder / "tables.json"),
         "--doc", doc, "-v", "--json", str(folder / "compare.json")],
        capture_output=True, text=True,
    )
    (folder / "compare.txt").write_text(out.stdout + out.stderr, encoding="utf-8")
    counts = json.loads((folder / "compare.json").read_text(encoding="utf-8"))["counts"]
    return {"doc": doc, "rows": {t: len(payload["tables"][t]) for t in TABLES},
            "contracts": payload["contracts"], "counts": counts}


def main() -> int:
    ap = argparse.ArgumentParser(description="按引擎跑三份并打分")
    ap.add_argument("--engine", choices=["v1", "v2"], required=True)
    ap.add_argument("--docs", nargs="*", choices=list(COMPANIES), default=list(COMPANIES))
    ap.add_argument("--rebuild-index", action="store_true")
    args = ap.parse_args()

    rows = []
    for doc in args.docs:
        s = run_doc(args.engine, doc, args.rebuild_index)
        rows.append(s)
        c = s["counts"]
        print(f"{doc}: 正例 {c['pos_hit']}/{c['positive']} 负例 {c['neg_hit']}/{c['negative']} "
              f"违规 {c['violated']} | 行 {sum(s['rows'].values())} | contracts {s['contracts']}",
              flush=True)

    total_pos = sum(r["counts"]["pos_hit"] for r in rows)
    total_p = sum(r["counts"]["positive"] for r in rows)
    total_neg = sum(r["counts"]["neg_hit"] for r in rows)
    total_n = sum(r["counts"]["negative"] for r in rows)
    summary = {"engine": args.engine, "docs": rows,
               "total": {"pos_hit": total_pos, "positive": total_p,
                         "neg_hit": total_neg, "negative": total_n}}
    (OUT / args.engine / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{args.engine} 合计：正例 {total_pos}/{total_p}，负例 {total_neg}/{total_n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
