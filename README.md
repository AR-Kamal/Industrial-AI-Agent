# AI Agent in Manufacturing

Local Django application for a standalone FANUC ER-4iA technical-support
training prototype. The browser communicates only with Django; Django sends
text-generation requests through a provider-neutral gateway to a locally running
Ollama model.

The current milestone does not implement RAG, document indexing, embeddings,
image analysis, cloud providers, or machine connections.

## Prerequisites

- Windows 10 or 11
- Python 3.13.x available through the Python launcher (`py`)
- PowerShell
- Ollama installed locally

Node.js, cloud accounts, and paid services are not required.

## First-time setup in Windows PowerShell

Run these commands from the repository root:

```powershell
py -3.13 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -c "from secrets import token_urlsafe; print(token_urlsafe(50))"
```

Copy the generated value into `.env` as `SECRET_KEY`, replacing the example.
Keep the remaining local LLM values from `.env.example`, then initialize the
local SQLite database:

```powershell
New-Item -ItemType Directory -Force var | Out-Null
python manage.py migrate
python manage.py createsuperuser
```

Do not commit `.env`, `var\db.sqlite3`, documents, uploads, or logs.

## Set up the local text model

The default configuration uses `gemma3:4b`. Download it once:

```powershell
ollama pull gemma3:4b
ollama list
```

The model is approximately 3.3 GB. If another local text model is already
installed, set its exact name in `.env` as `LLM_TEXT_MODEL`.

Ollama normally starts as a Windows background application. If the service is
not running, start Ollama before running the connection check.

Verify Django-to-Ollama connectivity:

```powershell
python manage.py check_llm
```

A successful result identifies the configured provider and model. The command
does not print the API-key placeholder or base URL.

## Run the website

With the virtual environment active:

```powershell
python manage.py runserver 127.0.0.1:8000
```

Open <http://127.0.0.1:8000/>. Log in with the superuser account and open the
chat page. Submit a text question; the request travels from the browser to
Django and then from Django to local Ollama.

Stop the server with `Ctrl+C`.

## Validation commands

```powershell
python manage.py check
python manage.py check_llm
python manage.py makemigrations --check --dry-run
python manage.py migrate
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy apps manufacturing_agent
python -m bandit -q -r apps manufacturing_agent
```

## Environment settings

| Variable | Local purpose |
|---|---|
| `SECRET_KEY` | Required Django signing secret |
| `DEBUG` | Use `True` only for local development |
| `ALLOWED_HOSTS` | Comma-separated local hostnames |
| `LOG_LEVEL` | Structured console logging threshold |
| `LLM_PROVIDER` | Must be `ollama` in the local prototype |
| `LLM_BASE_URL` | Local OpenAI-compatible URL; must be a loopback `/v1` URL |
| `LLM_API_KEY` | Required placeholder; Ollama ignores it |
| `LLM_TEXT_MODEL` | Exact installed Ollama text-model name |
| `LLM_TIMEOUT_SECONDS` | Request timeout, greater than zero |
| `LLM_TEMPERATURE` | Generation temperature from 0 through 2 |
| `LLM_MAX_TOKENS` | Maximum generated tokens where Ollama supports it |

Example:

```env
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=ollama
LLM_TEXT_MODEL=gemma3:4b
LLM_TIMEOUT_SECONDS=60
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=800
```

The Ollama adapter rejects non-loopback URLs. No credential or provider setting
is rendered into HTML or JavaScript.

## Repository layout

- `manufacturing_agent/`: Django settings and root URL configuration
- `apps/accounts/`: home page and authentication helpers
- `apps/chatbot/`: conversations, messages, protected HTMX chat workflow
- `apps/knowledge_base/`: approved-document lifecycle, extraction, cleaning,
  chunking, review, ingestion commands, and future indexing interfaces
- `apps/feedback/`: reserved feedback app
- `apps/ai_gateway/`: provider-neutral contracts, validated configuration,
  Ollama adapter, normalized errors, and health command
- `apps/safety/`: manufacturing system prompt plus deterministic request/output
  controls
- `templates/`: shared, page, authentication, and error templates
- `static/`: local Bootstrap, HTMX, and application styling
- `tests/`: startup, authentication, page, and persistence tests
- `var/`: ignored SQLite and future runtime files

## Safety and scope

This application is a training demonstration. It has no connection to a robot,
PLC, sensor, HMI, production system, or safety circuit. It must never be used to
bypass an emergency stop, guard, interlock, safety relay, or approved
lockout/tagout procedure.

Model responses are not yet grounded in approved documents. The system prompt
requires the model to identify them as general training information, and users
must verify answers against approved manuals and qualified personnel.

## Local LLM troubleshooting

| Result | Check |
|---|---|
| `provider_unavailable` | Start Ollama and confirm it is listening locally |
| `model_not_installed` | Run `ollama list`, then pull or configure the exact model |
| `timeout` | Increase `LLM_TIMEOUT_SECONDS` or select a smaller local model |
| `malformed_response` / `empty_response` | Retry, then confirm the model works with Ollama directly |
| `configuration_error` | Compare `.env` with `.env.example`; use a loopback `/v1` URL |

Application error messages intentionally omit raw provider bodies, local URLs,
environment values, and credentials.

## Knowledge-base ingestion (Milestone 3)

Supported source formats are PDF, DOCX, TXT, and Markdown. Sources remain
private, and registration does not approve them.

```env
INGESTION_TARGET_CHUNK_TOKENS=600
INGESTION_CHUNK_OVERLAP_TOKENS=75
INGESTION_MIN_CHUNK_TOKENS=100
INGESTION_MAX_CHUNK_TOKENS=900
KNOWLEDGE_MAX_UPLOAD_BYTES=52428800
```

Register and validate the supplied FANUC handbook:

```powershell
python manage.py register_fanuc_document
python manage.py validate_document_metadata FANUC-B-80687EN-12
```

Run Django, sign in to `/admin/`, open **Knowledge documents**, select the
FANUC document, and run **Approve selected documents**. Approval records the
staff reviewer. Then process it:

```powershell
python manage.py process_knowledge_document FANUC-B-80687EN-12
```

Use **Preview extraction and chunks** from the document admin to inspect
metadata, text, references, warnings, and errors. In **Document chunks**, mark
records approved, requires correction, or excluded.

```powershell
New-Item -ItemType Directory -Force var\exports
python manage.py export_document_chunks FANUC-B-80687EN-12 --output var\exports\FANUC-B-80687EN-12.chunks.json
python manage.py reprocess_knowledge_document FANUC-B-80687EN-12
python manage.py list_failed_ingestion_jobs
```

Reprocessing rebuilds generated chunks and resets ordinary generated-chunk
review decisions. Applied split corrections are re-created only when their
source hash still matches exactly. The September 2014 handbook remains marked
as requiring current-version verification.
Tables, diagrams, short chunks, and missing structural evidence require manual
review. OCR, embeddings, vector search, retrieval, and chatbot citations remain
unimplemented.

### Split a chunk during review

In Django Admin, open **Document chunks**, select exactly one generated chunk,
and choose **Split chunk**. The same link is available in the document preview.

1. Insert a line containing `--- SPLIT ---` at every desired boundary.
2. Select **Preview child chunks**.
3. Review or correct each child's content, chapter, section, pages, safety
   flags, retrieval setting, and reviewer notes.
4. If content was removed or corrected, describe the extraction artifact in
   **Correction audit**.
5. For safety/procedure-shaped content, complete the explicit safety-boundary
   confirmation.
6. Apply the correction, or use **Cancel without changes**.

Applying a split never deletes or overwrites the generated source. It marks the
source superseded and retrieval-disabled and creates reviewed correction
children. The correction recipe and reviewer identity remain visible under
**Chunk split corrections**.

Reprocessing reapplies the split only when the regenerated source hash has one
exact match. Otherwise, the correction becomes **Stale — revalidation
required**, and its children remain retrieval-disabled. Review stale
corrections before any future indexing. Splitting correction children, chunk
merging, and unrestricted content editing are intentionally unsupported.

### Bulk chunk review

Export the current generated and correction-child chunks. XLSX is the default:

```powershell
python manage.py export_chunk_review_workbook FANUC-B-80687EN-12
```

The default file is
`var\exports\FANUC-B-80687EN-12.chunk-review.xlsx`. CSV and JSON are also
supported by choosing the extension:

```powershell
python manage.py export_chunk_review_workbook FANUC-B-80687EN-12 --output var\exports\fanuc-review.csv
python manage.py export_chunk_review_workbook FANUC-B-80687EN-12 --output var\exports\fanuc-review.json
```

Set `proposed_action` to exactly one of `NO_CHANGE`, `APPROVE`, `EXCLUDE`,
`CORRECT_METADATA`, or `SPLIT`. Never change `chunk_id`,
`source_content_hash`, document identity, version, sequence, or content.
Every changed row requires reviewer notes.

For warning/caution approval or metadata correction, put this in
`correction_payload`:

```json
{"safety_confirmed": true}
```

For a split, `correction_payload` is a JSON object:

```json
{
  "safety_confirmed": true,
  "artifact_note": "",
  "children": [
    {
      "content": "First complete child text",
      "chapter": "1 SAFETY",
      "section": "1.1 FIRST TOPIC",
      "page_start": 1,
      "page_end": 1,
      "contains_warning": false,
      "contains_caution": false,
      "retrieval_enabled": true,
      "reviewer_notes": "Compared with PDF page 1."
    },
    {
      "content": "Second complete child text",
      "chapter": "1 SAFETY",
      "section": "1.2 SECOND TOPIC",
      "page_start": 2,
      "page_end": 2,
      "contains_warning": true,
      "contains_caution": false,
      "retrieval_enabled": true,
      "reviewer_notes": "Warning and procedure verified together."
    }
  ]
}
```

Run validation before applying:

```powershell
python manage.py import_chunk_reviews var\exports\FANUC-B-80687EN-12.chunk-review.xlsx --dry-run --reviewer user
```

Fix every reported row and repeat until dry-run passes. Back up SQLite, then
apply the unchanged file:

```powershell
Copy-Item var\db.sqlite3 var\db.before-bulk-review.sqlite3
python manage.py import_chunk_reviews var\exports\FANUC-B-80687EN-12.chunk-review.xlsx --apply --reviewer user
```

If no matching dry-run report exists, `--apply` refuses to continue unless
`--confirm` is supplied. This explicit confirmation does not bypass validation.
Dry-run writes `*.dry-run.json`; apply writes `*.apply-report.json`. Any invalid
row blocks all changes, and any runtime failure rolls the transaction back.

### Replace one correction child

Save the complete corrected text as a UTF-8 text file, then run:

```powershell
python manage.py replace_correction_child CHK-C-339b06c8219cf796339a4985baeb12 `
  --content-file var\corrections\CHK-C-339b06c8219cf796339a4985baeb12.txt `
  --source-hash 1a7211e38c18a8d7adef9b14ae718110e3f59cc56e18c30725bca12aafc8afac `
  --reason "Complete the truncated final sentence." `
  --reviewer-notes "Corrected text verified against the source PDF." `
  --reviewer user `
  --safety-confirmed
```

The command preserves and supersedes the old child, disables its retrieval,
creates one approved `CHK-R-...` replacement, and records the audit under
**Chunk replacement corrections**. It rejects generated, stale, unchanged,
empty, out-of-range, unauthorized, or insufficiently reviewed replacements.
