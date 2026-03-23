import React, { useEffect, useState } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'
import {
  Users, BarChart2, Activity, Trash2, ShieldCheck,
  ShieldOff, ChevronDown, ChevronUp, RefreshCw,
  TrendingUp, TrendingDown, Calendar, Mail, User
} from 'lucide-react'

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
    hour: '2-digit', minute: '2-digit'
  })
}

export default function AdminPage() {
  const [stats,      setStats]      = useState(null)
  const [users,      setUsers]      = useState([])
  const [loading,    setLoading]    = useState(true)
  const [expanded,   setExpanded]   = useState(null)
  const [snapshots,  setSnapshots]  = useState({})
  const [loadingSnap,setLoadingSnap]= useState(null)
  const [deleting,   setDeleting]   = useState(null)
  const [toggling,   setToggling]   = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const [statsRes, usersRes] = await Promise.all([
        axios.get('/admin/stats'),
        axios.get('/admin/users'),
      ])
      setStats(statsRes.data)
      setUsers(usersRes.data)
    } catch (err) {
      if (err?.response?.status === 403) {
        toast.error('Admin access required')
      } else {
        toast.error('Failed to load admin data')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const loadSnapshots = async (userId) => {
    if (snapshots[userId]) return
    setLoadingSnap(userId)
    try {
      const { data } = await axios.get(`/admin/users/${userId}/snapshots`)
      setSnapshots(s => ({ ...s, [userId]: data }))
    } catch {
      toast.error('Failed to load snapshots')
    } finally {
      setLoadingSnap(null)
    }
  }

  const toggleExpand = (userId) => {
    if (expanded === userId) {
      setExpanded(null)
    } else {
      setExpanded(userId)
      loadSnapshots(userId)
    }
  }

  const deleteUser = async (userId, username) => {
    if (!window.confirm(`Delete user "${username}"?\n\nThis will also delete all their snapshots. This cannot be undone.`)) return
    setDeleting(userId)
    try {
      await axios.delete(`/admin/users/${userId}`)
      setUsers(u => u.filter(x => x.id !== userId))
      toast.success(`User ${username} deleted`)
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Delete failed')
    } finally {
      setDeleting(null)
    }
  }

  const toggleActive = async (userId, username) => {
    setToggling(userId)
    try {
      const { data } = await axios.patch(`/admin/users/${userId}/toggle-active`)
      setUsers(u => u.map(x => x.id === userId ? { ...x, is_active: data.is_active } : x))
      toast.success(`${username} ${data.is_active ? 'activated' : 'deactivated'}`)
    } catch {
      toast.error('Failed to toggle user status')
    } finally {
      setToggling(null)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <span className="w-7 h-7 border-2 border-ink-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  return (
    <div className="p-5 lg:p-7 max-w-[1200px] mx-auto animate-fade-in space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <ShieldCheck size={20} className="text-ink-600" />
            Admin Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Manage users and monitor system activity
          </p>
        </div>
        <button className="btn-outline" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-4">
          <div className="card p-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-ink-50 rounded-xl flex items-center justify-center">
                <Users size={18} className="text-ink-600" />
              </div>
              <div>
                <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Total Users</p>
                <p className="text-2xl font-bold text-slate-900">{stats.total_users}</p>
              </div>
            </div>
          </div>
          <div className="card p-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-emerald-50 rounded-xl flex items-center justify-center">
                <BarChart2 size={18} className="text-emerald-600" />
              </div>
              <div>
                <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Total Analyses</p>
                <p className="text-2xl font-bold text-slate-900">{stats.total_snapshots}</p>
              </div>
            </div>
          </div>
          <div className="card p-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-amber-50 rounded-xl flex items-center justify-center">
                <Activity size={18} className="text-amber-600" />
              </div>
              <div>
                <p className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Active Today</p>
                <p className="text-2xl font-bold text-slate-900">{stats.active_today}</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Users list */}
      <div>
        <h2 className="text-sm font-semibold text-slate-700 mb-3">
          All Users ({users.length})
        </h2>
        <div className="space-y-3">
          {users.map(u => (
            <div key={u.id} className="card overflow-hidden">

              {/* User row */}
              <div className="p-4 flex items-center gap-4">

                {/* Avatar + info */}
                <div className="w-10 h-10 bg-ink-100 rounded-full flex items-center justify-center shrink-0">
                  <User size={16} className="text-ink-600" />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-slate-900">{u.full_name}</span>
                    <span className="text-slate-400 text-sm">@{u.username}</span>
                    {u.is_admin && (
                      <span className="badge-blue text-xs">Admin</span>
                    )}
                    {!u.is_active && (
                      <span className="badge-red text-xs">Inactive</span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-1 flex-wrap">
                    <span className="flex items-center gap-1 text-xs text-slate-400">
                      <Mail size={11} /> {u.email}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-slate-400">
                      <Calendar size={11} /> Joined {fmtDate(u.created_at)}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-slate-500 font-medium">
                      <BarChart2 size={11} /> {u.total_analyses} analyses
                    </span>
                    {u.last_analysis && (
                      <span className="text-xs text-slate-400">
                        Last: {fmtDate(u.last_analysis)}
                      </span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => toggleExpand(u.id)}
                    className="btn-outline text-sm px-3 py-2"
                  >
                    {expanded === u.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    {expanded === u.id ? 'Hide' : 'View'} History
                  </button>
                  <button
                    onClick={() => toggleActive(u.id, u.username)}
                    disabled={toggling === u.id}
                    className={`btn text-xs px-3 py-2 border rounded-xl transition-colors
                      ${u.is_active
                        ? 'border-amber-200 text-amber-700 hover:bg-amber-50'
                        : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
                      }`}
                  >
                    {toggling === u.id
                      ? <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                      : u.is_active ? <ShieldOff size={13} /> : <ShieldCheck size={13} />
                    }
                    {u.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                  {!u.is_admin && (
                    <button
                      onClick={() => deleteUser(u.id, u.username)}
                      disabled={deleting === u.id}
                      className="btn-danger"
                    >
                      {deleting === u.id
                        ? <span className="w-3 h-3 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
                        : <Trash2 size={13} />
                      }
                      Delete
                    </button>
                  )}
                </div>
              </div>

              {/* Expanded snapshots */}
              {expanded === u.id && (
                <div className="border-t border-slate-100 bg-slate-50/50 p-4">
                  {loadingSnap === u.id ? (
                    <div className="flex justify-center py-4">
                      <span className="w-5 h-5 border-2 border-ink-600 border-t-transparent rounded-full animate-spin" />
                    </div>
                  ) : snapshots[u.id]?.length > 0 ? (
                    <div className="space-y-2">
                      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
                        Analysis History — {snapshots[u.id].length} snapshots
                      </p>
                      <div className="tbl-wrap">
                        <table className="tbl">
                          <thead>
                            <tr>
                              <th>Label</th>
                              <th>Client</th>
                              <th className="text-right">Current Value</th>
                              <th className="text-right">Total P&L</th>
                              <th className="text-right">XIRR</th>
                              <th>Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {snapshots[u.id].map(s => {
                              const summary = s.summary || {}
                              const cv      = summary['Total Current Value (₹)']
                              const pnl     = summary['Total P&L (Realized + Unreal)']
                              const xirr    = s.xirr_pct
                              const pnlPos  = +pnl >= 0
                              return (
                                <tr key={s.id}>
                                  <td className="font-medium text-slate-800">{s.label}</td>
                                  <td className="text-slate-500">{s.client_name || '—'}</td>
                                  <td className="tbl-num">{inr(cv)}</td>
                                  <td className={`tbl-num font-medium ${pnlPos ? 'text-emerald-600' : 'text-red-600'}`}>
                                    {inr(pnl)}
                                  </td>
                                  <td className={`tbl-num font-medium ${xirr != null && xirr >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                    {xirr != null ? `${Number(xirr).toFixed(2)}%` : '—'}
                                  </td>
                                  <td className="text-slate-400 text-xs">{fmtDate(s.created_at)}</td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : (
                    <p className="text-center text-slate-400 text-sm py-4">No analyses yet</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
