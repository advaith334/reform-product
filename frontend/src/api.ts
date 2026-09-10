import type { DocumentDetail, DocumentSummary, UploadAccepted } from './types'

// Vite proxies /api to the FastAPI server, so requests are same-origin in dev.
const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) {
    // FastAPI puts the human-readable reason in `detail`; surface it rather than
    // a bare status code, since upload rejections are the common failure here.
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const listDocuments = () => request<DocumentSummary[]>('/documents')

export const getDocument = (id: string) => request<DocumentDetail>(`/documents/${id}`)

export const deleteDocument = (id: string) =>
  request<void>(`/documents/${id}`, { method: 'DELETE' })

export function uploadDocument(file: File): Promise<UploadAccepted> {
  const body = new FormData()
  body.append('file', file)
  return request<UploadAccepted>('/documents', { method: 'POST', body })
}

export const documentFileUrl = (id: string) => `${BASE}/documents/${id}/file`
