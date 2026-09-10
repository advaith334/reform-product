// Mirrors backend/src/reform/api/schemas.py.

/** Mirrors the match_method docstring in backend/src/reform/confidence.py. */
export type MatchMethod = 'exact' | 'fuzzy' | 'token' | 'unmatched' | 'absent'

export interface ExtractedField {
  name: string
  value: string | null
  min_confidence: number | null
  mean_confidence: number | null
  match_method: MatchMethod | null
  match_ratio: number | null
}

export interface LineItem {
  id: string
  line_no: number
  fields: ExtractedField[]
}

export type DocumentStatus = 'pending' | 'processing' | 'complete' | 'failed'

export interface DocumentSummary {
  id: string
  source_file: string
  original_filename: string | null
  status: DocumentStatus
  error: string | null
  uploaded_at: string | null
  extracted_at: string | null
  identifier: string | null
  line_item_count: number
  ocr_avg_confidence: number | null
  ocr_min_confidence: number | null
  worst_field_confidence: number | null
  unmatched_field_count: number
}

export interface DocumentDetail extends DocumentSummary {
  ocr_model: string | null
  extraction_model: string | null
  fields: ExtractedField[]
  line_items: LineItem[]
}

export interface UploadAccepted {
  id: string
  status: DocumentStatus
  original_filename: string
}
