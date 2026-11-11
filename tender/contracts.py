"""四段流水线之间的契约。冻结后不再改：改契约等于改所有段的接口。

三条硬规矩，写在这里而不是写在提示词里：

1. **没有框的条款不放行**。`Evidence` 必须同时有 `page` 与四数 `bbox`，
   而且面积大于零——整页框能通过（它是真的几何），但 `is_clause_level()`
   会把它标出来，校验段不认它。
2. **段与段之间只传这里的模型**，不传自由文本。`ParsedDoc` → `Clause` →
   `Finding` → `Verified`，每段只吃上一段的产物。
3. **页码一律 PDF 物理页**（第 1 页 = 封面）。页脚的印刷页码由渲染层换算，
   不进契约——beijing、chongzuo 两者差 2 页，wenling 一致。

对应文档：`docs/契约样例.md`（p8 保证金那条的手写样例）、`docs/迁移计划.md` 阶段 1。
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# 条款类型 = 它该落哪张表，一对一，不许多开
ClauseType = Literal["废标", "评分", "材料", "空位", "时间", "合同"]
TableName = Literal["废标对照", "评分对照", "材料对照", "空位对照", "时间节点", "合同要点"]
Verdict = Literal["满足", "不满足", "人工看", "无须提供"]
Source = Literal["rule", "model", "follow", "manual"]
CheckName = Literal["page_exists", "text_contains", "cross_ref_section", "value_normalized"]

TYPE_TO_TABLE: dict[str, str] = {
    "废标": "废标对照",
    "评分": "评分对照",
    "材料": "材料对照",
    "空位": "空位对照",
    "时间": "时间节点",
    "合同": "合同要点",
}


class ContractError(ValueError):
    """契约不成立。带上是哪一条、缺什么，别只抛一句 pydantic 报错。"""


def _check_bbox(v: list[float]) -> list[float]:
    """四个数、面积大于零。允许整页框，但不许反的、零面积的、三个数的。"""
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        raise ContractError(f"bbox 必须是 4 个数 [x1, y1, x2, y2]，收到 {v!r}")
    x1, y1, x2, y2 = (float(x) for x in v)
    if x2 <= x1 or y2 <= y1:
        raise ContractError(f"bbox 面积必须大于零，收到 {v!r}")
    return [x1, y1, x2, y2]


class Evidence(BaseModel):
    """一条出处。页 + 框 + 原文，三者缺一不可。"""

    page: int = Field(ge=1)
    bbox: list[float]
    text: str = Field(min_length=1)
    chapter: str = ""
    clause: str = ""

    _bbox = field_validator("bbox")(_check_bbox)


class ParsedDoc(BaseModel):
    """解析段产物：章节树 + 表格结构 + 页码坐标。纯解析，不调模型。"""

    pdf: str
    page_count: int = Field(ge=1)
    page_numbering: Literal["physical"] = "physical"
    sections: list["Section"]
    tables: list["Table"] = Field(default_factory=list)


class Section(BaseModel):
    type: str
    title: str
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self):
        if self.end_page < self.start_page:
            raise ContractError(f"章节 {self.title!r} 的 end_page 小于 start_page")
        return self


class Table(BaseModel):
    """表格：表头和单元格绑在一起（跨页表用表头接续，不是两截）。"""

    page: int = Field(ge=1)
    bbox: list[float]
    header: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    continued_from: Optional[int] = None  # 接续自第几页的同名表

    _bbox = field_validator("bbox")(_check_bbox)


class Clause(BaseModel):
    """抽取段产物：一段原文在讲什么、归哪一类。没有 verdict，不对照公司。"""

    id: str = Field(min_length=1)
    type: ClauseType
    text: str = Field(min_length=1)
    evidence: Evidence
    extra: list[Evidence] = Field(default_factory=list)  # follow_reference 补的出处
    section_type: Optional[str] = None
    star: bool = False
    value: Optional[str] = None  # 归一后的金额/天数/比例，供校验段比对
    source: Source = "model"

    @property
    def table(self) -> str:
        return TYPE_TO_TABLE[self.type]


class Finding(BaseModel):
    """比对段产物：拿条款 + company.yaml 出的结论，落哪张表也在这里定死。"""

    clause_id: str = Field(min_length=1)
    table: TableName
    verdict: Verdict = "人工看"
    evidence: list[Evidence] = Field(min_length=1)
    note: str = ""


class Check(BaseModel):
    """一条机械回查的结果。校验段只做这些，不判「合不合理」。"""

    name: CheckName
    ok: bool
    detail: str = ""


class Verified(BaseModel):
    """校验段产物：通过或退回。退回必须指到具体一条，不能只说「表里有个空」。"""

    finding_id: str = Field(min_length=1)
    ok: bool
    checks: list[Check] = Field(min_length=1)
    reject_reason: str = ""

    @model_validator(mode="after")
    def _reason_required(self):
        if not self.ok and not self.reject_reason.strip():
            raise ContractError("退回必须写 reject_reason（指到 clause_id 与缺什么）")
        if self.ok and self.reject_reason.strip():
            raise ContractError("通过就不要写 reject_reason，避免下游误读")
        return self


def is_clause_level(ev: Evidence, page_height: float = 842.0) -> bool:
    """框是不是条款级。整页高的框画出来盖满一页，校验段也不算它。

    阈值用页高的 60%：正常条款段落很少超过这个高度。
    """
    return (ev.bbox[3] - ev.bbox[1]) <= page_height * 0.6


def table_matches(clause: Clause, finding: Finding) -> bool:
    """条款类型与落表是否一致（废标只许落废标对照）。"""
    return TYPE_TO_TABLE[clause.type] == finding.table


def evidence_ok(clause: Clause) -> bool:
    """进下一段的门槛：所有出处都是条款级。"""
    return all(is_clause_level(ev) for ev in [clause.evidence, *clause.extra])
