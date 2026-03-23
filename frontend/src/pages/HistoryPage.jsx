import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import toast from 'react-hot-toast'
import { History, Eye, Trash2, RefreshCw, FileText, Calendar, User2, TrendingUp, TrendingDown } from 'lucide-react'

function inr(v) {
  if (v == null || isNaN(+v)) return '—'
  const n = +v
  if (Math.abs(n) >= 1e7) return `₹${(n/1e7).toFixed(2)} Cr`
  if (Math.abs(n) >= 1e5) return `₹${(n/1e5).toFixed(2)} L`
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function HistoryPage() {
  const [snaps,    setSnaps]    = useState([])
  const [loading,  setLoading]  = useState(true)
  const [deleting, setDeleting] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await axios.get('/history')
      setSnaps(data)
    } catch {
      toast.error('Could not load history')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const del = async (id, label) => {
    if (!window.confirm(`Delete "${label}"?\n\nThis cannot be undone.`)) return
    setDeleting(id)
    try {
      await axios.delete(`/history/${id}`)
      setSnaps(s => s.filter(x => x.id !== id))
      toast.success('Snapshot deleted')
    } catch {
      toast.error('Delete failed')
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div className="p-5 lg:p-7 max-w-[1200px] mx-auto animate-fade-in">

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <History size={20} className="text-ink-600" />
            Analysis History
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Every analysis you run is saved here automatically — nothing is lost.
          </p>
        </div>
        <button className="btn-outline" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-24">
          <span className="w-7 h-7 border-2 border-ink-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : snaps.length === 0 ? (
        <div className="card p-16 text-center flex flex-col items-center gap-4">
          <div className="w-14 h-14 bg-ink-50 rounded-2xl flex items-center justify-center">
            <History size={24} className="text-ink-400" />
          </div>
          <div>
            <p className="font-semibold text-slate-700">No saved analyses yet</p>
            <p className="text-slate-400 text-sm mt-1">
              Run your first analysis from the Dashboard — it will appear here.
            </p>
          </div>
          <Link to="/" className="btn-primary mt-2">Go to Dashboard</Link>
        </div>
      ) : (
        <div className="space-y-3">
          {snaps.map(snap => {
            const S   = snap.summary || {}
            const pnl = +S['Total Unrealized P&L (₹)']
            const pos = !isNaN(pnl) && pnl >= 0

            return (
              <div key={snap.id}
                className="card p-5 hover:shadow-md transition-shadow duration-200">
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">

                  {/* Icon + info */}
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="w-10 h-10 bg-ink-50 border border-ink-100 rounded-xl
                                    flex items-center justify-center shrink-0">
                      <FileText size={17} className="text-ink-600" />
                    </div>

                    <div className="min-w-0 flex-1">
                      <h3 className="font-semibold text-slate-900 truncate">{snap.label}</h3>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1">
                        {snap.client_name && (
                          <span className="flex items-center gap-1 text-xs text-slate-500">
                            <User2 size={11} />
                            {snap.client_name}
                            {snap.client_id && ` · ${snap.client_id}`}
                          </span>
                        )}
                        <span className="flex items-center gap-1 text-xs text-slate-400">
                          <Calendar size={11} />
                          {fmtDate(snap.created_at)}
                        </span>
                        {snap.date_range && (
                          <span className="text-xs text-slate-400">Period: {snap.date_range}</span>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {snap.trade_file && (
                          <span className="badge-blue">{snap.trade_file}</span>
                        )}
                        {snap.hold_file && (
                          <span className="badge-green">{snap.hold_file}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Numbers */}
                  <div className="flex items-center gap-5 text-right">
                    <div className="hidden sm:block">
                      <div className="text-xs text-slate-400 mb-0.5">Invested</div>
                      <div className="text-sm font-semibold text-slate-800">
                        {inr(S['Total Cost Value (₹)'])}
                      </div>
                    </div>
                    <div className="hidden sm:block">
                      <div className="text-xs text-slate-400 mb-0.5">Current</div>
                      <div className="text-sm font-semibold text-slate-800">
                        {inr(S['Total Current Value (₹)'])}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400 mb-0.5">Unreal. P&L</div>
                      <div className={`text-sm font-semibold flex items-center gap-1 justify-end
                        ${pos ? 'text-emerald-600' : 'text-red-600'}`}>
                        {pos ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                        {inr(pnl)}
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    <Link to={`/history/${snap.id}`} className="btn-outline text-sm px-3 py-2">
                      <Eye size={14} />
                      View
                    </Link>
                    <button
                      className="btn-danger"
                      disabled={deleting === snap.id}
                      onClick={() => del(snap.id, snap.label)}
                    >
                      {deleting === snap.id
                        ? <span className="w-3.5 h-3.5 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
                        : <Trash2 size={13} />
                      }
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
