"""
薄 HTTP 接口。核对在后台线程里跑，页面只负责显示。

  python main.py web
  浏览器打开 http://127.0.0.1:8765
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from io import BytesIO
from pathlib import Path

import yaml
from openpyxl import Workbook
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from tender.ask_box import ask_question
from tender.parse import render_page_png
from tender.tools import set_context
from tender.workflow import run_check, run_check_saved

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PDF = ROOT / "sample" / "beijing_road.pdf"
SAMPLE_COMPANY = ROOT / "sample" / "company.yaml"
PAGE = ROOT / "static" / "index.html"
VENDOR = ROOT / "static" / "vendor"
UPLOAD_ROOT = ROOT / "data" / "web_jobs"

# 页面顶部进度条的固定顺序
STAGE_DEFS = [
    ("parse", "解析", "按页抽文字和块坐标"),
    ("sections", "切章", "按标题标成章节类型"),
    ("index", "建索引", "每种章单独建 BM25 和 FAISS"),
    ("feibiao", "1 查废标", "只搜：投标邀请、投标人须知、资格审查"),
    ("pingfen", "2 查评分", "只搜：评标办法"),
    ("cailiao", "3 查材料", "只搜：须知、资格审查、格式，再对 company.yaml"),
    ("kongwei", "4 列空位", "只搜：投标文件格式"),
    ("aux", "辅助", "时间节点和合同要点"),
]

TABLE_KEYS = ("feibiao", "pingfen", "cailiao", "kongwei", "shijian", "hetong")
TABLE_TITLES = {
    "feibiao": "废标对照",
    "pingfen": "评分对照",
    "cailiao": "材料对照",
    "kongwei": "空位对照",
    "shijian": "时间节点",
    "hetong": "合同要点",
}

_lock = threading.Lock()
_ask_lock = threading.Lock()
_jobs: dict[str, dict] = {}


class Json(JSONResponse):
    """中文按 UTF-8 原样输出。"""

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False).encode("utf-8")


def _blank_stages() -> list[dict]:
    return [
        {"id": sid, "name": name, "scope": scope, "state": "wait", "detail": ""}
        for sid, name, scope in STAGE_DEFS
    ]


def _blank_tables() -> dict:
    return {key: [] for key in TABLE_KEYS}


def _parse_company(text: str) -> dict:
    if not (text or "").strip():
        raise ValueError("company.yaml 是空的")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"company.yaml 无法解析: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("company.yaml 须是一份映射")
    return data


def _public(job: dict) -> dict:
    return {
        "id": job["id"],
        "status": job["status"],
        "error": job["error"],
        "file_name": job["file_name"],
        "company_name": job["company_name"],
        "page_count": job["page_count"],
        "sections": copy.deepcopy(job["sections"]),
        "stages": copy.deepcopy(job["stages"]),
        "tables": copy.deepcopy(job["tables"]),
        "missing": list(job["missing"]),
    }


def _apply(job_id: str, event: dict) -> None:
    """把 run_check 的进度写进任务。索引对象只留在内存里。"""
    with _lock:
        job = _jobs[job_id]
        stage_id = event["stage"]
        for stage in job["stages"]:
            if stage["id"] != stage_id:
                continue
            stage["state"] = event["state"]
            if event.get("detail"):
                stage["detail"] = event["detail"]
        if "page_count" in event:
            job["page_count"] = event["page_count"]
        if "sections" in event:
            job["sections"] = event["sections"]
        if "rows" in event:
            job["tables"][stage_id] = event["rows"]
        if "missing" in event:
            job["missing"] = event["missing"]
        if "shijian" in event:
            job["tables"]["shijian"] = event["shijian"]
        if "hetong" in event:
            job["tables"]["hetong"] = event["hetong"]
        if event.get("index") is not None:
            job["index"] = event["index"]
        if event.get("company") is not None:
            job["company"] = event["company"]
        if event.get("pdf_path"):
            job["pdf_path"] = event["pdf_path"]


def _worker(job_id: str, pdf_path: str, company_path: str, use_index: bool = False) -> None:
    run = run_check_saved if use_index else run_check
    try:
        result = run(pdf_path, company_path, on_progress=lambda event: _apply(job_id, event))
    except Exception as exc:
        with _lock:
            job = _jobs[job_id]
            job["status"] = "error"
            job["error"] = str(exc)
            for stage in job["stages"]:
                if stage["state"] == "running":
                    stage["state"] = "error"
                    stage["detail"] = str(exc)
        return
    with _lock:
        job = _jobs[job_id]
        job["status"] = "done"
        job["index"] = result["index"]
        job["company"] = result["company"]
        job["pdf_path"] = result["pdf_path"]
        job["sections"] = result["sections"]
        job["missing"] = result["missing"]
        job["page_count"] = result.get("page_count") or len(result["pages"])
        for key in TABLE_KEYS:
            job["tables"][key] = result[key]


def _launch(job_id: str, file_name: str, company: dict, pdf_path: Path, company_path: Path, use_index: bool = False) -> None:
    job = {
        "id": job_id,
        "status": "running",
        "error": "",
        "file_name": file_name,
        "company_name": str(company.get("name") or "company.yaml"),
        "page_count": 0,
        "sections": [],
        "stages": _blank_stages(),
        "tables": _blank_tables(),
        "missing": [],
        "pdf_path": str(pdf_path),
        "company": company,
        "index": None,
    }
    with _lock:
        _jobs[job_id] = job
    threading.Thread(
        target=_worker,
        args=(job_id, str(pdf_path), str(company_path), use_index),
        daemon=True,
    ).start()


async def page(request: Request):
    """演示页。"""
    return FileResponse(PAGE, media_type="text/html; charset=utf-8")


async def meta(request: Request):
    """空页面用的阶段列表和默认 company.yaml。"""
    text = SAMPLE_COMPANY.read_text(encoding="utf-8")
    return Json({"stages": _blank_stages(), "company": text})


async def start_upload(request: Request):
    """上传 PDF 和 company.yaml，立刻返回任务号。"""
    form = await request.form()
    upload = form.get("pdf")
    company_text = form.get("company")
    if not isinstance(company_text, str):
        return Json({"error": "缺少 company.yaml"}, status_code=400)
    try:
        company = _parse_company(company_text)
    except ValueError as exc:
        return Json({"error": str(exc)}, status_code=400)
    if upload is None or not getattr(upload, "filename", ""):
        return Json({"error": "请上传 PDF"}, status_code=400)
    raw = await upload.read()
    if not raw:
        return Json({"error": "PDF 是空的"}, status_code=400)
    job_id = uuid.uuid4().hex[:12]
    folder = UPLOAD_ROOT / job_id
    folder.mkdir(parents=True, exist_ok=True)
    pdf_path = folder / Path(upload.filename).name
    pdf_path.write_bytes(raw)
    (folder / "company.yaml").write_text(company_text, encoding="utf-8")
    use_index = str(form.get("mode") or "") == "library"
    _launch(
        job_id,
        Path(upload.filename).name,
        company,
        pdf_path,
        folder / "company.yaml",
        use_index,
    )
    return Json({"job_id": job_id})


async def start_sample(request: Request):
    """用样本 PDF 开始。company 文本来自页面上的编辑框。"""
    body = await request.json()
    company_text = body.get("company") if isinstance(body, dict) else ""
    if not isinstance(company_text, str):
        return Json({"error": "缺少 company.yaml"}, status_code=400)
    try:
        company = _parse_company(company_text)
    except ValueError as exc:
        return Json({"error": str(exc)}, status_code=400)
    if not SAMPLE_PDF.exists():
        return Json({"error": f"样本不存在: {SAMPLE_PDF.name}"}, status_code=400)
    job_id = uuid.uuid4().hex[:12]
    folder = UPLOAD_ROOT / job_id
    folder.mkdir(parents=True, exist_ok=True)
    company_path = folder / "company.yaml"
    company_path.write_text(company_text, encoding="utf-8")
    use_index = (body.get("mode") if isinstance(body, dict) else "") == "library"
    _launch(job_id, SAMPLE_PDF.name, company, SAMPLE_PDF, company_path, use_index)
    return Json({"job_id": job_id})


async def job_state(request: Request):
    """当前进度和已经出的表。"""
    job_id = request.path_params["job_id"]
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return Json({"error": "任务不存在"}, status_code=404)
        payload = _public(job)
    return Json(payload)


async def job_pdf(request: Request):
    """把当前任务的招标 PDF 原件交给浏览器渲染。"""
    job_id = request.path_params["job_id"]
    with _lock:
        job = _jobs.get(job_id)
        pdf_path = job["pdf_path"] if job else ""
        file_name = job["file_name"] if job else "tender.pdf"
    if not pdf_path:
        return Json({"error": "任务不存在"}, status_code=404)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=file_name,
        content_disposition_type="inline",
    )


async def page_png(request: Request):
    """按页渲 PNG。有 bbox 时在原件上画黄框。"""
    job_id = request.path_params["job_id"]
    page_num = int(request.path_params["page"])
    with _lock:
        job = _jobs.get(job_id)
        pdf_path = job["pdf_path"] if job else ""
    if not pdf_path:
        return Json({"error": "任务不存在"}, status_code=404)
    boxes = []
    for raw in request.query_params.getlist("bbox"):
        parts = raw.split(",")
        if len(parts) != 4:
            return Json({"error": "bbox 须是 x0,y0,x1,y1"}, status_code=400)
        boxes.append([float(part) for part in parts])
    try:
        png = await run_in_threadpool(render_page_png, pdf_path, page_num, boxes or None)
    except ValueError as exc:
        return Json({"error": str(exc)}, status_code=400)
    return Response(png, media_type="image/png")


def _ask_sync(index, company, question: str) -> dict:
    with _ask_lock:
        set_context(index, company)
        return ask_question(question)


async def ask(request: Request):
    """对这份招标文件提问。索引建完后即可用，不必等六张表都出完。"""
    job_id = request.path_params["job_id"]
    body = await request.json()
    question = (body.get("question") if isinstance(body, dict) else "") or ""
    question = question.strip()
    if not question:
        return Json({"error": "问题不能为空"}, status_code=400)
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return Json({"error": "任务不存在"}, status_code=404)
        index = job.get("index")
        company = job.get("company")
    if index is None:
        return Json({"error": "索引还没建好"}, status_code=409)
    out = await run_in_threadpool(_ask_sync, index, company, question)
    return Json({"answer": out["answer"], "trace": out["trace"]})


def _xlsx(tables: dict) -> bytes:
    wb = Workbook()
    first = True
    for key in TABLE_KEYS:
        title = TABLE_TITLES[key]
        ws = wb.active if first else wb.create_sheet(title)
        if first:
            ws.title = title
            first = False
        rows = tables.get(key) or []
        if not rows:
            ws.append(["空"])
            continue
        cols = [col for col in rows[0].keys() if col != "refs"]
        ws.append(cols + ["出处"])
        for row in rows:
            src = "；".join(
                f"p.{ref.get('page')} {ref.get('chapter')}"
                for ref in (row.get("refs") or [])
                if ref.get("page")
            )
            ws.append([str(row.get(col, "")) for col in cols] + [src])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def export_xlsx(request: Request):
    """导出当前已经出的表。"""
    job_id = request.path_params["job_id"]
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return Json({"error": "任务不存在"}, status_code=404)
        tables = {key: list(job["tables"].get(key) or []) for key in TABLE_KEYS}
    data = await run_in_threadpool(_xlsx, tables)
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=tender-check.xlsx"},
    )


app = Starlette(
    routes=[
        Route("/", page, methods=["GET"]),
        Route("/api/meta", meta, methods=["GET"]),
        Route("/api/check", start_upload, methods=["POST"]),
        Route("/api/check/sample", start_sample, methods=["POST"]),
        Route("/api/jobs/{job_id}", job_state, methods=["GET"]),
        Route("/api/jobs/{job_id}/file", job_pdf, methods=["GET"]),
        Route("/api/jobs/{job_id}/pages/{page:int}", page_png, methods=["GET"]),
        Route("/api/jobs/{job_id}/ask", ask, methods=["POST"]),
        Route("/api/jobs/{job_id}/export.xlsx", export_xlsx, methods=["GET"]),
        Mount("/vendor", app=StaticFiles(directory=str(VENDOR))),
    ]
)
