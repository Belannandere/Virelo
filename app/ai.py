import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas import Invoice


SYSTEM_PROMPT = """You are an invoice data extraction engine.
Read the invoice text and return ONE JSON object.

Return ONLY valid JSON. No explanations. No markdown. No code fences.

The JSON must match this exact schema:

{
  "supplier_name":  string | null,
  "invoice_number": string | null,
  "invoice_date":   string | null,
  "due_date":       string | null,
  "currency":       string | null,
  "subtotal":       number | null,
  "tax":            number | null,
  "total":          number | null,
  "line_items": [
    {
      "description": string | null,
      "quantity":    number | null,
      "unit_price":  number | null,
      "total":       number | null
    }
  ]
}

Rules:
- Use null for any field you cannot find in the text.
- Never invent or guess values.
- Dates: ISO format YYYY-MM-DD when possible.
- Currency: 3-letter code (EUR, USD, RUB, GBP...).
- Numbers: numeric type, dot as decimal separator, no currency symbols.
- If no line items are present, return an empty array.
"""


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
        # Safety cap on the input length.
        if len(text) > 20000:
            text = text[:20000]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "format": "json",       # ask Ollama to force JSON output
            "stream": False,
            "options": {"temperature": 0},  # deterministic extraction
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat", json=payload
                )
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise OllamaUnavailableError(
                f"Could not reach Ollama at {self.base_url}. "
                "Is it running?"
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