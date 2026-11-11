"""契约的硬规矩：没有框不放行、落错表要能挡、退回必须指到具体一条。

只测契约本身，不碰 PDF、不调模型。
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tender.contracts import (  # noqa: E402
    Check,
    Clause,
    ContractError,
    Evidence,
    Finding,
    ParsedDoc,
    Section,
    Table,
    Verified,
    evidence_ok,
    is_clause_level,
    table_matches,
)

P8_BBOX = [65.8, 377.1, 562.2, 696.5]  # beijing p8「注1 保证金形式」的真实框


def _ev(**kw):
    base = dict(page=8, bbox=P8_BBOX, text="投标人应以出具保函（保险）形式提交投标保证金", chapter="第二章投标人须知", clause="12.1")
    base.update(kw)
    return Evidence(**base)


# ---------- 1. 出处：页 + 四数框 + 原文 ----------

def test_evidence_ok():
    ev = _ev()
    assert ev.page == 8 and len(ev.bbox) == 4


def test_evidence_requires_bbox():
    with pytest.raises(ValidationError):
        Evidence(page=8, text="没有框的条款")


def test_bbox_must_be_four_numbers():
    with pytest.raises((ContractError, ValidationError)):
        _ev(bbox=[65.8, 377.1, 562.2])


def test_bbox_must_have_area():
    with pytest.raises((ContractError, ValidationError)):
        _ev(bbox=[65.8, 377.1, 65.8, 377.1])


def test_page_must_be_positive_physical():
    with pytest.raises(ValidationError):
        _ev(page=0)


def test_text_must_not_be_empty():
    with pytest.raises(ValidationError):
        _ev(text="")


# ---------- 2. 条款：无出处不放行 ----------

def test_clause_requires_evidence():
    with pytest.raises(ValidationError):
        Clause(id="c1", type="废标", text="未缴纳投标保证金的投标无效")


def test_clause_type_maps_to_table():
    c = Clause(id="c1", type="废标", text="未缴纳投标保证金的投标无效", evidence=_ev())
    assert c.table == "废标对照"
    assert Clause(id="c2", type="空位", text="开标一览表", evidence=_ev()).table == "空位对照"


# ---------- 3. 差异：必须至少一条出处，落表要和类型一致 ----------

def test_finding_requires_evidence():
    with pytest.raises(ValidationError):
        Finding(clause_id="c1", table="废标对照", verdict="不满足", evidence=[])


def test_table_matches_blocks_cross_table():
    clause = Clause(id="c1", type="合同", text="履约保证金为中标金额的5%", evidence=_ev())
    good = Finding(clause_id="c1", table="合同要点", verdict="人工看", evidence=[_ev()])
    bad = Finding(clause_id="c1", table="废标对照", verdict="人工看", evidence=[_ev()])
    assert table_matches(clause, good)
    assert not table_matches(clause, bad)


# ---------- 4. 校验：退回必须指到具体一条 ----------

def test_verified_reject_needs_reason():
    with pytest.raises((ContractError, ValidationError)):
        Verified(finding_id="f1", ok=False, checks=[Check(name="page_exists", ok=False)])


def test_verified_reject_with_reason():
    v = Verified(
        finding_id="f1",
        ok=False,
        checks=[Check(name="text_contains", ok=False, detail="bbox 内没有 8000 元")],
        reject_reason="c1 原文该 bbox 只写「按资料表金额」，没写金额",
    )
    assert not v.ok and "c1" in v.reject_reason


def test_verified_pass_must_not_carry_reason():
    with pytest.raises((ContractError, ValidationError)):
        Verified(finding_id="f1", ok=True, checks=[Check(name="page_exists", ok=True)], reject_reason="多余的说明")


def test_verified_needs_at_least_one_check():
    with pytest.raises(ValidationError):
        Verified(finding_id="f1", ok=True, checks=[])


# ---------- 5. 解析段：章节顺序、页码口径、表格有框 ----------

def test_section_end_before_start_rejected():
    with pytest.raises((ContractError, ValidationError)):
        Section(type="notice", title="第二章 投标人须知", start_page=20, end_page=7)


def test_parsed_doc_page_numbering_is_physical():
    doc = ParsedDoc(pdf="sample/beijing_road.pdf", page_count=92,
                    sections=[Section(type="invite", title="第一章 投标邀请", start_page=3, end_page=6)])
    assert doc.page_numbering == "physical"
    with pytest.raises(ValidationError):
        ParsedDoc(pdf="x.pdf", page_count=1, page_numbering="printed",
                  sections=[Section(type="invite", title="t", start_page=1, end_page=1)])


def test_table_requires_bbox():
    with pytest.raises(ValidationError):
        Table(page=8, header=["包号", "保证金"])


# ---------- 6. 条款级判定：整页框不算 ----------

def test_page_height_box_is_not_clause_level():
    page_tall = Evidence(page=8, bbox=[47.0, 37.3, 548.2, 804.3], text="整页框")
    assert not is_clause_level(page_tall)


def test_normal_box_is_clause_level():
    assert is_clause_level(_ev())


def test_evidence_ok_rejects_page_tall():
    c = Clause(id="c9", type="废标", text="整页框的条款", evidence=_ev(bbox=[47.0, 37.3, 548.2, 804.3]))
    assert not evidence_ok(c)


# ---------- 7. 手写样例必须能过契约（docs/契约样例.md 引的就是这几个文件） ----------

SAMPLES = PROJECT_ROOT / "eval" / "contracts" / "samples"


def _load(name):
    import json
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,model", [
    ("p8_parsed.json", ParsedDoc),
    ("p8_clause_amount.json", Clause),
    ("p8_clause_form.json", Clause),
    ("p8_finding.json", Finding),
    ("p8_verified_reject.json", Verified),
    ("p8_verified_pass.json", Verified),
])
def test_samples_match_contracts(name, model):
    assert model.model_validate(_load(name))


def test_sample_amount_evidence_is_page_tall():
    """p8 的金额那条，v1 只给得出整页框——样例故意留着它，用来演示校验段退回。"""
    clause = Clause.model_validate(_load("p8_clause_amount.json"))
    assert not is_clause_level(clause.evidence)
    assert not evidence_ok(clause)


def test_sample_form_evidence_is_clause_level():
    clause = Clause.model_validate(_load("p8_clause_form.json"))
    assert is_clause_level(clause.evidence)
    assert evidence_ok(clause)


def test_sample_reject_reason_points_to_clause():
    v = Verified.model_validate(_load("p8_verified_reject.json"))
    assert not v.ok
    assert "beijing_road:notice:12.1" in v.reject_reason
