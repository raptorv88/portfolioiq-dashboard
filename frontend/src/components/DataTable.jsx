import React, { useState, useMemo } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown, Search } from 'lucide-react'

/**
 * cols: [{ key, label, align?, className?, render?, fmt?, sortable? }]
 * rows: array of plain objects
 * maxH: max-height string for the scroll container
 */
export default function DataTable({ rows = [], cols = [], maxH = '440px', searchable = true }) {
  const [sort,   setSort]   = useState({ key: null, dir: 'asc' })
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!search.trim()) return rows
    const q = search.trim().toLowerCase()
    return rows.filter(r =>
      Object.values(r).some(v => String(v ?? '').toLowerCase().includes(q))
    )
  }, [rows, search])

  const sorted = useMemo(() => {
    if (!sort.key) return filtered
    return [...filtered].sort((a, b) => {
      const va = a[sort.key], vb = b[sort.key]
      const na = parseFloat(va), nb = parseFloat(vb)
      const cmp =
        !isNaN(na) && !isNaN(nb) ? na - nb
        : String(va ?? '').localeCompare(String(vb ?? ''))
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }, [filtered, sort])

  const toggleSort = (key) =>
    setSort(s => s.key === key
      ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: 'asc' }
    )

  const SortIcon = ({ k }) => {
    if (sort.key !== k) return <ChevronsUpDown size={11} className="opacity-30" />
    return sort.dir === 'asc'
      ? <ChevronUp size={11} className="text-ink-600" />
      : <ChevronDown size={11} className="text-ink-600" />
  }

  if (!rows.length) {
    return (
      <div className="text-center py-12 text-slate-400 text-sm">
        No data available
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {searchable && rows.length > 8 && (
        <div className="relative max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="field-input pl-9 py-2 text-sm"
            placeholder="Search table…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
      )}

      <div className="tbl-wrap" style={{ maxHeight: maxH }}>
        <table className="tbl">
          <thead>
            <tr>
              {cols.map(col => (
                <th
                  key={col.key}
                  onClick={() => toggleSort(col.key)}
                  className={col.align === 'right' ? 'text-right' : ''}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    <SortIcon k={col.key} />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr key={i}>
                {cols.map(col => {
                  const raw = row[col.key]
                  const content = col.render
                    ? col.render(raw, row)
                    : col.fmt
                      ? col.fmt(raw, row)
                      : (raw ?? '—')

                  return (
                    <td
                      key={col.key}
                      className={[
                        col.align === 'right' ? 'tbl-num' : '',
                        col.bold ? 'font-medium text-slate-900' : '',
                        col.className || '',
                      ].join(' ')}
                    >
                      {content}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>

        {sorted.length === 0 && (
          <div className="py-8 text-center text-slate-400 text-sm">
            No rows match your search
          </div>
        )}
      </div>

      <p className="text-xs text-slate-400 text-right">
        {sorted.length} of {rows.length} rows
      </p>
    </div>
  )
}
