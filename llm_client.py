"""Provider-neutral LLM clients for JARVIS v4.

The rest of the application uses the small Anthropic-style ``messages.create``
surface.  This module preserves that interface while translating requests and
responses for OpenAI and compatible providers such as Kimi, Qwen, Gemini, and Grok.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import anthropic
import httpx


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def normalize_api_key(value: str | None) -> str:
    """Return a key safe to pass to a provider SDK.

    Keys are often pasted from a ``Bearer …`` header or from a quoted ``.env``
    line.  Keeping that harmless formatting in the stored value results in a
    confusing 401 from every provider, so normalize it at the single boundary
    shared by the Anthropic and OpenAI-compatible adapters.
    """
    cleaned = (value or "").strip()
    if not cleaned or any(character in cleaned for character in "\r\n\0"):
        return ""

    def unquote(candidate: str) -> str:
        result = candidate.strip()
        for _ in range(2):
            if len(result) < 2 or result[0] not in {"\"", "'"} or result[-1] != result[0]:
                break
            result = result[1:-1].strip()
        return result

    cleaned = unquote(cleaned)
    # Accept a complete line copied from a shell/provider setup guide. Match
    # only variable names ending in API_KEY so base64 padding ('=') inside the
    # credential is never mistaken for an assignment.
    assignment = re.fullmatch(
        r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*API_KEY)\s*=\s*(.*)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if assignment:
        cleaned = unquote(assignment.group(2))
    cleaned = re.sub(r"^authorization\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    if re.match(r"^bearer\s+", cleaned, flags=re.IGNORECASE):
        cleaned = re.sub(r"^bearer\s+", "", cleaned, count=1, flags=re.IGNORECASE).strip()
    cleaned = unquote(cleaned)
    if any(character in cleaned for character in "\r\n\0"):
        return ""
    return cleaned


def normalize_base_url(value: str, *, allow_empty: bool = False) -> str:
    """Validate a user-supplied OpenAI-compatible base URL.

    HTTPS is required for remote services. Plain HTTP is accepted only for a
    loopback service such as LM Studio or Ollama-compatible gateways.
    """
    raw = value.strip().rstrip("/")
    if not raw and allow_empty:
        return ""
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Base URL must be a complete HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Base URL cannot contain credentials, a query, or a fragment")
    if parsed.scheme == "http" and parsed.hostname.lower() not in LOOPBACK_HOSTS:
        raise ValueError("Remote custom endpoints must use HTTPS; HTTP is allowed only on this computer")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def chat_completions_url(base_url: str) -> str:
    normalized = normalize_base_url(base_url)
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


@dataclass(slots=True)
class TextBlock:
    text: str


@dataclass(slots=True)
class CompatibleResponse:
    content: list[TextBlock]
    usage: Any


class ProviderHTTPError(RuntimeError):
    """A sanitized OpenAI-compatible provider error with a stable status."""

    def __init__(self, provider: str, status_code: int, detail: str = "") -> None:
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{provider} returned HTTP {status_code}: {detail or 'request failed'}")


def _openai_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    converted: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            converted.append({"type": "text", "text": str(block.get("text", ""))})
        elif block_type == "image":
            source = block.get("source") or {}
            if source.get("type") == "base64" and source.get("data"):
                media_type = source.get("media_type", "image/png")
                converted.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{source['data']}"},
                })
            elif source.get("type") == "url" and source.get("url"):
                converted.append({
                    "type": "image_url",
                    "image_url": {"url": str(source["url"])},
                })
    return converted or ""


def _response_text(payload: dict[str, Any]) -> str:
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("The provider returned no assistant message") from exc
    if not isinstance(message, dict):
        raise RuntimeError("The provider returned no assistant message")
    # Some reasoning-capable OpenAI-compatible services return ``content`` as
    # null and put the visible answer in ``reasoning_content``.  Prefer the
    # normal answer, but keep the adapter useful for those responses too.
    content = message.get("content")
    if content is None:
        content = message.get("reasoning_content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
        )
    return str(content or "")


class _OpenAIMessages:
    def __init__(self, owner: "OpenAICompatibleClient") -> None:
        self.owner = owner

    async def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict[str, Any]],
        system: str | None = None,
        **extra: Any,
    ) -> CompatibleResponse:
        request_messages: list[dict[str, Any]] = []
        if system:
            request_messages.append({"role": "system", "content": system})
        request_messages.extend(
            {"role": item.get("role", "user"), "content": _openai_content(item.get("content", ""))}
            for item in messages
        )
        payload: dict[str, Any] = {
            "model": model,
            "messages": request_messages,
        }
        # Current OpenAI reasoning-family models use max_completion_tokens on
        # Chat Completions. Keep max_tokens for compatibility providers that
        # still document that spelling as their portable baseline.
        if self.owner.provider in {"openai", "kimi", "qwen"}:
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens
        for name in ("temperature", "top_p", "stop"):
            if name in extra:
                payload[name] = extra[name]
        if self.owner.provider == "kimi" and model.startswith(("kimi-k2.5", "kimi-k2.6")):
            payload["thinking"] = {"type": "disabled"}
        if self.owner.provider == "kimi" and model.startswith("kimi-k3"):
            # The normal preset reserves K3 for explicit quality-first research.
            payload["reasoning_effort"] = "max"
        if self.owner.provider == "qwen" and model.startswith("qwen3.7-"):
            payload["enable_thinking"] = model.startswith("qwen3.7-max")
        if (
            self.owner.provider == "openai"
            and model.startswith("gpt-5.6-")
            and model not in self.owner.unsupported_reasoning_models
        ):
            # Voice turns should begin immediately and must not spend paid
            # output tokens on hidden reasoning. Luna is the nano-like route;
            # Terra/Sol can still be selected explicitly for harder work.
            payload["reasoning_effort"] = (
                "none" if model.startswith("gpt-5.6-luna") else
                "low" if model.startswith("gpt-5.6-terra") else
                "medium"
            )
        if (
            self.owner.provider == "openai"
            and model.startswith("gpt-5.6-")
            and model not in self.owner.unsupported_verbosity_models
        ):
            # Voice conversation benefits from direct, short answers. This
            # trims visible generation time and paid output tokens without
            # weakening the model selected by the user.
            payload["verbosity"] = "low"
        # Do not add optional reasoning or verbosity controls to GPT-5.4 Nano.
        # Repeated measurements against the configured production account
        # showed the provider's default path answering in 0.65–0.87 s, versus
        # 1.02–1.96 s with those hints. Nano already optimizes this workload.
        if self.owner.provider == "ollama" and model.startswith("qwen3.5"):
            # Qwen 3.5 can spend the whole short voice-response budget on a
            # hidden reasoning trace. Ollama's OpenAI-compatible endpoint
            # supports disabling that work for low-latency conversational use.
            payload["reasoning_effort"] = "none"

        headers = {"Content-Type": "application/json"}
        if self.owner.api_key:
            headers["Authorization"] = f"Bearer {self.owner.api_key}"
        response = await self.owner.http_client.post(self.owner.endpoint, headers=headers, json=payload)
        removed_optional_fields: set[str] = set()
        # OpenAI model aliases do not all expose the same optional controls.
        # Discover support once, cache the result, and keep later turns to a
        # single request. At most two first-use retries are possible when an
        # alias rejects both controls independently.
        for _ in range(2):
            if not (
                response.is_error
                and response.status_code == 400
                and self.owner.provider == "openai"
            ):
                break
            try:
                error_payload = response.json()
                error_text = json.dumps(error_payload, ensure_ascii=True).casefold()
            except Exception:
                error_text = str(getattr(response, "text", "")).casefold()
            rejected_field = ""
            if "verbosity" in payload and "verbosity" in error_text:
                rejected_field = "verbosity"
            elif (
                "reasoning_effort" in payload
                and ("reasoning" in error_text or "effort" in error_text)
            ):
                rejected_field = "reasoning_effort"
            if not rejected_field:
                break
            payload = dict(payload)
            payload.pop(rejected_field, None)
            removed_optional_fields.add(rejected_field)
            response = await self.owner.http_client.post(
                self.owner.endpoint,
                headers=headers,
                json=payload,
            )
        if not response.is_error:
            if "reasoning_effort" in removed_optional_fields:
                self.owner.unsupported_reasoning_models.add(model)
            if "verbosity" in removed_optional_fields:
                self.owner.unsupported_verbosity_models.add(model)
        if response.is_error:
            detail = ""
            try:
                error = response.json().get("error", {})
                detail = error.get("message", "") if isinstance(error, dict) else str(error)
            except Exception:
                detail = response.text
            detail = " ".join(str(detail).split())[:300]
            # Provider error payloads occasionally include the submitted token
            # (or a short prefix of it).  Never retain that credential in a
            # message that may be shown in the Settings panel or logs.
            detail = detail.replace(self.owner.api_key, "[redacted]") if self.owner.api_key else detail
            raise ProviderHTTPError(self.owner.provider, response.status_code, detail)

        result = response.json()
        visible_text = _response_text(result).strip()
        if not visible_text:
            raise RuntimeError("The provider returned no visible assistant text")
        usage = result.get("usage") or {}
        return CompatibleResponse(
            content=[TextBlock(visible_text)],
            usage=SimpleNamespace(
                input_tokens=int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
                output_tokens=int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
            ),
        )


class OpenAICompatibleClient:
    def __init__(self, *, provider: str, api_key: str, base_url: str) -> None:
        self.provider = provider
        self.api_key = normalize_api_key(api_key)
        self.endpoint = chat_completions_url(base_url)
        self.unsupported_reasoning_models: set[str] = set()
        self.unsupported_verbosity_models: set[str] = set()
        # Reuse TLS and local socket connections across turns. Creating a new
        # client per message adds avoidable latency to every voice exchange.
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5, keepalive_expiry=30.0),
        )
        self.messages = _OpenAIMessages(self)

    async def aclose(self) -> None:
        close = getattr(self.http_client, "aclose", None)
        if close is not None:
            await close()


def create_llm_client(*, provider: str, api_key: str, base_url: str) -> Any:
    api_key = normalize_api_key(api_key)
    if provider == "anthropic":
        if not api_key:
            return None
        # A desktop assistant must recover promptly when a provider or network
        # stalls.  The SDK default can leave the UI waiting for several
        # minutes, which feels like a frozen application.
        return anthropic.AsyncAnthropic(api_key=api_key, timeout=60.0, max_retries=1)
    if provider in {"openai", "kimi", "qwen", "gemini", "grok"} and not api_key:
        return None
    return OpenAICompatibleClient(provider=provider, api_key=api_key, base_url=base_url)
