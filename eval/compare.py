"""对着人工核过的题集，给一次 check 的输出打分。

用法:
  python eval/compare.py eval/baseline/beijing_road/check.txt --doc beijing_road -v
  python eval/compare.py <check.txt> --doc <doc> --json out.json   # 门禁读这个
  python eval/compare.py <check.txt> --json -                     # JSON 打到 stdout

判定（只读文本、不调模型）：
  候选 = 落在 tables 允许的表里、且正文含 keyword 的条目
  正例：没有候选 → absent；候选页码与 expect_pages 有交集 → hit；否则 → miss
  负例：没有候选 → hit（该表确实没混进来）；有候选 → violated
  多余页码不算错，单独记成 extra_pages，是排查串章、引错页的信号
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = Path(__file__).resolve().parent / "questions.json"

ROW_RE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*(?:\[([\d,\s]+)\]|\[无页码\])\s*$")

# tables.json 的键 → render_tables 的表标题，题集里用中文名
TABLE_TITLES = {
    "feibiao": "废标对照",
    "pingfen": "评分对照",
    "cailiao": "材料对照",
    "kongwei": "空位对照",
    "shijian": "时间节点",
    "hetong": "合同要点",
}


def load_rows(path: Path):
    """读一次核对的产物：.json（结构化，优先）或 .txt（渲染后的文本）。

    json 更可信：渲染会丢字段（例如评分表的 standard 不打印），文本打分就摸不到。
    """
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        tables = data.get("tables") if isinstance(data.get("tables"), dict) else data
        rows = []
        for key, items in tables.items():
            title = TABLE_TITLES.get(key, key)
            for r in items or []:
                pages = sorted({x.get("page") for x in (r.get("refs") or []) if x.get("page")})
                rows.append({
                    "table": title,
                    "text": json.dumps(r, ensure_ascii=False),
                    "pages": pages,
                    "no_page": not pages,
                    "verdict": r.get("verdict"),
                    "star": bool(r.get("star")),
                })
        return rows
    return parse_rows(path)


VERDICTS = {"满足", "不满足", "人工看", "无须提供"}


def parse_rows(path: Path):
    """返回 [{table, text, pages, no_page}]，table 是 render_tables 的表标题。"""
    rows, table = [], ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^== (.+?) \d+ 条 ==", line.strip())
        if m:
            table = m.group(1)
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        pages = [int(x) for x in re.split(r"[,\s]+", m.group(3) or "") if x.strip().isdigit()]
        text = m.group(2)
        head = text.split("|")[0].strip()
        rows.append({
            "table": table,
            "text": text,
            "pages": pages,
            "no_page": m.group(3) is None,
            # 渲染文本里废标/材料两表的第一列就是判定值，能捞到；别的表捞不到
            "verdict": head if head in VERDICTS else None,
            "star": False,
        })
    return rows


def marker_report(rows, doc):
    """★/▲ 对账：原文标记数 vs 废标表里 star=True 的行数。"""
    path = Path(__file__).resolve().parent / "markers.json"
    if not path.exists() or not doc:
        return None
    meta = json.loads(path.read_text(encoding="utf-8"))["docs"].get(doc)
    if not meta:
        return None
    total = sum(meta["total"].values())
    marker_pages = set(meta.get("marker_pages") or [])
    star_rows = [r for r in rows if r.get("star")]
    cited = set()
    for r in star_rows:
        cited |= set(r["pages"])
    return {
        "markers_total": total,
        "markers_by_char": meta["total"],
        "marker_pages": sorted(marker_pages),
        "star_rows": len(star_rows),
        "covered_pages": sorted(cited & marker_pages),
        "missed_pages": sorted(marker_pages - cited),
        "note": meta.get("note", ""),
    }


def _candidates(rows, q):
    """落对表、且含关键词的候选条目。"""
    return [r for r in rows if r["table"] in q["tables"] and q["keyword"] in r["text"]]


def _passes(r, q):
    """这一条候选算不算过：页码命中，且（若题面要求）判定值也在允许集合里。"""
    if not (set(r["pages"]) & set(q.get("expect_pages") or [])):
        return False
    want = q.get("expect_verdict")
    if want is None:
        return True
    want = want if isinstance(want, list) else [want]
    return r.get("verdict") in want


def score(rows, questions):
    """逐题判定，返回计数与明细。"""
    res = {"total": len(questions), "hit": 0, "miss": 0, "absent": 0, "violated": 0,
           "positive": 0, "negative": 0, "verdict_checked": 0, "detail": []}

    for q in questions:
        kind = q.get("kind", "positive")
        res["positive" if kind == "positive" else "negative"] += 1
        if q.get("expect_verdict") is not None and kind == "positive":
            res["verdict_checked"] += 1
        cands = _candidates(rows, q)
        pages = sorted({p for r in cands for p in r["pages"]})
        tables = sorted({r["table"] for r in cands})
        verdicts = sorted({r.get("verdict") for r in cands if r.get("verdict")})

        reason = ""
        if kind == "negative":
            status = "hit" if not cands else "violated"
        elif not cands:
            status = "absent"
        elif any(_passes(r, q) for r in cands):
            status = "hit"
        else:
            status = "miss"
            # 页码对但判定错，与「页码就不对」分开记，排查方向不同
            page_ok = any(set(r["pages"]) & set(q.get("expect_pages") or []) for r in cands)
            reason = "verdict" if page_ok else "page"

        res[status] += 1
        res["detail"].append({
            "id": q["id"],
            "doc": q["doc"],
            "kind": kind,
            "status": status,
            "reason": reason,
            "tables": tables,
            "expect_tables": q["tables"],
            "pages": pages,
            "expect_pages": q.get("expect_pages") or [],
            "extra_pages": sorted(set(pages) - set(q.get("expect_pages") or [])),
            "verdicts": verdicts,
            "expect_verdict": q.get("expect_verdict"),
            "note": q.get("note", ""),
        })
    return res


def _report(r, rows, doc=None):
    pos_hit = sum(1 for d in r["detail"] if d["kind"] == "positive" and d["status"] == "hit")
    neg_hit = sum(1 for d in r["detail"] if d["kind"] == "negative" and d["status"] == "hit")
    head = f"题集 {r['total']} 条（正例 {r['positive']} / 负例 {r['negative']}）"
    if doc:
        head = f"[{doc}] " + head
    print(f"{head} | 命中 {pos_hit + neg_hit} | 页码错 {r['miss']} | 未抽到 {r['absent']} | 负例违规 {r['violated']}")
    parts = []
    if r["positive"]:
        parts.append(f"正例通过率 {pos_hit}/{r['positive']}（{pos_hit / r['positive']:.0%}）")
    if r["negative"]:
        parts.append(f"负例通过 {neg_hit}/{r['negative']}")
    if parts:
        print(" · ".join(parts))
    print(f"输出条目 {len(rows)} 行，其中无页码 {sum(1 for x in rows if x['no_page'])} 行")
    if r["verdict_checked"]:
        print(f"其中断言判定值（verdict）的 {r['verdict_checked']} 条")
    mk = marker_report(rows, doc)
    if mk and mk["markers_total"]:
        chars = "、".join(f"{k}{v}" for k, v in mk["markers_by_char"].items() if v)
        line = (f"★/▲ 对账：原文 {mk['markers_total']} 个（{chars}，页 {mk['marker_pages']}）"
                f"→ 废标表 star=True {mk['star_rows']} 行，引到标记页 {len(mk['covered_pages'])}/{len(mk['marker_pages'])}")
        print(line)
        if mk["missed_pages"]:
            print(f"  未覆盖标记页：{mk['missed_pages']}")
    noisy = [d for d in r["detail"] if d["extra_pages"]]
    if noisy:
        print(f"多引页码 {len(noisy)} 条（不算错，排查用）：" + "、".join(d["id"] for d in noisy))


def _verbose(r):
    mark = {"hit": "✓", "miss": "✗", "absent": "—", "violated": "!"}
    for d in r["detail"]:
        got = f"p{d['pages']}" if d["pages"] else "（无）"
        want = f"p{d['expect_pages']}" if d["expect_pages"] else "不应出现"
        tbl = "/".join(d["tables"]) or "—"
        print(f"  {mark[d['status']]} {d['id']:<22} 期望 {want:<24} 实际 {got:<28} 表 {tbl}")
        if d["expect_verdict"] is not None:
            want_v = d["expect_verdict"] if isinstance(d["expect_verdict"], str) else "/".join(d["expect_verdict"])
            have_v = "/".join(d["verdicts"]) or "（无判定字段）"
            flag = "" if d["status"] == "hit" else ("  ← 判定不符" if d["reason"] == "verdict" else "")
            print(f"       判定 期望「{want_v}」实际「{have_v}」{flag}")


def main():
    ap = argparse.ArgumentParser(description="给一次 check 的输出打分")
    ap.add_argument("output", help="check 的文本输出")
    ap.add_argument("--doc", default=None, help="只看某份 PDF 的题")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--json", default=None, help="把结果写成 JSON（- 表示打到标准输出）")
    args = ap.parse_args()

    rows = load_rows(Path(args.output))
    data = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    qs = [q for q in data if args.doc is None or q["doc"] == args.doc]

    if not qs:
        print(f"[{args.doc or '全部'}] 题集 0 条（没有对应题目），跳过打分")
        print(f"输出条目 {len(rows)} 行，其中无页码 {sum(1 for x in rows if x['no_page'])} 行")
        return

    r = score(rows, qs)
    pos_hit = sum(1 for d in r["detail"] if d["kind"] == "positive" and d["status"] == "hit")
    neg_hit = sum(1 for d in r["detail"] if d["kind"] == "negative" and d["status"] == "hit")
    payload = {
        "doc": args.doc,
        "output": str(args.output),
        "rows": len(rows),
        "rows_without_page": sum(1 for x in rows if x["no_page"]),
        "counts": {**{k: r[k] for k in
                      ("total", "positive", "negative", "hit", "miss", "absent", "violated",
                       "verdict_checked")},
                   "pos_hit": pos_hit, "neg_hit": neg_hit},
        "markers": marker_report(rows, args.doc),
        "detail": r["detail"],
    }

    if args.json == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    _report(r, rows, args.doc)
    if args.verbose:
        _verbose(r)
    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON 已写入 {args.json}")


if __name__ == "__main__":
    main()
