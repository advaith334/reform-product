# Reform

Upload a trade document — a commercial invoice or a bill of lading — and get its fields
back as structured data, with a confidence score attached to every value.

The hard part of document extraction isn't reading the page; it's knowing which of the
values you got back you can trust. Reform answers that for each field individually. Hover
any extracted value in the UI and it tells you how legibly the underlying text was read,
and how the value was located on the page.

```
┌──────────┐   upload    ┌─────────────┐   OCR + extract   ┌──────────┐
│ frontend │ ──────────► │   backend   │ ────────────────► │ Postgres │
│  React   │ ◄────────── │   FastAPI   │ ◄──────────────── │          │
└──────────┘   fields +  └─────────────┘                   └──────────┘
               confidence
```

## Getting started

You'll need Docker, [uv](https://docs.astral.sh/uv/), Node 18+, and a Mistral API key.

```bash
# 1. Configuration — put your MISTRAL_API_KEY in the new file
cp backend/.env.example backend/.env

# 2. Postgres
docker compose up -d

# 3. Backend (leave it running)
cd backend && uv sync && uv run uvicorn reform.api.app:app --reload --port 8000

# 4. Frontend (in a second terminal)
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173> and drop a PDF onto the page. The database schema is created
automatically the first time the backend starts, so there is no migration step.

## What's in here

| | |
|---|---|
| [`backend/`](backend/) | FastAPI service and the extraction pipeline. Also runs as a CLI. |
| [`frontend/`](frontend/) | React + Vite app: upload, browse, hover for confidence. |
| `docker-compose.yml` | Local Postgres. Credentials match `backend/.env.example`. |

Each folder has its own README with the details.

## How a document flows through

1. **You upload a file.** The backend saves it to disk, records a row, and returns
   immediately with a status of `pending`. It does *not* wait — reading a document takes
   tens of seconds, which is far too long to hold an HTTP request open.
2. **A background job reads it.** Mistral OCR turns the page into text, and a second
   model pulls the structured fields out of that text.
3. **Every field gets scored.** Mistral reports a confidence per *word* it reads, not per
   field, so the backend works backwards: it finds where each extracted value appears in
   the page text and aggregates the confidence of the words behind it.
4. **The UI polls until it's done.** The row moves from `pending` to `processing` to
   `complete`, then the fields appear with their scores.

## Reading the confidence scores

A value's colour comes from the weakest OCR word behind it — green above 95%, amber above
85%, red below. Clean print scores above 99%, so amber is already worth a glance.

The tooltip also names *how* the value was found on the page, which matters as much as the
number:

- **exact** — found verbatim, as one run of words.
- **fuzzy** — found as one run, with small differences in spacing or spelling.
- **token** — assembled from parts scattered across the page, such as an address split
  over several lines. Each part was scored separately.
- **unmatched** — never found on the page. There's no OCR reading behind it, so there's no
  score either. Worth checking by hand.
- **absent** — the field simply isn't on this document. A bill of lading has no invoice
  number; an invoice has no B/L number. Shown as `—`.

That last distinction is the one people trip on: a blank field usually means "not on this
document", not "we failed to read it".
