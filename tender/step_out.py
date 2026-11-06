"""把每一步的可读结果写到 data/step_output/<pdf文件名>/。"""

from pathlib import Path

from tender.sections import TYPE_LABEL

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def step_dir(pdf_path) -> Path:
    """这一份 PDF 的输出目录。"""
    folder = PROJECT_ROOT / "data" / "step_output" / Path(pdf_path).stem
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_step(pdf_path, filename: str, text: str) -> Path:
    """按 UTF-8 写入一步的全文。"""
    path = step_dir(pdf_path) / filename
    path.write_text(text, encoding="utf-8")
    return path


def _one_line(text: str, limit: int = 48) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def format_parse(pages: list[dict]) -> tuple[str, str]:
    """返回 (终端摘要, 按页全文)。"""
    block_count = sum(len(page.get("blocks") or []) for page in pages)
    source = pages[0]["source"] if pages else ""
    brief = [f"解析完成：{source}  {len(pages)} 页，文本块 {block_count}", ""]
    full = [
        f"来源: {source}",
        f"页数: {len(pages)}",
        f"文本块: {block_count}",
        "",
    ]
    for page in pages:
        text = page.get("text") or ""
        nblk = len(page.get("blocks") or [])
        brief.append(f"第{page['page']}页  {nblk}块  {len(text)}字  {_one_line(text)}")
        full.append(
            f"======== 第 {page['page']} 页  "
            f"{page['width']:.1f} x {page['height']:.1f}  块 {nblk} ========"
        )
        full.append(text)
        full.append("")
    return "\n".join(brief), "\n".join(full)


def format_sections(sections: list[dict]) -> str:
    """切章结果，终端和文件用同一份。"""
    lines = [f"切章完成：{len(sections)} 章", ""]
    for sec in sections:
        label = TYPE_LABEL.get(sec["type"], sec["type"])
        lines.append(f"{label}  {sec['title']}  p.{sec['start_page']}-{sec['end_page']}")
    return "\n".join(lines)


def format_index(index) -> tuple[str, str]:
    """返回 (各章段数, 全部分段正文)。"""
    total = 0
    brief = []
    full = []
    for typ, store in index.stores.items():
        chunks = list(store.chunks or [])
        total += len(chunks)
        label = TYPE_LABEL.get(typ, typ)
        brief.append(f"{label}  {len(chunks)} 段")
        full.append(f"======== {label}  {len(chunks)} 段 ========")
        for i, chunk in enumerate(chunks, start=1):
            full.append(f"[{i}] p.{chunk['page']}  {chunk['section_title']}")
            full.append(chunk["text"])
            full.append("")
        full.append("")
    head = f"索引完成：{total} 段"
    return "\n".join([head, ""] + brief), "\n".join([head, ""] + full)
