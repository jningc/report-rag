"""
招标文件核对：分步查看 / 切章出表 / 提问

用法:
  python main.py parse sample/beijing_road.pdf
  python main.py sections sample/beijing_road.pdf
  python main.py index sample/beijing_road.pdf
  python main.py check sample/beijing_road.pdf sample/company.yaml
  python main.py ask "投标保证金多少" --pdf sample/beijing_road.pdf --company sample/company.yaml
  python main.py web
"""

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_COMPANY = PROJECT_ROOT / "sample" / "company.yaml"


def _show(brief: str, path) -> None:
    print(brief)
    print(f"\n全文已写入 {path}")


def cmd_parse(args):
    """按页抽文本，摘要打在终端，全文写入文件。"""
    from tender.parse import parse_pdf
    from tender.step_out import format_parse, write_step

    pages = parse_pdf(args.pdf)
    brief, full = format_parse(pages)
    path = write_step(args.pdf, "01_parse.txt", full)
    _show(brief, path)


def cmd_sections(args):
    """切章并打印每一章的页码范围。"""
    from tender.parse import parse_pdf
    from tender.sections import split_sections
    from tender.step_out import format_sections, write_step

    pages = parse_pdf(args.pdf)
    text = format_sections(split_sections(pages))
    path = write_step(args.pdf, "02_sections.txt", text)
    _show(text, path)


def cmd_index(args):
    """切块并建索引。终端只打各章段数，分段正文写入文件。"""
    from tender.index import build_tender_index
    from tender.parse import parse_pdf
    from tender.sections import split_sections
    from tender.step_out import format_index, write_step

    print(f"解析并切章 {args.pdf}", flush=True)
    pages = parse_pdf(args.pdf)
    sections = split_sections(pages)
    print("开始建索引。向量化在 CPU 上，要几分钟。", flush=True)
    index = build_tender_index(pages, sections, args.pdf)
    brief, full = format_index(index)
    path = write_step(args.pdf, "03_index.txt", full)
    _show(brief, path)


def cmd_check(args):
    """解析招标文件，跑四步对照并打印。"""
    from tender.step_out import write_step
    from tender.workflow import render_tables, run_check

    result = run_check(args.pdf, args.company)
    text = render_tables(result)
    print(text)
    path = write_step(args.pdf, "04_check.txt", text)
    print(f"\n全文已写入 {path}")


def cmd_ask(args):
    """对当前文件提问。"""
    from tender.ask_box import ask_question
    from tender.index import build_tender_index
    from tender.parse import parse_pdf
    from tender.sections import split_sections
    from tender.tools import set_context
    from tender.workflow import load_company

    pages = parse_pdf(args.pdf)
    sections = split_sections(pages)
    index = build_tender_index(pages, sections, args.pdf)
    set_context(index, load_company(args.company))
    out = ask_question(args.question)
    lines = [args.question, ""]
    for step in out["trace"]:
        line = f"  {step['tool']} {step['args']}"
        print(line)
        lines.append(line)
    print()
    print(out["answer"])
    lines.extend(["", out["answer"]])
    from tender.step_out import write_step
    path = write_step(args.pdf, "05_ask.txt", "\n".join(lines))
    print(f"\n全文已写入 {path}")


def cmd_web(args):
    """启动核对页面。浏览器打开 http://127.0.0.1:8765"""
    import uvicorn

    uvicorn.run("tender.web:app", host="127.0.0.1", port=args.port, log_level="info")


def main():
    parser = argparse.ArgumentParser(description="招标文件核对")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="按页抽文本，写出全文")
    p_parse.add_argument("pdf", help="招标文件 PDF")
    p_parse.set_defaults(func=cmd_parse)

    p_sections = sub.add_parser("sections", help="切章并写出页码范围")
    p_sections.add_argument("pdf", help="招标文件 PDF")
    p_sections.set_defaults(func=cmd_sections)

    p_index = sub.add_parser("index", help="切块建索引，写出分段正文")
    p_index.add_argument("pdf", help="招标文件 PDF")
    p_index.set_defaults(func=cmd_index)

    p_check = sub.add_parser("check", help="切章、四步出表")
    p_check.add_argument("pdf", help="招标文件 PDF")
    p_check.add_argument("company", nargs="?", default=str(DEFAULT_COMPANY), help="company.yaml")
    p_check.set_defaults(func=cmd_check)

    p_web = sub.add_parser("web", help="打开核对页面")
    p_web.add_argument("--port", type=int, default=8765, help="端口，默认 8765")
    p_web.set_defaults(func=cmd_web)

    p_ask = sub.add_parser("ask", help="只在指定章节里提问")
    p_ask.add_argument("question", help="问题")
    p_ask.add_argument("--pdf", required=True, help="招标文件 PDF")
    p_ask.add_argument("--company", default=str(DEFAULT_COMPANY), help="company.yaml")
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
