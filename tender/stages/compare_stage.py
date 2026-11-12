"""比对段：条款 + company.yaml 的结论 → `Finding`（落哪张表在这一段定死）。

阶段 2 没有自己的模型调用：结论仍由 v1 的抽取调用一并给出，这一段负责
**把结论按契约归位**——落表、表与类型一致、证据带上。真正「抽取不出 verdict、
比对单独判」的拆分是下一轮的事，单独测。

拿不到结论的行不造 Finding：宁可空着，也不给下游一个没有证据的判定。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from tender.contracts import TYPE_TO_TABLE, ContractError, Finding, table_matches
from tender.stages.extract_stage import ExtractResult


@dataclass
class CompareResult:
    findings: list = field(default_factory=list)   # list[Finding]
    rejects: list = field(default_factory=list)


def run(ex: ExtractResult) -> CompareResult:
    findings, rejects = [], []
    for clause in ex.clauses:
        row = ex.row_of.get(clause.id) or {}
        verdict = row.get("verdict")
        if not verdict:
            continue  # 评分/空位/时间/合同本来就没有 verdict
        table = TYPE_TO_TABLE[clause.type]
        try:
            finding = Finding(
                clause_id=clause.id,
                table=table,
                verdict=verdict,
                evidence=[clause.evidence, *clause.extra],
                note=(row.get("company") or row.get("note") or "")[:160],
            )
        except (ValidationError, ContractError) as e:
            rejects.append({"clause_id": clause.id, "reason": "finding_invalid", "detail": str(e)[:100]})
            continue
        if not table_matches(clause, finding):
            rejects.append({"clause_id": clause.id, "reason": "table_mismatch",
                            "detail": f"{clause.type} 落到了 {finding.table}"})
            continue
        findings.append(finding)

    return CompareResult(findings=findings, rejects=rejects)


def dump(cmp: CompareResult, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "compare.findings.json").write_text(
        json.dumps([f.model_dump() for f in cmp.findings], ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "compare.rejects.json").write_text(
        json.dumps(cmp.rejects, ensure_ascii=False, indent=2), encoding="utf-8")
