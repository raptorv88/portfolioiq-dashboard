import React from 'react'

export default function KpiCard({ label, value, sub, color, icon }) {
  const valClass =
    color === 'green'  ? 'text-emerald-600' :
    color === 'red'    ? 'text-red-600'     :
    color === 'blue'   ? 'text-ink-600'     : 'text-slate-900'

  return (
    <div className="kpi-card">
      <div className="flex items-start justify-between">
        <span className="kpi-label">{label}</span>
        {icon && <span className="text-slate-300 mt-0.5">{icon}</span>}
      </div>
      <div className={`kpi-value ${valClass}`}>{value ?? '—'}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  )
}
