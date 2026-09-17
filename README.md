# Virelo

**Local AI invoice processing.**  
Turn PDF invoices into structured, validated data using a local LLM.

```
PDF  →  AI extraction  →  Validation  →  Review  →  CSV / Excel
```

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

🇷🇺 [Русский](README.ru.md) · 🇬🇧 **English**

---

## Demo

<p align="center">
  <img src="docs/demo.gif" alt="Virelo demo — upload an invoice and get structured data" width="720">
</p>

Sign up → upload an invoice PDF → AI extracts the fields → review → approve → export to CSV or Excel.

> **Note:** this is an early MVP. Not every invoice format is handled perfectly. See [Limitations](#limitations).

---

## Why Virelo?

Manual invoice data entry is slow, repetitive, and easy to get wrong. Most AI-powered tools solve this by sending your documents to a cloud provider. Virelo takes a different approach.

Virelo runs the language model **locally** through [Ollama](https://ollama.com). Invoice contents stay on the machine that runs the server — nothing is sent to OpenAI, Anthropic, Google, or any other cloud AI service.

Key ideas:

- **Local processing** — inference runs on your own hardware.
- **Structured output** — the model returns a strict JSON schema, validated with Pydantic.
- **Deterministic validation** — business rules (arithmetic, required fields) are enforced in Python, not guessed by the model.
- **Human review** — every invoice can be approved, edited, or rejected before it enters your records.

---

## Features

**AI pipeline**

- Drag & drop PDF invoice upload
- Text extraction from text-based PDFs (`pypdf`, pure Python)
- Local Llama inference via Ollama
- Structured JSON extraction with a fixed schema
- Pydantic schema validation
- Deterministic business-rule validation (arithmetic checks, required fields)

**Review & editing**

- Human review with inline editing
- Full line-item editing (add / edit / remove rows)
- Approve / Reject workflow
- Automatic re-validation after each edit

**Accounts & limits**

- Email + password registration and login
- Sign in with Google (OAuth 2.0 / OpenID Connect)
- Sign in with GitHub (OAuth 2.0)
- Account linking by verified email
- Free plan with a **10 invoices / month** limit
- Monthly usage tracking with automatic reset
- Settings page: change email, set or change password, delete account

**Data & export**

- SQLite persistence
- Strict per-user data isolation (user A never sees user B's invoices)
- CSV export (single invoice or all)
- Excel export (`.xlsx`, includes a second sheet with line items)

**UI**

- Light and dark theme
- Mobile-friendly layout

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
CSV / Excel export
```

**Architectural principle:**

> The LLM is responsible for **extracting** information. Business rules — required fields, arithmetic consistency, currency handling — are enforced **deterministically** in Python.

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
| Passwords | bcrypt |
| Sessions | Starlette SessionMiddleware |
| OAuth | Authlib |
| Excel | openpyxl |
| Tests | pytest |

---

## Requirements

- **OS:** Windows, macOS, or Linux
- **Python:** 3.11 or newer (tested on 3.11, 3.12, and 3.14)
- **Ollama:** installed locally — [download here](https://ollama.com/download)
- **Model:** `llama3.2` (~2 GB) pulled through Ollama

No cloud AI API keys are required. No paid services are used.

---

## Installation

### 1. Install Ollama

Download from the official site: <https://ollama.com/download> and follow the installer for your OS.

Verify it is running:

```bash
ollama --version
```

### 2. Pull the model

```bash
ollama pull llama3.2
```

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

```bash
copy .env.example .env       # Windows
cp .env.example .env         # macOS / Linux
```

Generate a `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the output into `SECRET_KEY=` in `.env`. The rest of the defaults work out of the box.

### 7. (Optional) Set up OAuth

If you want "Sign in with Google" / "Sign in with GitHub", follow the setup guides at the end of this document. If you skip this step, the OAuth buttons will simply redirect to `?error=oauth_unavailable` — email/password auth still works.

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

1. Sign up at `/register` — or use Google / GitHub.
2. Go to **Upload**.
3. Drop a PDF invoice with a text layer (you should be able to select text in any PDF viewer).
4. Wait for extraction. On CPU-only inference this can take 30–90 seconds per page.
5. Review the extracted fields, line items, and validation messages.
6. Choose one of:
   - **Approve** — accept the data as-is.
   - **Edit** — correct any field or line item, then save. Validation runs again automatically.
   - **Reject** — mark the document as not processed.
7. Download the result as **CSV** or **Excel** — for a single invoice or for all invoices from the **Invoices** page.

Free plan: **10 invoices per month**.

---

## Running tests

```bash
pytest -v
```

The test suite covers authentication, user-data isolation (user A cannot access user B's documents through any URL or method), monthly limits, line-item editing, and settings operations.

---

## Limitations

Virelo is an early MVP. It is honest about what it does and does not do.

**What it does NOT do:**

- **OCR for scanned PDFs.** If a PDF has no text layer, Virelo will refuse to process it and tell you clearly. OCR (Tesseract, EasyOCR) is on the roadmap.
- **Email ingestion.** Invoices must be uploaded manually. IMAP ingestion is not implemented.
- **Accounting integrations.** No QuickBooks, Xero, or similar yet.
- **Paid plans / billing.** The Free plan is the only plan that works end-to-end. The "Pro" tier on the pricing page is a placeholder.

**Quality caveats:**

- Llama 3.2 (3B) is a small model. It handles clean, text-based invoices well, but may occasionally miss line items or produce a wrong total on dense or unusual layouts. This is exactly why deterministic validation and human review exist.
- On CPU-only inference, processing is slow. `llama3.2:1b` is faster but less accurate on tables. A GPU dramatically improves speed.

---

## Roadmap

Ideas being considered for future versions:

- OCR for scanned documents
- IMAP / email ingestion
- Paid plans with Stripe
- QuickBooks / Xero integrations
- Multi-currency validation rules
- Export to accounting-ready formats (SAF-T, UBL)
- Self-hosted installation script (one-command setup)

Nothing here is promised. It's a wishlist, not a contract.

---

## Project structure

```
Virelo/
├── app/
│   ├── main.py             # FastAPI app, routes
│   ├── config.py           # Settings from .env
│   ├── database.py         # SQLite engine, migrations, session
│   ├── models.py           # SQLModel tables (User, Document, ...)
│   ├── schemas.py          # Pydantic Invoice schema
│   ├── repository.py       # DB CRUD operations
│   ├── auth.py             # Password hashing, sessions, current user
│   ├── limiter.py          # Monthly invoice limit logic
│   ├── oauth.py            # Authlib OAuth providers
│   ├── pdf.py              # PDFExtractor + PypdfExtractor
│   ├── ai.py               # AIExtractor + OllamaInvoiceExtractor
│   ├── validation.py       # Deterministic business rules
│   ├── export.py           # CSV generation
│   ├── export_excel.py     # XLSX generation
│   ├── timing.py           # Per-stage timing helpers
│   ├── templates/          # Jinja2 templates
│   └── static/             # CSS, favicon
├── tests/                  # pytest suite
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## Configuration

Virelo reads settings from `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | — | Signs session cookies. **Change in production.** |
| `SESSION_MAX_AGE` | `1209600` | Session lifetime in seconds (14 days) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Model name (e.g. `llama3.2:1b`) |
| `UPLOAD_DIR` | `uploads` | Where PDFs are stored |
| `MAX_UPLOAD_MB` | `10` | Maximum upload size |
| `DATABASE_URL` | SQLite file in project root | Database connection string |
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `GITHUB_CLIENT_ID` | — | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | — | GitHub OAuth client secret |

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

### Faster PDF parsing (PyMuPDF)

`pypdf` is a pure-Python package and works on any Python version. For faster parsing or better handling of complex layouts, you can switch to **PyMuPDF** — but it ships as compiled wheels, which may not exist for the newest Python releases on Windows.

1. `python -m pip install pymupdf`
2. Add a `PyMuPDFExtractor(PDFExtractor)` class next to `PypdfExtractor` in `app/pdf.py`.
3. Change the singleton at the bottom of the file.

---

## Google OAuth setup

1. Open the [Google Cloud Console](https://console.cloud.google.com/) → create a new project (e.g. `Virelo`).
2. **APIs & Services** → **OAuth consent screen** (now called *Google Auth Platform*):
   - User Type: **External**.
   - Fill in app name and support email.
   - Add your own Google account under **Test users** while in testing mode.
3. **APIs & Services → Credentials → Create OAuth client ID**:
   - Application type: **Web application**.
   - Name: `Virelo Local`.
   - Authorized JavaScript origins: `http://localhost:8000`
   - Authorized redirect URIs: `http://localhost:8000/auth/google/callback`
4. Copy the **Client ID** and **Client secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   ```

For production, add your production domain to both lists.

## GitHub OAuth setup

1. Open [GitHub Developer Settings](https://github.com/settings/developers) → **OAuth Apps** → **New OAuth App**.
2. Fill in:
   - Application name: `Virelo`
   - Homepage URL: `http://localhost:8000`
   - Authorization callback URL: `http://localhost:8000/auth/github/callback`
3. Copy the **Client ID** and generate a **Client secret**.
4. Add to `.env`:
   ```
   GITHUB_CLIENT_ID=...
   GITHUB_CLIENT_SECRET=...
   ```

GitHub allows only one callback URL per OAuth App. For production, create a **second** OAuth App pointed at your production domain.

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
| `redirect_uri_mismatch` from Google / GitHub | The callback URL in the OAuth app settings doesn't match the one the app sends. Verify scheme, host, port, and path. |
| `Access blocked: Virelo has not completed verification` | Your Google account isn't in the **Test users** list of the OAuth consent screen. |
| Database contains stale data | Delete `invoices.db` and restart the app. |
| Sessions disappear after server restart | `SECRET_KEY` changed. Set it once in `.env` and don't rotate it in development. |

---

## License

MIT