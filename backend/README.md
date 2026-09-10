# Backend

A FastAPI service wrapped around a two-stage document extraction pipeline, storing results
in Postgres. The same pipeline also runs from the command line.

## Running it

```bash
cp .env.example .env          # then fill in MISTRAL_API_KEY
uv sync
uv run uvicorn reform.api.app:app --reload --port 8000
```

Postgres needs to be up first (`docker compose up -d` from the repo root). The schema is
applied on startup, every time — it's written to be safe to re-run, so there's no
migration tool and nothing to remember.

Interactive API docs are at <http://localhost:8000/docs>.

## The two stages, and why there are two

**Stage one is OCR.** `ocr.py` sends the file to Mistral's OCR endpoint and asks for
word-level confidence scores. What comes back is the page as text, plus a confidence
number for every single word.

**Stage two is extraction.** `extraction.py` hands that text to a general model and asks
for it back in the shape of the `ShipmentDocument` schema in `models.py`.

Doing it in one call is possible — Mistral's OCR endpoint can return structured fields
directly — and that was the first implementation. It went badly on these documents:
fields that were plainly on the page came back null, and string fields degenerated into
repetition loops, with one tariff code returned as the same ten digits repeated for a
kilobyte. The OCR *text* was excellent throughout, so the fix was to keep the OCR call and
do the field extraction separately. `extraction.py`'s docstring records this so nobody
re-litigates it.

## Where the confidence numbers come from

Mistral scores words, not fields. There is no "how sure are you about this invoice number"
in the response — only "how clearly did I read each word on this page".

So `confidence.py` works backwards. For each extracted value it finds where that value
appears in the word stream and aggregates the confidence of the words behind it. How the
value was located is recorded alongside the score as `match_method`: `exact`, `fuzzy`,
`token`, `unmatched` or `absent` (the root README explains what each means).

This is worth being precise about: **the score measures how legibly the text was read, not
whether the extractor put it in the right field.** A number can be a confident 99.9% and
still be in the wrong slot. `match_method` is what separates those two questions.

## Layout

```
src/reform/
  config.py       Environment and paths
  models.py       The Pydantic schema — its field descriptions are the extraction prompt
  ocr.py          Stage one
  extraction.py   Stage two
  confidence.py   Matching values back to OCR words
  db.py           Writes (shared by the API and the CLI)
  cli.py          Batch commands
  api/
    app.py        App setup, connection pool, schema on startup
    routes.py     Endpoints
    schemas.py    Response shapes
    repository.py Reads
    service.py    The background extraction job
    storage.py    Uploaded files on disk
sql/schema.sql    The whole schema, idempotent
```

A note on `models.py`: every field's `description=` is sent to the model as part of the
prompt. Vague wording there is the most common cause of a bad extraction, so edit those
strings carefully.

## Endpoints

| | | |
|---|---|---|
| `POST` | `/api/documents` | Upload a file. Returns `202` immediately with a document id. |
| `GET` | `/api/documents` | List everything, newest first. |
| `GET` | `/api/documents/{id}` | Fields and line items, each with its confidence. |
| `GET` | `/api/documents/{id}/file` | The original file, served inline. |
| `DELETE` | `/api/documents/{id}` | Remove the document and its file. |
| `GET` | `/api/health` | Liveness, including a database round-trip. |

Upload returns before the work is done, so clients poll `GET /api/documents/{id}` until
`status` is `complete` or `failed`. A failure is written onto the row as an `error`
message rather than disappearing into the server log.

## The command line

The batch pipeline predates the API and still works. It's the cheap way to reload data,
because `load` reads cached JSON and makes no API calls at all.

```bash
uv run reform extract   # OCR every PDF in documents/, cache the result in out/
uv run reform rescore   # recompute confidences from cached words — no API calls
uv run reform load      # load out/*.json into Postgres
uv run reform run       # extract, then load
```

`rescore` exists because tuning the matching logic shouldn't cost another OCR bill — the
OCR words are cached alongside the extracted fields.

## Schema

Three tables. `documents` holds one row per file with the document-level fields;
`line_items` holds the goods lines; `field_confidences` holds one row per extracted field
with its score and match method, pointing at a line item when the field belongs to one.

Loading is idempotent and keyed on `source_file`. Line items and confidence rows are
replaced wholesale on each load rather than merged, so a re-extraction that finds fewer
lines doesn't leave stale ones behind.

## Configuration

| | |
|---|---|
| `MISTRAL_API_KEY` | Required. |
| `DATABASE_URL` | Defaults to the local Docker Postgres. |
| `MISTRAL_OCR_MODEL` | Defaults to `mistral-ocr-latest`. |
| `MISTRAL_EXTRACTION_MODEL` | Defaults to `mistral-large-latest`. |
| `CORS_ORIGINS` | Comma-separated. Defaults to the Vite dev server. |

Both model settings use `-latest` aliases so the pipeline tracks Mistral's current
releases. Pin a dated model id if you need reproducibility more than upgrades.

## Useful reading

- [Mistral OCR](https://docs.mistral.ai/capabilities/OCR/basic_ocr/) — the OCR endpoint,
  including the `confidence_scores_granularity` option that everything here is built on.
- [Structured outputs](https://docs.mistral.ai/capabilities/structured-output/custom_structured_output/)
  — how a Pydantic model becomes an enforced response schema, which is stage two.
