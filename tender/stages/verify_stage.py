"""校验段：机械回查，不调模型。

阶段 2 只做一件事——**页码存在性**。条款级框、原文含值、交叉引用落章
这些检查在阶段 4 补；现在把管线接通、把结果落盘，`enforce=False` 表示
退回不改变表内容（避免阶段 2 顺手改变输出、破坏「等价」）。
"""

import json
from pathlib import Path

from tender.contracts import Check, Verified
from tender.stages.compare_stage import CompareResult
from tender.stages.extract_stage import ExtractResult


def run(cmp: CompareResult, ex: ExtractResult, enforce: bool = False) -> list:
    """返回 list[Verified]。enforce=True 时才会把退回当成真正退（阶段 4）。"""
    out = []
    for f in cmp.findings:
        checks = [
            Check(name="page_exists", ok=all(e.page >= 1 for e in f.evidence),
                  detail="、".join(f"p{e.page}" for e in f.evidence)),
        ]
        ok = all(c.ok for c in checks)
        try:
            out.append(Verified(
                finding_id=f.clause_id, ok=ok, checks=checks,
                reject_reason="" if ok else f"{f.clause_id} 有出处缺页码",
            ))
        except Exception as e:  # 契约本身不允许通过又带原因，这种行不写
            out.append({"finding_id": f.clause_id, "error": str(e)[:120]})
    return out


def summary(verified: list) -> dict:
    ok = sum(1 for v in verified if getattr(v, "ok", False))
    return {"checked": len(verified), "passed": ok, "rejected": len(verified) - ok}


def dump(verified: list, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    payload = [v.model_dump() if hasattr(v, "model_dump") else v for v in verified]
    (folder / "verify.verified.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
