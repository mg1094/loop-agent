from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None  # type: ignore

AGENT_DIR = Path(__file__).resolve().parents[1]
_ENV_CANDIDATES = [
    Path.home() / ".loop-agent" / ".env",
    AGENT_DIR / ".env",
    Path.cwd() / ".env",
]
_dotenv_loaded = False


def _ensure_dotenv() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    for candidate in _ENV_CANDIDATES:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break
    _dotenv_loaded = True


_PROVIDER_CONFIG: dict[str, tuple[Optional[str], str]] = {
    "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
    "dashscope": ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"),
    "qwen": ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"),
    "moonshot": ("MOONSHOT_API_KEY", "MOONSHOT_BASE_URL"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_BASE_URL"),
    "groq": ("GROQ_API_KEY", "GROQ_BASE_URL"),
    "ollama": (None, "OLLAMA_BASE_URL"),
}


def _sync_provider_env() -> None:
    _ensure_dotenv()
    provider = os.getenv("LANGCHAIN_PROVIDER", "openai").lower()
    key_env, base_env = _PROVIDER_CONFIG.get(provider, ("OPENAI_API_KEY", "OPENAI_BASE_URL"))

    if key_env is not None:
        api_key = os.getenv(key_env, "") or os.getenv("OPENAI_API_KEY", "")
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

    base_url = os.getenv(base_env, "")
    if base_url:
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        os.environ["OPENAI_API_BASE"] = base_url
        os.environ["OPENAI_BASE_URL"] = base_url


def build_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_retries: Optional[int] = None,
    timeout: Optional[int] = None,
) -> Any:
    if ChatOpenAI is None:
        raise RuntimeError("langchain-openai is not installed")

    _sync_provider_env()

    model_name = model or os.getenv("LANGCHAIN_MODEL_NAME", "gpt-4o-mini")
    temp = temperature if temperature is not None else float(os.getenv("LANGCHAIN_TEMPERATURE", "0.0"))
    retries = max_retries if max_retries is not None else int(os.getenv("MAX_RETRIES", "2"))
    to = timeout if timeout is not None else int(os.getenv("TIMEOUT_SECONDS", "120"))

    kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": temp,
        "max_retries": retries,
        "timeout": to,
    }

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    return ChatOpenAI(**kwargs)
