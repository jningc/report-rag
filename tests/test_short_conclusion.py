"""对照层漏报 / 误报：只比 kind 与 amount，不调 LLM。"""

import pytest

from impact import (
    KIND_ALLOW,
    KIND_CAP,
    KIND_COND,
    KIND_DENY,
    KIND_REFUSE,
    parse_short_conclusion,
    score_flip,
)


def _ans(first_line: str, body: str = "依据见制度。") -> str:
    """拼成与 rag 一致的多行回答。"""
    return f"结论：{first_line}\n{body}"


# --- 误报：制度没变，第一行措辞不同，字符串对齐会判成翻转 ---

@pytest.mark.parametrize(
    "old_line,new_line,note",
    [
        (
            "不可报",
            "不可报，日常通勤费用明确不能报销",
            "overtime_commute：第一行多半句解释",
        ),
        (
            "不可报",
            "不可报，抬头必须是公司全称",
            "invoice_title：第一行带依据摘要",
        ),
        (
            "可报上限550",
            "可报上限 550 元",
            "hotel_cap：空格和「元」",
        ),
        (
            "可报上限550",
            "可报上限550元",
            "hotel_cap：只多「元」",
        ),
        (
            "条件分支",
            "条件分支（未事先申请的跨城差旅财务可否决）",
            "no_trip_apply：条款重写但仍是可否决",
        ),
        (
            "拒答",
            "根据现有资料无法回答。",
            "bitcoin：拒答文案与结论标签",
        ),
    ],
)
def test_false_positive_same_slots_not_flip(old_line, new_line, note):
    """不该变的题：字段相同则对齐，不能因同义句误报。"""
    old = old_line if old_line.startswith("根据现有") else _ans(old_line)
    new = new_line if new_line.startswith("根据现有") else _ans(new_line)
    assert score_flip(old, new, should_flip=False), note


# --- 该变：数字或可否报换了，必须判翻转 ---

@pytest.mark.parametrize(
    "old_line,new_line,note",
    [
        ("可报上限500", "可报上限550", "hotel_cap：500→550"),
        ("可报上限500", "可报上限 550 元", "hotel_cap：数字变了，写法也不同"),
        ("可报", "不可报", "meal_after_hospitality：可否报翻转"),
    ],
)
def test_true_flip_kind_or_amount(old_line, new_line, note):
    """该变的题：kind 或 amount 不同则对齐。"""
    assert score_flip(_ans(old_line), _ans(new_line), should_flip=True), note


def test_true_negative_identical_deny():
    """通勤两版都是不可报，完整回答也应判没变。"""
    text = _ans("不可报", "日常通勤费用明确不可报销。")
    assert score_flip(text, text, should_flip=False)


# --- 解析：槽位本身 ---

@pytest.mark.parametrize(
    "text,kind,amount",
    [
        (_ans("可报上限500"), KIND_CAP, 500),
        (_ans("可报上限 550 元"), KIND_CAP, 550),
        (_ans("可报"), KIND_ALLOW, None),
        (_ans("不可报，日常通勤费用明确不能报销"), KIND_DENY, None),
        (_ans("条件分支（未申请可否决）"), KIND_COND, None),
        (_ans("拒答"), KIND_REFUSE, None),
        ("根据现有资料无法回答。", KIND_REFUSE, None),
    ],
)
def test_parse_kind_amount(text, kind, amount):
    parsed = parse_short_conclusion(text)
    assert parsed["kind"] == kind
    assert parsed["amount"] == amount


# --- 漏报：生成没把口径写进槽，字段对齐也救不回来 ---

def test_false_negative_both_conditional_when_should_flip():
    """餐补该变，但两边都写成条件分支：kind 相同，对齐失败（生成层责任）。"""
    old = _ans("条件分支")
    new = _ans("条件分支")
    assert score_flip(old, new, should_flip=True) is False


def test_false_negative_cap_without_number():
    """住宿该变，数字写在第二行、第一行只有「可报上限」：两边都落到可报，漏报。"""
    old = _ans("可报上限", "一线城市上限 500 元。")
    new = _ans("可报上限", "一线城市上限 550 元。")
    assert parse_short_conclusion(old)["kind"] == KIND_ALLOW
    assert parse_short_conclusion(old)["amount"] is None
    assert score_flip(old, new, should_flip=True) is False
