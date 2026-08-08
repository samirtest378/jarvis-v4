"""Shared runtime configuration and writable application paths.

The source checkout is writable during development, while a packaged desktop
application is not. Electron sets the directory variables below to a per-user
location so databases and preferences survive application updates.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
CONFIG_DIR = Path(os.getenv("JARVIS_CONFIG_DIR", APP_ROOT)).expanduser().resolve()
DATA_DIR = Path(os.getenv("JARVIS_DATA_DIR", CONFIG_DIR / "data")).expanduser().resolve()
LOCAL_VOICE_PACK_DIR = Path(
    os.getenv("JARVIS_LOCAL_VOICE_PACK", DATA_DIR.parent / "voice-pack" / "current")
).expanduser().resolve()
SPEECH_RUNTIME_DIR = Path(
    os.getenv("JARVIS_SPEECH_RUNTIME", APP_ROOT / "speech-runtime")
).expanduser().resolve()

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

ENV_FILE = CONFIG_DIR / ".env"
ENV_EXAMPLE_FILE = APP_ROOT / ".env.example"
FRONTEND_DIST = APP_ROOT / "frontend" / "dist"
TEMPLATES_DIR = APP_ROOT / "templates" / "prompts"

def load_env_file() -> None:
    """Load simple KEY=VALUE entries without overriding process variables."""
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

SUPPORTED_LLM_PROVIDERS = (
    "openai",
    "anthropic",
    "kimi",
    "qwen",
    "gemini",
    "grok",
    "custom",
)

# Environment-variable aliases are intentionally additive.  Existing names
# remain canonical, while common Kimi/Qwen/OpenAI-compatible names work in
# managed installs without requiring users to rename their secrets.
PROVIDER_KEY_ENV_ALIASES = {
    "ollama": (),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "kimi": ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
    "qwen": ("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "grok": ("XAI_API_KEY", "GROK_API_KEY"),
    "custom": ("OPENAI_COMPATIBLE_API_KEY",),
}

PROVIDER_DEFAULTS = {
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen3.5:9b",
        "research_model": "qwen3.5:27b",
        "key_env": "",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        # Keep every route on the user's explicitly selected GPT-5.4 Nano.
        # Research mode improves orchestration and context, not the model.
        "model": "gpt-5.4-nano",
        "research_model": "gpt-5.4-nano",
        "key_env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "base_url": "",
        "model": "claude-sonnet-5",
        "research_model": "claude-opus-4-8",
        "key_env": "ANTHROPIC_API_KEY",
    },
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "model": "kimi-k2.6",
        "research_model": "kimi-k3",
        "key_env": "MOONSHOT_API_KEY",
    },
    "qwen": {
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-plus",
        "research_model": "qwen3.7-max",
        "key_env": "DASHSCOPE_API_KEY",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.6-flash",
        "research_model": "gemini-3.1-pro-preview",
        "key_env": "GEMINI_API_KEY",
    },
    "grok": {
        "base_url": "https://api.x.ai/v1",
        "model": "grok-4.3",
        "research_model": "grok-4.3",
        "key_env": "XAI_API_KEY",
    },
    "custom": {
        "base_url": "https://provider.example/v1",
        "model": "provider-model",
        "research_model": "provider-model",
        "key_env": "OPENAI_COMPATIBLE_API_KEY",
    },
}


def normalize_llm_provider(value: str | None) -> str:
    provider = (value or "openai").strip().lower()
    return provider if provider in SUPPORTED_LLM_PROVIDERS else "openai"


LLM_PROVIDER = normalize_llm_provider(os.getenv("JARVIS_LLM_PROVIDER"))
_provider_defaults = PROVIDER_DEFAULTS[LLM_PROVIDER]
LLM_BASE_URL = os.getenv("JARVIS_LLM_BASE_URL", _provider_defaults["base_url"]).strip()
DEFAULT_MODEL = _provider_defaults["model"]
DEFAULT_RESEARCH_MODEL = _provider_defaults["research_model"]
LLM_MODEL = os.getenv("JARVIS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
RESEARCH_MODEL = (
    os.getenv("JARVIS_RESEARCH_MODEL", DEFAULT_RESEARCH_MODEL).strip()
    or DEFAULT_RESEARCH_MODEL
)
