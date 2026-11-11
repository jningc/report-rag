"""题集清单和 questions.json 必须说同一件事。

清单是给人复核的，questions.json 是给 compare.py 打分的。两边一旦分叉，
清单上写着「期望 满足」而打分器不检查，分数就会替人撒谎。
这个测试逐条比对：id、正/负、期望表、期望页、期望判定。

改任何一边都必须同时改另一边；不想同步就改这条测试——但先想清楚为什么。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIST = ROOT / "eval" / "题集核对清单.md"
QUESTIONS = ROOT / "eval" / "questions.json"

DOC_HEAD = re.compile(r"^## (\w+)\s*$")


def parse_pages(cell: str) -> list[int]:
    cell = cell.strip()
    if cell in {"不应出现", "", "-"}:
        return []
    return [int(x) for x in re.split(r"[/,、\s]+", cell) if x.strip().isdigit()]


def parse_verdict(cell: str):
    """「不适用（…）」表示该表没有判定字段，等价于 None。"""
    cell = cell.strip()
    if cell.startswith("不适用"):
        return None
    if "/" in cell:
        return sorted(x.strip() for x in cell.split("/") if x.strip())
    return cell


def parse_list() -> dict[str, dict]:
    """从清单里读出 {doc: {id: {...}}}。"""
    rows: dict[str, dict] = {}
    doc = None
    for line in LIST.read_text(encoding="utf-8").splitlines():
        m = DOC_HEAD.match(line.strip())
        if m:
            doc = m.group(1)
            continue
        if not doc or not line.startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 8:
            continue
        mid = re.search(r"`([a-z0-9\-]+)`", cells[2])
        if not mid:
            continue
        rows.setdefault(doc, {})[mid.group(1)] = {
            "kind": "positive" if cells[3].strip() == "正" else "negative",
            "tables": sorted(t.strip() for t in cells[4].strip().split("、") if t.strip()),
            "pages": parse_pages(cells[5]),
            "verdict": parse_verdict(cells[6]),
        }
    return rows


def load_questions() -> dict[str, dict]:
    data = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    out: dict[str, dict] = {}
    for q in data:
        v = q.get("expect_verdict")
        if isinstance(v, list):
            v = sorted(v)
        out[q["id"]] = {
            "doc": q["doc"],
            "kind": q.get("kind", "positive"),
            "tables": sorted(q["tables"]),
            "pages": sorted(q.get("expect_pages") or []),
            "verdict": v,
        }
    return out


def test_list_and_questions_agree():
    listed = parse_list()
    qs = load_questions()

    listed_ids = {i for doc in listed.values() for i in doc}
    assert listed_ids == set(qs), (
        f"清单与题集 id 不一致：只在清单 {sorted(listed_ids - set(qs))}；"
        f"只在题集 {sorted(set(qs) - listed_ids)}"
    )

    problems = []
    for doc, items in listed.items():
        if doc not in {"beijing_road", "chongzuo_green", "wenling_video"}:
            continue
        for qid, cell in items.items():
            q = qs[qid]
            if q["doc"] != doc:
                problems.append(f"{qid}: 清单放在 {doc}，题集写在 {q['doc']}")
            for field in ("kind", "tables", "pages", "verdict"):
                if cell[field] != q[field]:
                    problems.append(f"{qid}: {field} 清单={cell[field]!r} 题集={q[field]!r}")
    assert not problems, "清单与题集口径不一致：\n  " + "\n  ".join(problems)


def test_verdict_assertions_counted():
    """断言判定值的条数，两边必须相同（当前 12 条，其余标不适用）。"""
    listed = parse_list()
    n_list = sum(1 for doc in listed.values() for cell in doc.values() if cell["verdict"])
    qs = load_questions()
    n_json = sum(1 for q in qs.values() if q["verdict"])
    assert n_list == n_json, f"清单断言 {n_list} 条判定，题集只有 {n_json} 条"
