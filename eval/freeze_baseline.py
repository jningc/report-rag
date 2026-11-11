"""冻结 v1 基线：三份样本各跑一次核对，把六表原样存下来，供改造后逐条对比。

用法:
  python eval/freeze_baseline.py                    # 跑三份样本
  python eval/freeze_baseline.py --docs beijing_road

产物（进 Git，data/ 不进）:
  eval/baseline/<doc>/check.txt      render_tables 的文本，compare.py 直接吃
  eval/baseline/<doc>/tables.json    六条表 + missing 的原始数据
  eval/baseline/<doc>/sections.json  切章结果，改造后要能对上
  eval/baseline/<doc>/meta.json      页数、条数、耗时、模型、git 提交
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tender.workflow import render_tables, run_check  # noqa: E402

DOCS = {
    "beijing_road": ROOT / "sample" / "beijing_road.pdf",
    "chongzuo_green": ROOT / "sample" / "chongzuo_green.pdf",
    "wenling_video": ROOT / "sample" / "wenling_video.pdf",
}
COMPANY = ROOT / "sample" / "company.yaml"
OUT = ROOT / "eval" / "baseline"
TABLES = ["feibiao", "pingfen", "cailiao", "kongwei", "shijian", "hetong"]


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return ""


def freeze(doc: str, pdf: Path) -> dict:
    """跑一次核对，落四份产物，返回 meta。"""
    folder = OUT / doc
    folder.mkdir(parents=True, exist_ok=True)
    print(f"\n=== {doc}（{pdf.name}）", flush=True)

    started = datetime.now().isoformat(timespec="seconds")
    t0 = time.time()
    result = run_check(str(pdf), str(COMPANY))
    duration = round(time.time() - t0, 1)

    text = render_tables(result)
    (folder / "check.txt").write_text(text, encoding="utf-8")
    (folder / "tables.json").write_text(
        json.dumps(
            {
                "doc": doc,
                "missing": result.get("missing") or [],
                "tables": {k: result.get(k) or [] for k in TABLES},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (folder / "sections.json").write_text(
        json.dumps(result.get("sections") or [], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    counts = {k: len(result.get(k) or []) for k in TABLES}
    meta = {
        "doc": doc,
        "pdf": str(pdf.relative_to(ROOT)),
        "started": started,
        "duration_s": duration,
        "pages": len(result.get("pages") or []),
        "sections": len(result.get("sections") or []),
        "missing_sections": result.get("missing") or [],
        "rows": counts,
        "git_commit": _git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"    {counts}  {duration}s", flush=True)
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description="冻结 v1 基线")
    ap.add_argument("--docs", nargs="*", choices=list(DOCS), help="默认跑全部")
    ap.add_argument("--skip-compare", action="store_true", help="只出表，不打分")
    args = ap.parse_args()

    docs = args.docs or list(DOCS)
    missing = [d for d in docs if not DOCS[d].exists()]
    if missing:
        print(f"缺 PDF：{missing}，先按 sample/sources.md 下载", flush=True)
        return 1

    metas = []
    for doc in docs:
        metas.append(freeze(doc, DOCS[doc]))

    # 只跑了部分文档时，保留其余文档已有的 meta，别把 summary 冲掉
    summary_path = OUT / "summary.json"
    kept = {}
    if summary_path.exists():
        old = json.loads(summary_path.read_text(encoding="utf-8")).get("docs", [])
        kept = {m["doc"]: m for m in old}
    kept.update({m["doc"]: m for m in metas})
    summary_path.write_text(
        json.dumps(
            {
                "frozen_at": datetime.now().isoformat(timespec="seconds"),
                "engine": "v1",
                "docs": [kept[d] for d in DOCS if d in kept],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if not args.skip_compare:
        print("\n=== compare.py 基线分", flush=True)
        for doc in docs:
            # 用结构化产物打分（渲染文本会丢字段）；JSON 留给门禁读
            out = subprocess.run(
                [sys.executable, str(ROOT / "eval" / "compare.py"),
                 str(OUT / doc / "tables.json"), "--doc", doc, "-v",
                 "--json", str(OUT / doc / "compare.json")],
                capture_output=True, text=True,
            )
            (OUT / doc / "compare.txt").write_text(out.stdout + out.stderr, encoding="utf-8")
            print(f"-- {doc}\n{out.stdout.strip()}", flush=True)

    print(f"\n基线已冻结到 {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
