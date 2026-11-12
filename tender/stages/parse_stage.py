"""解析段：PDF → 章节树 + 页码；建索引或复用已有索引。

阶段 2 不做表格结构识别（`ParsedDoc.tables` 为空），那是 bbox 那一轮的事。
这一段的产物是 `ParsedDoc`，另外把索引对象带出来——索引是实现细节，不进契约。
"""

from pathlib import Path
from typing import Optional

from tender.contracts import ParsedDoc, Section
from tender.index import TenderIndex, build_tender_index, load_tender_index
from tender.parse import page_count, parse_pdf
from tender.sections import split_sections
from tender.workflow import _emit


def index_cache_exists(pdf_path) -> bool:
    return (Path("data") / "tender_index" / Path(pdf_path).stem / "manifest.json").exists()


def run(pdf_path, reuse_index: bool = True) -> tuple[ParsedDoc, TenderIndex]:
    """返回 (ParsedDoc, index)。reuse_index 且缓存存在时跳过解析与向量化。"""
    cached = reuse_index and index_cache_exists(pdf_path)

    if cached:
        _emit("parse", "running", "载入已有向量库")
        index = load_tender_index(pdf_path)
        sections = index.sections
        n_pages = page_count(pdf_path)
        _emit("parse", "done", f"{n_pages} 页（复用索引）", page_count=n_pages)
        _emit("sections", "done", f"{len(sections)} 章", sections=sections)
    else:
        _emit("parse", "running", "按页抽文字和块坐标")
        pages = parse_pdf(pdf_path)
        _emit("parse", "done", f"{len(pages)} 页", page_count=len(pages))
        _emit("sections", "running", "按标题切章")
        sections = split_sections(pages)
        _emit("sections", "done", f"{len(sections)} 章", sections=sections)
        _emit("index", "running", "开始按章建向量")
        index = build_tender_index(
            pages, sections, pdf_path,
            on_chapter=lambda label, count: _emit("index", "running", f"正在建库 {label} {count} 段"),
        )
        n_pages = len(pages)
        _emit("index", "done", "索引建完")

    doc = ParsedDoc(
        pdf=str(Path(pdf_path).resolve()),
        page_count=n_pages,
        sections=[
            Section(type=s["type"], title=s["title"],
                    start_page=s["start_page"], end_page=s["end_page"])
            for s in sections
        ],
        tables=[],  # 阶段 2 不识别表格
    )
    return doc, index
