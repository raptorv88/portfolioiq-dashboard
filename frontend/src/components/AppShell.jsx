import React, { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import {
  BarChart2, History, LogOut, ChevronLeft, ChevronRight,
  Menu, User, TrendingUp, PieChart, Percent,
  GitMerge, Activity, BarChart, FileBarChart
} from 'lucide-react'

const NAV = [
  { to: '/',        icon: BarChart,  label: 'Dashboard' },
  { to: '/history', icon: History,   label: 'History'   },
]

export const TAB_ITEMS = [
  { id: 'holdings',    icon: BarChart2,    label: 'Holdings'       },
  { id: 'pnl',         icon: TrendingUp,   label: 'P&L Analysis'   },
  { id: 'allocation',  icon: PieChart,     label: 'Allocation'     },
  { id: 'xirr',        icon: Percent,      label: 'XIRR'           },
  { id: 'recon',       icon: GitMerge,     label: 'Reconciliation' },
  { id: 'derivatives', icon: Activity,     label: 'Derivatives'    },
  { id: 'report',      icon: FileBarChart, label: 'Report'         },
]

function Logo({ collapsed }) {
  return (
    <div className={`flex items-center gap-2.5 ${collapsed ? 'justify-center' : ''}`}>
      <div className="w-8 h-8 bg-ink-600 rounded-lg flex items-center justify-center shrink-0 shadow shadow-ink-700/40">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white"
          strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
          <polyline points="16 7 22 7 22 13" />
        </svg>
      </div>
      {!collapsed && (
        <span className="font-bold text-slate-900 tracking-tight text-sm">PortfolioIQ</span>
      )}
    </div>
  )
}

export default function AppShell() {
  const { user, logout }        = useAuth()
  const navigate                 = useNavigate()
  const [col, setCol]            = useState(false)
  const [mob, setMob]            = useState(false)
  const [activeTab, setActiveTab] = useState('holdings')
  const [hasResult, setHasResult] = useState(false)

  const handleLogout = () => { logout(); navigate('/login') }

  const SidebarContent = ({ mobile = false }) => (
    <div className={`flex flex-col h-full bg-white border-r border-slate-200
      ${mobile ? 'w-64' : col ? 'w-[62px]' : 'w-52'}
      transition-all duration-200 ease-in-out relative`}
    >
      {/* Header */}
      <div className={`px-4 py-4 border-b border-slate-100 ${col && !mobile ? 'px-3' : ''}`}>
        <Logo collapsed={col && !mobile} />
      </div>

      {/* Nav links */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            onClick={() => mobile && setMob(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium
               transition-all duration-150
               ${isActive
                 ? 'bg-ink-50 text-ink-700 border border-ink-100'
                 : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
               }
               ${col && !mobile ? 'justify-center px-0 w-10 mx-auto' : ''}`
            }
          >
            <Icon size={17} className="shrink-0" />
            {(!col || mobile) && <span>{label}</span>}
          </NavLink>
        ))}

        {/* Analysis tabs — shown after result loads */}
        {hasResult && (
          <>
            {(!col || mobile) && (
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest
                            px-3 pt-4 pb-1.5">
                Analysis
              </p>
            )}
            {col && !mobile && <div className="border-t border-slate-100 my-2" />}

            {TAB_ITEMS.map(({ id, icon: Icon, label }) => (
              <button
                key={id}
                onClick={() => { setActiveTab(id); if (mobile) setMob(false) }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium
                  transition-all duration-150
                  ${activeTab === id
                    ? 'bg-ink-50 text-ink-700 border border-ink-100'
                    : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
                  }
                  ${col && !mobile ? 'justify-center px-0 w-10 mx-auto' : ''}`}
              >
                <Icon size={17} className="shrink-0" />
                {(!col || mobile) && <span>{label}</span>}
              </button>
            ))}
          </>
        )}
      </nav>

      {/* User + logout */}
      <div className={`border-t border-slate-100 p-3 space-y-1 ${col && !mobile ? 'flex flex-col items-center' : ''}`}>
        {(!col || mobile) && (
          <div className="flex items-center gap-2.5 px-2 py-1.5 mb-1">
            <div className="w-7 h-7 bg-ink-100 rounded-full flex items-center justify-center shrink-0">
              <User size={13} className="text-ink-600" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-slate-800 truncate">{user?.full_name}</p>
              <p className="text-xs text-slate-400 truncate">@{user?.username}</p>
            </div>
          </div>
        )}
        <button
          onClick={handleLogout}
          className={`flex items-center gap-2 text-slate-400 hover:text-red-500
            text-xs px-2 py-2 rounded-lg hover:bg-red-50 transition-colors w-full
            ${col && !mobile ? 'justify-center' : ''}`}
        >
          <LogOut size={14} />
          {(!col || mobile) && <span>Sign out</span>}
        </button>
      </div>

      {/* Collapse toggle — desktop only */}
      {!mobile && (
        <button
          onClick={() => setCol(c => !c)}
          className="absolute -right-3 top-[72px] w-6 h-6 bg-white border border-slate-200
                     rounded-full flex items-center justify-center shadow-sm
                     hover:bg-slate-50 text-slate-500 z-20 transition-colors"
        >
          {col ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
        </button>
      )}
    </div>
  )

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">

      {/* Desktop sidebar */}
      <div className="hidden md:block relative shrink-0">
        <SidebarContent />
      </div>

      {/* Mobile sidebar */}
      {mob && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"
               onClick={() => setMob(false)} />
          <div className="relative z-10 h-full">
            <SidebarContent mobile />
          </div>
        </div>
      )}

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">

        {/* Topbar */}
        <header className="h-13 bg-white border-b border-slate-200 px-5
                           flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <button className="md:hidden btn-icon" onClick={() => setMob(true)}>
              <Menu size={18} />
            </button>
            <span className="text-sm font-semibold text-slate-700 hidden sm:block">
              Portfolio Analysis Dashboard
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
            <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
            Live
          </div>
        </header>

        {/* Page outlet */}
        <main className="flex-1 overflow-y-auto">
          <Outlet context={{ activeTab, setActiveTab, hasResult, setHasResult }} />
        </main>
      </div>
    </div>
  )
}
