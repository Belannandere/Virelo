from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PDFExtractionError(Exception):
    """Base error for PDF extraction problems."""


class ScannedPDFError(PDFExtractionError):
    """PDF has no selectable text (most likely a scan)."""


@dataclass
class PDFExtractionResult:
    text: str
    page_count: int
    char_count: int


class PDFExtractor:
    """Abstract interface. Swap implementation without touching the rest of the app."""

    def extract_text(self, filepath: str | Path) -> PDFExtractionResult:
        raise NotImplementedError


class PypdfExtractor(PDFExtractor):
    """Extracts selectable text using pypdf (pure Python, works on any Python)."""

    def extract_text(self, filepath: str | Path) -> PDFExtractionResult:
        path = Path(filepath)
        if not path.exists():
            raise PDFExtractionError(f"File not found: {path}")

        try:
            reader = PdfReader(str(path))
        except PdfReadError as exc:
            raise PDFExtractionError(f"Could not read PDF: {exc}") from exc
        except Exception as exc:
            raise PDFExtractionError(f"Unexpected error opening PDF: {exc}") from exc

        if reader.is_encrypted:
            # Try the empty password — many PDFs use it just to set permissions
            try:
                reader.decrypt("")
            except Exception as exc:
                raise PDFExtractionError("PDF is password-protected.") from exc

        parts: list[str] = []
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                # A single bad page should not kill the whole extraction
                page_text = ""
            parts.append(page_text)

        text = "\n\n".join(parts).strip()

        if not text:
            raise ScannedPDFError(
                "This PDF appears to be a scanned document. OCR is required."
            )

        return PDFExtractionResult(
            text=text,
            page_count=len(reader.pages),
            char_count=len(text),
        )


# Module-level instance used by the app.
# To switch to PyMuPDF later, change this one line.
pdf_extractor: PDFExtractor = PypdfExtractor()