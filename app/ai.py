import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas import Invoice
from app.timing import timer


# Compact prompt — every token here costs CPU time on every request.
# Ollama's `format: "json"` guarantees valid JSON, so we don't need
# to explain that in words.
SYSTEM_PROMPT = (
    "Extract invoice data from the text. "
    "Return ONLY JSON, no explanations, no markdown. "
    'Schema: {"supplier_name":str|null,"invoice_number":str|null,'
    '"invoice_date":str|null,"due_date":str|null,"currency":str|null,'
    '"subtotal":num|null,"tax":num|null,"total":num|null,'
    '"line_items":[{"description":str|null,"quantity":num|null,'
    '"unit_price":num|null,"total":num|null}]}. '
    "Rules: null for missing; never invent values; dates as YYYY-MM-DD; "
    "currency as 3-letter code; numbers without symbols."
)


class AIExtractionError(Exception):
    """Base error for AI extraction problems."""


class OllamaUnavailableError(AIExtractionError):
    """Ollama is not reachable."""


class AIBadResponseError(AIExtractionError):
    """Llama returned something we could not turn into an Invoice."""


class AIExtractor:
    """Abstract interface. Swap implementation without touching the rest of the app."""

    async def extract_invoice(self, text: str) -> Invoice:
        raise NotImplementedError


class OllamaInvoiceExtractor(AIExtractor):
    def __init__(self, base_url: str, model: str, timeout: float = 240.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def extract_invoice(self, text: str) -> Invoice:
        # Invoices are 1-2 pages. 8000 chars cover header + totals + line items.
        # Anything beyond is boilerplate (T&C, second language, etc.).
        if len(text) > 8000:
            text = text[:8000]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "format": "json",        # force valid JSON output
            "stream": False,
            "keep_alive": "30m",     # keep model in RAM between requests
            "options": {
                "temperature": 0,    # deterministic extraction
                "num_predict": 800,  # cap output length
                "num_ctx": 4096,     # shrink context (default is much bigger)
                "num_thread": 0,     # 0 = use all CPU cores
            },
        }

        try:
            with timer("ollama_http"):
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/api/chat", json=payload
                    )
                    response.raise_for_status()
        except httpx.ConnectError as exc:
            raise OllamaUnavailableError(
                f"Could not reach Ollama at {self.base_url}. Is it running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise AIExtractionError(
                "Ollama took too long to respond. "
                "Try a smaller document or a smaller model."
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = ""
            try:
                body = exc.response.text[:300]
            except Exception:
                pass
            raise AIExtractionError(
                f"Ollama returned HTTP {exc.response.status_code}. "
                f"Details: {body or 'no body'}"
            ) from exc

        data = response.json()
        content = (data.get("message") or {}).get("content", "")
        if not content:
            raise AIBadResponseError("AI returned an empty response.")

        raw = _strip_code_fences(content)

        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIBadResponseError(
                "AI could not understand the document. "
                "Please try again or edit the data manually."
            ) from exc

        try:
            return Invoice.model_validate(parsed)
        except ValidationError as exc:
            raise AIBadResponseError(
                "AI returned JSON that does not match the invoice schema."
            ) from exc


def _strip_code_fences(s: str) -> str:
    """Remove ```json ... ``` wrappers if the model added them."""
    s = s.strip()
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


# Module-level singleton used by the app.
# To swap to a different provider, replace this one line.
ai_extractor: AIExtractor = OllamaInvoiceExtractor(
    base_url=settings.ollama_url,
    model=settings.ollama_model,
)