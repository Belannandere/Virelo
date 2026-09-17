🌐 **Language:** **English** · [Русский](README.ru.md)
# Virelo

**Local AI invoice processing.**  
Turn PDF invoices into structured, validated data using a local LLM.

```
PDF  →  AI extraction  →  Validation  →  Review  →  CSV
```

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

🌐 **Language:** **English** · [Русский](README.ru.md)

---

## Demo

<p align="center">
  <img src="docs/demo.gif" alt="Virelo demo — upload an invoice and get structured data" width="720">
</p>

Upload an invoice PDF → let AI extract the fields → review the result → export to CSV.

> **Note:** This is an early MVP. Not every invoice format is handled perfectly yet. See [Limitations](#limitations).

---

## Why Virelo?

Manual invoice data entry is slow, repetitive, and easy to get wrong. Most AI-powered tools solve this by sending your documents to a cloud provider. Virelo takes a different approach.

Virelo runs the language model **locally** on your machine through [Ollama](https://ollama.com). Invoice contents stay on your computer during processing — nothing is sent to OpenAI, Anthropic, Google, or any other cloud AI service.

Key ideas:

- **Local processing** — inference runs on your hardware.
- **Structured output** — the model returns a strict JSON schema, validated with Pydantic.
- **Deterministic validation** — business rules (arithmetic, required fields) are enforced in Python, not guessed by the model.
- **Human review** — every invoice can be approved, edited, or rejected before it enters your records.

---

## Features

- Drag & drop PDF invoice upload
- Text extraction from text-based PDFs
- Local Llama inference via Ollama
- Structured JSON extraction with a fixed schema
- Pydantic schema validation
- Deterministic invoice validation (arithmetic checks, required fields)
- Human review and inline editing
- Approve / Reject workflow
- SQLite persistence
- CSV export (single invoice or all invoices)
- Invoice history with basic statistics

---

## How it works

```
PDF invoice
    ↓
pypdf (text extraction)
    ↓
Ollama + Llama 3.2 (local inference)
    ↓
Structured JSON
    ↓
Pydantic (schema validation)
    ↓
Python validation rules
    ↓
SQLite (persistence)
    ↓
Web UI (review, edit, approve/reject)
    ↓
CSV export
```

**Architectural principle:**

> The LLM is responsible for **extracting** information. Business rules — required fields, arithmetic consistency, currency handling — are handled **deterministically** in Python.

This separation keeps the system predictable. If the model hallucinates a total, the validator catches it. If a required field is missing, the UI surfaces it. The AI never decides what is "correct" — it only proposes values that Python then checks.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| Templates | Jinja2, Bootstrap 5 |
| Validation | Pydantic 2 |
| ORM | SQLModel (SQLAlchemy) |
| Database | SQLite |
| PDF text | pypdf (pure Python) |
| AI | Ollama + Llama 3.2 (local) |
| HTTP client | httpx |

---

## Architecture

```
PDF invoice
    ↓
pypdf
    ↓
Ollama / Llama
    ↓
Structured JSON
    ↓
Pydantic
    ↓
Python validation rules
    ↓
SQLite
    ↓
Web UI
    ↓
CSV
```

The application is a single FastAPI process. There are no microservices, no queue, no external database. The AI provider is abstracted behind an `AIExtractor` interface, so swapping Llama for another model (or an API) only requires writing a new class and changing one line in `app/ai.py`.

The same is true for PDF extraction: `PDFExtractor` is an interface, and `PypdfExtractor` is the current implementation. A future `OCRPdfExtractor` would slot in without touching the rest of the code.

---

## Requirements

- **OS:** Windows, macOS, or Linux
- **Python:** 3.11 or newer (tested on 3.11, 3.12, and 3.14)
- **Ollama:** installed locally — [download here](https://ollama.com/download)
- **Model:** `llama3.2` (~2 GB) pulled through Ollama

No cloud API keys are required. No paid services are used.

---

## Installation

### 1. Install Ollama

Download from the official site: <https://ollama.com/download>

Follow the installer for your OS. Once installed, Ollama runs as a background service.

Verify it is running:

```bash
ollama --version
```

### 2. Pull the model

```bash
ollama pull llama3.2
```

This downloads the model (~2 GB) and caches it locally.

Verify:

```bash
ollama list
```

You should see `llama3.2` in the output.

### 3. Clone the repository

```bash
git clone https://github.com/Belannandere/Virelo.git
cd Virelo
```

### 4. Create a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 5. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 6. Configure environment variables

Copy the example file:

```bash
copy .env.example .env       # Windows
cp .env.example .env         # macOS / Linux
```

The defaults work out of the box. You can adjust `OLLAMA_URL`, `OLLAMA_MODEL`, upload limits, and the database URL if needed.

---

## Running Virelo

You need **two terminals** — one for Ollama, one for the app.

### Terminal 1 — Ollama

```bash
ollama serve
```

> **If Ollama crashes with a CUDA error** on Windows with an NVIDIA GPU, force CPU mode:
>
> ```powershell
> $env:OLLAMA_LLM_LIBRARY="cpu_avx2"
> ollama serve
> ```
>
> To make this permanent, add `OLLAMA_LLM_LIBRARY=cpu_avx2` to your user environment variables.

### Terminal 2 — Virelo

```bash
python -m uvicorn app.main:app --reload
```

Open <http://localhost:8000> in your browser.

---

## Usage

1. Go to **Upload**.
2. Drop a PDF invoice with a text layer (you should be able to select text in any PDF viewer).
3. Wait for the extraction. On CPU-only inference, this can take 30–90 seconds for a single page.
4. Review the extracted fields, line items, and validation messages.
5. Choose one of:
   - **Approve** — accept the data as-is.
   - **Edit** — correct any field, then re-save. Validation runs again automatically.
   - **Reject** — mark the document as not processed.
6. Download the result as CSV — either for one invoice or for all invoices at once from the **Invoices** page.

---

## Limitations

Virelo is an early MVP. It is honest about what it can and cannot do.

**What it does NOT do:**

- **OCR for scanned PDFs.** If a PDF has no text layer, Virelo will refuse to process it and tell you clearly. OCR (Tesseract, EasyOCR) is on the roadmap.
- **Email ingestion.** Invoices must be uploaded manually. IMAP ingestion is not implemented.
- **Accounting integrations.** No QuickBooks, Xero, or similar yet.
- **Line-item editing in the UI.** You can edit invoice-level fields; individual line items are currently read-only after extraction.
- **Multi-user / authentication.** The current build is single-user, running locally.

**Quality caveats:**

- Llama 3.2 (3B) is a small model. It handles clean, text-based invoices well, but may occasionally miss line items or produce a wrong total on dense or unusual layouts. This is exactly why deterministic validation and human review exist.
- On CPU-only inference, processing is slow. `llama3.2:1b` is faster but less accurate on tables. A GPU dramatically improves speed.

---

## Roadmap

Ideas being considered for future versions:

- OCR support for scanned documents
- IMAP / email ingestion
- Full line-item editing in the review UI
- Excel export (`.xlsx`)
- Multi-currency validation rules
- QuickBooks / Xero integrations
- Optional API keys for a hosted version

Nothing here is promised. It's a wishlist, not a contract.

---

## Project structure

```
Virelo/
├── app/
│   ├── main.py          # FastAPI app, routes
│   ├── config.py        # Settings loaded from .env
│   ├── database.py      # SQLite engine, session, init_db
│   ├── models.py        # SQLModel tables
│   ├── schemas.py       # Pydantic Invoice schema
│   ├── repository.py    # Database CRUD operations
│   ├── pdf.py           # PDFExtractor + PypdfExtractor
│   ├── ai.py            # AIExtractor + OllamaInvoiceExtractor
│   ├── validation.py    # Deterministic business rules
│   ├── export.py        # CSV generation
│   ├── timing.py        # Per-stage timing helpers
│   ├── templates/       # Jinja2 templates
│   └── static/          # CSS, favicon
├── uploads/             # Uploaded PDFs (gitignored)
├── .env.example
├── requirements.txt
└── README.md
```

---

## Configuration

Virelo reads settings from `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Model name (e.g. `llama3.2:1b` for a smaller one) |
| `UPLOAD_DIR` | `uploads` | Where PDFs are stored |
| `MAX_UPLOAD_MB` | `10` | Maximum upload size |
| `DATABASE_URL` | SQLite file in project root | Database connection string |

Switching models is a one-line change — edit `OLLAMA_MODEL` and restart the app.

---

## Extending Virelo

### Use a different LLM

`app/ai.py` defines an abstract `AIExtractor`. To plug in another provider (Mistral, Qwen, or even a cloud API), subclass it and change the singleton at the bottom of the file:

```python
ai_extractor: AIExtractor = YourNewExtractor(...)
```

### Add OCR for scanned PDFs

`app/pdf.py` defines an abstract `PDFExtractor`. Add an `OCRPdfExtractor(PDFExtractor)` and swap the singleton:

```python
pdf_extractor: PDFExtractor = OCRPdfExtractor()
```

The rest of the app does not need to know.

### Faster PDF parsing (PyMuPDF)

`pypdf` is a pure-Python package and works on any Python version. If you want faster parsing or better handling of complex layouts, you can switch to **PyMuPDF** — but it ships as compiled wheels, which may not exist for the newest Python releases on Windows.

To switch:

1. `python -m pip install pymupdf`
2. Add a `PyMuPDFExtractor(PDFExtractor)` class next to `PypdfExtractor` in `app/pdf.py`.
3. Change the singleton at the bottom of the file.

No other code changes are needed.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `pip: command not found` | Use `python -m pip` instead |
| `uvicorn: command not found` | Use `python -m uvicorn` instead |
| Ollama crashes with a CUDA error | Start it with `OLLAMA_LLM_LIBRARY=cpu_avx2` |
| `AI extraction failed` / HTTP 500 from Ollama | Ollama is not running or crashed. Test with `curl http://localhost:11434/api/tags` |
| "This PDF appears to be a scanned document" | The PDF has no text layer. OCR is not yet supported. |
| Processing takes 2+ minutes | You are running on CPU. Try `llama3.2:1b` via `OLLAMA_MODEL=llama3.2:1b` in `.env`. |
| Database contains stale data | Delete `invoices.db` and restart the app. |

---

## License

MIT