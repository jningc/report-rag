"""检索 / schema / 翻转分层打分，以及离线重放；不调 LLM。"""

import json

from impact import (
    _collect_offline_rows,
    schema_ok,
    score_row,
)


def _ans(first_line: str, body: str = "依据见制度。") -> str:
    return f"结论：{first_line}\n{body}"


def _hotel_case() -> dict:
    return {
        "id": "hotel_cap",
        "question": "上海出差住了600一晚，能报多少？",
        "old_conclusion": "可报上限500，超出自理",
        "new_conclusion": "可报上限550，超出自理",
        "should_flip": True,
        "risk": "金额",
    }


def _v12():
    return [{"source": "02_reimbursement_v12.pdf", "page": 3}]


def _v13():
    return [{"source": "02_reimbursement.pdf", "page": 3}]


def test_schema_ok_five_kinds_and_cap_number():
    assert schema_ok(_ans("可报上限550"))
    assert schema_ok(_ans("可报上限 550 元"))
    assert schema_ok(_ans("可报"))
    assert schema_ok(_ans("不可报"))
    assert schema_ok(_ans("条件分支"))
    assert schema_ok(_ans("拒答"))
    assert schema_ok("根据现有资料无法回答。")
    assert schema_ok(_ans("可报上限")) is False
    assert schema_ok("今天天气好") is False


def test_score_row_three_layers_hotel_cap():
    row = score_row(
        _hotel_case(),
        _ans("可报上限500"),
        _ans("可报上限 550 元"),
        _v12(),
        _v13(),
    )
    assert row["retrieval_ok"] is True
    assert row["schema_ok"] is True
    assert row["flipped"] is True
    assert row["aligned"] is True


def test_score_row_schema_fail_aligned_none():
    """上限没数字：schema 不过，翻转未评。"""
    row = score_row(
        _hotel_case(),
        _ans("可报上限", "上限 500"),
        _ans("可报上限", "上限 550"),
        _v12(),
        _v13(),
    )
    assert row["schema_ok"] is False
    assert row["aligned"] is None
    assert row["retrieval_ok"] is True


def test_score_row_retrieval_miss():
    row = score_row(
        _hotel_case(),
        _ans("可报上限500"),
        _ans("可报上限550"),
        [{"source": "03_leave_policy.pdf", "page": 1}],
        _v13(),
    )
    assert row["retrieval_ok"] is False
    assert row["old_retrieval_ok"] is False
    assert row["schema_ok"] is True
    assert row["aligned"] is True


def test_offline_rescore_from_saved_json(tmp_path):
    """落盘后改打分：离线重算翻转，不 ask。"""
    case = _hotel_case()
    saved = score_row(
        case,
        _ans("可报上限500"),
        _ans("可报上限550"),
        _v12(),
        _v13(),
    )
    last_path = tmp_path / "impact_last.json"
    last_path.write_text(json.dumps([saved], ensure_ascii=False), encoding="utf-8")
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(json.dumps([case], ensure_ascii=False), encoding="utf-8")

    from impact import load_cases

    rows = _collect_offline_rows(load_cases(cases_file), last_path=last_path)
    assert len(rows) == 1
    assert rows[0]["aligned"] is True
    assert rows[0]["old_short"] == "可报上限500"
    assert rows[0]["new_short"] == "可报上限550"
