"""
招标核对用的 LLM 客户端，复用现有 OpenAI 兼容接口。

后端优先级：DeepSeek（可用）→ DevAGI（api.fe8.cn，key 已失效，保留兼容）。
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _resolve_backend(model=None):
    """按可用性挑后端，返回 (api_key, base_url, model)。"""
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        return (
            deepseek_key,
            os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )

    devagi_key = os.environ.get("DEVAGI_API_KEY")
    if devagi_key:
        return (
            devagi_key,
            os.environ.get("DEVAGI_BASE_URL", "https://api.fe8.cn/v1"),
            model or os.environ.get("DEVAGI_MODEL", "gpt-3.5-turbo"),
        )

    raise RuntimeError("请设置 DEEPSEEK_API_KEY（或 DEVAGI_API_KEY）")


def get_llm(model=None, temperature: float = 0):
    """创建对话模型。对照抽表用温度 0。"""
    api_key, base_url, model = _resolve_backend(model)
    return ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=temperature,
    )
