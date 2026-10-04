"""AI provayderlari uchun yagona interfeys: OpenRouter (standart), OpenAI, Ollama.

Kalit yo'q yoki so'rov muvaffaqiyatsiz bo'lsa — AIReportError ko'tariladi. Hech qanday
"standart" yoki to'qima hisobot qaytarilmaydi (SIMPLE.md §1: soxta ma'lumot taqiqlanadi).
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from backend.app.core.config import settings
from backend.app.core.errors import AIReportError
from backend.app.core.telemetry import logger
from backend.app.usage.tracker import record_api_call

Message = dict[str, str]


class AIProvider(Protocol):
    """Bitta AI provayderi: xabarlar ro'yxatini yuborib, javob matnini qaytaradi."""

    name: str

    def is_configured(self) -> bool: ...

    async def complete(
        self, messages: list[Message], model: str, run_id: int | None
    ) -> str: ...


class _BaseHTTPProvider:
    name = "base"
    timeout_s: float = float(settings.ai_request_timeout_s)

    def __init__(self, client_factory: Callable[[], httpx.AsyncClient] | None = None) -> None:
        self._client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=self.timeout_s))

    def _url(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _payload(self, messages: list[Message], model: str) -> dict[str, Any]:
        raise NotImplementedError

    def _parse(self, data: dict[str, Any]) -> tuple[str, int | None, int | None, float | None]:
        raise NotImplementedError

    async def complete(self, messages: list[Message], model: str, run_id: int | None) -> str:
        start = time.perf_counter()
        status, err, content = "success", None, ""
        tokens_in = tokens_out = None
        cost = None
        nbytes = 0
        try:
            async with self._client_factory() as client:
                # Umumiy muddat: provayder keep-alive bo'shliqlari yuborsa ham so'rov cheksiz cho'zilmasin
                resp = await asyncio.wait_for(
                    client.post(self._url(), headers=self._headers(), json=self._payload(messages, model)),
                    timeout=self.timeout_s,
                )
                nbytes = len(resp.content)
                if resp.status_code >= 400:
                    raise AIReportError(
                        f"AI provayderi xato qaytardi (HTTP {resp.status_code}): {resp.text[:200]}"
                    )
                content, tokens_in, tokens_out, cost = self._parse(resp.json())
            if not content or not content.strip():
                raise AIReportError("AI provayderi boʻsh javob qaytardi.")
            return content
        except AIReportError as e:
            status, err = "error", e.message_uz
            raise
        except asyncio.CancelledError:
            status, err = "cancelled", "Vazifa toʻxtatildi"
            raise
        except (httpx.TimeoutException, TimeoutError) as e:
            status, err = "timeout", str(e) or "timeout"
            raise AIReportError("AI provayderi belgilangan vaqtda javob bermadi.") from e
        except Exception as e:
            status, err = "error", str(e)
            raise AIReportError(f"AI provayderiga ulanib boʻlmadi: {str(e)[:200]}") from e
        finally:
            await record_api_call(
                run_id=run_id,
                service=self.name,
                operation="chat/completions",
                purpose="report_generation",
                dataset=model,
                request=f"model={model}, messages={len(messages)}",
                status=status,
                duration_ms=(time.perf_counter() - start) * 1000.0,
                bytes_count=nbytes,
                response=f"chars={len(content)}" if content else "",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                error=err,
            )


class OpenAICompatibleProvider(_BaseHTTPProvider):
    """OpenAI Chat Completions formatidagi provayder (OpenRouter va OpenAI)."""

    def __init__(self, name: str, base_url: str, key_getter: Callable[[], str], **kw: Any) -> None:
        super().__init__(**kw)
        self.name = name
        self._base_url = base_url
        self._key_getter = key_getter

    def is_configured(self) -> bool:
        return bool(self._key_getter())

    def _url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Authorization": f"Bearer {self._key_getter()}"}
        if self.name == "openrouter":
            h["X-Title"] = "ZaminTahlil"
        return h

    def _payload(self, messages: list[Message], model: str) -> dict[str, Any]:
        return {"model": model, "messages": messages, "temperature": 0.1}

    def _parse(self, data: dict[str, Any]) -> tuple[str, int | None, int | None, float | None]:
        choices = data.get("choices") or []
        if not choices:
            err = data.get("error", {})
            raise AIReportError(f"AI javobida natija yoʻq: {str(err)[:200]}")
        content = (choices[0].get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        cost = usage.get("cost")
        return content, usage.get("prompt_tokens"), usage.get("completion_tokens"), float(cost) if cost is not None else None


class OllamaProvider(_BaseHTTPProvider):
    """Mahalliy Ollama serveri (/api/chat)."""

    name = "ollama"

    def is_configured(self) -> bool:
        return bool(settings.ollama_base_url)

    def _url(self) -> str:
        return f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    def _payload(self, messages: list[Message], model: str) -> dict[str, Any]:
        return {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.1}}

    def _parse(self, data: dict[str, Any]) -> tuple[str, int | None, int | None, float | None]:
        content = (data.get("message") or {}).get("content") or ""
        return content, data.get("prompt_eval_count"), data.get("eval_count"), None


def build_providers() -> dict[str, AIProvider]:
    """Barcha provayderlar (kalitlar faqat .env dan)."""
    return {
        "openrouter": OpenAICompatibleProvider(
            "openrouter", "https://openrouter.ai/api/v1", lambda: settings.openrouter_api_key
        ),
        "openai": OpenAICompatibleProvider("openai", "https://api.openai.com/v1", lambda: settings.openai_api_key),
        "ollama": OllamaProvider(),
    }


class AIClient:
    """Provayderni tanlaydi va xabarlar tarixini (history window) cheklaydi."""

    def __init__(self, providers: dict[str, AIProvider] | None = None) -> None:
        self.providers = providers or build_providers()
        self._history: dict[str, list[Message]] = {}

    async def generate(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        history_key: str,
        history_size: int,
        run_id: int | None = None,
    ) -> str:
        """Hisobot matnini yaratadi. Kontekst: system + shu kalit bo'yicha oxirgi `history_size` xabar."""
        p = self.providers.get(provider)
        if p is None:
            raise AIReportError(f"Nomaʼlum AI provayderi: {provider}", code="AI_PROVIDER_UNKNOWN")
        if not p.is_configured():
            raise AIReportError(
                f"{provider} uchun API kaliti .env faylida sozlanmagan.", code="AI_NOT_CONFIGURED"
            )
        hist = self._history.setdefault(history_key, [])
        hist.append({"role": "user", "content": user_prompt})
        del hist[:-history_size]
        messages = [{"role": "system", "content": system_prompt}, *hist]
        try:
            content = await p.complete(messages, model, run_id)
        except AIReportError:
            hist.pop()  # muvaffaqiyatsiz so'rov tarixda qolmasin
            raise
        hist.append({"role": "assistant", "content": content})
        del hist[:-history_size]
        logger.info(f"AI hisobot tayyor ({provider}/{model}, {len(content)} belgi)")
        return content

    def forget(self, history_key: str) -> None:
        self._history.pop(history_key, None)


ai_client = AIClient()
