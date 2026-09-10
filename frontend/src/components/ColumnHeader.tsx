import { Tooltip } from './Tooltip'

/** A table heading with a one-line explanation on hover. */
export function ColumnHeader({ label, help }: { label: string; help: string }) {
  return (
    <Tooltip className="th-tip" content={<span className="tooltip__note">{help}</span>}>
      {label}
    </Tooltip>
  )
}

/** What each column of the document list means. */
export const LIST_COLUMNS: { label: string; help: string; numeric?: boolean }[] = [
  { label: 'Document', help: 'The filename you uploaded.' },
  {
    label: 'Status',
    help: 'Where the document is in the pipeline: queued, extracting, complete, or failed.',
  },
  {
    label: 'Identifier',
    help: 'The invoice number, or the bill of lading number when there is no invoice number.',
  },
  {
    label: 'Lines',
    help: 'How many goods lines were found in the document’s itemised table. 0 means it has no such table.',
    numeric: true,
  },
  {
    label: 'Lowest field confidence',
    help: 'The weakest OCR score across every extracted value — the one field most worth checking.',
    numeric: true,
  },
  { label: 'Uploaded', help: 'When the file was uploaded.' },
]

/** What each column of the line-items table means. */
export const LINE_ITEM_HELP: Record<string, string> = {
  quantity: 'Units shipped on this line, with any unit suffix removed.',
  description: 'The goods description, as printed on the line.',
  value: 'The extended line total (quantity × unit price), not the unit price.',
  hts_code: 'Harmonized Tariff Schedule code for this line. Blank if the document shows none.',
}

/** What each document-level field means, condensed from models.py's field descriptions. */
export const DOCUMENT_FIELD_HELP: Record<string, string> = {
  bill_of_lading_number:
    'The B/L, BOL, HBL or MBL number. Blank when the document is not a bill of lading.',
  invoice_number: 'The commercial invoice number. Blank when the document carries none.',
  shipper_name: 'The shipper, exporter or seller sending the goods — company name only.',
  shipper_address: 'The shipper’s full postal address, joined onto one line.',
  consignee_name: 'The party the goods are consigned to — company name only.',
  consignee_address: 'The consignee’s full postal address, joined onto one line.',
  total_value_of_goods: 'The document’s grand total — its invoice, grand or final total figure.',
}
