"""
提问框和条款跳转用的工具。都是普通函数，价格分由代码算。
"""

from langchain_core.tools import tool

from tender.index import TenderIndex
from tender.sections import TYPE_ALIASES, classify_title

# 当前正在核对的文件，由 run_check / ask 写入
CTX: dict = {
    "index": None,
    "company": None,
}


def set_context(index: TenderIndex, company: dict) -> None:
    """绑定当前招标文件和公司情况。"""
    CTX["index"] = index
    CTX["company"] = company


def _need_index() -> TenderIndex:
    idx = CTX.get("index")
    if idx is None:
        raise RuntimeError("尚未加载招标文件，请先运行 check")
    return idx


def _types_from_name(name: str) -> list[str]:
    typ = classify_title(name)
    if typ != "unknown":
        return [typ]
    for key, aliases in TYPE_ALIASES.items():
        if name in aliases or name == key:
            return [key]
    return [name]


@tool
def search_section(query: str, section: str) -> str:
    """在指定章节类型里检索。section 例如：投标人须知、评标办法、资格审查、合同、投标文件格式、投标邀请。"""
    idx = _need_index()
    types = _types_from_name(section)
    hits = idx.search(query, types, k=4)
    if not hits:
        return "文件中未找到"
    lines = []
    for h in hits:
        lines.append(f"第{h['page']}页 {h['section_title']}\n{h['text'][:400]}")
    return "\n\n".join(lines)


@tool
def follow_reference(hint: str) -> str:
    """跟随「见前附表 / 详见第X章」这类引用，到对应章节再取一段。"""
    idx = _need_index()
    types = [s["type"] for s in idx.sections]
    hits = idx.search(hint, types, k=3)
    if not hits:
        return "文件中未找到"
    lines = [f"第{h['page']}页 {h['section_title']}\n{h['text'][:400]}" for h in hits]
    return "\n\n".join(lines)


@tool
def read_company() -> str:
    """读取当前 company.yaml。"""
    company = CTX.get("company")
    if not company:
        return "未加载公司情况"
    import yaml
    return yaml.safe_dump(company, allow_unicode=True)


@tool
def calc_price_score(base: float, bid: float, full: float = 30) -> str:
    """按评标办法常见公式算价格分：基准价 / 投标报价 × 满分。不由模型口算。"""
    if bid <= 0:
        raise ValueError("投标报价必须大于 0")
    score = round(base / bid * full, 2)
    return f"价格分 = ({base} / {bid}) × {full} = {score}"


ALL_TOOLS = [search_section, follow_reference, read_company, calc_price_score]
