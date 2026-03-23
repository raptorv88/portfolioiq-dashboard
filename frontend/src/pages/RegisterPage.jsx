import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import toast from 'react-hot-toast'
import { Eye, EyeOff, UserPlus } from 'lucide-react'

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate     = useNavigate()
  const [form, setForm] = useState({ username: '', email: '', full_name: '', password: '', confirm: '' })
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)

  const set = (k) => (e) => setForm(p => ({ ...p, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    const { username, email, full_name, password, confirm } = form
    if (!username || !email || !full_name || !password) {
      toast.error('All fields are required'); return
    }
    if (password !== confirm) { toast.error('Passwords do not match'); return }
    if (password.length < 6)  { toast.error('Password must be at least 6 characters'); return }

    setBusy(true)
    try {
      const u = await register({
        username:  username.trim().toLowerCase(),
        email:     email.trim().toLowerCase(),
        full_name: full_name.trim(),
        password,
      })
      toast.success(`Account created. Welcome, ${u.full_name.split(' ')[0]}!`)
      navigate('/')
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Registration failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-8">
      <div className="w-full max-w-[420px] animate-fade-up">

        {/* Logo */}
        <div className="flex items-center gap-2.5 mb-8">
          <div className="w-9 h-9 bg-ink-600 rounded-xl flex items-center justify-center shadow-md shadow-ink-600/30">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
              <polyline points="16 7 22 7 22 13" />
            </svg>
          </div>
          <span className="font-bold text-slate-900 tracking-tight">PortfolioIQ</span>
        </div>

        <div className="card p-8">
          <h2 className="text-xl font-bold text-slate-900 mb-1">Create account</h2>
          <p className="text-slate-500 text-sm mb-6">Fill in the details to get started</p>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="field-label">Full Name</label>
              <input value={form.full_name} onChange={set('full_name')}
                placeholder="Rahul Sharma" className="field-input" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="field-label">Username</label>
                <input value={form.username} onChange={set('username')}
                  placeholder="rahul.sharma" className="field-input" />
              </div>
              <div>
                <label className="field-label">Email</label>
                <input type="email" value={form.email} onChange={set('email')}
                  placeholder="rahul@firm.com" className="field-input" />
              </div>
            </div>

            <div>
              <label className="field-label">Password</label>
              <div className="relative">
                <input
                  type={show ? 'text' : 'password'}
                  value={form.password} onChange={set('password')}
                  placeholder="Min. 6 characters" className="field-input pr-10"
                />
                <button type="button" onClick={() => setShow(s => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                  {show ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <div>
              <label className="field-label">Confirm Password</label>
              <input
                type={show ? 'text' : 'password'}
                value={form.confirm} onChange={set('confirm')}
                placeholder="Repeat password" className="field-input"
              />
            </div>

            <button type="submit" disabled={busy}
              className="btn-primary w-full justify-center py-2.5 mt-1">
              {busy
                ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                : <UserPlus size={15} />
              }
              {busy ? 'Creating…' : 'Create account'}
            </button>
          </form>

          <p className="text-center text-sm text-slate-500 mt-5">
            Already have an account?{' '}
            <Link to="/login" className="text-ink-600 font-medium hover:underline">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
