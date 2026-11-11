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

from tender.workflow import render_tables, run_check, run_check_saved  # noqa: E402

DOCS = {
    # 三份行业不同，各配一家虚构公司；基线必须成对读，不能拿北京的公司去对崇左
    "beijing_road": {
        "pdf": ROOT / "sample" / "beijing_road.pdf",
        "company": ROOT / "sample" / "beijing_road_company.yaml",
    },
    "chongzuo_green": {
        "pdf": ROOT / "sample" / "chongzuo_green.pdf",
        "company": ROOT / "sample" / "chongzuo_green_company.yaml",
    },
    "wenling_video": {
        "pdf": ROOT / "sample" / "wenling_video.pdf",
        "company": ROOT / "sample" / "wenling_video_company.yaml",
    },
}
OUT = ROOT / "eval" / "baseline"
TABLES = ["feibiao", "pingfen", "cailiao", "kongwei", "shijian", "hetong"]


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        return ""


def _sha(path: Path) -> str:
    """公司文件指纹：改了公司就像换了题，基线不能混着比。"""
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def freeze(doc: str, pdf: Path, company: Path, reuse_index: bool = True) -> dict:
    """跑一次核对，落四份产物，返回 meta。"""
    folder = OUT / doc
    folder.mkdir(parents=True, exist_ok=True)
    cached = (ROOT / "data" / "tender_index" / pdf.stem / "manifest.json").exists()
    mode = "cached-index" if (reuse_index and cached) else "full-parse"
    print(f"\n=== {doc}（{pdf.name} + {company.name}，{mode}）", flush=True)

    started = datetime.now().isoformat(timespec="seconds")
    t0 = time.time()
    runner = run_check_saved if mode == "cached-index" else run_check
    result = runner(str(pdf), str(company))
    duration = round(time.time() - t0, 1)

    text = render_tables(result)
    (folder / "check.txt").write_text(text, encoding="utf-8")
    (folder / "tables.json").write_text(
        json.dumps(
            {
                "doc": doc,
                "missing": result.get("missing") or [],
                "tables": {k: result.get(k) or [] for k in TABLES},
                "dropped": result.get("dropped") or {},
                "degraded": result.get("degraded") or {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (folder / "dropped_rows.json").write_text(
        json.dumps(
            {
                "doc": doc,
                "dropped": result.get("dropped") or {},
                "degraded": result.get("degraded") or {},
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
        "company": str(company.relative_to(ROOT)),
        "company_sha256": _sha(company),
        "page_numbering": "physical",  # 页码一律 PDF 物理页；页脚印刷页码 beijing/chongzuo 差 2、wenling 一致
        "engine_mode": mode,
        "started": started,
        "duration_s": duration,
        "pages": len(result.get("pages") or []) or result.get("page_count") or 0,
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
    ap.add_argument("--rebuild-index", action="store_true",
                    help="强制重新解析和向量化（默认复用 data/tender_index 里已有索引）")
    args = ap.parse_args()

    docs = args.docs or list(DOCS)
    missing = [d for d in docs
               if not DOCS[d]["pdf"].exists() or not DOCS[d]["company"].exists()]
    if missing:
        print(f"缺 PDF 或公司文件：{missing}，先按 sample/sources.md 下载/补齐", flush=True)
        return 1

    metas = []
    for doc in docs:
        metas.append(freeze(doc, DOCS[doc]["pdf"], DOCS[doc]["company"],
                            reuse_index=not args.rebuild_index))

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

        _attach_eval(summary_path, docs)

    print(f"\n基线已冻结到 {OUT}", flush=True)
    return 0


def _attach_eval(summary_path: Path, docs: list[str]) -> None:
    """把 compare.json 的分数并进 summary，别让 summary 只剩行数没有分数。"""
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    by_doc = {m["doc"]: m for m in summary.get("docs", [])}
    for doc in docs:
        cmp_path = OUT / doc / "compare.json"
        if not cmp_path.exists():
            continue
        cmp = json.loads(cmp_path.read_text(encoding="utf-8"))
        c = cmp["counts"]
        by_doc[doc]["eval"] = {
            "questions": c["total"], "positive": c["positive"], "negative": c["negative"],
            "pos_hit": c["pos_hit"], "miss": c["miss"], "absent": c["absent"],
            "neg_hit": c["neg_hit"], "violated": c["violated"],
            "verdict_checked": c.get("verdict_checked", 0),
            "positive_rate": round(c["pos_hit"] / c["positive"], 3) if c["positive"] else None,
            "rows": cmp["rows"], "rows_without_page": cmp["rows_without_page"],
            "markers": cmp.get("markers"),
        }
    summary["docs"] = [by_doc[d] for d in DOCS if d in by_doc]
    summary["question_set"] = {
        **{k: v for k, v in summary.get("question_set", {}).items() if k != "total"},
        "file": "eval/questions.json",
        "total": len(json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))["questions"]),
        "markers_file": "eval/markers.json",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
