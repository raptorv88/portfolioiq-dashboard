import React, { useState, useRef, useCallback } from 'react'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'
import toast from 'react-hot-toast'
import {
  Upload, FileSpreadsheet, BarChart2, TrendingUp, TrendingDown,
  CheckCircle2, AlertCircle, RefreshCw, X, Save, Activity, Calendar, Hash, DollarSign
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, ReferenceLine
} from 'recharts'
import KpiCard    from '../components/KpiCard'
import DataTable  from '../components/DataTable'

// ── Colour maps ────────────────────────────────────────────────────────────
const SECTOR_PAL  = ['#4452ef','#5a6ef8','#7c96fc','#a4bcff','#c7d7ff',
                     '#3640d5','#2e36ac','#1c2166','#6366f1','#818cf8','#34d399','#fb923c']
const CAP_COLOR   = { 'Large Cap':'#4452ef','Mid Cap':'#5a6ef8','Small Cap':'#7c96fc',
                      'Micro Cap':'#a4bcff','Unknown':'#e2e8f0','Index/ETF':'#cbd5e1','Commodity':'#fbbf24' }
const GROUP_COLOR = { 'Opening Assets':'#f59e0b','Long Term':'#7c3aed',
                      'Short Term':'#ef4444','Trade Period':'#4452ef','Unknown':'#94a3b8' }
const GROUP_BADGE = {
  'Opening Assets': 'badge-amber',
  'Long Term':      'badge-violet',
  'Short Term':     'badge-red',
  'Trade Period':   'badge-blue',
  'MISSING_BUY':   'badge-red',
}

// ── Formatting ─────────────────────────────────────────────────────────────
function inr(v) {
  if (v == null || isNaN(Number(v))) return '—'
  const n = Number(v)
  if (Math.abs(n) >= 1e7) return `₹${(n/1e7).toFixed(2)} Cr`
  if (Math.abs(n) >= 1e5) return `₹${(n/1e5).toFixed(2)} L`
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
function pct(v)      { return Number(v) >= 0 ? 'text-emerald-600' : 'text-red-600' }
// Normalise a {key: value} dict so values sum to exactly 100%
// Adjusts the largest bucket by the rounding remainder so total is always 100.00
function normalise(obj) {
  if (!obj) return {}
  const entries = Object.entries(obj).map(([k, v]) => [k, Math.max(0, +v)])
  const t = entries.reduce((a, [, v]) => a + v, 0)
  if (t <= 0) return obj
  const scaled = entries.map(([k, v]) => [k, +((v / t) * 100).toFixed(2)])
  const sum    = scaled.reduce((a, [, v]) => a + v, 0)
  const diff   = +(100 - sum).toFixed(2)
  if (diff !== 0) {
    let maxIdx = 0
    scaled.forEach((_, i) => { if (scaled[i][1] > scaled[maxIdx][1]) maxIdx = i })
    scaled[maxIdx][1] = +(scaled[maxIdx][1] + diff).toFixed(2)
  }
  return Object.fromEntries(scaled)
}

// Normalise CST so Core+Satellite+Tail = exactly 100, all values >= 0
function normaliseCst(all) {
  if (!all) return all
  const core = Math.max(0, +(all['Core Allocation %']      || 0))
  const sat  = Math.max(0, +(all['Satellite Allocation %'] || 0))
  const tail = Math.max(0, +(all['Tail Allocation %']      || 0))
  const t    = core + sat + tail
  if (t <= 0) return all
  const coreP = +((core / t) * 100).toFixed(2)
  const satP  = +((sat  / t) * 100).toFixed(2)
  const tailP = +(100 - coreP - satP).toFixed(2)
  return {
    ...all,
    'Core Allocation %'      : coreP,
    'Satellite Allocation %' : satP,
    'Tail Allocation %'      : Math.max(0, tailP),
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  SCRIP DETAIL MODAL
// ─────────────────────────────────────────────────────────────────────────────
function ScripModal({ scrip, unified, realized, onClose }) {
  if (!scrip) return null

  // All unified rows for this scrip
  const holdingRows = unified.filter(r => r['Scrip Name'] === scrip)
  // All realized rows for this scrip
  const realRows    = realized.filter(r => r['Scrip Name'] === scrip)

  // Summary from first holding row
  const h = holdingRows[0] || {}
  const totalUnreal = holdingRows.reduce((s, r) => s + (+r['Unrealized P&L'] || 0), 0)
  const totalReal   = realRows.reduce((s, r)    => s + (+r['Realized P&L']   || 0), 0)
  const totalQty    = holdingRows.reduce((s, r) => s + (+r['Net Quantity']    || 0), 0)

  // Close on backdrop click
  const onBackdrop = (e) => { if (e.target === e.currentTarget) onClose() }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(15,17,32,0.55)', backdropFilter: 'blur(4px)' }}
      onClick={onBackdrop}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col animate-fade-up">

        {/* Header */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-900">{scrip}</h2>
            <div className="flex flex-wrap items-center gap-3 mt-1">
              {h['Sector']       && <span className="badge-blue">{h['Sector']}</span>}
              {h['Cap Category'] && <span className="badge-slate">{h['Cap Category']}</span>}
              {h['Group']        && <span className={GROUP_BADGE[h['Group']] || 'badge-slate'}>{h['Group']}</span>}
            </div>
          </div>
          <button onClick={onClose} className="btn-icon mt-0.5"><X size={16} /></button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 px-6 py-5 space-y-6">

          {/* Summary KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="card-inset p-3">
              <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-1">Net Qty</p>
              <p className="text-lg font-bold text-slate-900">{totalQty}</p>
            </div>
            <div className="card-inset p-3">
              <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-1">Avg Cost</p>
              <p className="text-lg font-bold text-slate-900">{inr(h['Avg Cost'])}</p>
            </div>
            <div className="card-inset p-3">
              <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-1">Current Price</p>
              <p className="text-lg font-bold text-slate-900">{inr(h['Effective Price'])}</p>
            </div>
            <div className="card-inset p-3">
              <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-1">Weight</p>
              <p className="text-lg font-bold text-slate-900">{Number(h['Weight %']||0).toFixed(2)}%</p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="card-inset p-3">
              <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-1">Invested</p>
              <p className="text-base font-bold text-slate-900">{inr(h['Buy Amount'])}</p>
            </div>
            <div className="card-inset p-3">
              <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-1">Unrealized P&L</p>
              <p className={`text-base font-bold ${pct(totalUnreal)}`}>{inr(totalUnreal)}</p>
            </div>
            <div className="card-inset p-3">
              <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-1">Realized P&L</p>
              <p className={`text-base font-bold ${realRows.length ? pct(totalReal) : 'text-slate-400'}`}>
                {realRows.length ? inr(totalReal) : '—'}
              </p>
            </div>
          </div>

          {/* Holdings breakdown — shows if scrip appears in multiple sources */}
          {holdingRows.length > 0 && (
            <div>
              <p className="section-title flex items-center gap-1.5">
                <Activity size={13} className="text-ink-500" /> Current Holdings
              </p>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Group</th>
                      <th className="text-right">Qty</th>
                      <th className="text-right">Avg Cost</th>
                      <th className="text-right">Eff. Price</th>
                      <th className="text-right">Invested</th>
                      <th className="text-right">Current Val</th>
                      <th className="text-right">Unreal. P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {holdingRows.map((r, i) => (
                      <tr key={i}>
                        <td>{r['Source'] || '—'}</td>
                        <td><span className={GROUP_BADGE[r['Group']] || 'badge-slate'}>{r['Group'] || '—'}</span></td>
                        <td className="tbl-num">{r['Net Quantity'] ?? '—'}</td>
                        <td className="tbl-num">{inr(r['Avg Cost'])}</td>
                        <td className="tbl-num">{inr(r['Effective Price'])}</td>
                        <td className="tbl-num">{inr(r['Buy Amount'])}</td>
                        <td className="tbl-num">{inr(r['Current Value'])}</td>
                        <td className={`tbl-num font-medium ${pct(r['Unrealized P&L'])}`}>
                          {inr(r['Unrealized P&L'])}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Trade activity — buy/sell history */}
          {realRows.length > 0 && (
            <div>
              <p className="section-title flex items-center gap-1.5">
                <Calendar size={13} className="text-ink-500" /> Trade Activity (Realized)
              </p>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th className="text-right">Sell Qty</th>
                      <th className="text-right">Sell Price</th>
                      <th className="text-right">Sell Proceeds</th>
                      <th className="text-right">Cost of Sold</th>
                      <th className="text-right">Realized P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {realRows.map((r, i) => {
                      const d = r['Date']
                      const dateStr = d
                        ? (typeof d === 'string' && d.includes('T')
                            ? new Date(d).toLocaleDateString('en-IN', {day:'2-digit',month:'short',year:'numeric'})
                            : d)
                        : '—'
                      return (
                        <tr key={i}>
                          <td className="font-mono text-xs">{dateStr}</td>
                          <td className="tbl-num">{r['Sell Qty'] ?? r['Sell Quantity'] ?? '—'}</td>
                          <td className="tbl-num">{inr(r['Sell Price'])}</td>
                          <td className="tbl-num">{inr(r['Sell Proceeds'])}</td>
                          <td className="tbl-num">{inr(r['Cost of Sold'])}</td>
                          <td className={`tbl-num font-medium ${pct(r['Realized P&L'])}`}>
                            {inr(r['Realized P&L'])}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {/* Realized total */}
              <div className="flex justify-end mt-2">
                <span className="text-xs text-slate-500 mr-2">Total Realized P&L:</span>
                <span className={`text-xs font-bold ${pct(totalReal)}`}>{inr(totalReal)}</span>
              </div>
            </div>
          )}

          {realRows.length === 0 && (
            <div className="text-center py-4 text-slate-400 text-sm">
              No realized trades for this scrip
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-100 flex justify-end">
          <button onClick={onClose} className="btn-outline text-sm">Close</button>
        </div>
      </div>
    </div>
  )
}

// ── File drop zone ─────────────────────────────────────────────────────────
function DropZone({ label, hint, accent, file, onChange, onClear }) {
  const ref  = useRef()
  const [drag, setDrag] = useState(false)

  const handle = (f) => {
    if (!f) return
    if (!f.name.endsWith('.xlsx')) { toast.error('Only .xlsx files are supported'); return }
    onChange(f)
  }

  return (
    <div
      onClick={() => !file && ref.current.click()}
      onDragOver={e => { e.preventDefault(); setDrag(true) }}
      onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); handle(e.dataTransfer.files[0]) }}
      className={[
        'relative rounded-2xl border-2 border-dashed p-6 transition-all duration-200',
        'flex flex-col items-center gap-2 text-center',
        file   ? 'border-emerald-300 bg-emerald-50/60 cursor-default'
               : drag ? 'border-ink-400 bg-ink-50 cursor-copy'
               : 'border-slate-200 hover:border-ink-300 hover:bg-slate-50/80 cursor-pointer',
      ].join(' ')}
    >
      <input ref={ref} type="file" accept=".xlsx" className="sr-only"
        onChange={e => handle(e.target.files[0])} />

      {file ? (
        <>
          <CheckCircle2 size={26} className="text-emerald-500 shrink-0" />
          <div className="min-w-0 w-full">
            <p className="text-sm font-semibold text-emerald-700 truncate">{file.name}</p>
            <p className="text-xs text-slate-500 mt-0.5">{(file.size/1024).toFixed(1)} KB · click × to remove</p>
          </div>
          <button
            onClick={e => { e.stopPropagation(); onClear() }}
            className="absolute top-3 right-3 p-1 rounded-full hover:bg-red-100 text-slate-400 hover:text-red-500 transition-colors"
          >
            <X size={14} />
          </button>
        </>
      ) : (
        <>
          <div className={`w-11 h-11 rounded-xl flex items-center justify-center
            ${drag ? 'bg-ink-100' : 'bg-slate-100'}`}>
            <Upload size={20} className={drag ? 'text-ink-600' : 'text-slate-400'} />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-700">{label}</p>
            <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{hint}</p>
          </div>
          <p className="text-xs text-slate-300 mt-1">Drag & drop or click to browse</p>
        </>
      )}
    </div>
  )
}

// ── Tabs ───────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'holdings',   label: 'Holdings'        },
  { id: 'pnl',        label: 'P&L Analysis'    },
  { id: 'allocation', label: 'Allocation'       },
  { id: 'xirr',       label: 'XIRR'            },
  { id: 'recon',      label: 'Reconciliation'  },
  { id: 'derivatives',label: 'Derivatives'     },
]

// ── Custom tooltip for recharts ────────────────────────────────────────────
function ChartTip({ active, payload, label, formatter }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-slate-200 rounded-xl px-3.5 py-2.5 shadow-lg text-sm">
      <p className="font-medium text-slate-800 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.fill || p.stroke || '#4452ef' }}>
          {formatter ? formatter(p.value) : p.value}
        </p>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
//  MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════
export default function DashboardPage() {
  const { activeTab, setActiveTab, setHasResult } = useOutletContext()
  const [tradeFile,     setTradeFile]     = useState(null)
  const [holdFile,      setHoldFile]      = useState(null)
  const [label,         setLabel]         = useState('')
  const [busy,          setBusy]          = useState(false)
  const [result,        setResult]        = useState(null)
  const [selectedScrip, setSelectedScrip] = useState(null)
  const [loadingLast,   setLoadingLast]   = useState(true)
  const [lastSnap,      setLastSnap]      = useState(null)

  // Auto-load the most recent snapshot on mount
  React.useEffect(() => {
    const loadLatest = async () => {
      try {
        const { data: history } = await axios.get('/history')
        if (history && history.length > 0) {
          const latest = history[0]
          const { data: snap } = await axios.get(`/history/${latest.id}`)
          setResult(snap)
          setLastSnap({ label: latest.label, client_name: latest.client_name, created_at: latest.created_at })
          setHasResult(true)
          setActiveTab('holdings')
        }
      } catch {
        // silently fail — user sees upload screen
      } finally {
        setLoadingLast(false)
      }
    }
    loadLatest()
  }, [])

  const runAnalysis = async () => {
    if (!tradeFile && !holdFile) { toast.error('Upload at least one file first'); return }
    setBusy(true)
    const fd = new FormData()
    if (tradeFile) fd.append('trade_file',   tradeFile)
    if (holdFile)  fd.append('holding_file', holdFile)
    fd.append('label', label.trim())

    try {
      const { data } = await axios.post('/analysis/run', fd)
      setResult(data)
      setActiveTab('holdings')
      setHasResult(true)
      toast.success('Analysis complete — snapshot saved to history')
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Analysis failed. Check your files and try again.'
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-5 lg:p-7 space-y-6 max-w-[1600px] mx-auto animate-fade-in">

      {/* ── Upload card — collapses when result is loaded ─────────────────── */}
      <div className={result ? "card p-4" : "card p-6"}>
        <div className="flex items-start justify-between mb-5">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              {result ? 'Run New Analysis' : 'Upload Files'}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {result
                ? 'Upload new files to replace the current analysis. Previous run is saved in History.'
                : 'Upload one or both files. Results are saved to history automatically.'}
            </p>
          </div>
          {result && (
            <span className="badge-green text-xs">
              <CheckCircle2 size={11} className="mr-1" />
              Snapshot saved
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
          <DropZone
            label="Trade Report (.xlsx)"
            hint="Broker transaction log — all buys, sells, FnO"
            file={tradeFile}
            onChange={setTradeFile}
            onClear={() => setTradeFile(null)}
          />
          <DropZone
            label="Holdings File (.xlsx)"
            hint="IT_Report_Equity — Opening Assets / Assets / Short Term"
            file={holdFile}
            onChange={setHoldFile}
            onClear={() => setHoldFile(null)}
          />
        </div>

        <div className="flex flex-wrap gap-3 items-center">
          <input
            className="field-input max-w-sm text-sm"
            placeholder="Label this snapshot, e.g. Q1 2024 Review (optional)"
            value={label}
            onChange={e => setLabel(e.target.value)}
          />
          <button
            className="btn-primary"
            onClick={runAnalysis}
            disabled={(!tradeFile && !holdFile) || busy}
          >
            {busy
              ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              : <BarChart2 size={15} />
            }
            {busy ? 'Analysing files…' : 'Run Analysis'}
          </button>
        </div>
      </div>

      {/* ── Empty state ─────────────────────────────────────────────────── */}
      {/* Loading last snapshot */}
      {loadingLast && !result && (
        <div className="flex items-center justify-center py-20 gap-3 text-slate-400">
          <span className="w-5 h-5 border-2 border-ink-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading your last analysis…</span>
        </div>
      )}

      {!result && !busy && !loadingLast && (
        <div className="card p-16 flex flex-col items-center text-center gap-4">
          <div className="w-16 h-16 bg-ink-50 rounded-2xl flex items-center justify-center">
            <BarChart2 size={28} className="text-ink-400" />
          </div>
          <div>
            <p className="font-semibold text-slate-700">No analysis yet</p>
            <p className="text-slate-400 text-sm mt-1">
              Upload your files above and click Run Analysis to get started
            </p>
          </div>
        </div>
      )}

      {/* ── Results ─────────────────────────────────────────────────────── */}
      {result && lastSnap && (
        <div className="flex items-center justify-between bg-ink-50 border border-ink-100 rounded-xl px-4 py-2.5 text-xs text-ink-700">
          <span>
            Showing: <strong>{lastSnap.label || 'Last analysis'}</strong>
            {lastSnap.client_name && <span className="ml-1 text-ink-500">— {lastSnap.client_name}</span>}
            <span className="ml-2 text-ink-400">
              {lastSnap.created_at && new Date(lastSnap.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </span>
          </span>
          <button
            onClick={() => { setResult(null); setLastSnap(null); setHasResult(false) }}
            className="text-ink-500 hover:text-ink-800 font-medium ml-4 underline underline-offset-2"
          >
            Clear &amp; upload new
          </button>
        </div>
      )}
      {result && <Results data={result} tab={activeTab} onScripClick={setSelectedScrip} />}
      {selectedScrip && result && (
        <ScripModal
          scrip={selectedScrip}
          unified={Array.isArray(result.unified)  ? result.unified  : []}
          realized={Array.isArray(result.realized) ? result.realized : []}
          onClose={() => setSelectedScrip(null)}
        />
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
//  RESULTS
// ═══════════════════════════════════════════════════════════════════════════
function Results({ data, tab, onScripClick }) {
  const S   = data.summary   || {}
  const ALL = data.allocation || {}
  const SEC = normalise(data.sector_wt   || {})
  const CAP = normalise(data.cap_summary || {})
  const C   = data.client    || {}

  const unified = Array.isArray(data.unified)  ? data.unified  : []
  const realized= Array.isArray(data.realized) ? data.realized : []
  const indexPnl= Array.isArray(data.index_pnl)? data.index_pnl: []
  const recon   = Array.isArray(data.recon)    ? data.recon    : []

  return (
    <div className="space-y-5 animate-fade-up">

      {/* Client banner */}
      {(C.client_name || C.date_range) && (
        <div className="bg-ink-50 border border-ink-100 rounded-xl px-4 py-2.5
                        flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-800">
          {C.client_name && <span><span className="font-semibold">Client:</span> {C.client_name}</span>}
          {C.client_id   && <span><span className="font-semibold">ID:</span> {C.client_id}</span>}
          {C.date_range  && <span><span className="font-semibold">Period:</span> {C.date_range}</span>}
          {data.label    && <span className="ml-auto text-ink-500">📌 {data.label}</span>}
        </div>
      )}

      {/* KPI row 1 */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        <KpiCard label="Current Value"   value={inr(S['Total Current Value (₹)'])}
          sub={`Cost ${inr(S['Total Cost Value (₹)'])}`} />
        <KpiCard label="Unrealized P&L"  value={inr(S['Total Unrealized P&L (₹)'])}
          sub={`${Number(S['Total Unrealized P&L %']||0).toFixed(2)}%`}
          color={Number(S['Total Unrealized P&L (₹)']) >= 0 ? 'green' : 'red'} />
        <KpiCard label="Realized P&L"    value={inr(S['Total Realized P&L (₹)'])}
          sub="FIFO · Trade Report"
          color={Number(S['Total Realized P&L (₹)']) >= 0 ? 'green' : 'red'} />
        <KpiCard label="Total P&L"       value={inr(S['Total P&L (Realized + Unreal)'])}
          sub="Realized + Unrealized"
          color={Number(S['Total P&L (Realized + Unreal)']) >= 0 ? 'green' : 'red'} />
        <KpiCard label="Open Positions"  value={S['Number of Open Positions'] ?? '—'}
          sub={`${S['Total Rows'] ?? 0} rows`} />
        <KpiCard label="ENS"             value={Number(data.ens||0).toFixed(2)}
          sub="Eff. No. of Stocks" />
      </div>

      {/* KPI row 2 — CST */}
      <div className="grid grid-cols-3 gap-3">
        <KpiCard label="Core (≥ 5%)"       value={`${Number(ALL['Core Allocation %']||0).toFixed(1)}%`}
          sub={`${ALL['Core Count']??0} stocks`} color="blue" />
        <KpiCard label="Satellite (1–5%)"  value={`${Number(ALL['Satellite Allocation %']||0).toFixed(1)}%`}
          sub={`${ALL['Satellite Count']??0} stocks`} />
        <KpiCard label="Tail (< 1%)"       value={`${Number(ALL['Tail Allocation %']||0).toFixed(1)}%`}
          sub={`${ALL['Tail Count']??0} stocks`} />
      </div>

      {/* Tab content */}
      <div className="card overflow-hidden">
        <div className="p-5 lg:p-6">
          {tab === 'holdings'    && <HoldingsTab unified={unified} onScripClick={onScripClick} />}
          {tab === 'pnl'         && <PnlTab unified={unified} realized={realized} onScripClick={onScripClick} />}
          {tab === 'allocation'  && <AllocationTab sec={SEC} cap={CAP} all={ALL} unified={unified} />}
          {tab === 'xirr'        && <XirrTab xirr={data.xirr} />}
          {tab === 'recon'       && <ReconTab recon={recon} />}
          {tab === 'derivatives' && <DerivativesTab rows={indexPnl} />}
          {tab === 'report'      && <ReportTab data={data} />}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB 1 — Holdings
// ─────────────────────────────────────────────────────────────────────────────
function HoldingsTab({ unified, onScripClick }) {
  // Filter out any remaining negative-qty rows (backend handles this, frontend is a safety net)
  const validRows = unified.filter(r => (+r['Net Quantity'] || 0) > 0)

  // dedup to one row per scrip for weight chart
  const dedup = validRows.filter((r, i, a) =>
    a.findIndex(x => x['Scrip Name'] === r['Scrip Name']) === i
  )

  const chartData = [...dedup]
    .filter(r => (r['Weight %'] || 0) > 0)
    .sort((a, b) => (b['Weight %']||0) - (a['Weight %']||0))
    .slice(0, 22)
    .map(r => ({ name: r['Scrip Name'], w: +(r['Weight %']||0).toFixed(2) }))
    .reverse()

  const cols = [
    { key: 'Scrip Name', label: 'Scrip', bold: true,
      render: v => (
        <button onClick={() => onScripClick(v)}
          className="text-ink-700 font-semibold hover:text-ink-500 hover:underline text-left">
          {v}
        </button>
      )
    },
    { key: 'Source',         label: 'Source' },
    { key: 'Group',          label: 'Group',
      render: v => <span className={GROUP_BADGE[v] || 'badge-slate'}>{v||'—'}</span> },
    { key: 'Net Quantity',   label: 'Qty',          align: 'right' },
    { key: 'Status', label: '', render: v => v === 'MISSING_BUY'
        ? <span title="Buy history missing — this scrip was sold in the trade period but the purchase predates the report. Cost basis unknown." className="badge-red cursor-help text-xs">No Buy Data</span>
        : null },
    { key: 'Avg Cost',       label: 'Avg Cost',     align: 'right', fmt: inr },
    { key: 'Effective Price',label: 'Eff. Price',   align: 'right', fmt: inr },
    { key: 'Buy Amount',     label: 'Invested',     align: 'right', fmt: inr },
    { key: 'Current Value',  label: 'Current Val',  align: 'right', fmt: inr },
    { key: 'Unrealized P&L', label: 'Unreal. P&L',  align: 'right',
      render: v => <span className={pct(v)}>{inr(v)}</span> },
    { key: 'Unrealized P&L %',label:'P&L %',        align: 'right',
      render: v => <span className={pct(v)}>{Number(v||0).toFixed(2)}%</span> },
    { key: 'Weight %',       label: 'Wt %',         align: 'right',
      render: v => <span className="font-medium">{Number(v||0).toFixed(2)}%</span> },
    { key: 'Sector',         label: 'Sector' },
    { key: 'Cap Category',   label: 'Cap' },
  ]

  return (
    <div className="space-y-7">
      <div>
        <p className="section-title">Portfolio Weights — Top 22 Positions</p>
        <ResponsiveContainer width="100%" height={Math.max(260, chartData.length * 26)}>
          <BarChart data={chartData} layout="vertical"
            margin={{ left: 8, right: 50, top: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }}
                   tickFormatter={v => `${v}%`} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" width={155}
                   tick={{ fontSize: 11, fill: '#475569' }} axisLine={false} tickLine={false} />
            <Tooltip content={<ChartTip formatter={v => `${v}%`} />} />
            <Bar dataKey="w" radius={[0, 5, 5, 0]} maxBarSize={16}>
              {chartData.map((e, i) => (
                <Cell key={i} fill={e.w >= 5 ? '#4452ef' : e.w >= 1 ? '#7c96fc' : '#c7d7ff'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <p className="section-title">All Positions</p>
        <DataTable rows={dedup} cols={cols} maxH="460px" />
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB 2 — P&L
// ─────────────────────────────────────────────────────────────────────────────
function PnlTab({ unified, realized, onScripClick }) {
  const unrData = [...unified]
    .filter(r => r['Unrealized P&L'] != null)
    .sort((a, b) => +a['Unrealized P&L'] - +b['Unrealized P&L'])
    .map(r => ({ name: r['Scrip Name'], v: +(r['Unrealized P&L']||0).toFixed(2) }))

  const realMap = {}
  realized.forEach(r => {
    const n = r['Scrip Name'] || '?'
    realMap[n] = (realMap[n]||0) + (+r['Realized P&L']||0)
  })
  const realData = Object.entries(realMap)
    .map(([name, v]) => ({ name, v: +v.toFixed(2) }))
    .sort((a, b) => a.v - b.v)

  const realCols = [
    { key: 'Scrip Name', label: 'Scrip', bold: true,
      render: v => (
        <button onClick={() => onScripClick(v)}
          className="text-ink-700 font-semibold hover:text-ink-500 hover:underline text-left">
          {v}
        </button>
      )
    },
    { key: 'Date',       label: 'Date' },
    { key: 'Sell Qty',   label: 'Qty',          align: 'right' },
    { key: 'Sell Price', label: 'Sell Price',   align: 'right', fmt: inr },
    { key: 'Cost of Sold',label: 'Cost',        align: 'right', fmt: inr },
    { key: 'Realized P&L',label: 'Realized P&L',align: 'right',
      render: v => <span className={pct(v)}>{inr(v)}</span> },
  ]

  const barH = (data) => Math.max(280, data.length * 24)

  return (
    <div className="space-y-8">
      {unrData.length > 0 && (
        <div>
          <p className="section-title">Unrealized P&L by Position</p>
          <ResponsiveContainer width="100%" height={barH(unrData)}>
            <BarChart data={unrData} layout="vertical"
              margin={{ left: 8, right: 60, top: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }}
                     tickFormatter={v => inr(v)} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" width={155}
                     tick={{ fontSize: 11, fill: '#475569' }} axisLine={false} tickLine={false} />
              <ReferenceLine x={0} stroke="#e2e8f0" />
              <Tooltip content={<ChartTip formatter={inr} />} />
              <Bar dataKey="v" radius={[0, 5, 5, 0]} maxBarSize={16}
                   style={{ cursor: 'pointer' }}
                   onClick={(d) => onScripClick(d.name)}>
                {unrData.map((e, i) => <Cell key={i} fill={e.v >= 0 ? '#059669' : '#dc2626'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {realData.length > 0 && (
        <div className="space-y-4">
          <p className="section-title">Realized P&L by Stock (FIFO)</p>
          <ResponsiveContainer width="100%" height={Math.max(200, realData.length * 30)}>
            <BarChart data={realData} margin={{ left: 10, right: 50, top: 4, bottom: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }} angle={-35} textAnchor="end" />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={v => inr(v)} />
              <ReferenceLine y={0} stroke="#e2e8f0" />
              <Tooltip content={<ChartTip formatter={inr} />} />
              <Bar dataKey="v" radius={[4, 4, 0, 0]}>
                {realData.map((e, i) => <Cell key={i} fill={e.v >= 0 ? '#059669' : '#dc2626'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          {realized.length > 0 && (
            <DataTable rows={realized} cols={realCols} maxH="340px" />
          )}
        </div>
      )}

      {unrData.length === 0 && realData.length === 0 && (
        <div className="text-center py-12 text-slate-400 text-sm">
          No P&L data — upload a Trade Report to see realized gains
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB 3 — Allocation
// ─────────────────────────────────────────────────────────────────────────────
function AllocationTab({ sec, cap, all, unified }) {
  const secData = Object.entries(sec).map(([n, v], i) => ({ name: n, value: v, fill: SECTOR_PAL[i % SECTOR_PAL.length] }))
  const capData = Object.entries(cap).map(([n, v])    => ({ name: n, value: v, fill: CAP_COLOR[n] || '#94a3b8' }))

  const grpMap = {}
  unified.forEach(r => {
    const g = r['Group'] || 'Unknown'
    grpMap[g] = (grpMap[g]||0) + (+r['Current Value']||0)
  })
  const grpTotal = Object.values(grpMap).reduce((a, b) => a + b, 0)
  const grpData  = Object.entries(grpMap)
    .filter(([, v]) => v > 0)
    .map(([n, v]) => ({ name: n, value: +((v/grpTotal)*100).toFixed(2), fill: GROUP_COLOR[n]||'#94a3b8' }))

  return (
    <div className="space-y-8">
      {/* CST progress bars */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Core (≥ 5%)',     pct: all['Core Allocation %'],      cnt: all['Core Count'],      col: '#4452ef' },
          { label: 'Satellite (1–5%)',pct: all['Satellite Allocation %'], cnt: all['Satellite Count'], col: '#7c3aed' },
          { label: 'Tail (< 1%)',     pct: all['Tail Allocation %'],       cnt: all['Tail Count'],      col: '#94a3b8' },
        ].map(item => (
          <div key={item.label} className="card-inset p-4">
            <div className="text-xs font-semibold text-slate-500 mb-1">{item.label}</div>
            <div className="text-2xl font-bold mb-0.5" style={{ color: item.col }}>
              {Number(item.pct||0).toFixed(1)}%
            </div>
            <div className="text-xs text-slate-400">{item.cnt??0} stocks</div>
            <div className="mt-3 h-1.5 bg-slate-200 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: `${Math.min(item.pct||0, 100)}%`, background: item.col }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* 3 pie charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <PiePanel title="Sector Allocation"    data={secData} />
        <PiePanel title="Market Cap Breakdown" data={capData} />
        <PiePanel title="Holdings by Group"    data={grpData}
          tooltipFmt={v => `${Number(v).toFixed(2)}%`} />
      </div>
    </div>
  )
}

function PiePanel({ title, data, tooltipFmt }) {
  const fmt = tooltipFmt || (v => `${Number(v).toFixed(2)}%`)
  return (
    <div>
      <p className="section-title">{title}</p>
      <ResponsiveContainer width="100%" height={230}>
        <PieChart>
          <Pie data={data} cx="50%" cy="44%" innerRadius="48%" outerRadius="70%"
               paddingAngle={2} dataKey="value">
            {data.map((e, i) => <Cell key={i} fill={e.fill} />)}
          </Pie>
          <Legend iconType="circle" iconSize={8}
            formatter={v => <span style={{ fontSize: '11px', color: '#64748b' }}>{v}</span>} />
          <Tooltip formatter={fmt} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB 4 — XIRR
// ─────────────────────────────────────────────────────────────────────────────
function XirrTab({ xirr }) {
  if (!xirr) return (
    <div className="text-center py-12 text-slate-400 text-sm">
      XIRR not available — analysis may not have completed
    </div>
  )

  const port      = xirr.portfolio || {}
  const perGroup  = Array.isArray(xirr.per_group) ? xirr.per_group : []
  const perScrip  = Array.isArray(xirr.per_scrip) ? xirr.per_scrip : []
  const xpct      = port.xirr_pct
  const positive  = xpct != null && xpct >= 0

  const chartData = perScrip
    .filter(r => r['XIRR %'] != null)
    .sort((a, b) => (b['Current Value']||0) - (a['Current Value']||0))
    .slice(0, 20)
    .sort((a, b) => +a['XIRR %'] - +b['XIRR %'])

  const grpCols = [
    { key: 'Group',           label: 'Group',     bold: true },
    { key: 'XIRR %',          label: 'XIRR %',    align: 'right',
      render: v => v != null ? <span className={pct(v)}>{Number(v).toFixed(2)}%</span> : <span className="text-slate-400">N/A</span> },
    { key: 'Current Value',   label: 'Value',     align: 'right', fmt: inr },
    { key: 'Cash Flow Count', label: 'CF Events', align: 'right' },
    { key: 'Note',            label: 'Status' },
  ]

  const scripCols = [
    { key: 'Scrip Name',      label: 'Scrip',     bold: true },
    { key: 'XIRR %',          label: 'XIRR %',    align: 'right',
      render: v => v != null ? <span className={pct(v)}>{Number(v).toFixed(2)}%</span> : <span className="text-slate-400">N/A</span> },
    { key: 'Current Value',   label: 'Value',     align: 'right', fmt: inr },
    { key: 'Earliest Buy',    label: 'Since' },
    { key: 'Cash Flow Count', label: 'CF Count',  align: 'right' },
  ]

  return (
    <div className="space-y-8">
      {/* Portfolio XIRR hero */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className={`rounded-2xl border p-5
          ${positive ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'}`}>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
            Portfolio XIRR
          </p>
          <p className={`text-3xl font-bold ${positive ? 'text-emerald-700' : 'text-red-700'}`}>
            {xpct != null ? `${Number(xpct).toFixed(2)}%` : 'N/A'}
          </p>
          <p className="text-xs text-slate-400 mt-1">Annualised return p.a.</p>
        </div>
        <KpiCard label="Total Invested"    value={inr(port.total_invested)} sub="All buy outflows" />
        <KpiCard label="Terminal Value"    value={inr(port.total_current)}  sub="Portfolio today" />
        <KpiCard label="Cash Flow Events"  value={port.flow_count ?? '—'}
          sub={port.earliest_date
            ? `Since ${new Date(port.earliest_date).toLocaleDateString('en-IN', {day:'2-digit',month:'short',year:'numeric'})}`
            : 'n/a'} />
      </div>

      {/* Scrip chart */}
      {chartData.length > 0 && (
        <div>
          <p className="section-title">XIRR by Scrip — Top 20 by Current Value</p>
          <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 28)}>
            <BarChart data={chartData} layout="vertical"
              margin={{ left: 8, right: 60, top: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }}
                     tickFormatter={v => `${v}%`} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="Scrip Name" width={155}
                     tick={{ fontSize: 10, fill: '#475569' }} axisLine={false} tickLine={false} />
              <ReferenceLine x={0} stroke="#e2e8f0" />
              <Tooltip content={<ChartTip formatter={v => `${v}%`} />} />
              <Bar dataKey="XIRR %" radius={[0, 5, 5, 0]} maxBarSize={16}>
                {chartData.map((e, i) => (
                  <Cell key={i} fill={+e['XIRR %'] >= 0 ? '#059669' : '#dc2626'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Per-group table */}
      {perGroup.length > 0 && (
        <div>
          <p className="section-title">XIRR by Holding Group</p>
          <DataTable rows={perGroup} cols={grpCols} maxH="240px" />
        </div>
      )}

      {/* Per-scrip table */}
      {perScrip.length > 0 && (
        <div>
          <p className="section-title">XIRR by Scrip — Full Detail</p>
          <DataTable rows={perScrip} cols={scripCols} maxH="440px" />
        </div>
      )}

      {/* Methodology note */}
      <details className="card-inset px-4 py-3 text-sm text-slate-600 cursor-pointer">
        <summary className="font-medium text-slate-700 select-none">
          How XIRR is calculated
        </summary>
        <div className="mt-3 space-y-2 text-slate-500 text-xs leading-relaxed">
          <p><strong>Buy outflows (negative):</strong> Every buy from the Trade Report uses its exact date and amount. Holdings File scrips not in the Trade Report use Net Quantity × Avg Buy Rate on recorded Buy Date.</p>
          <p><strong>Sell inflows (positive):</strong> Every sell from the Trade Report uses its exact date and proceeds.</p>
          <p><strong>Terminal inflow:</strong> Today's portfolio value is the final positive cash flow (date = today).</p>
          <p><strong>No double-counting:</strong> Scrips in both files use Holdings File only for opening cost. All subsequent activity uses Trade Report dates.</p>
          <p><strong>Solver:</strong> pyxirr with scipy brentq fallback. Returns N/A if mathematically unsolvable.</p>
        </div>
      </details>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB 5 — Reconciliation
// ─────────────────────────────────────────────────────────────────────────────
function ReconTab({ recon }) {
  const cols = [
    { key: 'Scrip Name', label: 'Scrip', bold: true,
      render: v => (
        <button onClick={() => onScripClick(v)}
          className="text-ink-700 font-semibold hover:text-ink-500 hover:underline text-left">
          {v}
        </button>
      )
    },
    { key: 'Source',         label: 'Source' },
    { key: 'Group',          label: 'Group',
      render: v => <span className={GROUP_BADGE[v]||'badge-slate'}>{v||'—'}</span> },
    { key: 'IT Buy Qty',     label: 'IT Buy',      align: 'right' },
    { key: 'IT Sell Qty',    label: 'IT Sell',     align: 'right' },
    { key: 'Trade Buy Qty',  label: 'TR Buy',      align: 'right' },
    { key: 'Trade Sell Qty', label: 'TR Sell',     align: 'right' },
    { key: 'Net Quantity',   label: 'Net Qty',     align: 'right',
      render: v => {
        const n = Number(v)
        return <span className={n > 0 ? 'text-emerald-600 font-medium' : n < 0 ? 'text-red-600 font-medium' : ''}>{v}</span>
      } },
    { key: 'Status', label: 'Status',
      render: v => {
        const m = { OPEN: 'badge-green', CLOSED: 'badge-slate', ANOMALY: 'badge-red' }
        return <span className={m[v]||'badge-slate'}>{v}</span>
      }
    },
  ]

  return (
    <div>
      <p className="text-xs text-slate-500 mb-4 leading-relaxed">
        Net Quantity = (IT Buy + Trade Buy) − (IT Sell + Trade Sell). &nbsp;
        <span className="badge-green mr-1">OPEN</span> = still held &nbsp;
        <span className="badge-slate mr-1">CLOSED</span> = fully exited &nbsp;
        <span className="badge-red">ANOMALY</span> = net qty &lt; 0, investigate
      </p>
      {recon.length > 0
        ? <DataTable rows={recon} cols={cols} maxH="520px" />
        : <div className="text-center py-12 text-slate-400 text-sm">No reconciliation data</div>
      }
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  TAB 6 — Derivatives
// ─────────────────────────────────────────────────────────────────────────────
function DerivativesTab({ rows }) {
  if (!rows.length) return (
    <div className="text-center py-12 text-slate-400 text-sm">
      No index / derivative trades — upload a Trade Report to see this section
    </div>
  )

  const chartData = [...rows].sort((a, b) => +a['Net P&L'] - +b['Net P&L'])
  const total     = rows.reduce((s, r) => s + (+r['Net P&L']||0), 0)

  const cols = [
    { key: 'Scrip Name',  label: 'Instrument', bold: true },
    { key: 'Buy Amount',  label: 'Buy Amount',  align: 'right', fmt: inr },
    { key: 'Sell Amount', label: 'Sell Amount', align: 'right', fmt: inr },
    { key: 'Net P&L',     label: 'Net P&L',     align: 'right',
      render: v => <span className={pct(v)}>{inr(v)}</span> },
  ]

  return (
    <div className="space-y-6">
      <div>
        <p className="section-title">Index & Derivative Net P&L</p>
        <ResponsiveContainer width="100%" height={Math.max(200, chartData.length * 36)}>
          <BarChart data={chartData} margin={{ left: 10, right: 60, top: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="Scrip Name" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={v => inr(v)} />
            <ReferenceLine y={0} stroke="#e2e8f0" />
            <Tooltip content={<ChartTip formatter={inr} />} />
            <Bar dataKey="Net P&L" radius={[4, 4, 0, 0]}>
              {chartData.map((e, i) => <Cell key={i} fill={+e['Net P&L']>=0 ? '#059669' : '#dc2626'} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard label="Total Index P&L" value={inr(total)} sub="All instruments"
          color={total >= 0 ? 'green' : 'red'} />
      </div>

      <DataTable rows={rows} cols={cols} />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  REPORT TAB
// ─────────────────────────────────────────────────────────────────────────────
function ReportTab({ data }) {
  const [niftyReturn, setNiftyReturn] = React.useState(null)
  const [niftyLoading, setNiftyLoading] = React.useState(true)

  React.useEffect(() => {
    axios.get('/analysis/nifty-return')
      .then(r => setNiftyReturn(r.data.return_pct))
      .catch(() => setNiftyReturn(null))
      .finally(() => setNiftyLoading(false))
  }, [])

  const S       = data.summary    || {}
  const ALL     = data.allocation  || {}
  const SEC     = normalise(data.sector_wt   || {})
  const CAP     = normalise(data.cap_summary || {})
  const unified = Array.isArray(data.unified) ? data.unified : []
  const xirr    = data.xirr?.portfolio || {}
  const xpct    = xirr.xirr_pct

  const dedup = unified.filter((r, i, a) =>
    a.findIndex(x => x['Scrip Name'] === r['Scrip Name']) === i
  )

  const coreP   = Number(ALL['Core Allocation %'] || 0)
  const satP    = Number(ALL['Satellite Allocation %'] || 0)
  const tailP   = Number(ALL['Tail Allocation %'] || 0)
  const tailCnt = Number(ALL['Tail Count'] || 0)

  let diversVerdict = 'Portfolio structure looks balanced.'
  if (tailP > 30 && tailCnt > 15) diversVerdict = 'High tail clutter — too many small positions.'
  else if (coreP < 40) diversVerdict = 'Low core concentration — strategy may lack focus.'
  else if (coreP >= 60) diversVerdict = 'Portfolio is well concentrated in core positions.'

  const largePct = Number(CAP['Large Cap'] || 0)
  const smallPct = Number(CAP['Small Cap'] || 0) + Number(CAP['Micro Cap'] || 0)
  let balanceVerdict = 'Balanced mix across market caps.'
  if (smallPct > 50) balanceVerdict = 'Aggressive / growth-oriented — more than half outside large caps.'
  else if (largePct > 70) balanceVerdict = 'Conservative — heavily weighted in large caps.'

  const holdCols = [
    { key: 'Scrip Name',       label: 'Scrip Name',   bold: true },
    { key: 'Net Quantity',     label: 'Qty',           align: 'right' },
    { key: 'Avg Cost',         label: 'Avg Rate',      align: 'right', fmt: inr },
    { key: 'Effective Price',  label: 'Closing Price', align: 'right', fmt: inr },
    { key: 'Buy Amount',       label: 'Invested',      align: 'right', fmt: inr },
    { key: 'Current Value',    label: 'Current Amt',   align: 'right', fmt: inr },
    { key: 'Unrealized P&L',   label: 'Overall P&L',   align: 'right',
      render: v => <span className={pct(v)}>{inr(v)}</span> },
    { key: 'Unrealized P&L %', label: '% Change',      align: 'right',
      render: v => <span className={pct(v)}>{Number(v||0).toFixed(2)}%</span> },
    { key: 'Weight %',         label: 'Weightage',     align: 'right',
      render: v => <span>{Number(v||0).toFixed(2)}%</span> },
    { key: 'Cap Category',     label: 'M.Cap' },
    { key: 'Sector',           label: 'Sector' },
  ]

  const secRows = Object.entries(SEC).sort((a, b) => b[1] - a[1]).map(([sector, wt]) => ({ sector, wt }))
  const capRows = Object.entries(CAP).sort((a, b) => b[1] - a[1]).map(([cap, wt]) => ({ cap, wt }))

  return (
    <div className="space-y-6 animate-fade-in">

      {/* Risk vs Reward */}
      <div>
        <p className="section-title">Risk vs Reward</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className={`card p-4 border-2 ${xpct != null && xpct >= 0 ? 'border-emerald-200 bg-emerald-50/40' : 'border-red-200 bg-red-50/40'}`}>
            <p className="kpi-label">Portfolio XIRR</p>
            <p className={`kpi-value ${xpct != null && xpct >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
              {xpct != null ? `${Number(xpct).toFixed(2)}%` : 'N/A'}
            </p>
            <p className="kpi-sub">Annualised return</p>
          </div>
          <div className="card p-4">
            <p className="kpi-label">Nifty 50 (1Y)</p>
            <p className="kpi-value text-slate-700">
              {niftyLoading
                ? <span className="w-4 h-4 border-2 border-ink-400 border-t-transparent rounded-full animate-spin inline-block" />
                : niftyReturn != null ? `${niftyReturn}%` : 'N/A'}
            </p>
            <p className="kpi-sub">Benchmark return</p>
          </div>
          <div className="card p-4">
            <p className="kpi-label">Alpha vs Nifty</p>
            {xpct != null && niftyReturn != null ? (
              <>
                <p className={`kpi-value ${xpct - niftyReturn >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                  {(xpct - niftyReturn).toFixed(2)}%
                </p>
                <p className="kpi-sub">{xpct - niftyReturn >= 0 ? 'Outperforming' : 'Underperforming'}</p>
              </>
            ) : <p className="kpi-value text-slate-400">N/A</p>}
          </div>
          <KpiCard label="Total P&L" value={inr(S['Total P&L (Realized + Unreal)'])}
            sub="Realized + Unrealized"
            color={Number(S['Total P&L (Realized + Unreal)']) >= 0 ? 'green' : 'red'} />
        </div>
      </div>

      {/* Diversification */}
      <div>
        <p className="section-title">Diversification</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card p-5 space-y-3">
            {[
              { label: 'Core (≥ 5%)',     val: coreP, col: '#4452ef', cnt: ALL['Core Count'] },
              { label: 'Satellite (1–5%)',val: satP,  col: '#7c3aed', cnt: ALL['Satellite Count'] },
              { label: 'Tail (< 1%)',     val: tailP, col: '#94a3b8', cnt: ALL['Tail Count'] },
            ].map(item => (
              <div key={item.label}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs font-semibold text-slate-600">{item.label}</span>
                  <span className="text-xs font-bold" style={{ color: item.col }}>
                    {Number(item.val||0).toFixed(1)}% · {item.cnt ?? 0} stocks
                  </span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(item.val||0,100)}%`, background: item.col }} />
                </div>
              </div>
            ))}
            <p className="text-xs text-slate-500 pt-2 border-t border-slate-100">
              <span className="font-semibold">Verdict:</span> {diversVerdict}
            </p>
          </div>
          <div className="card p-5 space-y-3">
            {capRows.map(({ cap, wt }) => (
              <div key={cap}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs font-semibold text-slate-600">{cap}</span>
                  <span className="text-xs font-bold text-ink-600">{Number(wt).toFixed(1)}%</span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full bg-ink-500" style={{ width: `${Math.min(wt,100)}%` }} />
                </div>
              </div>
            ))}
            <p className="text-xs text-slate-500 pt-2 border-t border-slate-100">
              <span className="font-semibold">Verdict:</span> {balanceVerdict}
            </p>
          </div>
        </div>
      </div>

      {/* Holdings Table */}
      <div>
        <p className="section-title">Holdings Detail</p>
        <DataTable rows={dedup} cols={holdCols} maxH="480px" />
      </div>

      {/* Sector & Cap Tables */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-5">
          <p className="section-title">Sector Allocation</p>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Sector</th><th className="text-right">Weight %</th></tr></thead>
              <tbody>
                {secRows.map(({ sector, wt }) => (
                  <tr key={sector}>
                    <td>{sector}</td>
                    <td className="tbl-num font-medium">{Number(wt).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card p-5">
          <p className="section-title">Market Cap Breakdown</p>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Category</th><th className="text-right">Weight %</th></tr></thead>
              <tbody>
                {capRows.map(({ cap, wt }) => (
                  <tr key={cap}>
                    <td>{cap}</td>
                    <td className="tbl-num font-medium">{Number(wt).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

    </div>
  )
}
