"""tender 的离线测试：只测不调 LLM 的判定，跑起来不需要 Key 和索引。

覆盖四件事：
1. 章类型归并（同名不同叫法、格式章优先于资格章）
2. 切章：目录页不埋伏笔、同一类型只留正文那次
3. 没页码就不能给结论，降级成「人工看」
4. company.yaml 能读出来，缺字段时不炸
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tender.sections import (  # noqa: E402
    classify_title,
    required_types_present,
    section_of_page,
    split_sections,
)
from tender.tables import Ref, force_manual_if_no_page  # noqa: E402
from tender.workflow import load_company  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _page(num: int, *lines: str) -> dict:
    """构造一页：前几个块是标题候选。"""
    return {"page": num, "blocks": [{"text": t} for t in lines]}


# ---------- 1. 章类型归并 ----------

@pytest.mark.parametrize(
    "title,expect",
    [
        ("第三章 评标办法（综合评分法）", "score"),
        ("第五章 投标文件格式", "format"),
        ("第四章 合同条款及格式", "contract"),
        ("第二章 投标人须知", "notice"),
        ("第一章 招标公告", "invite"),
        ("第七章 资格审查办法", "qualify"),
        ("第九章 其他事项", "unknown"),
    ],
)
def test_classify_title(title, expect):
    assert classify_title(title) == expect


def test_format_wins_over_qualify():
    """「投标文件格式」里也含「资格」，必须优先判成格式章。"""
    assert classify_title("第六章 投标文件格式（含资格证明）") == "format"


# ---------- 2. 切章 ----------

def test_split_sections_skips_toc_page():
    """目录页把几章堆在前 4 页，不能当成章节起点。"""
    pages = [
        _page(2, "第一章 招标公告", "第二章 投标人须知", "第三章 评标办法"),
        _page(5, "第一章 招标公告"),
        _page(9, "第二章 投标人须知"),
        _page(15, "第三章 评标办法"),
    ]
    sections = split_sections(pages)
    assert [s["type"] for s in sections] == ["invite", "notice", "score"]
    assert [s["start_page"] for s in sections] == [5, 9, 15]
    # 后一章的起点前一行就是前一章的终点
    assert sections[0]["end_page"] == 8
    assert sections[1]["end_page"] == 14


def test_section_of_page_and_missing_types():
    sections = split_sections(
        [_page(3, "第一章 招标公告"), _page(10, "第三章 评标办法")]
    )
    assert section_of_page(sections, 10)["type"] == "score"
    assert section_of_page(sections, 1) is None
    missing = required_types_present(sections, ["invite", "score", "contract"])
    assert missing == ["contract"]


def test_split_sections_never_empty():
    """切不出来也要给一个兜底章，不能让下游拿 None。"""
    sections = split_sections([_page(1, "随便一段正文")])
    assert len(sections) == 1
    assert sections[0]["type"] == "unknown"


# ---------- 3. 没页码就人工看 ----------

def test_no_page_forces_manual():
    row_refs = [Ref(page=None, text="未见保证金比例")]
    assert force_manual_if_no_page(row_refs, "可报") == "人工看"


def test_no_refs_forces_manual():
    assert force_manual_if_no_page([], "不可报") == "人工看"


def test_with_page_keeps_verdict():
    assert force_manual_if_no_page([Ref(page=17, text="保证金 2%")], "可报") == "可报"


# ---------- 4. company.yaml ----------

def test_load_sample_company():
    company = load_company(PROJECT_ROOT / "sample" / "company.yaml")
    assert isinstance(company, dict)
    assert company  # 非空
