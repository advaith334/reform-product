-- Schema for structured trade-document extraction (bills of lading, commercial invoices).
-- Safe to run repeatedly.

create extension if not exists pgcrypto;

create table if not exists documents (
  id                     uuid primary key default gen_random_uuid(),
  source_file            text not null unique,
  bill_of_lading_number  text,
  invoice_number         text,
  shipper_name           text,
  shipper_address        text,
  consignee_name         text,
  consignee_address      text,
  total_value_of_goods   numeric(14,2),
  ocr_markdown           text,
  ocr_avg_confidence     numeric(6,5),   -- mean of per-page average confidence
  ocr_min_confidence     numeric(6,5),   -- worst per-page minimum confidence
  ocr_model              text,
  extraction_model       text,
  extracted_at           timestamptz not null default now()
);

create table if not exists line_items (
  id           uuid primary key default gen_random_uuid(),
  document_id  uuid not null references documents(id) on delete cascade,
  line_no      int  not null,
  quantity     numeric,
  description  text,
  value        numeric(14,2),
  hts_code     text,
  unique (document_id, line_no)
);

-- One row per extracted field, carrying the OCR confidence of the source text that
-- backs it. line_item_id is null for document-level fields.
create table if not exists field_confidences (
  id               uuid primary key default gen_random_uuid(),
  document_id      uuid not null references documents(id) on delete cascade,
  line_item_id     uuid references line_items(id) on delete cascade,
  field_name       text not null,
  field_value      text,
  min_confidence   numeric(6,5),
  mean_confidence  numeric(6,5),
  match_method     text not null
                     check (match_method in ('exact','fuzzy','token','unmatched','absent')),
  match_ratio      numeric(6,5)
);

-- `create table if not exists` above leaves an existing table's constraint alone, so
-- restate it here for databases created before a method was added.
alter table field_confidences drop constraint if exists field_confidences_match_method_check;
alter table field_confidences add constraint field_confidences_match_method_check
  check (match_method in ('exact','fuzzy','token','unmatched','absent'));

-- Postgres treats NULLs as distinct in unique constraints, so document-level and
-- line-level rows need separate partial indexes.
create unique index if not exists field_confidences_doc_field_uidx
  on field_confidences (document_id, field_name)
  where line_item_id is null;

create unique index if not exists field_confidences_line_field_uidx
  on field_confidences (line_item_id, field_name)
  where line_item_id is not null;

create index if not exists line_items_hts_code_idx on line_items (hts_code);
create index if not exists field_confidences_min_idx on field_confidences (min_confidence);

-- Upload lifecycle. Added separately so an existing database picks these up on the
-- next init_schema() without a migration tool. Documents loaded by the CLI predate
-- the API and are complete by definition, hence the default.
alter table documents add column if not exists original_filename text;
alter table documents add column if not exists stored_path       text;
alter table documents add column if not exists content_type      text;
alter table documents add column if not exists status            text not null default 'complete';
alter table documents add column if not exists error             text;
alter table documents add column if not exists uploaded_at       timestamptz not null default now();

-- A pending upload has not been extracted yet, so extracted_at must be allowed to
-- stay empty until db.load() sets it.
alter table documents alter column extracted_at drop not null;
alter table documents alter column extracted_at drop default;

do $$
begin
  alter table documents add constraint documents_status_check
    check (status in ('pending', 'processing', 'complete', 'failed'));
exception
  when duplicate_object then null;
end
$$;

create index if not exists documents_status_idx      on documents (status);
create index if not exists documents_uploaded_at_idx on documents (uploaded_at desc);
