import { useCallback, useEffect, useRef, useState } from 'react'

import { getDocument, uploadDocument } from '../api'
import type { DocumentStatus } from '../types'

const POLL_INTERVAL_MS = 2000

type Phase = 'idle' | 'uploading' | 'working' | 'error'

interface Props {
  /** Called when a document reaches a terminal state, so the list can refresh. */
  onFinished: (documentId: string, status: DocumentStatus) => void
}

/**
 * Drag-and-drop upload with status polling.
 *
 * The API returns 202 immediately and extracts in the background, so this component
 * owns the wait: it polls the document until it leaves 'pending'/'processing'.
 */
export function UploadDropzone({ onFinished }: Props) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [message, setMessage] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const timer = useRef<number | null>(null)

  // A poll in flight must not outlive the component, or it will set state on an
  // unmounted tree every two seconds forever.
  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current)
  }, [])

  const poll = useCallback(
    (id: string, filename: string) => {
      timer.current = window.setTimeout(async () => {
        try {
          const doc = await getDocument(id)
          if (doc.status === 'pending' || doc.status === 'processing') {
            setMessage(`Extracting ${filename}…`)
            poll(id, filename)
            return
          }
          if (doc.status === 'failed') {
            setPhase('error')
            setMessage(doc.error ?? 'Extraction failed.')
          } else {
            setPhase('idle')
            setMessage(null)
          }
          onFinished(id, doc.status)
        } catch (err) {
          setPhase('error')
          setMessage(err instanceof Error ? err.message : String(err))
        }
      }, POLL_INTERVAL_MS)
    },
    [onFinished],
  )

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      const file = files?.[0]
      if (!file) return

      setPhase('uploading')
      setMessage(`Uploading ${file.name}…`)
      try {
        const accepted = await uploadDocument(file)
        setPhase('working')
        setMessage(`Extracting ${file.name}…`)
        // Show the row straight away, in its pending state.
        onFinished(accepted.id, accepted.status)
        poll(accepted.id, file.name)
      } catch (err) {
        setPhase('error')
        setMessage(err instanceof Error ? err.message : String(err))
      }
    },
    [onFinished, poll],
  )

  const busy = phase === 'uploading' || phase === 'working'

  return (
    <div
      className={`dropzone${dragging ? ' dropzone--active' : ''}${busy ? ' dropzone--busy' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        if (!busy) void handleFiles(e.dataTransfer.files)
      }}
      onClick={() => !busy && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (!busy && (e.key === 'Enter' || e.key === ' ')) inputRef.current?.click()
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.webp"
        hidden
        onChange={(e) => {
          void handleFiles(e.target.files)
          e.target.value = '' // so the same file can be picked twice in a row
        }}
      />

      {busy && <span className="spinner" aria-hidden />}
      <div className="dropzone__text">
        {phase === 'idle' && (
          <>
            <strong>Drop a document here</strong>
            <span className="muted">or click to choose — PDF, PNG, JPEG or WebP, up to 20 MB</span>
          </>
        )}
        {busy && <span>{message}</span>}
        {phase === 'error' && (
          <>
            <strong className="error">Upload failed</strong>
            <span className="muted">{message}</span>
          </>
        )}
      </div>
    </div>
  )
}
