"""引擎开关：默认 v1、环境变量可切 v2、写错回退，以及分发到哪条链路。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import tender.workflow as wf  # noqa: E402
import tender.workflow_v2 as wf2  # noqa: E402
from tender.engine import check, current  # noqa: E402


def test_default_is_v1(monkeypatch):
    monkeypatch.delenv("TENDER_ENGINE", raising=False)
    assert current() == "v1"


def test_env_switches_to_v2(monkeypatch):
    monkeypatch.setenv("TENDER_ENGINE", "v2")
    assert current() == "v2"


def test_unknown_engine_falls_back(monkeypatch):
    monkeypatch.setenv("TENDER_ENGINE", "v3")
    assert current() == "v1"


def test_check_dispatches_v2(monkeypatch):
    called = {}

    def fake(pdf, company, on_progress=None, reuse_index=True):
        called["v2"] = (pdf, company, reuse_index)
        return {"engine": "v2"}

    monkeypatch.setattr(wf2, "run_check_v2", fake)
    assert check("a.pdf", "c.yaml", engine="v2", reuse_index=True)["engine"] == "v2"
    assert called["v2"] == ("a.pdf", "c.yaml", True)


def test_check_dispatches_v1_with_and_without_index(monkeypatch):
    called = {}
    monkeypatch.setattr(wf, "run_check", lambda pdf, company, on_progress=None: called.setdefault("full", pdf) or {"engine": "v1"})
    monkeypatch.setattr(wf, "run_check_saved", lambda pdf, company, on_progress=None: called.setdefault("saved", pdf) or {"engine": "v1"})

    check("b.pdf", "c.yaml", engine="v1", reuse_index=False)
    check("b.pdf", "c.yaml", engine="v1", reuse_index=True)
    assert called == {"full": "b.pdf", "saved": "b.pdf"}
