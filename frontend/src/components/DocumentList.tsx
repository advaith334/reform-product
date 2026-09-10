import { Link } from 'react-router-dom'

import type { DocumentSummary } from '../types'
import { ColumnHeader, LIST_COLUMNS } from './ColumnHeader'

const STATUS_LABEL: Record<string, string> = {
  pending: 'Queued',
  processing: 'Extracting',
  complete: 'Complete',
  failed: 'Failed',
}

function confidenceClass(value: number | null): string {
  if (value === null) return 'value--unmatched'
  if (value >= 0.95) return 'value--high'
  if (value >= 0.85) return 'value--medium'
  return 'value--low'
}

const formatDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'

export function DocumentList({ documents }: { documents: DocumentSummary[] }) {
  if (documents.length === 0) {
    return <p className="muted">No documents yet. Upload one above to get started.</p>
  }

  return (
    <div className="table-scroll">
      <table className="documents">
        <thead>
          <tr>
            {LIST_COLUMNS.map((column) => (
              <th key={column.label} className={column.numeric ? 'numeric' : undefined}>
                <ColumnHeader label={column.label} help={column.help} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id}>
              <td>
                <Link to={`/documents/${doc.id}`} className="doc-link">
                  {doc.original_filename ?? doc.source_file}
                </Link>
              </td>
              <td>
                <span className={`badge badge--${doc.status}`}>
                  {STATUS_LABEL[doc.status] ?? doc.status}
                </span>
              </td>
              <td>{doc.identifier ?? <span className="muted">—</span>}</td>
              <td className="numeric">{doc.line_item_count}</td>
              <td className="numeric">
                {doc.status === 'complete' ? (
                  <span className={`chip ${confidenceClass(doc.worst_field_confidence)}`}>
                    {doc.worst_field_confidence === null
                      ? '—'
                      : `${(doc.worst_field_confidence * 100).toFixed(1)}%`}
                  </span>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td className="muted">{formatDate(doc.uploaded_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
