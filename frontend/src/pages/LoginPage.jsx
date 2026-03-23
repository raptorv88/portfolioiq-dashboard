import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import toast from 'react-hot-toast'
import { Eye, EyeOff, ArrowRight } from 'lucide-react'

export default function LoginPage() {
  const { login }       = useAuth()
  const navigate        = useNavigate()
  const [form, setForm] = useState({ username: '', password: '' })
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)

  const set = (k) => (e) => setForm(p => ({ ...p, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    if (!form.username.trim() || !form.password) {
      toast.error('Both fields are required'); return
    }
    setBusy(true)
    try {
      const u = await login(form.username.trim(), form.password)
      toast.success(`Welcome back, ${u.full_name.split(' ')[0]}`)
      navigate('/')
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Incorrect credentials')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* ── Left panel ─────────────────────────────────────── */}
      <div
        className="hidden lg:flex flex-col justify-between w-[46%] p-14 relative overflow-hidden"
        style={{ background: 'linear-gradient(145deg, #111440 0%, #1c2166 50%, #2e36ac 100%)' }}
      >
        {/* Decorative circles */}
        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #7c96fc, transparent)' }} />
        <div className="absolute -bottom-20 -left-20 w-72 h-72 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #a4bcff, transparent)' }} />

        {/* Logo */}
        <div className="flex items-center gap-3 relative z-10">
          <div className="w-9 h-9 bg-white/10 border border-white/20 rounded-xl
                          flex items-center justify-center backdrop-blur-sm">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
              <polyline points="16 7 22 7 22 13" />
            </svg>
          </div>
          <span className="text-white font-semibold tracking-tight">PortfolioIQ</span>
        </div>

        {/* Body copy */}
        <div className="relative z-10">
          <h1 className="text-[2.6rem] font-bold text-white leading-[1.15] mb-5">
            Every rupee,<br />accounted for.
          </h1>
          <p className="text-white/55 text-base leading-relaxed max-w-xs">
            Upload your trade report and holdings file. Get XIRR, sector allocation,
            P&L, and every metric your team needs — in seconds.
          </p>

          <div className="grid grid-cols-2 gap-3 mt-10">
            {[
              { v: 'XIRR',     d: 'Time-weighted returns' },
              { v: 'Sector',   d: 'Allocation breakdown'  },
              { v: 'P&L',      d: 'FIFO realized gains'   },
              { v: 'History',  d: 'Every snapshot saved'  },
            ].map(item => (
              <div key={item.v}
                className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 backdrop-blur-sm">
                <div className="text-ink-300 font-bold text-base">{item.v}</div>
                <div className="text-white/40 text-xs mt-0.5">{item.d}</div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-white/20 text-xs relative z-10">
          Internal use · Institutional portfolio analysis
        </p>
      </div>

      {/* ── Right panel ────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-8 bg-slate-50">
        <div className="w-full max-w-[380px] animate-fade-up">

          {/* Mobile logo */}
          <div className="flex items-center gap-2 mb-8 lg:hidden">
            <div className="w-8 h-8 bg-ink-600 rounded-lg flex items-center justify-center">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
              </svg>
            </div>
            <span className="font-semibold text-slate-900">PortfolioIQ</span>
          </div>

          <h2 className="text-2xl font-bold text-slate-900 mb-1">Sign in</h2>
          <p className="text-slate-500 text-sm mb-7">Enter your credentials to continue</p>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="field-label">Username</label>
              <input
                value={form.username}
                onChange={set('username')}
                placeholder="your.username"
                className="field-input"
                autoComplete="username"
                autoFocus
              />
            </div>

            <div>
              <label className="field-label">Password</label>
              <div className="relative">
                <input
                  type={show ? 'text' : 'password'}
                  value={form.password}
                  onChange={set('password')}
                  placeholder="••••••••"
                  className="field-input pr-10"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShow(s => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={busy}
              className="btn-primary w-full justify-center py-3 mt-1"
            >
              {busy
                ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                : <ArrowRight size={16} />
              }
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="text-center text-sm text-slate-500 mt-6">
            No account?{' '}
            <Link to="/register" className="text-ink-600 font-medium hover:underline">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
