"""
招标文件核对：切章出表 / 提问

用法:
  python main.py check sample/beijing_road.pdf sample/company.yaml
  python main.py ask "投标保证金多少" --pdf sample/beijing_road.pdf --company sample/company.yaml
"""

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_COMPANY = PROJECT_ROOT / "sample" / "company.yaml"


def cmd_check(args):
    """解析招标文件，跑四步对照并打印。"""
    from tender.workflow import print_tables, run_check

    result = run_check(args.pdf, args.company)
    print_tables(result)


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
    for step in out["trace"]:
        print(f"  {step['tool']} {step['args']}")
    print()
    print(out["answer"])


def main():
    parser = argparse.ArgumentParser(description="招标文件核对")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="切章、四步出表")
    p_check.add_argument("pdf", help="招标文件 PDF")
    p_check.add_argument("company", nargs="?", default=str(DEFAULT_COMPANY), help="company.yaml")
    p_check.set_defaults(func=cmd_check)

    p_ask = sub.add_parser("ask", help="只在指定章节里提问")
    p_ask.add_argument("question", help="问题")
    p_ask.add_argument("--pdf", required=True, help="招标文件 PDF")
    p_ask.add_argument("--company", default=str(DEFAULT_COMPANY), help="company.yaml")
    p_ask.set_defaults(func=cmd_ask)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
