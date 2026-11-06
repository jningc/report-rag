"""
四张主表和两张辅助表的字段合同。模型输出必须过这些模型。
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


Verdict = Literal["满足", "不满足", "人工看", "无须提供"]


class Ref(BaseModel):
    """一条出处：页、章、框。"""
    page: Optional[int] = None
    chapter: str = ""
    clause: str = ""
    text: str = ""
    bbox: list[float] = Field(default_factory=list)


class FeibiaoRow(BaseModel):
    condition: str
    company: str = ""
    verdict: Verdict = "人工看"
    star: bool = False
    refs: list[Ref] = Field(default_factory=list)


class PingfenRow(BaseModel):
    item: str
    score: str = ""
    standard: str = ""
    company: str = ""
    estimate: str = ""
    refs: list[Ref] = Field(default_factory=list)


class CailiaoRow(BaseModel):
    material: str
    company: str = ""
    verdict: Verdict = "人工看"
    refs: list[Ref] = Field(default_factory=list)


class KongweiRow(BaseModel):
    form: str
    field: str
    note: str = ""
    refs: list[Ref] = Field(default_factory=list)


class ShijianRow(BaseModel):
    name: str
    when: str = ""
    note: str = ""
    refs: list[Ref] = Field(default_factory=list)


class HetongRow(BaseModel):
    item: str
    content: str = ""
    note: str = ""
    verdict: Optional[Verdict] = None
    refs: list[Ref] = Field(default_factory=list)


class FeibiaoTable(BaseModel):
    rows: list[FeibiaoRow] = Field(default_factory=list)


class PingfenTable(BaseModel):
    rows: list[PingfenRow] = Field(default_factory=list)


class CailiaoTable(BaseModel):
    rows: list[CailiaoRow] = Field(default_factory=list)


class KongweiTable(BaseModel):
    rows: list[KongweiRow] = Field(default_factory=list)


class ShijianTable(BaseModel):
    rows: list[ShijianRow] = Field(default_factory=list)


class HetongTable(BaseModel):
    rows: list[HetongRow] = Field(default_factory=list)


def force_manual_if_no_page(refs: list[Ref], verdict: str) -> str:
    """没有页码就不能当正式结论。"""
    if not refs or all(r.page is None for r in refs):
        return "人工看"
    return verdict
