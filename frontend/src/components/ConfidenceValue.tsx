import type { ExtractedField } from '../types'
import { Tooltip } from './Tooltip'

/**
 * Renders one extracted value with its OCR confidence.
 *
 * Every field in the app goes through this component, so the hover behaviour and the
 * colour scale are defined in exactly one place.
 */

/** 'shipper_address' -> 'Shipper Address' */
export function humanise(name: string): string {
  return name
    .split('_')
    .map((word) =>
      // Acronyms the pipeline uses; title-casing them would read as "Hts".
      ['hts', 'ocr', 'id'].includes(word) ? word.toUpperCase() : word[0].toUpperCase() + word.slice(1),
    )
    .join(' ')
}

const percent = (value: number | null) =>
  value === null ? '—' : `${(value * 100).toFixed(2)}%`

/**
 * Buckets for colour. These follow the confidence numbers the pipeline actually
 * produces: clean text scores above 0.99, so 0.95 is already worth a second look and
 * anything under 0.85 usually means the OCR was guessing at the glyphs.
 */
function level(field: ExtractedField): 'high' | 'medium' | 'low' | 'unmatched' | 'empty' {
  if (field.value === null || field.match_method === 'absent') return 'empty'
  // 'unmatched' has no OCR reading behind it at all, so it gets its own neutral
  // treatment rather than a colour that would imply a measured score.
  if (field.match_method === 'unmatched' || field.min_confidence === null) return 'unmatched'
  if (field.min_confidence >= 0.95) return 'high'
  if (field.min_confidence >= 0.85) return 'medium'
  return 'low'
}

const EXPLANATION: Record<string, string> = {
  exact: 'Found verbatim on the page, as one run of words.',
  fuzzy: 'Found as one run of words, with small differences in spacing or spelling.',
  token: 'Assembled from parts scattered across the page, so each part was scored on its own.',
  unmatched:
    'Never found on the page, so there is no OCR reading behind it. Check this value against the document.',
  absent: 'This field is not on this document.',
}

/** match_ratio means similarity for a fuzzy match and coverage for a token match. */
const RATIO_LABEL: Record<string, string> = { fuzzy: 'similarity', token: 'coverage' }

export function ConfidenceValue({ field }: { field: ExtractedField }) {
  const tone = level(field)

  if (tone === 'empty') {
    return (
      <span className="value value--empty" title="Not present in this document">
        —
      </span>
    )
  }

  return (
    <Tooltip
      className={`value value--${tone}`}
      content={
        <>
          <span className="tooltip__headline">
            {field.min_confidence === null ? (
              <strong>No OCR confidence</strong>
            ) : (
              <>
                <strong>{percent(field.min_confidence)}</strong> confidence
                <span className="tooltip__sub">lowest-scoring word behind this value</span>
              </>
            )}
          </span>
          {field.mean_confidence !== null && (
            <span className="tooltip__row">
              <span>Average word</span>
              <span>{percent(field.mean_confidence)}</span>
            </span>
          )}
          <span className="tooltip__row">
            <span>Match</span>
            <span>{field.match_method ?? '—'}</span>
          </span>
          {field.match_ratio !== null &&
            field.match_method !== null &&
            RATIO_LABEL[field.match_method] && (
              <span className="tooltip__row">
                <span>{humanise(RATIO_LABEL[field.match_method])}</span>
                <span>{percent(field.match_ratio)}</span>
              </span>
            )}
          {field.match_method && (
            <span className="tooltip__note">{EXPLANATION[field.match_method]}</span>
          )}
        </>
      }
    >
      {field.value}
    </Tooltip>
  )
}
