"""对着人工核过的题集，给一次 check 的输出打分。

用法:
  python eval/compare.py data/step_output/beijing_road/04_check.txt
  python eval/compare.py /tmp/check.txt --doc beijing_road -v

只读文本、不调模型：输出里每行形如
  2. 不满足 | 投标保证金：01包8000元…  [8,17,25]
判定：含 keyword 的条目里，只要有一条的页码命中 expect_pages 就算过；
     一条都没命中记 miss；压根没抽到这条记 absent。
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = Path(__file__).resolve().parent / "questions.json"

ROW_RE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*(?:\[([\d,\s]+)\]|\[无页码\])\s*$")


def parse_rows(path: Path):
    """返回 [{table, text, pages, no_page}]。"""
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
        rows.append({
            "table": table,
            "text": m.group(2),
            "pages": pages,
            "no_page": m.group(3) is None,
        })
    return rows


def score(rows, questions, verbose=False):
    result = {"hit": 0, "miss": 0, "absent": 0, "detail": []}
    for q in questions:
        cands = [r for r in rows if q["keyword"] in r["text"]]
        if not cands:
            result["absent"] += 1
            result["detail"].append(("absent", q, []))
            continue
        ok = [r for r in cands if set(r["pages"]) & set(q["expect_pages"])]
        if ok:
            result["hit"] += 1
            result["detail"].append(("hit", q, ok[0]))
        else:
            result["miss"] += 1
            result["detail"].append(("miss", q, cands[0]))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", help="check 的文本输出")
    ap.add_argument("--doc", default=None, help="只看某份 PDF 的题，留给多文档时用")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    rows = parse_rows(Path(args.output))
    data = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    qs = [q for q in data if args.doc is None or q["doc"] == args.doc]

    r = score(rows, qs)
    total = len(qs)
    print(f"题集 {total} 条 | 命中 {r['hit']} | 页码错 {r['miss']} | 未抽到 {r['absent']}")
    print(f"抽取率 {(r['hit'] + r['miss']) / total:.0%} · 页码准确率 {r['hit'] / total:.0%}")
    print(f"输出条目 {len(rows)} 行，其中无页码 {sum(1 for x in rows if x['no_page'])} 行")
    if args.verbose:
        for kind, q, row in r["detail"]:
            mark = {"hit": "✓", "miss": "✗", "absent": "—"}[kind]
            got = f"p{row['pages']}" if isinstance(row, dict) else "（无）"
            print(f"  {mark} {q['id']:<20} 期望 p{q['expect_pages']} 实际 {got}")


if __name__ == "__main__":
    main()
