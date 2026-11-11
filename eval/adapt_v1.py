"""把 v1 基线的六表转成契约对象，量出「现状有多少条能进契约」。

阶段 1 的验收不是「转得过去」——v1 里 45% 的出处没有 bbox，按契约就是不放行。
所以这个脚本的产出是**转化率 + 拒绝原因分布**，作为阶段 2 的对照起点。

用法:
  python eval/adapt_v1.py                 # 三份都转
  python eval/adapt_v1.py --docs beijing_road

产物（进 Git）:
  eval/contracts/<doc>/clauses.json   能进契约的条款
  eval/contracts/<doc>/findings.json  有 verdict 的差异条目
  eval/contracts/<doc>/rejects.json   被挡下的行 + 原因
  eval/contracts/<doc>/summary.json   转化率、条款级框占比、拒绝原因计数
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from tender.contracts import (  # noqa: E402
    Clause,
    ContractError,
    Evidence,
    Finding,
    is_clause_level,
)

BASELINE = ROOT / "eval" / "baseline"
OUT = ROOT / "eval" / "contracts"
DOCS = ["beijing_road", "chongzuo_green", "wenling_video"]

# 表 → (条款类型, 拼成 text 的字段)
TABLE_FIELDS = {
    "feibiao": ("废标", ["condition"]),
    "pingfen": ("评分", ["item", "score", "standard"]),
    "cailiao": ("材料", ["material"]),
    "kongwei": ("空位", ["form", "field"]),
    "shijian": ("时间", ["name", "when"]),
    "hetong": ("合同", ["item", "content"]),
}


def _ev(raw: dict) -> Evidence:
    """一条 ref → Evidence。缺页、缺框、缺原文都直接抛，让上层记拒绝原因。"""
    return Evidence(
        page=raw.get("page") or 0,
        bbox=raw.get("bbox") or [],
        text=(raw.get("text") or "").strip(),
        chapter=raw.get("chapter") or "",
        clause=raw.get("clause") or "",
    )


def _text(row: dict, fields: list[str]) -> str:
    parts = [str(row.get(f) or "").strip() for f in fields]
    return "；".join(p for p in parts if p)


def adapt_doc(doc: str) -> dict:
    tables = json.loads((BASELINE / doc / "tables.json").read_text(encoding="utf-8"))["tables"]
    clauses, findings, rejects = [], [], []
    reasons = Counter()
    evidence_total = evidence_clause_level = 0
    rows_total = 0

    for key, (ctype, fields) in TABLE_FIELDS.items():
        for i, row in enumerate(tables.get(key) or []):
            rows_total += 1
            rid = f"{doc}:{key}:{i:03d}"
            text = _text(row, fields)
            refs = row.get("refs") or []

            if not text:
                rejects.append({"row": rid, "reason": "text_empty"})
                reasons["text_empty"] += 1
                continue
            if not refs:
                rejects.append({"row": rid, "reason": "no_refs"})
                reasons["no_refs"] += 1
                continue

            ok_evs, bad = [], []
            for raw in refs:
                try:
                    ev = _ev(raw)
                except (ValidationError, ContractError) as e:
                    bad.append(str(e).split("\n")[0][:80])
                    continue
                ok_evs.append(ev)
                evidence_total += 1
                if is_clause_level(ev):
                    evidence_clause_level += 1

            if not ok_evs:
                rejects.append({"row": rid, "reason": "evidence_invalid", "detail": bad[:2], "text": text[:80]})
                reasons["evidence_invalid"] += 1
                continue

            try:
                clause = Clause(
                    id=rid, type=ctype, text=text,
                    evidence=ok_evs[0], extra=ok_evs[1:],
                    star=bool(row.get("star")),
                )
            except (ValidationError, ContractError) as e:
                rejects.append({"row": rid, "reason": "clause_invalid", "detail": str(e)[:120]})
                reasons["clause_invalid"] += 1
                continue
            clauses.append(clause)

            verdict = row.get("verdict")
            if verdict:
                try:
                    findings.append(Finding(
                        clause_id=rid, table=clause.table, verdict=verdict,
                        evidence=ok_evs, note=(row.get("company") or "")[:120],
                    ))
                except (ValidationError, ContractError) as e:
                    rejects.append({"row": rid, "reason": "finding_invalid", "detail": str(e)[:120]})
                    reasons["finding_invalid"] += 1

            if bad:
                reasons["partial_refs_dropped"] += len(bad)

    summary = {
        "doc": doc,
        "rows": rows_total,
        "clauses": len(clauses),
        "findings": len(findings),
        "rejects": len(rejects),
        "reject_reasons": dict(reasons),
        "convert_rate": round(len(clauses) / rows_total, 3) if rows_total else None,
        "evidence_refs": evidence_total,
        "clause_level_refs": evidence_clause_level,
        "clause_level_rate": round(evidence_clause_level / evidence_total, 3) if evidence_total else None,
    }

    folder = OUT / doc
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "clauses.json").write_text(
        json.dumps([c.model_dump() for c in clauses], ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "findings.json").write_text(
        json.dumps([f.model_dump() for f in findings], ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "rejects.json").write_text(
        json.dumps(rejects, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="v1 六表 → 契约对象")
    ap.add_argument("--docs", nargs="*", choices=DOCS, help="默认三份")
    args = ap.parse_args()

    docs = args.docs or DOCS
    missing = [d for d in docs if not (BASELINE / d / "tables.json").exists()]
    if missing:
        print(f"缺基线产物：{missing}，先跑 eval/freeze_baseline.py", flush=True)
        return 1

    out = []
    for doc in docs:
        s = adapt_doc(doc)
        out.append(s)
        print(f"{doc}: 行 {s['rows']} → 条款 {s['clauses']}（{s['convert_rate']:.0%}）"
              f"· 差异 {s['findings']} · 拒绝 {s['rejects']} {s['reject_reasons']}"
              f"· 条款级框 {s['clause_level_refs']}/{s['evidence_refs']}（{s['clause_level_rate']:.0%}）",
              flush=True)
    (OUT / "summary.json").write_text(
        json.dumps({"docs": out}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n契约样例已写到 {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
