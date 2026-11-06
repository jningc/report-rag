"""
提问框：模型只在四个工具里选，最多 5 步，找不到就说文件中未找到。
"""

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from tender.llm import get_llm
from tender.tools import ALL_TOOLS

SYSTEM = """你只根据当前这份招标文件回答。
必须通过工具取证：search_section、follow_reference、read_company、calc_price_score。
search_section 必须指定章节，禁止假装搜过整份文件。
价格分必须调用 calc_price_score，不要自己乘除。
资料不够就回答「文件中未找到」，不要编。
回答里写明页码，例如 [p.22]。
投标保证金和履约保证金不是一笔钱，引用时必须分开。"""


def ask_question(question: str, max_steps: int = 5) -> dict:
    """跑一轮工具循环，返回回答和调用轨迹。"""
    q = (question or "").strip()
    if not q:
        raise ValueError("问题不能为空")
    llm = get_llm().bind_tools(ALL_TOOLS)
    tools = {t.name: t for t in ALL_TOOLS}
    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=q)]
    trace = []
    for _ in range(max_steps):
        ai = llm.invoke(messages)
        messages.append(ai)
        if not getattr(ai, "tool_calls", None):
            text = (ai.content or "").strip() or "文件中未找到"
            return {"answer": text, "trace": trace}
        for call in ai.tool_calls:
            name = call["name"]
            args = call.get("args") or {}
            tool = tools.get(name)
            if tool is None:
                result = "未知工具"
            else:
                result = tool.invoke(args)
            trace.append({"tool": name, "args": args, "result": str(result)[:240]})
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
    return {"answer": "文件中未找到（已达工具步数上限）", "trace": trace}
