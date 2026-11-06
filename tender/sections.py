from __future__ import annotations

"""
按目录和标题把招标文件切成章，并标成固定类型。

类型：invite / notice / qualify / score / demand / contract / format / unknown
三份样本的章名不一样，靠别名表对齐，不写死某一份的目录。
"""

import re

# 章类型 -> 标题里会出现的词
TYPE_ALIASES = {
    "invite": ["投标邀请", "招标公告", "采购公告", "邀请书"],
    "notice": ["投标人须知", "供应商须知", "磋商须知", "须知资料表"],
    "qualify": ["资格审查", "资格要求", "资格预审"],
    "score": ["评标办法", "评标方法", "评标标准", "评分标准", "评标程序"],
    "demand": ["采购需求", "项目需求", "技术规格", "服务要求", "公开招标需求", "招标需求"],
    "contract": ["合同文本", "合同条款", "拟签订的合同", "合同草案", "合同主要条款"],
    "format": ["投标文件格式", "响应文件格式", "报价文件格式"],
}

TYPE_LABEL = {
    "invite": "投标邀请/招标公告",
    "notice": "投标人须知",
    "qualify": "资格审查",
    "score": "评标办法",
    "demand": "采购需求",
    "contract": "合同",
    "format": "投标文件格式",
    "unknown": "未分类",
}

# 只认行首的章标题，避免「见第四章」「详见第五章」这种正文
_CHAPTER_LINE_RE = re.compile(
    r"^[\s　]*(第[一二三四五六七八九十百零0-9]+[章节部分篇])"
    r"[\s　]*([^\s　].{0,36})$"
)


def classify_title(title: str) -> str:
    """用别名表给标题标类型；对不上就是 unknown。"""
    text = title.replace(" ", "")
    # 格式章里也会出现「资格」二字，先匹配更长、更具体的
    ordered = [
        "format", "contract", "score", "qualify", "notice", "demand", "invite",
    ]
    for typ in ordered:
        for alias in TYPE_ALIASES[typ]:
            if alias.replace(" ", "") in text:
                return typ
    return "unknown"


def _heading_candidates(pages: list[dict]) -> list[dict]:
    """从每页靠前的块里找章标题。"""
    found = []
    seen = set()
    for page in pages:
        early = [b["text"].replace("\n", "").strip() for b in page.get("blocks", [])[:12]]
        chapter_hits = [t for t in early if _CHAPTER_LINE_RE.match(t)]
        # 目录页同一页堆多条「第X章」，跳过，等正文
        if len(chapter_hits) >= 3:
            continue
        for block in page.get("blocks", [])[:10]:
            line = block["text"].replace("\n", "").strip()
            if "见第" in line or "详见" in line or "按照第" in line:
                continue
            m = _CHAPTER_LINE_RE.match(line)
            if not m:
                continue
            title = line
            typ = classify_title(title)
            if typ == "unknown":
                continue
            if typ in seen:
                continue
            seen.add(typ)
            found.append({
                "page": page["page"],
                "title": title,
                "type": typ,
            })
            break
    return found


def split_sections(pages: list[dict]) -> list[dict]:
    """按出现顺序切章。同一类型只保留第一次，避免目录页和正文各切一次。"""
    if not pages:
        return []
    heads = _heading_candidates(pages)
    # 丢掉目录里的预告：若连续两个标题页码相同且都在前 6 页，多半是目录，等后文
    cleaned = []
    for h in heads:
        if h["type"] == "unknown":
            continue
        if cleaned and cleaned[-1]["type"] == h["type"] and h["page"] - cleaned[-1]["page"] <= 1:
            continue
        # 目录页常把所有章堆在第 1～4 页；同页出现多个类型则跳过这一条
        same_page = [x for x in heads if x["page"] == h["page"] and x["type"] != "unknown"]
        if h["page"] <= 4 and len({x["type"] for x in same_page}) >= 3:
            continue
        cleaned.append(h)

    if not cleaned:
        return [{
            "type": "unknown",
            "title": "全文未切出章节",
            "start_page": pages[0]["page"],
            "end_page": pages[-1]["page"],
        }]

    last_page = pages[-1]["page"]
    sections = []
    used = set()
    for i, h in enumerate(cleaned):
        if h["type"] in used:
            continue
        used.add(h["type"])
        end = last_page
        for nxt in cleaned[i + 1:]:
            if nxt["type"] not in used and nxt["page"] > h["page"]:
                end = nxt["page"] - 1
                break
        sections.append({
            "type": h["type"],
            "title": h["title"],
            "start_page": h["page"],
            "end_page": max(end, h["page"]),
        })
    return sections


def section_of_page(sections: list[dict], page: int) -> dict | None:
    """页码落到哪一章。"""
    for sec in sections:
        if sec["start_page"] <= page <= sec["end_page"]:
            return sec
    return None


def required_types_present(sections: list[dict], types: list[str]) -> list[str]:
    """返回缺失的章类型。"""
    have = {s["type"] for s in sections}
    return [t for t in types if t not in have]
