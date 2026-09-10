import { useCallback, useEffect, useState } from 'react'
import { Link, Route, Routes } from 'react-router-dom'

import { listDocuments } from './api'
import { DocumentDetail } from './components/DocumentDetail'
import { DocumentList } from './components/DocumentList'
import { UploadDropzone } from './components/UploadDropzone'
import type { DocumentSummary } from './types'

function Home() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setDocuments(await listDocuments())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // The dropzone reports every state change of the upload it is watching; a refresh
  // on each one is what moves the new row from "Queued" to "Complete".
  const onFinished = useCallback(() => void refresh(), [refresh])

  return (
    <>
      <UploadDropzone onFinished={onFinished} />
      {error && <p className="error">{error}</p>}
      <h2>Documents</h2>
      <DocumentList documents={documents} />
    </>
  )
}

export default function App() {
  return (
    <div className="app">
      <header className="app__header">
        <Link to="/" className="brand">
          Reform
        </Link>
        <span className="muted">Trade-document extraction</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/documents/:id" element={<DocumentDetail />} />
        </Routes>
      </main>
    </div>
  )
}
