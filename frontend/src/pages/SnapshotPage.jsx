import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import axios from 'axios'
import toast from 'react-hot-toast'
import { ArrowLeft, Calendar, User2 } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend, ReferenceLine
} from 'recharts'
import KpiCard   from '../components/KpiCard'
import DataTable from '../components/DataTable'

// ── reuse helpers ──────────────────────────────────────────────────────────
function inr(v) {
  if (v == null || isNaN(+v)) return '—'
  const n = +v
  if (Math.abs(n) >= 1e7) return `₹${(n/1e7).toFixed(2)} Cr`
  if (Math.abs(n) >= 1e5) return `₹${(n/1e5).toFixed(2)} L`
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}
function pct(v)       { return +v >= 0 ? 'text-emerald-600' : 'text-red-600' }
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
const SECTOR_PAL  = ['#4452ef','#5a6ef8','#7c96fc','#a4bcff','#c7d7ff','#3640d5','#2e36ac']
const CAP_COLOR   = { 'Large Cap':'#4452ef','Mid Cap':'#5a6ef8','Small Cap':'#7c96fc','Micro Cap':'#a4bcff','Unknown':'#e2e8f0' }
const GROUP_BADGE = { 'Opening Assets':'badge-amber','Long Term':'badge-violet','Short Term':'badge-red','Trade Period':'badge-blue' }

const TABS = [
  { id: 'holdings',   label: 'Holdings'    },
  { id: 'allocation', label: 'Allocation'  },
  { id: 'xirr',       label: 'XIRR'       },
]

export default function SnapshotPage() {
  const { id }           = useParams()
  const [snap, setSnap]  = useState(null)
  const [busy, setBusy]  = useState(true)
  const [tab,  setTab]   = useState('holdings')

  useEffect(() => {
    const go = async () => {
      try {
        const { data } = await axios.get(`/history/${id}`)
        setSnap(data)
      } catch {
        toast.error('Snapshot not found')
      } finally {
        setBusy(false)
      }
    }
    go()
  }, [id])

  if (busy) return (
    <div className="flex items-center justify-center h-64">
      <span className="w-7 h-7 border-2 border-ink-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
  if (!snap) return (
    <div className="p-6 text-center text-slate-500">
      Snapshot not found. <Link to="/history" className="text-ink-600 underline">Go back</Link>
    </div>
  )

  const S   = snap.summary   || {}
  const ALL = snap.allocation || {}
  const SEC = normalise(snap.sector_wt  || {})
  const CAP = normalise(snap.cap_summary || {})
  const unified = snap.unified || []

  return (
    <div className="p-5 lg:p-7 space-y-6 max-w-[1400px] mx-auto animate-fade-in">

      {/* Header */}
      <div className="flex items-start gap-4">
        <Link to="/history" className="btn-ghost mt-0.5">
          <ArrowLeft size={15} /> Back
        </Link>
        <div>
          <h1 className="text-xl font-bold text-slate-900">{snap.label}</h1>
          <div className="flex flex-wrap gap-4 mt-1">
            {snap.client_name && (
              <span className="flex items-center gap-1.5 text-sm text-slate-500">
                <User2 size={13} /> {snap.client_name}{snap.client_id && ` — ${snap.client_id}`}
              </span>
            )}
            <span className="flex items-center gap-1.5 text-sm text-slate-400">
              <Calendar size={13} />
              {snap.created_at && new Date(snap.created_at).toLocaleDateString('en-IN', {
                day:'2-digit', month:'short', year:'numeric',
                hour: '2-digit', minute: '2-digit'
              })}
            </span>
            {snap.date_range && <span className="text-sm text-slate-400">Period: {snap.date_range}</span>}
          </div>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Total Invested"  value={inr(S['Total Cost Value (₹)'])}       sub="Cost basis" />
        <KpiCard label="Current Value"   value={inr(S['Total Current Value (₹)'])}    sub="At effective price" />
        <KpiCard label="Unrealized P&L"  value={inr(S['Total Unrealized P&L (₹)'])}
          sub={`${Number(S['Total Unrealized P&L %']||0).toFixed(2)}%`}
          color={Number(S['Total Unrealized P&L (₹)'])>=0 ? 'green' : 'red'} />
        <KpiCard label="Open Positions"  value={S['Number of Open Positions'] ?? '—'} sub="Unique scrips" />
      </div>

      {/* Tabs */}
      <div className="card overflow-hidden">
        <div className="flex border-b border-slate-100 overflow-x-auto">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={tab === t.id ? 'nav-tab-active' : 'nav-tab-inactive'}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="p-5 lg:p-6">
          {tab === 'holdings'   && <SnapHoldings unified={unified} />}
          {tab === 'allocation' && <SnapAllocation sec={SEC} cap={CAP} all={ALL} unified={unified} />}
          {tab === 'xirr'       && <SnapXirr xirr={snap.xirr} />}
        </div>
      </div>
    </div>
  )
}

function SnapHoldings({ unified }) {
  const dedup = unified.filter((r, i, a) => a.findIndex(x => x['Scrip Name'] === r['Scrip Name']) === i)
  const cols = [
    { key: 'Scrip Name',     label: 'Scrip',      bold: true },
    { key: 'Group',          label: 'Group',
      render: v => <span className={GROUP_BADGE[v]||'badge-slate'}>{v||'—'}</span> },
    { key: 'Net Quantity',   label: 'Qty',         align: 'right' },
    { key: 'Avg Cost',       label: 'Avg Cost',    align: 'right', fmt: inr },
    { key: 'Effective Price',label: 'Price',       align: 'right', fmt: inr },
    { key: 'Current Value',  label: 'Value',       align: 'right', fmt: inr },
    { key: 'Unrealized P&L', label: 'P&L',         align: 'right',
      render: v => <span className={pct(v)}>{inr(v)}</span> },
    { key: 'Weight %',       label: 'Wt %',        align: 'right',
      render: v => <span className="font-medium">{Number(v||0).toFixed(2)}%</span> },
    { key: 'Sector',         label: 'Sector' },
  ]
  return <DataTable rows={dedup} cols={cols} maxH="480px" />
}

function SnapAllocation({ sec, cap, all, unified }) {
  const secData = Object.entries(sec).map(([n, v], i) => ({ name: n, value: v, fill: SECTOR_PAL[i % SECTOR_PAL.length] }))
  const capData = Object.entries(cap).map(([n, v])    => ({ name: n, value: v, fill: CAP_COLOR[n]||'#94a3b8' }))
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Core (≥5%)',   pct: all['Core Allocation %'],      cnt: all['Core Count'],      col: '#4452ef' },
          { label: 'Satellite',    pct: all['Satellite Allocation %'], cnt: all['Satellite Count'], col: '#7c3aed' },
          { label: 'Tail (<1%)',   pct: all['Tail Allocation %'],       cnt: all['Tail Count'],      col: '#94a3b8' },
        ].map(item => (
          <div key={item.label} className="card-inset p-4">
            <div className="text-xs font-semibold text-slate-500 mb-1">{item.label}</div>
            <div className="text-xl font-bold" style={{ color: item.col }}>{Number(item.pct||0).toFixed(1)}%</div>
            <div className="text-xs text-slate-400">{item.cnt??0} stocks</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[['Sector', secData], ['Market Cap', capData]].map(([title, data]) => (
          <div key={title}>
            <p className="section-title">{title}</p>
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie data={data} cx="50%" cy="44%" innerRadius="46%" outerRadius="68%" paddingAngle={2} dataKey="value">
                  {data.map((e, i) => <Cell key={i} fill={e.fill} />)}
                </Pie>
                <Legend iconType="circle" iconSize={8}
                  formatter={v => <span style={{ fontSize: '11px', color: '#64748b' }}>{v}</span>} />
                <Tooltip formatter={v => `${Number(v).toFixed(2)}%`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        ))}
      </div>
    </div>
  )
}

function SnapXirr({ xirr }) {
  const port     = xirr?.portfolio || {}
  const perScrip = Array.isArray(xirr?.per_scrip) ? xirr.per_scrip : []
  const xpct     = port.xirr_pct
  const cols = [
    { key: 'Scrip Name',    label: 'Scrip',    bold: true },
    { key: 'XIRR %',        label: 'XIRR %',   align: 'right',
      render: v => v != null ? <span className={pct(v)}>{Number(v).toFixed(2)}%</span> : <span className="text-slate-400">N/A</span> },
    { key: 'Current Value', label: 'Value',    align: 'right', fmt: inr },
    { key: 'Earliest Buy',  label: 'Since' },
  ]
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className={`rounded-2xl border p-5
          ${xpct != null && xpct >= 0 ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'}`}>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Portfolio XIRR</p>
          <p className={`text-3xl font-bold ${xpct != null && xpct >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
            {xpct != null ? `${Number(xpct).toFixed(2)}%` : 'N/A'}
          </p>
          <p className="text-xs text-slate-400 mt-1">Annualised return</p>
        </div>
        <KpiCard label="Total Invested"   value={inr(port.total_invested)} />
        <KpiCard label="Terminal Value"   value={inr(port.total_current)}  />
        <KpiCard label="CF Events"        value={port.flow_count ?? '—'}   />
      </div>
      {perScrip.length > 0 && <DataTable rows={perScrip} cols={cols} maxH="420px" />}
    </div>
  )
}
