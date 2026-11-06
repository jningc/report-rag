from __future__ import annotations

"""
招标 PDF 解析：按页抽文本和块坐标，并可渲成页图。

每页：
  page / width / height / text / blocks[{text, bbox}]
bbox 为 PDF 点坐标 [x0, y0, x1, y1]，原点在左上。
"""

from pathlib import Path

import pymupdf as fitz


def parse_pdf(pdf_path) -> list[dict]:
    """按页抽出文本块和 bbox。"""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 不存在: {path}")

    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc, start=1):
        raw = page.get_text("dict")
        blocks = []
        texts = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            lines = []
            for line in block.get("lines", []):
                lines.append("".join(span.get("text", "") for span in line.get("spans", [])))
            text = "\n".join(part for part in lines if part).strip()
            if not text:
                continue
            x0, y0, x1, y1 = block["bbox"]
            blocks.append({
                "text": text,
                "bbox": [float(x0), float(y0), float(x1), float(y1)],
            })
            texts.append(text)
        pages.append({
            "source": path.name,
            "page": i,
            "width": float(page.rect.width),
            "height": float(page.rect.height),
            "text": "\n".join(texts),
            "blocks": blocks,
        })
    doc.close()
    return pages


def render_page_png(pdf_path, page_num: int, bboxes: list | None = None, scale: float = 1.6) -> bytes:
    """把一页渲成 PNG。bboxes 有值时在原件上画黄框。"""
    path = Path(pdf_path)
    doc = fitz.open(path)
    if page_num < 1 or page_num > doc.page_count:
        doc.close()
        raise ValueError(f"页码超出范围: {page_num}")
    page = doc[page_num - 1]
    if bboxes:
        shape = page.new_shape()
        for box in bboxes:
            if not box or len(box) != 4:
                continue
            rect = fitz.Rect(box)
            shape.draw_rect(rect)
        shape.finish(color=(0.83, 0.53, 0.02), fill=(1, 0.77, 0), fill_opacity=0.28, width=1.2)
        shape.commit()
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    data = pix.tobytes("png")
    doc.close()
    return data


def page_count(pdf_path) -> int:
    """PDF 页数。"""
    doc = fitz.open(pdf_path)
    n = doc.page_count
    doc.close()
    return n
