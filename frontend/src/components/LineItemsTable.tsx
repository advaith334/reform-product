import type { LineItem } from '../types'
import { ColumnHeader, LINE_ITEM_HELP } from './ColumnHeader'
import { ConfidenceValue, humanise } from './ConfidenceValue'

export function LineItemsTable({ items }: { items: LineItem[] }) {
  if (items.length === 0) {
    return <p className="muted">This document has no itemised goods table.</p>
  }

  // Every line carries the same fields in the same order (the API iterates
  // LINE_ITEM_FIELDS), so the first line defines the columns.
  const columns = items[0].fields.map((field) => field.name)

  return (
    <div className="table-scroll">
      <table className="line-items">
        <thead>
          <tr>
            <th className="line-no">#</th>
            {columns.map((name) => (
              <th key={name}>
                <ColumnHeader label={humanise(name)} help={LINE_ITEM_HELP[name] ?? ''} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td className="line-no">{item.line_no}</td>
              {item.fields.map((field) => (
                <td key={field.name}>
                  <ConfidenceValue field={field} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
