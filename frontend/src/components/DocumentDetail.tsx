import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { documentFileUrl, getDocument } from '../api'
import type { DocumentDetail as Detail } from '../types'
import { ColumnHeader, DOCUMENT_FIELD_HELP } from './ColumnHeader'
import { ConfidenceValue, humanise } from './ConfidenceValue'
import { LineItemsTable } from './LineItemsTable'

const POLL_INTERVAL_MS = 2000

export function DocumentDetail() {
  const { id = '' } = useParams()
  const [doc, setDoc] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setDoc(await getDocument(id))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  // Opening the page straight after an upload is normal, so keep refreshing until
  // extraction settles.
  useEffect(() => {
    if (doc?.status !== 'pending' && doc?.status !== 'processing') return
    const timer = window.setTimeout(() => void load(), POLL_INTERVAL_MS)
    return () => window.clearTimeout(timer)
  }, [doc?.status, load])

  if (error) {
    return (
      <div className="panel">
        <p className="error">{error}</p>
        <Link to="/">← Back to all documents</Link>
      </div>
    )
  }

  if (!doc) return <p className="muted">Loading…</p>

  const busy = doc.status === 'pending' || doc.status === 'processing'

  return (
    <div className="detail">
      <header className="detail__header">
        <Link to="/" className="back">
          ← All documents
        </Link>
        <h2>{doc.original_filename ?? doc.source_file}</h2>
        <p className="muted">
          {doc.identifier ? `${doc.identifier} · ` : ''}
          {doc.line_item_count} line {doc.line_item_count === 1 ? 'item' : 'items'}
        </p>
      </header>

      {busy && (
        <div className="notice">
          <span className="spinner" aria-hidden /> Extracting — this page refreshes itself.
        </div>
      )}
      {doc.status === 'failed' && (
        <div className="notice notice--error">
          <strong>Extraction failed.</strong> {doc.error}
        </div>
      )}

      <div className="detail__panes">
        <section className="panel">
          <h3>Extracted fields</h3>
          <p className="hint">
            Hover a field name for what it means, or a value for its OCR confidence.
          </p>

          <dl className="fields">
            {doc.fields.map((field) => (
              <div className="field" key={field.name}>
                <dt>
                  <ColumnHeader
                    label={humanise(field.name)}
                    help={DOCUMENT_FIELD_HELP[field.name] ?? ''}
                  />
                </dt>
                <dd>
                  <ConfidenceValue field={field} />
                </dd>
              </div>
            ))}
          </dl>

          <h3>Line items</h3>
          <LineItemsTable items={doc.line_items} />
        </section>

        <section className="panel panel--viewer">
          <h3>Original</h3>
          <iframe title="Original document" src={documentFileUrl(doc.id)} />
        </section>
      </div>
    </div>
  )
}
