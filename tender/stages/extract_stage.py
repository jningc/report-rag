"""抽取段：检索 + 每张表一次模型调用 → 六表行 + 条款清单（`Clause`）。

阶段 2 的做法是「搬边界不搬实现」：直接调用 v1 的五个节点函数，检索参数、
提示词、调用次数全都不动，所以输出应当与 v1 等价；只是把产物整理成契约对象，
并把坏行（缺页/缺框/缺原文）单独记账，供比对段与校验段使用。

真正的「抽/比分离」（抽取段不再出 verdict）留到下一轮单独测——那会改变输出，
不能和拆段混在一起。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from tender.contracts import Clause, ContractError, Evidence
from tender.workflow import (
    _emit,
    _merge_dict,
    node_aux,
    node_cailiao,
    node_feibiao,
    node_kongwei,
    node_pingfen,
)

TABLES = ("feibiao", "pingfen", "cailiao", "kongwei", "shijian", "hetong")

# 表 → 拼成条款原文的字段（与 adapt_v1.py 一致）
ROW_TEXT_FIELDS = {
    "feibiao": ("condition",),
    "pingfen": ("item", "score", "standard"),
    "cailiao": ("material",),
    "kongwei": ("form", "field"),
    "shijian": ("name", "when"),
    "hetong": ("item", "content"),
}

# v1 的表键 → 条款类型（契约里的 type 用中文类型名）
KEY_TO_TYPE = {
    "feibiao": "废标",
    "pingfen": "评分",
    "cailiao": "材料",
    "kongwei": "空位",
    "shijian": "时间",
    "hetong": "合同",
}


@dataclass
class ExtractResult:
    rows: dict = field(default_factory=dict)          # 六表行（v1 形状）
    row_of: dict = field(default_factory=dict)        # clause_id → 原始行
    clauses: list = field(default_factory=list)       # list[Clause]
    rejects: list = field(default_factory=list)       # 进不了契约的行 + 原因
    dropped: dict = field(default_factory=dict)
    degraded: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)


def _text(row: dict, fields: tuple[str, ...]) -> str:
    parts = [str(row.get(f) or "").strip() for f in fields]
    return "；".join(p for p in parts if p)


def _evidence(row: dict) -> tuple[list[Evidence], list[str]]:
    """把一行的 refs 转成 Evidence；没有框/没有原文的记原因。"""
    good, bad = [], []
    for raw in row.get("refs") or []:
        try:
            good.append(Evidence(
                page=raw.get("page") or 0,
                bbox=raw.get("bbox") or [],
                text=(raw.get("text") or "").strip(),
                chapter=raw.get("chapter") or "",
                clause=raw.get("clause") or "",
            ))
        except (ValidationError, ContractError) as e:
            bad.append(str(e).split("\n")[0][:60])
    return good, bad


def _to_clauses(stem: str, rows: dict) -> tuple[list[Clause], dict, list[dict]]:
    clauses, row_of, rejects = [], {}, []
    for table, items in rows.items():
        ctype = KEY_TO_TYPE[table]
        for i, row in enumerate(items or []):
            rid = f"{stem}:{table}:{i:03d}"
            text = _text(row, ROW_TEXT_FIELDS[table])
            if not text:
                rejects.append({"clause_id": rid, "reason": "text_empty"})
                continue
            good, bad = _evidence(row)
            if not good:
                rejects.append({"clause_id": rid, "reason": "no_evidence", "detail": bad[:2], "text": text[:80]})
                continue
            try:
                clause = Clause(id=rid, type=ctype, text=text, evidence=good[0],
                                extra=good[1:], star=bool(row.get("star")))
            except (ValidationError, ContractError) as e:
                rejects.append({"clause_id": rid, "reason": "clause_invalid", "detail": str(e)[:100]})
                continue
            clauses.append(clause)
            row_of[rid] = row
            if bad:
                rejects.append({"clause_id": rid, "reason": "partial_evidence_dropped", "detail": bad[:2]})
    return clauses, row_of, rejects


def run(doc, index, company) -> ExtractResult:
    """按 v1 的节点顺序跑一遍，返回行 + 条款。"""
    _emit("extract", "running", "检索并抽取六张表")
    state = {"pdf_path": doc.pdf, "company": company, "index": index}
    merged: dict = {}
    for node in (node_feibiao, node_pingfen, node_cailiao, node_kongwei, node_aux):
        out = node(state) or {}
        for key, value in out.items():
            if key in ("dropped", "degraded"):
                merged[key] = _merge_dict(merged.get(key) or {}, value)
            else:
                merged[key] = value

    rows = {t: merged.get(t) or [] for t in TABLES}
    stem = Path(doc.pdf).stem
    clauses, row_of, rejects = _to_clauses(stem, rows)
    _emit("extract", "done", f"六表 {sum(len(v) for v in rows.values())} 行，条款 {len(clauses)} 条")
    return ExtractResult(
        rows=rows, row_of=row_of, clauses=clauses, rejects=rejects,
        dropped=merged.get("dropped") or {}, degraded=merged.get("degraded") or {},
        missing=merged.get("missing") or [],
    )


def dump(ex: ExtractResult, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "extract.clauses.json").write_text(
        json.dumps([c.model_dump() for c in ex.clauses], ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "extract.rejects.json").write_text(
        json.dumps(ex.rejects, ensure_ascii=False, indent=2), encoding="utf-8")
