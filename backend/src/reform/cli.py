"""Command line entry point: `reform extract`, `reform load`, `reform run`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Optional

from .config import DOCUMENTS_DIR, OUTPUT_DIR
from .extraction import ExtractionResult, extract, rescore
from .ocr import make_client


def _pdfs(paths: Optional[list[str]]) -> list[Path]:
    if paths:
        return [Path(p) for p in paths]
    return sorted(DOCUMENTS_DIR.glob("*.pdf"))


def _cache_path(pdf: Path) -> Path:
    return OUTPUT_DIR / f"{pdf.stem}.json"


def _summarise(result: ExtractionResult) -> str:
    doc = result.document
    identifier = doc.invoice_number or doc.bill_of_lading_number or "(no id)"
    scored = [c.min_confidence for c in result.document_confidences if c.min_confidence is not None]
    worst = f"{min(scored):.3f}" if scored else "n/a"
    unmatched = sum(
        1
        for c in result.document_confidences
        if c.match_method == "unmatched" and c.field_value is not None
    )
    return (
        f"{result.source_file:<16} {identifier:<14} "
        f"lines={len(doc.line_items):<3} total={doc.total_value_of_goods} "
        f"worst_field_conf={worst} unmatched={unmatched}"
    )


def cmd_extract(args: argparse.Namespace) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = _pdfs(args.files)
    if not pdfs:
        print(f"No PDFs found in {DOCUMENTS_DIR}", file=sys.stderr)
        return 1

    client = make_client()
    failures = 0

    for pdf in pdfs:
        cache = _cache_path(pdf)
        if cache.exists() and not args.force:
            print(f"{pdf.name:<16} cached -> {cache.relative_to(OUTPUT_DIR.parent)}")
            continue
        try:
            result = extract(client, pdf)
        except Exception as exc:  # one bad document must not abort the batch
            failures += 1
            print(f"{pdf.name:<16} FAILED: {exc}", file=sys.stderr)
            continue
        cache.write_text(json.dumps(result.to_json_dict(), indent=2, ensure_ascii=False))
        print(_summarise(result))

    return 1 if failures else 0


def _cached_results(files: Optional[list[str]]) -> Iterable[ExtractionResult]:
    paths = [Path(f) for f in files] if files else sorted(OUTPUT_DIR.glob("*.json"))
    for path in paths:
        yield ExtractionResult.from_json_dict(json.loads(path.read_text()))


def cmd_rescore(args: argparse.Namespace) -> int:
    """Re-run the confidence matcher over cached OCR words. Makes no API calls."""
    paths = [Path(f) for f in args.files] if args.files else sorted(OUTPUT_DIR.glob("*.json"))
    if not paths:
        print(f"No cached extractions in {OUTPUT_DIR}; run `reform extract` first.", file=sys.stderr)
        return 1

    for path in paths:
        result = ExtractionResult.from_json_dict(json.loads(path.read_text()))
        if not result.words:
            print(f"{result.source_file:<16} no cached OCR words; re-run with --force", file=sys.stderr)
            continue
        rescore(result)
        path.write_text(json.dumps(result.to_json_dict(), indent=2, ensure_ascii=False))
        print(_summarise(result))
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    from . import db  # imported lazily so `extract` works with no DATABASE_URL set

    results = list(_cached_results(args.files))
    if not results:
        print(f"No cached extractions in {OUTPUT_DIR}; run `reform extract` first.", file=sys.stderr)
        return 1

    with db.connect() as conn:
        db.init_schema(conn)
        for result in results:
            document_id = db.load(conn, result)
            print(f"{result.source_file:<16} loaded  id={document_id}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    code = cmd_extract(args)
    if code:
        return code
    args.files = None
    return cmd_load(args)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="reform", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, handler, help_text in (
        ("extract", cmd_extract, "OCR the PDFs and cache structured JSON in out/"),
        ("rescore", cmd_rescore, "Recompute field confidences from cached OCR words"),
        ("load", cmd_load, "Load cached JSON into Postgres"),
        ("run", cmd_run, "Extract then load"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("files", nargs="*", help="Specific files (default: all)")
        p.add_argument(
            "--force",
            action="store_true",
            help="Re-run OCR even when a cached result exists",
        )
        p.set_defaults(func=handler)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
