"""
六张表的字段合同。模型输出必须过这些模型。

两种坏行分开处理：

- 整行都空（关键字段空、又没有任何出处或别的内容）：丢掉，记进 `dropped_rows`。
- 关键字段缺了但还有出处或别的内容：留下，结论降成「人工看」，备注写清缺哪个字段，
  记进 `degraded_rows`。和「没有页码就降级」是同一条规矩——人在表上看得见，
  不用去日志里捞。

丢的行不删原始内容，`dropped_rows` / `degraded_rows` 跟着 tables.json 一起落盘，
正式表里不出现空行。
"""

from typing import ClassVar, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, model_validator


class _Lenient(BaseModel):
    """null 一律走默认值，别让一个空字段整垮整份。

    before 阶段把值为 null 的键整个删掉，让字段默认值生效（"" / [] / 人工看）。
    """

    #: 行模型用：这一行的主体字段。
    key_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="before")
    @classmethod
    def _none_to_default(cls, data):
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


def _blank(value) -> bool:
    """空字符串、空白、None、False 都算空。"""
    if value is None:
        return True
    if isinstance(value, bool):
        return not value
    return not str(value).strip()


def _has_payload(row, keys: tuple[str, ...]) -> bool:
    """关键字段之外还有没有内容：别的内容，或一条带页码/原文的出处。"""
    data = row.model_dump()
    for name, value in data.items():
        if name in keys or name in {"refs", "verdict"}:
            continue
        if not _blank(value):
            return True
    for ref in data.get("refs") or []:
        if ref.get("page") is not None or not _blank(ref.get("text")):
            return True
    return False


def _degrade(row, missing: list[str]) -> None:
    """缺字段的行降成人工看，缺什么写进备注。"""
    fields = type(row).model_fields
    if "verdict" in fields:
        row.verdict = "人工看"
    if "note" in fields:
        tag = "缺字段：" + "、".join(missing)
        row.note = f"{row.note}；{tag}" if row.note else tag


RowT = TypeVar("RowT", bound="_Lenient")


class _Table(_Lenient, Generic[RowT]):
    """表的公共校验：空行丢弃、缺字段的行降级留痕，两者都另存一份。"""

    rows: list[RowT] = Field(default_factory=list)
    #: 整行空、被丢掉的行（原样 + 缺了什么）
    dropped_rows: list[dict] = Field(default_factory=list)
    #: 缺关键字段、降级成「人工看」的行（原样 + 缺了什么）
    degraded_rows: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _split_bad_rows(self):
        kept, dropped, degraded = [], [], []
        for row in self.rows or []:
            keys = getattr(type(row), "key_fields", ())
            missing = [k for k in keys if _blank(getattr(row, k, ""))]
            # 整行都空 = 关键字段一个都没填、也没有任何出处或别的内容
            if missing and len(missing) == len(keys) and not _has_payload(row, keys):
                dropped.append({"missing": missing, "raw": row.model_dump()})
                continue
            if missing:
                _degrade(row, missing)
                degraded.append({"missing": missing, "raw": row.model_dump()})
            kept.append(row)
        self.rows = kept
        self.dropped_rows = dropped
        self.degraded_rows = degraded
        if dropped or degraded:
            print(
                f"  ! {type(self).__name__} 丢弃 {len(dropped)} 条空行、"
                f"{len(degraded)} 条缺字段转人工看",
                flush=True,
            )
        return self

    @property
    def dropped(self) -> int:
        """被丢掉的行数。"""
        return len(self.dropped_rows)

    @property
    def degraded(self) -> int:
        """缺字段、降级成人工看的行数。"""
        return len(self.degraded_rows)


Verdict = Literal["满足", "不满足", "人工看", "无须提供"]


class Ref(_Lenient):
    """一条出处：页、章、框。"""
    page: Optional[int] = None
    chapter: str = ""
    clause: str = ""
    text: str = ""
    bbox: list[float] = Field(default_factory=list)


class FeibiaoRow(_Lenient):
    key_fields = ("condition",)

    condition: str = ""
    company: str = ""
    verdict: Verdict = "人工看"
    star: bool = False
    note: str = ""
    refs: list[Ref] = Field(default_factory=list)


class PingfenRow(_Lenient):
    key_fields = ("item",)

    item: str = ""
    score: str = ""
    standard: str = ""
    company: str = ""
    estimate: str = ""
    note: str = ""
    refs: list[Ref] = Field(default_factory=list)


class CailiaoRow(_Lenient):
    key_fields = ("material",)

    material: str = ""
    company: str = ""
    verdict: Verdict = "人工看"
    note: str = ""
    refs: list[Ref] = Field(default_factory=list)


class KongweiRow(_Lenient):
    key_fields = ("form", "field")

    form: str = ""
    field: str = ""
    note: str = ""
    refs: list[Ref] = Field(default_factory=list)


class ShijianRow(_Lenient):
    key_fields = ("name",)

    name: str = ""
    when: str = ""
    note: str = ""
    refs: list[Ref] = Field(default_factory=list)


class HetongRow(_Lenient):
    key_fields = ("item",)

    item: str = ""
    content: str = ""
    note: str = ""
    verdict: Optional[Verdict] = None
    refs: list[Ref] = Field(default_factory=list)


class FeibiaoTable(_Table[FeibiaoRow]):
    pass


class PingfenTable(_Table[PingfenRow]):
    pass


class CailiaoTable(_Table[CailiaoRow]):
    pass


class KongweiTable(_Table[KongweiRow]):
    pass


class ShijianTable(_Table[ShijianRow]):
    pass


class HetongTable(_Table[HetongRow]):
    pass


def force_manual_if_no_page(refs: list[Ref], verdict: str) -> str:
    """没有页码就不能当正式结论。"""
    if not refs or all(r.page is None for r in refs):
        return "人工看"
    return verdict
